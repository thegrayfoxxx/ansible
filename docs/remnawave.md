# Вкладка Remnawave: панель отдельно, ноды — по шагам add → deploy → config/update → move → remove

Шесть шаблонов с одной ответственностью:

| Шаблон | Где выполняется | Что делает |
| --- | --- | --- |
| `remnawave_node_add` | раннер → API панели | регистрирует ноду в панели, SSH не трогает |
| `remnawave_node_deploy` | нода | создаёт/пересобирает стек агента в Docker |
| `remnawave_node_config` | нода | `show`/`apply` монтирований, логов и xray у существующего стека |
| `remnawave_node_update` | нода | только обновляет образ (`pull + down + up -d`) |
| `remnawave_node_move` | нода(ы) | переезд 1:1: другая папка (`local`) или другой хост (`remote`) |
| `remnawave_node_remove` | панель и/или нода | удаляет запись в панели и/или стек на хосте |

Ручного создания шаблонов не нужно — приезжают через `update_templates`.

Соглашение об именах: `remnawave_*` — API панели, `remnanode_*` — рантайм агента на ноде.

## Миграция со старых шаблонов

- **`remnawave_node_add action=register`** → `remnawave_node_add` (теперь всегда только панель).
- **`remnawave_node_add action=deploy` или `action=both`** → `remnawave_node_add`, затем `remnawave_node_deploy` на ноде.
- **`remnawave_node_adopt`** удалён. Привести ручную ноду к стандарту = `remnawave_node_move`: `remnanode_move_action=move`, `remnanode_move_scope=local`, `remnanode_move_confirmed=true`.
- **`remnanode_xray_manage`** удалён, вместо него `remnanode_xray_mode`:
  - `manage=false` → `mode=keep`;
  - `manage=true` + версия → `mode=version`;
  - `manage=true` без версии → `mode=image`.
- Дефолтная папка проекта — `/opt/remnanode` (как в доках апстрима). Ноды из `/opt/remnawave` сами не переедут: `remnawave_node_move scope=local` с `remnanode_dir=/opt/remnanode`.

> ⚠️ BREAKING: старые survey-поля (`remnawave_action`, `remnawave_adopt_action`, `remnanode_xray_manage`) игнорируются. Обнови сохранённые запуски/расписания.

## Заполнение группы `remnawave_vars`

Сидинг создаёт группу сам (см. `environments_seed` в `templates.json`), причём сразу с дефолтами — руками дописывается только секрет:

1. **Вкладка Secrets** → `New Secret`, тип обязательно **env** (не var — иначе плейбук не найдёт через `lookup('env', ...)`):
   - имя `REMNAWAVE_TOKEN`, значение — API-токен панели.
2. **Вкладка JSON** — уже предзаполнена сидом, проверь/правь под себя:

```json
{
  "remnawave_default_panel_url": "https://panel.example.com",
  "remnawave_default_config_profile": "",
  "remnawave_default_inbounds": ""
}
```

   - `remnawave_default_panel_url` — обязателен (без `/` на конце — обрежется сам, но лучше без);
   - два `remnawave_default_*` — опциональны: пустые строки или убери ключи (плейбук трактует одинаково); заполненные — дефолт на все прогоны, survey перекрывает разово.

Правила сида (важно):

- сид пишется **один раз при создании группы** (`POST` → следом `PUT` только с этим JSON, `secrets: []` — секреты не задевает). Повторные `Run update_templates` значения **не трогают** — поменять можно только в UI руками;
- секреты не сидируются никогда (репо публичное): токен всегда вписывается руками, иначе плейбук упадёт с понятным `fail`, а не молча;
- проверка после сидинга: `Run remnawave_node_add` на заведомо новом имени — при пустой/кривой группе упадёт с текстом что именно заполнить.

Предусловия: панель доступна с раннера (сеть!); API-токену нужны права на nodes (создание/чтение/удаление), config-profiles (+ inbounds) и keygen (иначе `403`). На ноде: `docker` (шаблон `docker` — иначе `fail`), Debian/Ubuntu; панель должна доставать ноду по `address:port` (фаервол!).

