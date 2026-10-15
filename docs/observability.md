# Вкладка Observability: посмотреть и настроить наблюдение

## `playbooks/logs.yml` (read-only — безопасен на любом охвате)

- `log_source: journal` -> `file` для хвоста файла (Enum)
- `log_file: /var/log/syslog` (только для `source=file`, String)
- `log_unit: ""` (только journal, например `ssh`; пусто — все юниты)
- `log_priority: info` (только journal: уровень и срочнее; Enum)
- `log_since: "-1h"` (только journal: `-30min`, `today`, `2026-10-01`)
- `log_lines: 200` (Integer, guard `1..2000`)
- `log_grep: ""` (String, валидный Python regex-фильтр, например `error|fail`)
- `log_kernel: false` -> `true` для ring buffer ядра `-k` (только journal; Enum)

```json
{
  "target": "stage",
  "log_unit": "ssh",
  "log_since": "-30min"
}
```

```json
{
  "target": "vps-prod-01",
  "log_source": "file",
  "log_file": "/var/log/auth.log",
  "log_grep": "Failed"
}
```

## `playbooks/health.yml` (read-only — безопасен на любом охвате, достаточно `target`)

- одна строка summary на хост: `uptime/load/mem/disk/containers/fail2ban/crowdsec/remnanode` + компактная таблица контейнеров `имя (image) — state/status`
- mem считается без page cache, `(!)` помечает `mem>90%` и `disk>80%`
- опциональное только детектится (`missing`/`na`), не фейлит: нет fail2ban — `missing`, нет агента crowdsec — `na`, LAPI не отвечает — `fail`

```json
{
  "target": "prod"
}
```

## `playbooks/rsyslog.yml`

- `rsyslog_remote: ""` (String, пусто — только локальные логи; например `192.0.2.10:514`)
- `rsyslog_proto: tcp` (или `udp`; Enum)

С форвардингом на центральный сервер:

```json
{
  "target": "prod",
  "rsyslog_remote": "192.0.2.10:514",
  "rsyslog_proto": "tcp"
}
```
