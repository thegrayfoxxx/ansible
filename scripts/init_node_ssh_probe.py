#!/usr/bin/env python3
"""Check a fresh public-key SSH login using the controller's connection options."""

import json
import os
import shlex
import subprocess
import sys


def ssh_command(options):
    # OpenSSH uses the first value: put the safety options before user arguments.
    command = [options["executable"]]
    for setting in (
        "ControlMaster=no",
        "ControlPath=none",
        "BatchMode=yes",
        "PreferredAuthentications=publickey",
        "PubkeyAuthentication=yes",
        "PasswordAuthentication=no",
        "KbdInteractiveAuthentication=no",
        "ConnectTimeout=15",
        "ConnectionAttempts=1",
    ):
        command.extend(["-o", setting])
    if options.get("user"):
        command.extend(["-l", options["user"]])
    if options.get("port"):
        command.extend(["-p", str(options["port"])])
    if options.get("private_key_file"):
        command.extend(["-i", os.path.expanduser(options["private_key_file"])])
    for name in ("ssh_args", "ssh_common_args", "ssh_extra_args"):
        command.extend(shlex.split(options.get(name) or ""))
    # -S directly assigns ControlPath even when an earlier -o already set it.
    command.extend(["-S", "none"])
    command.extend(
        [
            "--",
            options["host"],
            'printf \'%s\\n\' "$(id -un)" "$SSH_CONNECTION"',
        ]
    )
    return command


def main():
    options = json.load(sys.stdin)
    try:
        result = subprocess.run(
            ssh_command(options),
            capture_output=True,
            text=True,
            timeout=25,
            check=False,
        )
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        print(f"Fresh public-key SSH probe failed: {error}", file=sys.stderr)
        return 1
    if result.returncode:
        print(result.stderr, file=sys.stderr, end="")
        return result.returncode
    lines = result.stdout.strip().splitlines()
    if len(lines) != 2 or len(lines[1].split()) != 4:
        print("SSH probe did not return a user and SSH_CONNECTION", file=sys.stderr)
        return 1
    print(result.stdout, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