## `remnawave_node_add` — только регистрация в панели

`hosts: localhost`, никакого SSH, ключей и деплоя. Все поля — про запись в панели:

- `remnawave_node_name` (3..30), `remnawave_node_address` (достижимый со стороны панели)
- `remnawave_node_port` (пусто — случайный `1024..65535`; явно — конкретный; `<1024` — warning). Порт фиксируется в панели, `deploy` заберёт его оттуда.
- `remnawave_country` (`XX`), `remnawave_note` (до 255)
- `remnawave_config_profile` (UUID/имя/пусто): survey → дефолт группы → авто по `default` (точное совпадение → вхождение `default` → `дефолт`; 0/несколько — `fail` со списками)
- `remnawave_inbounds` (Text, UUID построчно; пусто — все инбаунды профиля; чужие — `fail` с доступными тегами)
- `remnawave_token` (Secret, разовый override), `remnawave_validate_certs: true` → `false` для самоподписанного серта панели

Поведение:

- повтор с тем же именем — skip по `uuid`: `add` никогда не меняет существующую запись (ни адрес, ни порт, ни профиль). Если адрес в панели разошёлся с survey — будет warning, правка только в UI;
- запись без сохранённого порта — `fail` с подсказкой удалить/пересоздать ноду;
- дубликат адреса с другим именем — текст ошибки сервера как есть;
- `SECRET_KEY` здесь не запрашивается: его получает `deploy` при первой установке.

```json
{
  "remnawave_node_name": "de1-vpn",
  "remnawave_node_address": "de1.cdn.example.com",
  "remnawave_country": "DE"
}
```

## `remnawave_node_deploy` — стек на ноде

Создаёт стек в `remnanode_dir` (`compose.yml`, `.env 0600`), поднимает его и проверяет, что контейнер запущен и слушает порт.

Строгость:

- существующий стек (контейнер или `compose.yml`) — `fail`, пока не выставлен `remnanode_force=true`;
- стек, живущий в другой папке, — `fail` с подсказкой `remnawave_node_move scope=local`;
- `deploy` никогда не переезжает и не меняет существующий стек «по мелочи» — для этого есть `config`/`update`/`move`.

Поля:

- `target` — строго один хост ноды.
- `remnawave_node_name`, `remnawave_token` — нужны для **первой** установки, пока в `.env` нет хотя бы одного из значений (`NODE_PORT`, `SECRET_KEY`): недостающий порт берётся из записи панели, `SECRET_KEY` — из `GET /api/keygen`. Если `.env` уже содержит оба значения, панель не нужна (токен и имя можно не заполнять).
- `remnanode_dir` (пусто — `/opt/remnanode`), `remnanode_old_dir` (пусто — автоопределить по compose-меткам), `remnanode_agent_container` (пусто — `remnanode`).
- `remnanode_node_image` (пусто — текущий образ стека, а для новой установки `remnawave/node:latest`).
- `remnanode_force: false` → `true` — перерендерить существующий стек из survey. Force сохраняет креды `.env` (берёт их из running-контейнера или файла), текущий образ при пустом поле и кастомный xray при `xray_mode=keep`.
- `remnawave_open_port` + `remnawave_allow_from` — открыть порт агента в `ufw`, если он есть (нет — скип с warning; идемпотентно; только с IP панели, пусто — отовсюду). Выключение правило не удаляет — это ручной `ufw delete`.
- `remnanode_mount_shm`, `remnanode_mount_logs`, `remnanode_log_dir`, `remnanode_log_max_size`, `remnanode_log_keep` — монтирования и ротация логов (см. ниже).
- `remnanode_xray_mode` / `remnanode_xray_version` — xray при первой установке или force (см. «Версия xray-core»).

Порядок первой установки:

