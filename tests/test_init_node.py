"""Local regression checks; never connect to a node or change system sshd."""

import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "ssh_probe", ROOT / "scripts/init_node_ssh_probe.py"
)
PROBE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROBE)
PLAY = yaml.safe_load((ROOT / "playbooks/init_node.yml").read_text())[0]


class SSHProbeTests(unittest.TestCase):
    def test_resolves_inventory_and_cli_options_before_local_probe(self):
        with tempfile.TemporaryDirectory(
            prefix="init-node-probe-", dir="/tmp"
        ) as directory:
            directory = Path(directory)
            ssh = directory / "ssh"
            ssh.write_text(
                "#!/bin/sh\nprintf 'debian\\n192.0.2.1 45678 192.0.2.2 22\\n'\n"
            )
            ssh.chmod(0o700)
            tasks = copy.deepcopy(
                [
                    task
                    for task in PLAY["tasks"]
                    if task["name"]
                    in (
                        "Resolve controller SSH options before delegation",
                        "Verify public-key login before changing sshd",
                    )
                ]
            )
            tasks[1]["ansible.builtin.command"]["argv"][1] = str(
                ROOT / "scripts/init_node_ssh_probe.py"
            )
            tasks.append(
                {
                    "name": "Check resolved connection options",
                    "ansible.builtin.assert": {
                        "that": [
                            "init_node_probe_options.user == 'debian'",
                            "init_node_probe_options.port | int == 2222",
                            "init_node_probe_options.host == 'node-alias'",
                            "init_node_probe_options.private_key_file == '/tmp/test identity'",
                            "init_node_probe_options.ssh_common_args == '-J jump'",
                            "init_node_key_login.stdout_lines[0] == 'debian'",
                        ]
                    },
                }
            )
            playbook = directory / "test.yml"
            playbook.write_text(
                yaml.safe_dump(
                    [
                        {
                            "name": "Local controller probe regression",
                            "hosts": "localhost",
                            "gather_facts": False,
                            "vars": {
                                **PLAY["vars"],
                                "ansible_connection": "local",
                                "ansible_user": "debian",
                                "ansible_port": 2222,
                                "ansible_host": "node-alias",
                                "ansible_ssh_common_args": "-J jump",
                                "ansible_ssh_executable": str(ssh),
                                "ansible_python_interpreter": str(
                                    ROOT / ".venv/bin/python"
                                ),
                                "ansible_remote_tmp": str(directory / "remote"),
                            },
                            "tasks": tasks,
                        }
                    ],
                    sort_keys=False,
                )
            )
            result = subprocess.run(
                [
                    str(ROOT / ".venv/bin/ansible-playbook"),
                    "-i",
                    "localhost,",
                    str(playbook),
                    "--private-key",
                    "/tmp/test identity",
                ],
                env={
                    **os.environ,
                    "ANSIBLE_CONFIG": str(ROOT / "ansible.cfg"),
                    "ANSIBLE_LOCAL_TEMP": str(directory / "local"),
                },
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_forces_fresh_public_key_login_before_inventory_options(self):
        argv = PROBE.ssh_command(
            {
                "executable": "ssh",
                "host": "node",
                "user": "root",
                "port": 2222,
                "private_key_file": "/tmp/key with spaces",
                "ssh_args": "-o ControlPath=/tmp/existing -o PasswordAuthentication=yes",
                "ssh_common_args": '-o ProxyCommand="ssh jump -W %h:%p"',
            }
        )
        self.assertLess(
            argv.index("ControlPath=none"), argv.index("ControlPath=/tmp/existing")
        )
        self.assertLess(
            argv.index("PasswordAuthentication=no"),
            argv.index("PasswordAuthentication=yes"),
        )
        self.assertIn("BatchMode=yes", argv)
        self.assertIn("PreferredAuthentications=publickey", argv)
        self.assertIn("/tmp/key with spaces", argv)
        self.assertIn("ProxyCommand=ssh jump -W %h:%p", argv)
        self.assertEqual(argv[-3:-1], ["--", "node"])

    def test_failed_login_and_invalid_output_are_rejected(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as directory:
            ssh = Path(directory) / "ssh"
            for body in ("exit 255", "printf 'unexpected banner\\n'"):
                ssh.write_text("#!/bin/sh\n" + body + "\n")
                ssh.chmod(0o700)
                result = subprocess.run(
                    [
                        str(ROOT / ".venv/bin/python"),
                        str(ROOT / "scripts/init_node_ssh_probe.py"),
                    ],
                    input=json.dumps({"executable": str(ssh), "host": "node"}),
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertNotEqual(result.returncode, 0)


class ConfigTransactionTests(unittest.TestCase):
    def run_transaction(self, original, dropin, failure, check_mode=False):
        """Run real Ansible file tasks, with SSH/service operations replaced locally."""
        with tempfile.TemporaryDirectory(
            prefix="init-node-test-", dir="/tmp"
        ) as directory:
            directory = Path(directory)
            config = directory / "sshd_config"
            if original is not None:
                config.write_text(original)
                config.chmod(0o640)
            tasks = copy.deepcopy(
                [
                    task
                    for task in PLAY["tasks"]
                    if task["name"]
                    in (
                        "Inspect previous sshd configuration",
                        "Save previous sshd configuration for rollback",
                        "Apply and verify sshd configuration transaction",
                    )
                ]
            )
            transaction = tasks[-1]
            reload_log = directory / "reloads"
            reload_task = {
                "name": "Record reload",
                "ansible.builtin.shell": "printf 'reload\\n' >> " + str(reload_log),
            }
            sshd = directory / "sshd"
            expected_context = (
                "user=root,addr=192.0.2.1,host=192.0.2.1,laddr=192.0.2.2,lport=22"
            )
            sshd.write_text(
                "#!/bin/sh\n"
                'if [ "$2" = "-C" ]; then\n'
                f'  [ "$3" = "{expected_context}" ] || exit 66\n'
                "  cat <<'SETTINGS'\n"
                + self.settings(
                    conflict=failure == "match", root_conflict=failure == "root"
                )
                + "SETTINGS\nelse\ncat <<'SETTINGS'\n"
                + self.settings()
                + "SETTINGS\nfi\n"
            )
            sshd.chmod(0o700)
            # Exercise the production assertion, file writes and rescue with deterministic
            # command failures; no sshd or service manager is touched.
            for section in ("block", "rescue"):
                for index, task in enumerate(transaction[section]):
                    name = task["name"]
                    if "ansible.builtin.service" in task:
                        transaction[section][index] = copy.deepcopy(reload_task)
                    elif name == "Validate full sshd configuration before reload":
                        task["ansible.builtin.command"] = (
                            "false" if failure == "syntax" else "true"
                        )
                    elif name == "Validate restored sshd configuration":
                        task["ansible.builtin.command"] = "true"
                    elif name == "Verify fresh public-key login after reload":
                        task.pop("delegate_to")
                        task["ansible.builtin.command"] = (
                            "false" if failure == "login" else "true"
                        )
            settings = "PermitRootLogin prohibit-password\nPubkeyAuthentication yes\nPasswordAuthentication no\nPermitEmptyPasswords no\n"
            playbook = directory / "test.yml"
            playbook.write_text(
                yaml.safe_dump(
                    [
                        {
                            "name": "Local configuration transaction regression",
                            "hosts": "localhost",
                            "gather_facts": False,
                            "vars": {
                                **PLAY["vars"],
                                "ansible_connection": "local",
                                "ansible_python_interpreter": str(
                                    ROOT / ".venv/bin/python"
                                ),
                                "ansible_remote_tmp": str(directory / "remote"),
                                "init_node_config_path": str(config),
                                "init_node_sshd_settings": settings,
                                "sshd_include": {"rc": 0 if dropin else 1},
                                "init_node_key_login": (
                                    {}
                                    if check_mode
                                    else {
                                        "stdout_lines": [
                                            "root",
                                            "192.0.2.1 45678 192.0.2.2 22",
                                        ]
                                    }
                                ),
                            },
                            "tasks": tasks,
                        }
                    ],
                    sort_keys=False,
                )
            )
            result = subprocess.run(
                [
                    str(ROOT / ".venv/bin/ansible-playbook"),
                    "-i",
                    "localhost,",
                    str(playbook),
                ]
                + (["--check"] if check_mode else []),
                env={
                    **os.environ,
                    "ANSIBLE_CONFIG": str(ROOT / "ansible.cfg"),
                    "ANSIBLE_LOCAL_TEMP": str(directory / "local"),
                    "PATH": str(directory) + os.pathsep + os.environ["PATH"],
                },
                text=True,
                capture_output=True,
                check=False,
            )
            output = result.stdout + result.stderr
            if check_mode:
                self.assertEqual(result.returncode, 0, output)
                self.assertEqual(config.read_text(), original, output)
            elif failure:
                self.assertNotEqual(result.returncode, 0, output)
                self.assertIn("Настройки sshd восстановлены", output)
                self.assertEqual(
                    config.read_text() if config.exists() else None, original, output
                )
                if original is not None:
                    self.assertEqual(config.stat().st_mode & 0o777, 0o640)
            else:
                self.assertEqual(result.returncode, 0, output)
                text = config.read_text()
                self.assertTrue(text.startswith("# BEGIN ANSIBLE INIT NODE\n"), text)
                self.assertLess(
                    text.index("PasswordAuthentication no"),
                    text.index("PasswordAuthentication yes"),
                )
                self.assertLess(
                    text.index("PasswordAuthentication no"),
                    text.index("Match User backup"),
                )
            reloads = reload_log.read_text().splitlines() if reload_log.exists() else []
            expected_reloads = 0 if check_mode else (2 if failure == "login" else 1)
            self.assertEqual(len(reloads), expected_reloads, output)

    @staticmethod
    def settings(conflict=False, root_conflict=False):
        return (
            f"permitrootlogin {'yes' if root_conflict else 'without-password'}\npubkeyauthentication yes\n"
            f"passwordauthentication {'yes' if conflict else 'no'}\n"
            "permitemptypasswords no\nusedns no\n"
        )

    def test_restores_existing_dropin_after_invalid_configuration(self):
        self.run_transaction(
            "# old drop-in\nPasswordAuthentication yes\n", True, "syntax"
        )

    def test_removes_only_new_dropin_after_invalid_configuration(self):
        self.run_transaction(None, True, "syntax")

    def test_restores_main_config_after_failed_login(self):
        self.run_transaction("# original main config\n", False, "login")

    def test_match_conflict_fails_before_applying_new_settings(self):
        self.run_transaction("# original drop-in\n", True, "match")

    def test_root_login_conflict_fails_before_applying_new_settings(self):
        self.run_transaction("# original drop-in\n", True, "root")

    def test_check_mode_does_not_write_reload_or_require_probe_results(self):
        self.run_transaction("# original config\n", False, None, check_mode=True)

    def test_global_block_precedes_duplicates_and_match(self):
        self.run_transaction(
            "PasswordAuthentication yes\nPasswordAuthentication yes\n"
            "Match User backup\n    X11Forwarding no\n",
            False,
            None,
        )


if __name__ == "__main__":
    unittest.main()
