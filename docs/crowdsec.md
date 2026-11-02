# Вкладка CrowdSec: агент + баунсер в Docker (LAPI уже стоит)

Семь шаблонов, порядок флоу: сначала `crowdsec_register` (исполняется **на хосте LAPI**), потом `crowdsec_node` (на нодах флота), обновление — `crowdsec_node_update` (`pull` + пересоздание только изменившихся контейнеров, по одной ноде; секреты LAPI не нужны), снос — `crowdsec_unregister` (на хосте LAPI) + `crowdsec_node` с `action=remove` (на ноде), приём ручных нод — `crowdsec_node_adopt`, переезд — `crowdsec_node_move`, уборка бэкапов adopt/move — `crowdsec_node_purge`. Ручного создания шаблонов не нужно — все приезжают через `update_templates`; группу `crowdsec_nodes` сидинг создаст пустой сам.

Предусловия на ноде (не ставятся, только проверяются): `docker` (шаблон `docker` — иначе `fail`), `rsyslog` (шаблон `rsyslog` — иначе только warning). LAPI должен отвечать (`cscli lapi status`).

## `crowdsec_register` (Target — строго один хост LAPI, не `all`)

- `project_id` (Integer, обязательно — для записи в API)
- `crowdsec_node_names` (Text, обязательно; по одному `^[a-z0-9-]+$` на строку; повтор имени = ротация секретов; `local/dashboard/localhost` запрещены)
- `crowdsec_from_group` (String; например `de` — взять имена-алиасы из группы inventory вместо ручного списка; с `crowdsec_node_names` вместе нельзя — только один источник)
- `crowdsec_api_url` (String; пусто — взять текущий из группы, обязателен при первой регистрации; поле не для этого прогона — register ходит через `docker exec`, URL складируется в группу для деплоев нод)
- `crowdsec_lapi_container` (String; пусто — `crowdsec-lapi`)
- не запускай два register параллельно — записи в группу идут read-modify-write, второй затрет первого
- порядок: сначала проверяется доступ к Semaphore и группа (токен, `project_id`, URL), и только потом старые регистрации удаляются и создаются новые. PUT в группу повторяется 3 раза; если он так и не прошёл, новые креды (в LAPI уже действуют) сохраняются в файл `0600` на контроллере (`crowdsec_register_rescue_dir`, дефолт `/tmp/semaphore` — том `semaphore_tmp`) и прогон падает с путём к файлу. Секреты в лог не выводятся
- в группу пишутся `crowdsec_node_<имя>_agent_password`, `_api_key` и `_agent_username` (имя машины в LAPI)

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
- `crowdsec_extra_logs` (Text, по одному на строку: `путь` или `путь:type`, пути строго под `/var/log`). Каждый лог рендерится в `acquis.yaml` отдельным документом со своим `labels.type` (дефолт `syslog`), например `/var/log/nginx/access.log:nginx`. Стеки nginx этого репо пишут с `access_log off`, так что их логов на диске нет
- `crowdsec_tz` (String; пусто — взять из `/etc/timezone` хоста)
- `crowdsec_dir` (String; папка проекта на ноде, пусто — `/opt/crowdsec`)
- `crowdsec_bouncer_iptables_chains: [INPUT, DOCKER-USER]` — цепочки баунсера в режиме iptables. `DOCKER-USER` нужен, чтобы баны закрывали и опубликованные порты контейнеров (Docker пропускает их через FORWARD мимо INPUT). В режиме nftables баунсер вешается на хуки `input` и `forward`
- изменение `acquis.yaml` или конфига баунсера при `deploy` перезапускает соответствующий контейнер (конфиги читаются только при старте); после deploy проверяется и `cscli lapi status` агента, и что баунсер запущен
- `restart` — `docker compose restart` (`state: restarted`); `status` выводит контейнеры, `lapi status`, число записей ipset/nftables
- `remove` не требует кредов в группе: по документированному порядку он идёт после `crowdsec_unregister`
- файлы ноды: `crowdsec_dir` (дефолт `/opt/crowdsec`; пусто — дефолт) (`compose.yml`, `.env 0600`, `config/`); секреты подтягиваются из группы по имени, отсутствуют — `fail` «сначала register»
- логи контейнеров: `json-file 10m × 3` (зашито в compose, применяется со следующего deploy/recreate)
- имя агента берётся из группы (`_agent_username`), если его нет — `<имя>-agent`. После adopt/move имя машины в LAPI может отличаться от `<имя>-agent` — раньше deploy после них ломал аутентификацию агента
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

