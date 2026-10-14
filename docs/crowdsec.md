# Вкладка CrowdSec: агент + баунсер в Docker (LAPI уже стоит)

Четыре шаблона, порядок флоу: сначала `crowdsec_register` (исполняется **на хосте LAPI**), потом `crowdsec_node` (на нодах флота), обновление — `crowdsec_node_update` (`pull + down + up -d`, секреты LAPI не нужны, работает на группе), снос — `crowdsec_unregister` (на хосте LAPI) + `crowdsec_node` с `action=remove` (на ноде). Ручного создания шаблонов не нужно — все приезжают через `update_templates`; группу `crowdsec_nodes` сидинг создаст пустой сам.

Предусловия на ноде (не ставятся, только проверяются): `docker` (шаблон `docker` — иначе `fail`), `rsyslog` (шаблон `rsyslog` — иначе только warning). LAPI должен отвечать (`cscli lapi status`).

## `crowdsec_register` (Target — строго один хост LAPI, не `all`)

- `project_id` (Integer, обязательно — для записи в API)
- `crowdsec_node_names` (Text, обязательно; по одному `^[a-z0-9-]+$` на строку; повтор имени = ротация секретов; `local/dashboard/localhost` запрещены)
- `crowdsec_from_group` (String; например `de` — взять имена-алиасы из группы inventory вместо ручного списка; с `crowdsec_node_names` вместе нельзя — только один источник)
- `crowdsec_api_url` (String; пусто — взять текущий из группы, обязателен при первой регистрации; поле не для этого прогона — register ходит через `docker exec`, URL складируется в группу для деплоев нод)
- не запускай два register параллельно — записи в группу идут read-modify-write, второй затрет первого

```json
{
  "target": "lapi-01",
  "project_id": 1,
  "crowdsec_node_names": "us6\nus7",
  "crowdsec_api_url": "https://crowdsec.example.com"
}
```

Тот же register из группы (имена подтянутся из inventory сами):

```json
{
  "target": "lapi-01",
  "project_id": 1,
  "crowdsec_from_group": "de",
  "crowdsec_api_url": "https://crowdsec.example.com"
}
```

## `crowdsec_node`

- `crowdsec_node_name` (String; пусто — взять из имени хоста в inventory; для `remove` явное имя обязательно)
- `crowdsec_action: deploy` (`restart` / `status` read-only / `remove`; Enum)
- `crowdsec_remove_confirmed: false` -> `true` чтобы разрешить снос (volumes остаются, баны живут в LAPI; Enum)
- `crowdsec_mode: iptables` (или `nftables`; Enum)
- `crowdsec_extra_collections` (Text, по одной на строку; дефолт `linux/sshd/iptables`, сюда же ляжет `nginx`)
- `crowdsec_extra_logs` (Text, пути строго под `/var/log`, по одному на строку)
- `crowdsec_tz` (String; пусто — взять из `/etc/timezone` хоста)
- `crowdsec_dir` (String; папка проекта на ноде, пусто — `/opt/crowdsec`)
- файлы ноды: `crowdsec_dir` (дефолт `/opt/crowdsec`; пусто — дефолт) (`compose.yml`, `.env 0600`, `config/`); секреты подтягиваются из группы по имени, отсутствуют — `fail` «сначала register»
- логи контейнеров: `json-file 10m × 3` (зашито в compose, применяется со следующего deploy/recreate)
- перерегистрация ротирует секреты: после неё обязательно перепрогнать `node deploy`, иначе нода отвалится со старыми кредами
- ручные регистрации со старым неймингом (`имя_agent`) не подхватываются — мигрируй через перерегистрацию

Массовый флоу (любое число нод — два запуска):

```json
{
  "target": "stage",
  "crowdsec_node_name": "",
  "crowdsec_action": "deploy"
}
```

## `crowdsec_node_update` (обновление без секретов — достаточно `target` и опционально `crowdsec_dir`)

```json
{
  "target": "stage",
  "crowdsec_dir": ""
}
```

## `crowdsec_unregister` (Target — строго один хост LAPI; повтор по тем же именам = `already gone`, не ошибка)

- `project_id` (Integer, обязательно — для чистки группы)
- `crowdsec_node_names` (Text) или `crowdsec_from_group` (String) — тот же формат и валидация, что в register
- `crowdsec_lapi_container` (String; пусто — `crowdsec-lapi`)
- удаляет `<имя>-agent` и `<имя>-bouncer` из LAPI и стирает их креды из группы `crowdsec_nodes` (`crowdsec_api_url` не трогает); группы нет — чистка скипается с warning, не fail

Снос ноды целиком (два запуска — сначала LAPI, потом нода):

```json
{
  "target": "lapi-01",
  "project_id": 1,
  "crowdsec_node_names": "us6"
}
```

```json
{
  "target": "us6",
  "crowdsec_node_name": "us6",
  "crowdsec_action": "remove",
  "crowdsec_remove_confirmed": true
}
```
