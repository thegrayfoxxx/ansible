# Вкладка CrowdSec: агент + баунсер в Docker (LAPI уже стоит)

Шесть шаблонов, порядок флоу: сначала `crowdsec_register` (исполняется **на хосте LAPI**), потом `crowdsec_node` (на нодах флота), обновление — `crowdsec_node_update` (`pull + down + up -d`, секреты LAPI не нужны, работает на группе), снос — `crowdsec_unregister` (на хосте LAPI) + `crowdsec_node` с `action=remove` (на ноде), приём ручных нод — `crowdsec_node_adopt`, переезд — `crowdsec_node_move`. Ручного создания шаблонов не нужно — все приезжают через `update_templates`; группу `crowdsec_nodes` сидинг создаст пустой сам.

Предусловия на ноде (не ставятся, только проверяются): `docker` (шаблон `docker` — иначе `fail`), `rsyslog` (шаблон `rsyslog` — иначе только warning). LAPI должен отвечать (`cscli lapi status`).

## `crowdsec_register` (Target — строго один хост LAPI, не `all`)

- `project_id` (Integer, обязательно — для записи в API)
- `crowdsec_node_names` (Text, обязательно; по одному `^[a-z0-9-]+$` на строку; повтор имени = ротация секретов; `local/dashboard/localhost` запрещены)
- `crowdsec_from_group` (String; например `de` — взять имена-алиасы из группы inventory вместо ручного списка; с `crowdsec_node_names` вместе нельзя — только один источник)
- `crowdsec_api_url` (String; пусто — взять текущий из группы, обязателен при первой регистрации; поле не для этого прогона — register ходит через `docker exec`, URL складируется в группу для деплоев нод)
- `crowdsec_lapi_container` (String; пусто — `crowdsec-lapi`)
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

## `crowdsec_node_adopt` (принять ручную ноду под управление; LAPI-записи остаются валидны)

Соглашение: `adopt` = причесать на месте. Креды сохраняются (не ротируются), поэтому старые регистрации в LAPI продолжают работать; плюс креды записываются в группу `crowdsec_nodes` (нужны `project_id` + `service_vars`, как в register) — иначе следующий `deploy` упадёт «сначала register».

- `crowdsec_adopt_action: inspect` (только отчёт — безопасно; `migrate` — переезд)
- `target` — строго один хост; `crowdsec_agent_container` / `crowdsec_bouncer_container` (имена контейнеров, дефолты `crowdsec-agent`/`crowdsec-bouncer`)
- `crowdsec_node_name` (пусто — inventory hostname; под это имя пишутся ключи группы — обязано совпадать с будущими deploy)
- `crowdsec_old_dir` (пусто — из compose-меток), `crowdsec_dir` (куда, пусто — `/opt/crowdsec`), `crowdsec_mode` (пусто — из running-контейнера)
- discovery: running Env обоих контейнеров → старый `.env`; `extra_logs` — из старого `acquis.yaml` (filenames минус 3 базовых), `extra_collections` — обнаруженные минус базовые (рендер склеивает 1:1); `TZ` — обнаруженная → `/etc/timezone` → `Etc/UTC`
- `crowdsec_api_url` группы не перезаписываем: расхождение с обнаруженным — fail (URL общий)
- migrate: синк группы → stop+rename → рендер стандарта → `up` → `cscli lapi status` → rescue с подъёмом бэкапа
- тот же каталог как target — fail с подсказкой гнать `deploy`

```json
{
  "target": "us6",
  "crowdsec_adopt_action": "inspect"
}
```

```json
{
  "target": "us6",
  "crowdsec_adopt_action": "migrate",
  "project_id": 1,
  "crowdsec_old_dir": "/home/anatoliy/crowdsec_node"
}
```

## `crowdsec_node_move` (переезд на другую ноду; LAPI и DNS не трогаем — агенты сами dial-out)

Соглашение: `move` = переезд (`adopt` — на месте). Креды сохраняются 1:1, но ключи группы пишутся под **новое** имя (hostname цели или явное) — будущие deploy прозрачны; в LAPI останутся старые имена агента/баунсера (косметика, лечится ротацией через register).

- `target` — исходная нода (строго один хост); `crowdsec_move_dest` (цель в inventory, обязательно, строго один хост, ≠ источнику)
- `crowdsec_move_action: inspect` (отчёт+план) / `move`; `crowdsec_move_confirmed: true` — обязательно для `move`
- `crowdsec_node_name` (пусто — имя целевой ноды), остальные поля — как в adopt (`crowdsec_agent_container`/`crowdsec_bouncer_container` и `old_dir` — источник, `dir`/`mode` — уже цель)
- порядок: discovery → синк группы под новым именем → поднимаем цель (проверка `cscli lapi status`) → только потом гасим источник (stop+rename, каталоги целы); провал на цели — источник не тронут
