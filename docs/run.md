# Вкладка Run: выполнить что-то

Ad-hoc действия: проверка связи, команды, скрипты.

## `playbooks/ping.yml`

- `ping_mode: ssh` (`remote` — только ICMP с ноды, `both` — сначала SSH, потом ICMP; Enum)
- `ping_dest: ""` (IP/DNS для проверки с ноды; обязателен для `remote`/`both`, в `ssh` игнорируется с пометкой в summary)
- `ping_count: 4` (Integer, `1..100`)
- финал — одна строка `mode=both dest=8.8.8.8 0% packet loss`

Только SSH (дефолт, как раньше):

```json
{
  "target": "stage"
}
```

ICMP с ноды до панели (перед deploy remnawave):

```json
{
  "target": "de1",
  "ping_mode": "both",
  "ping_dest": "panel.example.com"
}
```

## `playbooks/run_script.yml`

- `script_src: scripts/hello.sh` (String; обязательно, путь от корня репо, резолвится через `playbook_dir`)
- `script_args: ""` (String, опционально)
- `script_env` (Text с JSON-объектом, опционально; например `{"FOO": "1"}`)
- `script_become: true` -> `false` чтобы запустить без sudo (Enum)

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

## `playbooks/run_cmd.yml`

- `cmd: "df -h"` (String, обязательно)
- `use_shell: true` -> `false` для строгого `command` без shell (Enum)
- `cmd_chdir: ""` (String, опционально, рабочая папка)
- `cmd_env` (Text с JSON-объектом, опционально; например `{"FOO": "1"}`)
- `cmd_become: true` -> `false` чтобы запустить без sudo (Enum)
- `cmd_tail: 0` (Integer, опционально, показать только последние N строк stdout/stderr)
- `allow_fail: false` -> `true` чтобы не фейлить хост при rc != 0 (rc виден в выводе; Enum)

Запуск команды через Semaphore Extra vars:

```json
{
  "target": "vps-prod-01",
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

Обновление docker-контейнеров с коротким хвостом лога:

```json
{
  "target": "prod",
  "cmd": "cd /opt/app && docker compose pull && docker compose up -d",
  "cmd_tail": 20
}
```

По гетерогенным хостам без фейла всего таска (rc виден в выводе):

```json
{
  "target": "all",
  "cmd": "cd /opt/app && docker compose up -d",
  "allow_fail": true,
  "cmd_tail": 15
}
```
