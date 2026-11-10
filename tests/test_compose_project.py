"""Exercise the real resolver on local files with a fake Docker label reader."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]


class ComposeProjectTests(unittest.TestCase):
    def test_resolution_and_ambiguity_in_normal_and_check_mode(self):
        ansible = shutil.which('ansible-playbook') or str(ROOT / '.venv/bin/ansible-playbook')
        with tempfile.TemporaryDirectory(prefix='compose-project-', dir='/tmp') as tmp:
            base = Path(tmp)
            labels = {}
            tasks = []
            cases = [
                ('empty', [], [], '', False),
                *[(name, [name], [], name, False) for name in (
                    'compose.yml', 'compose.yaml', 'docker-compose.yml', 'docker-compose.yaml'
                )],
                ('ambiguous', ['compose.yml', 'docker-compose.yml'], [], '', True),
                ('label-selects-legacy', ['compose.yml', 'docker-compose.yml'],
                 ['docker-compose.yml'], 'docker-compose.yml', False),
                ('label-selects-canonical', ['compose.yml', 'docker-compose.yml'],
                 ['compose.yml'], 'compose.yml', False),
                ('multiple-configs', ['compose.yml', 'override.yml'],
                 ['compose.yml', 'override.yml'], '', True),
                ('missing-label-file', ['compose.yml'], ['docker-compose.yml'], '', True),
                ('unsupported-name', ['custom.yml'], ['custom.yml'], '', True),
                ('other-directory', ['docker-compose.yaml'],
                 ['/unrelated/compose.yml'], 'docker-compose.yaml', False),
                ('empty-after-found', [], [], '', False),
            ]
            for index, (name, files, configs, expected, fails) in enumerate(cases):
                directory = base / name
                directory.mkdir()
                for file in files:
                    (directory / file).write_text('services: {}\n')
                container = f'case-{index}'
                labels[container] = ','.join(
                    str(directory / config) for config in configs
                )
                tasks.extend([
                    {'name': f'Reset failure for {name}', 'ansible.builtin.set_fact': {
                        'resolver_failed': False,
                    }},
                    {'name': f'Resolve {name}', 'block': [
                        {'name': 'Invoke resolver', 'ansible.builtin.include_role': {
                            'name': 'compose_project',
                        }, 'vars': {
                            'compose_project_dir': str(directory) + '/',
                            'compose_project_container': container,
                        }},
                    ], 'rescue': [
                        {'name': 'Record rejected configuration', 'ansible.builtin.set_fact': {
                            'resolver_failed': True,
                        }},
                    ]},
                    {'name': f'Check {name}', 'ansible.builtin.assert': {'that': [
                        f'resolver_failed == {fails}',
                        *([] if fails else [
                            'compose_project_file == ' + json.dumps(expected),
                            f'compose_project_exists == {bool(expected)}',
                        ]),
                    ]}},
                ])
            # Omitted optional container must not reuse labels from an earlier call.
            tasks.extend([
                {'name': 'Resolve without container', 'ansible.builtin.include_role': {
                    'name': 'compose_project',
                }, 'vars': {'compose_project_dir': str(base / 'docker-compose.yml')}},
                {'name': 'Check optional container', 'ansible.builtin.assert': {'that': [
                    "compose_project_file == 'docker-compose.yml'",
                ]}},
            ])
            docker = base / 'docker'
            docker.write_text('#!/usr/bin/env python3\nimport sys\nlabels = ' + repr(labels)
                              + '\nprint(labels.get(sys.argv[-1], ""))\n')
            docker.chmod(0o700)
            playbook = base / 'test.yml'
            playbook.write_text(yaml.safe_dump([{
                'name': 'Test compose resolver', 'hosts': 'localhost',
                'gather_facts': False, 'tasks': tasks,
            }], sort_keys=False))
            env = dict(os.environ, ANSIBLE_CONFIG=str(ROOT / 'ansible.cfg'),
                       ANSIBLE_ROLES_PATH=str(ROOT / 'roles'),
                       ANSIBLE_NOCOLOR='1', PATH=str(base) + os.pathsep + os.environ['PATH'])
            for flags in ([], ['--check']):
                result = subprocess.run([
                    ansible, '-i', 'localhost,', '-c', 'local', str(playbook), *flags,
                ], cwd=ROOT, env=env, capture_output=True, text=True, timeout=180)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


    def test_remnanode_render_preserves_existing_name_and_move_uses_canonical(self):
        ansible = shutil.which('ansible-playbook') or str(ROOT / '.venv/bin/ansible-playbook')
        # Run the real filename-selection and template tasks, without host setup.
        render_tasks = [task for task in yaml.safe_load(
            (ROOT / 'roles/remnanode/tasks/render.yml').read_text()
        ) if task['name'] in ('Select compose filename for rendering', 'Render compose file')]
        with tempfile.TemporaryDirectory(prefix='compose-render-', dir='/tmp') as tmp:
            base = Path(tmp)
            tasks = []
            cases = [
                ('existing', 'docker-compose.yml', False, 'docker-compose.yml'),
                ('new', '', False, 'compose.yml'),
                ('move', 'docker-compose.yaml', True, 'compose.yml'),
            ]
            for name, existing, canonical, expected in cases:
                directory = base / name
                directory.mkdir()
                tasks.append({'name': name, 'block': render_tasks, 'vars': {
                    'role_path': str(ROOT / 'roles/remnanode'),
                    'remnanode_dir_effective': str(directory),
                    'remnanode_target_compose_file': existing,
                    'remnanode_render_canonical': canonical,
                    'remnanode_agent_container_effective': 'remnanode',
                    'remnanode_node_image_effective': 'remnawave/node:latest',
                }})
            playbook = base / 'render.yml'
            playbook.write_text(yaml.safe_dump([{
                'name': 'Test rendering', 'hosts': 'localhost',
                'gather_facts': False, 'tasks': tasks,
            }], sort_keys=False))
            result = subprocess.run([
                ansible, '-i', 'localhost,', '-c', 'local', str(playbook),
            ], cwd=ROOT, env=dict(os.environ, ANSIBLE_CONFIG=str(ROOT / 'ansible.cfg')),
                capture_output=True, text=True, timeout=90)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            for name, _, _, expected in cases:
                self.assertEqual([file.name for file in (base / name).iterdir()], [expected])
                rendered = yaml.safe_load((base / name / expected).read_text())
                self.assertEqual(rendered['services']['remnanode']['image'], 'remnawave/node:latest')


if __name__ == '__main__':
    unittest.main()