`docker compose pull` + `up -d`: пересоздаются только контейнеры с новым образом, по одной ноде (`serial: 1`), затем проверяются агент (`cscli lapi status`) и баунсер. Раньше каждый прогон делал `down/up` на всём флоте — баунсер снимал правила, а `changed` всегда был `false`.

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
- удаляет `<имя>-agent` и `<имя>-bouncer` из LAPI и стирает их креды (`_agent_password`, `_api_key`, `_agent_username`) из группы `crowdsec_nodes` (`crowdsec_api_url` не трогает); группы нет — чистка скипается с warning, не fail

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
- migrate: синк группы → stop+rename → рендер стандарта → `up` → `cscli lapi status` + баунсер запущен → rescue с подъёмом бэкапа. Новый стек всегда с именами `crowdsec-agent`/`crowdsec-bouncer` (шаблон), `crowdsec_*_container` — имена старых контейнеров
- `crowdsec_adopt_purge_backup: false` — бэкап (контейнеры `*-adopt-bak-*` + каталог `*.adopt-bak-*`) остаётся для отката; `true` — удалить после успешной проверки. Удаление идёт вне блока с rollback. Потом бэкап убирает `crowdsec_node_purge`
- в группу пишется и имя агента (`_agent_username`) — следующий `deploy` подключится тем же пользователем
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

Соглашение: `move` = переезд (`adopt` — на месте). Креды сохраняются 1:1, ключи группы пишутся под **новое** имя (hostname цели или явное) вместе с `_agent_username` — поэтому будущие deploy подключаются тем же агентом; в LAPI останутся старые имена агента/баунсера (косметика, лечится ротацией через register).

- `target` — исходная нода (строго один хост); `crowdsec_move_dest` (цель в inventory, обязательно, строго один хост, ≠ источнику)
- `crowdsec_move_action: inspect` (отчёт+план) / `move`; `crowdsec_move_confirmed: true` — обязательно для `move`
- `crowdsec_node_name` (пусто — имя целевой ноды), остальные поля — как в adopt (`crowdsec_agent_container`/`crowdsec_bouncer_container` и `old_dir` — источник, `dir`/`mode` — уже цель)
- порядок: discovery → поднимаем цель (проверка `cscli lapi status` и баунсера) → только после успеха пишем креды в группу под новым именем и гасим источник (stop+rename, каталоги целы); провал на цели — ни группа, ни источник не тронуты (раньше источник гасился и при провале цели, а группа переписывалась заранее)
- `crowdsec_move_purge_backup: true` — удалить бэкап-контейнеры источника `*-moved-bak-*` после успеха; `false` — оставить для отката

## `crowdsec_node_purge` (уборка бэкапов adopt/move)

- `crowdsec_purge_action: inspect` / `purge`; `crowdsec_purge_confirm: true` — обязательно для `purge`; `crowdsec_purge_confirmed: true` — для нескольких хостов
- ищутся только бэкапы CrowdSec: контейнеры `crowdsec-agent|crowdsec-bouncer|<свои имена>-(adopt|move|moved)-bak-<ts>` и каталоги `*.adopt-bak-*`/`*.move-bak-*` под `/opt`, `/srv`, `/root`, `/home`, в compose которых есть `crowdsecurity/crowdsec` или `cs-firewall-bouncer`. Бэкапы nginx/Remnawave не трогаются
- удаляются все найденные; `crowdsec_purge_container` / `crowdsec_purge_dir` (через запятую или по строке) — только указанные, чужие имена и небезопасные пути отклоняются

## Хранение кредов

Креды нод лежат в JSON группы `crowdsec_nodes` открытым текстом — их видит любой, у кого есть доступ к окружениям проекта. Надёжнее держать их в **Secrets** окружения Semaphore (поле `secrets`); плейбуки пока пишут в JSON — перенос сделай вручную, если доступ к проекту есть не только у тебя.
