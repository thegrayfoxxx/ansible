# Вкладка Remnawave: VPN-панель уже стоит; ноды — register/deploy/both через API

Четыре шаблона: `remnawave_node_add` (два play внутри: register — только API панели, SSH не трогается; deploy — агент в Docker на ноде), `remnawave_node_update` (`pull + down + up -d` на любом числе нод, панель не нужна), `remnawave_node_adopt` (принять ручную ноду под управление на месте) и `remnawave_node_move` (переезд на другую ноду с сохранением кредов). Ручного создания шаблонов не нужно — приезжают через `update_templates`.

Соглашение об именах: `remnawave_*` — API панели, `remnanode_*` — рантайм агента на ноде.

> ⚠️ BREAKING: дефолтная папка проекта сменилась с `/opt/remnawave` на `/opt/remnanode` (как в доках апстрима), агентские переменные переименованы (`remnawave_dir` → `remnanode_dir` и т.д.). Старые имена в survey игнорируются — обнови сохранённые запуски/расписания. Ноды из `/opt/remnawave` сами не переедут: либо разово передай старый путь в `Project dir`, либо `down` в старом каталоге + deploy.

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
- проверка после сидинга: `Run remnawave_node_add` с `action=register` на заведомо новом имени — при пустой/кривой группе упадёт с текстом что именно заполнить.

Предусловия: панель доступна с раннера (сеть!); API-токену нужны scopes `nodes:create:write` + `list:read`, `config-profiles:list:read` + `list-profile-inbounds:read`, `keygen:get:read` (иначе `403`). На ноде: `docker` (шаблон `docker` — иначе `fail`), Debian/Ubuntu; панель должна доставать ноду по `address:port` (фаервол!).

## `remnawave_node_add`

`remnawave_action: both` (дефолт — регистрация + деплой одним прогоном; `register` / `deploy` по отдельности):

- `target` — строго один хост (в register-режиме значение игнорируется, но заполнить надо)
- `remnawave_node_name` (3..30), `remnawave_node_address` (достижимый со стороны панели)
- `remnawave_node_port` (пусто — случайный `1024..65535`, фиксируется на прогон; явно — конкретный; `<1024` — warning)
- `remnawave_country` (`XX`), `remnawave_note` (до 255)
- `remnawave_config_profile` (UUID/имя/пусто): survey → дефолт группы → авто по `default` (точное ci → вхождение `default` → `дефолт`; 0/несколько — `fail` со списками)
- `remnawave_inbounds` (Text, UUID построчно; пусто — все инбаунды профиля; чужие — `fail` с доступными тегами)
- `remnawave_open_port: false` -> `true` чтобы открыть порт в `ufw`, если он есть (нет — скип с warning; идемпотентно; Enum) + `remnawave_allow_from` (только с IP панели, пусто — отовсюду). `ufw` нет — громкий `fail`. Выключаешь назад — правило сносится руками (одной командой `ufw delete`), свои правила плейбук не трогает
- `remnawave_token` (Secret, разовый override), `remnawave_validate_certs: true` -> `false` для самоподписанного серта панели
- `remnanode_dir` (String; папка проекта на ноде, пусто — `/opt/remnanode`)
- `remnanode_mount_shm: true` -> `false` чтобы не прокидывать хостовый `/dev/shm` в контейнер (нужен для Selfsteal-сокета nginx из `docs/nginx.md`; применяется на deploy; существующим нодам нужен `down` + повторный `deploy`)
- `remnanode_mount_logs: true` -> `false` чтобы не прокидывать каталог логов xray (`<host>:/var/log/remnanode`; применяется на deploy)
- `remnanode_log_dir` (String; каталог на ноде под логи xray, пусто — `/var/log/remnanode`)
- `remnanode_log_max_size: 100M` (String; ротация по размеру — число + `k`/`M`/`G`)
- `remnanode_log_keep: 5` (Integer; сколько ротированных файлов хранить, `1..30`)
- ротация — host-level `logrotate` (`/etc/logrotate.d/remnanode`, `copytruncate` — контейнер не дёргаем); лимиты `json-file` в compose покрывают только stdout контейнера, не файлы в примонтированном каталоге
- `remnanode_xray_manage` + `remnanode_xray_version` — свой xray-core вместо встроенного в образ (см. «Версия xray-core» ниже)

Как это работает: register пишет запись (`201`), повтор с тем же именем — skip по `uuid` (ротации нет: снос VPN-ноды роняет юзеров); дубликат адреса с другим именем — текст ошибки сервера как есть. `SECRET_KEY` забирается живым `GET /api/keygen` (общий на панель, в ответе создания его нет) и нигде не светится (`no_log`, в summary только имена/uuid). Deploy кладёт в `remnanode_dir` (дефолт `/opt/remnanode/`) (`compose.yml`, `.env 0600`; логи контейнера `json-file 10m × 3`), `up -d`, ждёт `isConnected` (~2 мин); упал deploy — созданная в этом прогоне запись откатывается (`DELETE`), повтор — чистый лист.

