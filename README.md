# Ansible for Semaphore UI

Скелет репо для управления несколькими VPS (Debian) через Semaphore UI.

Принципы:
- Inventory ведётся в UI Semaphore, в репо его нет.
- Секреты ведётся в UI Semaphore (Key Store / Environment), в репо их нет.
- Плейбуки универсальные: хост/группа подставляется через `target` или `Limit`.
- `roles/` пока не заводим, только плоские `playbooks/`.

## Структура

```text
ansible.cfg
requirements.yml
playbooks/
  ping.yml       # проверка связи
  update.yml     # apt update + upgrade, опционально reboot
  base.yml       # timezone + base packages
  run_script.yml # запуск скриптов из scripts/
  run_cmd.yml    # произвольная команда
  reboot.yml     # перезагрузка хостов
scripts/
  hello.sh       # пример shell-задачи
```

## Semaphore UI: подключение

1. Project -> Repositories: подключить этот репозиторий.
2. Key Store: добавить SSH-ключ (`ansible_user`, обычно `debian`/`admin`/`root`).
3. Inventory -> New Inventory:
   - тип static YAML / static ini, вести в UI.
   - Пример:

```yaml
all:
  children:
    prod:
      hosts:
        vps-prod-01:
          ansible_host: 203.0.113.10
          ansible_user: debian
          ansible_port: 22
    stage:
      hosts:
        vps-stage-01:
          ansible_host: 203.0.113.20
          ansible_user: debian
```

4. Environment -> New Environment:
   - `ANSIBLE_HOST_KEY_CHECKING=False` уже задан в `ansible.cfg`, дополнительно не нужен.
   - Секреты (пароли, токены) добавлять как JSON / Environment Variables.
5. Task Templates:
   - `ping`: playbook `playbooks/ping.yml`, inventory из п.3, key из п.2.
   - `update`: playbook `playbooks/update.yml`, extra vars при необходимости.
   - `base`: playbook `playbooks/base.yml`.
   - `run_script`: playbook `playbooks/run_script.yml`, extra vars с `script_src`.
   - `run_cmd`: playbook `playbooks/run_cmd.yml`, extra vars с `cmd`.
   - `reboot`: playbook `playbooks/reboot.yml`, extra vars с `target`.

## Универсальный target

Все плейбуки используют:

```yaml
hosts: "{{ target | default('all') }}"
```

Варианты запуска:
- Всё: ничего не указывать (`target=all` по умолчанию).
- Группа: в Task Template поле `Limit = prod` или Extra vars `{"target": "prod"}`.
- Один хост: `Limit = vps-prod-01` или `{"target": "vps-prod-01"}`.

`Limit` и `target` можно комбинировать, приоритет у `Limit` (стандартный ansible `--limit`).

## Переменные

`playbooks/update.yml`:
- `apt_upgrade: dist` (или `safe`)
- `apt_autoremove: true`
- `apt_autoclean: true`
- `reboot_if_required: false` -> `true` для авторебута

`playbooks/base.yml`:
- `base_timezone: Etc/UTC`
- `base_packages: [python3, sudo, curl, htop]`

`playbooks/run_script.yml`:
- `script_src: scripts/hello.sh` (обязательно, путь от корня репо, резолвится через `playbook_dir`)
- `script_args: ""` (опционально, строка аргументов)
- `script_env: {}` (опционально)
- `script_become: true` -> `false` чтобы запустить без sudo

Передавать через Semaphore Environment / Extra vars JSON, например:

```json
{
  "target": "stage",
  "base_timezone": "Europe/Berlin"
}
```

Запуск скрипта через Semaphore Extra vars:

```json
{
  "target": "stage",
  "script_src": "scripts/hello.sh"
}
```

С аргументами, env и без sudo:

```json
{
  "target": "vps-prod-01",
  "script_src": "scripts/hello.sh",
  "script_args": "--foo bar",
  "script_env": {"FOO": "1"},
  "script_become": false
}
```

`playbooks/run_cmd.yml`:
- `cmd: "df -h"` (обязательно)
- `use_shell: true` -> `false` для строгого `command` без shell
- `cmd_chdir: ""` (опционально, рабочая папка)
- `cmd_env: {}` (опционально)
- `cmd_become: true` -> `false` чтобы запустить без sudo

Запуск команды через Semaphore Extra vars:

```json
{
  "target": "us_racknerd",
  "cmd": "df -h"
}
```

С shell-пайпом, chdir, env и без sudo:

```json
{
  "target": "stage",
  "cmd": "ls -la /opt | grep app",
  "use_shell": true,
  "cmd_chdir": "/opt",
  "cmd_env": {"FOO": "1"},
  "cmd_become": false
}
```

`playbooks/reboot.yml` (без подтверждения — аккуратнее с `target=all`):
- `reboot_msg: "Reboot via Semaphore"`
- `reboot_timeout: 600` (секунд ждать возвращения хоста)
- `reboot_connect_timeout: 30`
- `reboot_pre_delay: 5`, `reboot_post_delay: 15`

Перезагрузка через Semaphore Extra vars:

```json
{
  "target": "us_racknerd"
}
```

Группа с увеличенным таймаутом:

```json
{
  "target": "prod",
  "reboot_timeout": 900
}
```

## Локальная проверка

```bash
ansible-playbook --syntax-check playbooks/ping.yml
ansible-playbook --syntax-check playbooks/update.yml
ansible-playbook --syntax-check playbooks/base.yml
ansible-playbook --syntax-check playbooks/run_script.yml
ansible-playbook --syntax-check playbooks/run_cmd.yml
ansible-playbook --syntax-check playbooks/reboot.yml
ansible-galaxy collection install -r requirements.yml
```