1. `remnawave_node_add` создаёт запись в панели (порт уже там).
2. `remnawave_node_deploy` находит ноду по имени, берёт порт, генерирует `SECRET_KEY`, пишет `.env`, поднимает стек.
3. При `remnawave_node_name` и доступной панели `deploy` ждёт `isConnected` (~2 мин). Если ноды нет в панели — `fail` с подсказкой сначала прогнать `add`.

Если `deploy` упал, запись в панели не удаляется: исправь причину и повтори. Частично созданный стек можно пересобрать с `remnanode_force=true`.

```json
{
  "target": "de1",
  "remnawave_node_name": "de1-vpn",
  "remnawave_open_port": true,
  "remnawave_allow_from": "203.0.113.10"
}
```

Пересборка существующего стека без смены кредов и xray:

```json
{
  "target": "de1",
  "remnanode_force": true,
  "remnanode_node_image": "remnawave/node:latest"
}
```

### Монтирования и логи

- `remnanode_mount_shm: true` — прокинуть хостовый `/dev/shm` в контейнер (нужен для Selfsteal-сокета nginx из `docs/nginx.md`).
- `remnanode_mount_logs: true` — прокинуть каталог логов xray (`<host>:<remnanode_log_dir>` → `/var/log/remnanode`).
- `remnanode_log_dir` (пусто — `/var/log/remnanode`; например `/opt/xray-logs`), `remnanode_log_max_size: 100M` (например `50M`, `100M`, `1G`; число + `k`/`M`/`G`), `remnanode_log_keep: 5` (`1..30`, например `5` или `10`).
- Ротация — host-level `logrotate` (`/etc/logrotate.d/remnanode`, `copytruncate` — контейнер не дёргаем). Лимиты `json-file` в compose покрывают только stdout контейнера, не файлы в примонтированном каталоге.

## `remnawave_node_config` — host-конфиг существующего стека

`action=show` — только отчёт (безопасно). `action=apply` — применить изменения. Работает только с уже развёрнутым стеком: нет `compose.yml` или контейнера — `fail` с подсказкой про `deploy`.

`config` — единственный day-2 владелец xray. Он **никогда** не меняет образ, порт и `SECRET_KEY`: текущий образ берётся из контейнера, креды только читаются и проверяются.

Поля:

- `target` — строго один хост; `remnanode_dir` (пусто — `/opt/remnanode`), `remnanode_old_dir`, `remnanode_agent_container`.
- `remnanode_mount_shm`, `remnanode_mount_logs`: `keep` (дефолт) — оставить как есть; `true`/`false` — включить/выключить.
- `remnanode_log_dir`, `remnanode_log_max_size`, `remnanode_log_keep`: `keep` (дефолт) или пусто — оставить текущее; явное значение — изменить. Примеры: `/var/log/remnanode` или `/opt/xray-logs`, `100M`/`50M`/`1G`, `5`/`10` (`1..30`). Если текущего значения нет, используются `/var/log/remnanode`, `100M`, `5`.
- `remnanode_xray_mode`: `keep` (дефолт) — не трогать xray; `image` — снять кастомный mount и вернуться на xray из образа; `version` — поставить выбранную версию.
- `remnanode_xray_version` — только для `version`.

Поведение:

- `keep` (дефолт) и пустые поля трактуются как «оставить текущее»;
- если менять нечего — `No config changes` и выход без рестарта;
- изменения монтирований/логов/xray пересобирают контейнер; смена только logrotate может обойтись без рестарта, но проверка running/listen всё равно выполняется;
- `ufw` только отображается (`remnanode_ufw_state`, `remnanode_port_fw` + warning при закрытом порте) — правила меняет шаблон `firewall`;
- смена `remnanode_log_dir` переезжает только конфиг ротации: старые файлы остаются в прежнем каталоге, новые пишутся в новый.

```json
{
  "target": "de1",
  "remnawave_config_action": "show"
}
```

```json
{
  "target": "de1",
  "remnawave_config_action": "apply",
  "remnanode_mount_logs": true,
  "remnanode_log_max_size": "200M",
  "remnanode_log_keep": 10,
  "remnanode_xray_mode": "version",
  "remnanode_xray_version": "26.10.21"
}
```