```json
{
  "target": "de1",
  "remnawave_action": "both",
  "remnawave_node_name": "de1-vpn",
  "remnawave_node_address": "de1.cdn.theshadowfox.com",
  "remnawave_open_port": true,
  "remnawave_allow_from": "203.0.113.10"
}
```

### Версия xray-core

Нода может работать на xray из образа `remnawave/node` или на своём бинаре, примонтированном в `/usr/local/bin/xray`. Версия образа при этом не меняется — меняется только бинарь xray-core.

- `remnanode_xray_manage: false` (дефолт) — xray не трогаем: если на ноде уже стоит кастомный xray, он сохраняется (в adopt/move переносится), иначе работает xray из образа. `remnanode_xray_version` игнорируется (в логе будет warning).
- `remnanode_xray_manage: true` + `remnanode_xray_version` (например `26.10.21` или `v26.10.21`) — скачивается официальный релиз XTLS/Xray-core и монтируется в контейнер. Проверяется `SHA2-256` из `.dgst` релиза. Архитектуры: `x86_64` → `64`, `aarch64` → `arm64-v8a`, `armv7l` → `arm32-v7a`, `armv6l` → `arm32-v6`, `i686/i386` → `32`; остальные — fail.
- `remnanode_xray_manage: true` без версии — кастомный mount снимается, нода возвращается на xray из образа. Файл `<project dir>/xray-core` остаётся на диске (удалить вручную, если не нужен).
- Бинарь кладётся в `<project dir>/xray-core` (`0755`), версия фиксируется в `.xray-core.version`; повторный прогон с той же версией не перекачивает архив. Смена версии — повторный `action=deploy` (add) или `migrate` (adopt) с новой версией; контейнер пересоздаётся, чтобы подхватить новый бинарь.
- `remnawave_node_update` версию xray не меняет: mount и бинарь переживают `down/up`, обновляется только образ.
- `adopt`/`move` при `remnanode_xray_manage: false` сохраняют существующий кастом 1:1; в move `true` означает «не переносить кастом» (цель на xray из образа).

```json
{
  "target": "de1",
  "remnanode_xray_manage": true,
  "remnanode_xray_version": "26.10.21"
}
```

## `remnawave_node_update` (обновление без панели — достаточно `target` и опционально `remnanode_dir`)

```json
{
  "target": "de",
  "remnanode_dir": ""
}
```

## `remnawave_node_adopt` (принять ручную ноду под управление; офлайн, без панели)

Соглашение: `adopt` = причесать на месте (файлы переезжают в `remnanode_dir`, креды сохраняются).

- `remnawave_adopt_action: inspect` (только отчёт что найдено — безопасно; `migrate` — переезд)
- `target` — строго один хост; `remnanode_agent_container` (пусто — `remnanode`)
- `remnanode_old_dir` (пусто — автоопределить из compose-меток; нет меток — обязательно явно)
- `remnanode_dir` + флаги `mount_shm/mount_logs/log_dir/log_max_size/log_keep` — те же, что в deploy
- discovery: compose-метки → `working_dir`, креды — сначала из running-контейнера (`docker inspect` → `Env`), потом из старого `.env`; секрет в логах не светится
- `remnanode_xray_manage` + `remnanode_xray_version`: `false` (дефолт) — сохранить текущий кастомный xray; `true` + версия — поставить версию; `true` без версии — снять кастом и вернуться на xray из образа (см. «Версия xray-core»)
- фаервол только светим (`ufw=active/inactive/missing`, `port_fw=allowed/closed/na` + warning при закрытом) — правила меняет `firewall`-шаблон
- migrate: бэкап (переименование контейнера + каталога с timestamp, не удаление) → рендер стандарта → `up` → проверка running+listen; провал — автораollback (поднять бэкап) + fail с командой ручной проверки
- тот же каталог как target — fail с подсказкой гнать `deploy` (переезжать нечего)

```json
{
  "target": "de5",
  "remnawave_adopt_action": "inspect"
}
```

```json
{
  "target": "de5",
  "remnawave_adopt_action": "migrate",
  "remnanode_old_dir": "/home/anatoliy/remna_node"
}
```

## `remnawave_node_move` (переезд на другую ноду; тот же домен, DNS переключить руками)

Соглашение: `move` = переезд (`adopt` — на месте). Креды сохраняются 1:1, в панель не ходим (токены не нужны). Порядок: поднимаем новую → проверяем → только потом гасим старую (ноль даунтайма кроме TTL DNS).

- `target` — исходная нода (строго один хост); `remnanode_move_dest` (цель в inventory, обязательно, строго один хост, ≠ источнику)
- `remnawave_move_action: inspect` (отчёт+план) / `move`; `remnanode_move_confirmed: true` — обязательно для `move` (сносим рабочую ноду)
- `remnanode_xray_manage: false` (дефолт) — перенести текущий кастомный xray на цель 1:1; `true` — не переносить, цель на xray из образа
- остальные поля — как в adopt (`container`, `old_dir`, `dir` уже целевой, те же 6 флагов)
- rescue на цели: провал — новая гасится, источник не тронут; чистка источника (stop+rename, каталог цел) — только после verified новой; повторный прогон безопасен (источника с исходным именем уже нет → discovery упадёт с понятным текстом, а не переедет дважды)
