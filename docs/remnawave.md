# Вкладка Remnawave: VPN-панель уже стоит; ноды — register/deploy/both через API

Два шаблона: `remnawave_node_add` (два play внутри: register — только API панели, SSH не трогается; deploy — агент в Docker на ноде) и `remnawave_node_update` (`pull + down + up -d` на любом числе нод, панель не нужна). Ручного создания шаблонов не нужно — приезжают через `update_templates`.

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
- `remnawave_dir` (String; папка проекта на ноде, пусто — `/opt/remnawave`)

Как это работает: register пишет запись (`201`), повтор с тем же именем — skip по `uuid` (ротации нет: снос VPN-ноды роняет юзеров); дубликат адреса с другим именем — текст ошибки сервера как есть. `SECRET_KEY` забирается живым `GET /api/keygen` (общий на панель, в ответе создания его нет) и нигде не светится (`no_log`, в summary только имена/uuid). Deploy кладёт в `remnawave_dir` (дефолт `/opt/remnawave/`) (`compose.yml`, `.env 0600`; логи контейнера `json-file 10m × 3`), `up -d`, ждёт `isConnected` (~2 мин); упал deploy — созданная в этом прогоне запись откатывается (`DELETE`), повтор — чистый лист.

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

## `remnawave_node_update` (обновление без панели — достаточно `target` и опционально `remnawave_dir`)

```json
{
  "target": "de",
  "remnawave_dir": ""
}
```