Оставить логи как есть (значения по умолчанию):

```json
{
  "target": "de1",
  "remnawave_config_action": "apply",
  "remnanode_log_dir": "keep",
  "remnanode_log_max_size": "keep",
  "remnanode_log_keep": "keep"
}
```

Вернуться на xray из образа:

```json
{
  "target": "de1",
  "remnawave_config_action": "apply",
  "remnanode_xray_mode": "image"
}
```

## `remnawave_node_update` — только образ

`pull + down + up -d` на любом числе нод; панель не нужна. Монтирования, `.env`, креды и xray не меняются: кастомный бинарь и его mount переживают обновление. Если стека нет — `fail` с подсказкой `remnawave_node_deploy`.

```json
{
  "target": "de",
  "remnanode_dir": ""
}
```

## `remnawave_node_move` — переезд 1:1

Один шаблон для двух сценариев:

- `remnanode_move_scope=local` — другая папка на том же хосте (замена удалённого `adopt`);
- `remnanode_move_scope=remote` — другой хост inventory.

`move` всегда сохраняет текущие образ, креды, монтирования, настройки логов и xray. Полей конфига/xray в survey нет: источник читается из running-контейнера, `.env` и compose-меток.

Общие поля:

- `target` — исходная нода, строго один хост.
- `remnawave_move_action: inspect` — отчёт и план; `move` — переезд.
- `remnanode_move_confirmed: true` — обязательно для `move` (останавливаем рабочую ноду).
- `remnanode_agent_container`, `remnanode_old_dir` (пусто — автоопределить по compose-меткам; для контейнера, запущенного вручную через `docker run`, укажи явно), `remnanode_dir` (куда переезжаем).

### `scope=local`

- `remnanode_dir` — новый каталог; должен отсутствовать. Тот же каталог, вложенность source↔target и занятый target — `fail` с подсказкой.
- Порядок: сохранить кастомный xray → остановить контейнер → переименовать контейнер в `<name>-move-bak-<ts>` → переименовать старый каталог в `<dir>.move-bak-<ts>` → создать target, положить xray, отрендерить, поднять.
- Провал — rollback: target гасится/удаляется, старый каталог и имя контейнера возвращаются, старый контейнер стартует. Бэкапы после успеха не удаляются — проверь и снеси руками.
- Тот же каталог — `fail`: это не переезд; используй `config` или `deploy remnanode_force=true`.

```json
{
  "target": "de5",
  "remnawave_move_action": "move",
  "remnanode_move_scope": "local",
  "remnanode_move_confirmed": true,
  "remnanode_dir": "/opt/remnanode"
}
```

### `scope=remote`

- `remnanode_move_dest` — целевая нода inventory, строго один хост и не источник.
- Цель должна быть чистой: нет target-каталога, контейнера с тем же именем и слушателя на порту — иначе `fail` до изменений.
- Если xray кастомный и архитектуры источника/цели различаются — `fail` до любых изменений. Порядок обхода: на источнике `remnawave_node_config action=apply remnanode_xray_mode=image`, затем `move`, затем на цели `remnawave_node_config remnanode_xray_mode=version`.
- Порядок: source остаётся работать → на цели создаётся каталог, переносится xray/креды/настройки → стек поднимается и проверяется → только после этого source останавливается и переименовывается в `<name>-moved-bak-<ts>` (каталог источника цел). Провал на цели — source не тронут.
- Файлы логов на цель не копируются: переносятся mount и настройки ротации, старые логи остаются на источнике. Панель не трогаем — запись и креды те же; после переезда поправь DNS на новый адрес (TTL). Если в панели адрес ноды задан IP-адресом источника, обнови его на IP цели в UI панели вручную — `move` этого не делает.
- Панель/токен не нужны.

```json
{
  "target": "de5",
  "remnawave_move_action": "move",
  "remnanode_move_scope": "remote",
  "remnanode_move_dest": "de9",
  "remnanode_move_confirmed": true
}
```

## `remnawave_node_remove` — удаление

- `remnawave_remove_action: inspect` — только отчёт; `remove` — удалять.
- `remnawave_remove_scope`:
  - `panel` — только запись в панели; `target` можно не заполнять;
  - `host` — только стек на хосте; панель не трогается;
  - `both` (дефолт) — сначала хост, потом панель.
- `remnawave_remove_confirm: true` — обязательно для `remove`.
- `remnawave_remove_purge: false` — `true` дополнительно удаляет project dir и `/etc/logrotate.d/remnanode` (только для `scope=host/both`, после удаления стека и панели и только если стек вообще был найден).
- `remnawave_node_name` — точное имя в панели (обязательно для `panel`/`both`); `remnawave_token`, `remnawave_validate_certs`.
- `target` — хост ноды (обязателен для `host`/`both`), строго один; `remnanode_agent_container`, `remnanode_dir`, `remnanode_old_dir`.

Порядок для `both`: остановить/удалить контейнер (compose `down`, затем `docker stop`/`docker rm -f` для остатка) и убедиться, что контейнера нет → удалить запись в панели → при `purge=true` удалить каталог проекта (compose-dir, `remnanode_old_dir` или `remnanode_dir`) и logrotate. UFW **не трогается**: если правило было, будет warning с готовой командой `ufw delete`. Файлы xray-логов и бэкапы `move` автоматически не удаляются.

```json
{
  "target": "de5",
  "remnawave_remove_action": "inspect",
  "remnawave_remove_scope": "both",
  "remnawave_node_name": "de5-vpn"
}
```

Только убрать запись из панели (хост уже мёртв):

```json
{
  "remnawave_remove_action": "remove",
  "remnawave_remove_scope": "panel",
  "remnawave_remove_confirm": true,
  "remnawave_node_name": "de5-vpn"
}
```

## Версия xray-core

Нода может работать на xray из образа `remnawave/node` или на своём бинаре, примонтированном в `/usr/local/bin/xray`. Версия образа при этом не меняется — меняется только бинарь xray-core.

Режимы `remnanode_xray_mode`:

- `keep` (дефолт) — не менять текущее состояние: если на ноде уже есть кастомный xray, он сохраняется и монтируется; иначе работает xray из образа. `remnanode_xray_version` при `keep` должен быть пустым.
- `image` — снять кастомный mount и вернуться на xray из образа. Файл `<project dir>/xray-core` остаётся на диске, marker `.xray-core.version` удаляется (удалить бинарь вручную, если не нужен).
- `version` — скачать официальный релиз XTLS/Xray-core и смонтировать его. `remnanode_xray_version` обязателен (например `26.10.21` или `v26.10.21`).

Детали установки версии:

- только официальные релизы `XTLS/Xray-core` с GitHub;
- проверка `SHA2-256` из `.dgst` релиза, скачивание с `checksum`;
- архитектуры: `x86_64`/`amd64` → `64`, `aarch64`/`arm64` → `arm64-v8a`, `armv7l` → `arm32-v7a`, `armv6l` → `arm32-v6`, `i686`/`i386` → `32`; остальные — `fail`;
- `unzip` ставится только когда реально нужна распаковка релиза;
- бинарь кладётся в `<project dir>/xray-core` (`0755`), версия пишется в `.xray-core.version` только после успешного `up`;
- повтор с той же версией не перекачивает архив; смена версии пересоздаёт контейнер, чтобы подхватить новый бинарь.

Кто владеет xray:

- `add` — не касается;
- `deploy` — ставит/сохраняет xray при первой установке или `force` (при `keep` кастом сохраняется);
- `config` — единственный day-2 владелец: `keep`/`image`/`version`;
- `update` — никогда не трогает (mount и бинарь переживают `down/up`);
- `move` — всегда переносит текущее состояние 1:1; при cross-arch кастоме сначала переведи источник на `image`.
