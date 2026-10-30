# Вкладка Nginx: Selfsteal-заглушка + LE-серт (Xray уже стоит отдельно)

Восемь шаблонов: `nginx_fallback` (поднять заглушку с нуля + LE-серт), `nginx_adopt` (принять ручную заглушку под управление на месте), `nginx_move` (переезд на другую ноду с сохранением сертов), `nginx_proxy` (nginx впереди на 443 с маршрутом на Xray), `nginx_node_update` / `nginx_proxy_update` (обновить образы) и `nginx_node_purge` / `nginx_proxy_purge` (убрать бэкапы adopt/move). Xray (хостовая Remnanode / свой docker) сюда не входит — он шлёт невалидный трафик в сокет. Ручного создания шаблонов не нужно — приезжают через `update_templates`.

Предусловия на ноде: `docker` (шаблон `docker` — иначе `fail`), Debian/Ubuntu, свободный `:80` (иначе http-01 не пройдёт). Для `nginx_fallback` `:443` не проверяем — это вотчина Xray; `nginx_proxy` сам встаёт на `:443` и проверяет, что порт свободен.

## Первый деплой (серта ещё нет — норма)

Плейбук сам разруливает курицу-и-яйцо (nginx не стартует без сертов):

1. кладёт файлы (`compose.yml`, `.env`, `fallback.conf.template`, `index.html` из survey);
2. если LE-серта нет — генерит временный self-signed на 2 дня, чтобы nginx встал и отдал `:80`;
3. `up -d` → проверка, что оба контейнера running → ждёт сокет `/dev/shm/nginx.sock` → `chmod 666` (иначе не-root Xray не подключится);
4. `acme.sh --issue --webroot` → `--install-cert` → `nginx -t` → `nginx -s reload`;
5. успешный `--issue` сам по себе доказывает, что `:80` доступен снаружи (LE достучался).

Временный self-signed больше не «залипает»: если первый `--issue` упал, на повторном прогоне серт с издателем не Let's Encrypt (или issuer == subject) считается отсутствующим и перевыпускается. `--issue` идёт с `--force`, когда это нужно (`nginx_force_issue`, переход staging→prod, замена self-signed); ответ acme.sh «Skip, Next renewal» (rc 2) — не ошибка.

### Продление и сокет без Ansible

У web-контейнера свой entrypoint с двумя фоновыми циклами (см. `templates/nginx/compose*.yml.j2`):

- `nginx -t && nginx -s reload` раз в `nginx_reload_interval` (дефолт 43200 с = 12 ч). acme.sh в своём контейнере сам продлевает серт и кладёт его в `./letsencrypt`, но до nginx ему не достучаться (нет docker.sock) — раньше nginx отдавал протухший серт до ручного перезапуска;
- только у заглушки: `chmod 0666` на `/dev/shm/nginx.sock` каждые 5 с — сокет пересоздаётся при каждом старте nginx (update, reboot), раньше права чинил только прогон плейбука.

Новый compose с этими циклами появляется на ноде после прогона `nginx_fallback`/`nginx_proxy` (adopt/move рендерят его сразу).

Повторный прогон с новым `nginx_html` или конфигом перезапускает web-контейнер: файлы смонтированы по одному, и после атомарной замены контейнер видел старую версию, а шаблон nginx обрабатывается только при старте.

`:443` плейбук не проверяет — порт оживает после установки Xray.

## `nginx_fallback`

- `nginx_domain` (String, обязательно; plain hostname без схемы и слэшей)
- `nginx_email` (String; обязателен для первого выпуска — LE-аккаунт; когда серт уже есть, можно пустым)
- `nginx_html` (Text, обязательно; свой `index.html` целиком — файл из репо не берём)
- `nginx_dir` (String; папка проекта на ноде, пусто — `/opt/nginx`)
- `nginx_staging: false` -> `true` для обкатки на staging LE без рейт-лимитов (потом перепрогнать с `false` для боевого серта; staging-серт браузерами не доверен; переход staging→prod плейбук определяет сам по issuer и перевыпускает без флага)
- `nginx_force_issue: false` -> `true` чтобы перевыпустить серт принудительно (жрёт лимиты LE: 5 дубликатов в неделю — только по нужде)
- `nginx_open_ports: false` -> `true` чтобы открыть `80,443/tcp` в ufw, если он есть (нет — скип с warning)
- `nginx_reload_interval: 43200` — период фонового `nginx -s reload`, секунд
- сокет всегда `/dev/shm/nginx.sock` (`0666`); контейнеры фиксированы (`fallback-web`, `fallback-acme`); логи `json-file 10m × 3`
- смена домена оставляет мусор `letsencrypt/live/<старый>` — чистится руками

```json
{
  "target": "de1",
  "nginx_domain": "de1.example.com",
  "nginx_email": "admin@example.com",
  "nginx_html": "<!DOCTYPE html>...",
  "nginx_staging": true
}
```

Повторный прогон (обновить заглушку, серт уже есть):

```json
{
  "target": "de1",
  "nginx_domain": "de1.example.com",
  "nginx_html": "<!DOCTYPE html>..."
}
```

## `nginx_adopt` (принять ручную заглушку под управление; панель/панели не нужны)

Соглашение: файлы ищем по маунтам running-контейнеров (раскладка источника может быть любой), новый лейаут всегда стандартный.

- `nginx_adopt_action: inspect` (только отчёт — безопасно; `migrate` — переезд)
- `target` — строго один хост; `nginx_web_container` (пусто — авто по образу `nginx:`, должен быть ровно один)
- `nginx_old_dir` (пусто — из compose-меток; нет меток — обязательно явно)
- `nginx_dir` (куда, пусто — `/opt/nginx`), `nginx_email` (override; пусто — из старого `.env`, для будущих перевыпусков обязателен)
- `nginx_open_ports` (как в deploy), `nginx_overwrite_conf: false` -> `true` чтобы заменить найденный конфиг стоком (иначе сохранить + warning о diff)
- переезжает: `index.html` (файл или каталог-источник — оба), `letsencrypt/`, acme-учётка (`/acme.sh`-маунт; нет — warning, продлений не будет до перевыпуска), конфиг (см. флаг); `webroot` — свежий пустой
- только bind-маунты (v1); именованные вольюмы/неизвестные destination — понятный fail
- migrate: stop+rename обоих контейнеров → копии → `up` → проверки (`nginx -t`, running, `:80` слушается, сокет, серты на месте) → rescue с подъёмом бэкапа
- старый каталог — в бэкап с timestamp (не удаление), контейнеры переименованы (не снесены)
- `nginx_adopt_purge_backup: false` — бэкап остаётся для отката (раньше удалялся всегда, вопреки описанию); `true` — удалить после успешных проверок. Удаление идёт вне блока с rollback. Потом бэкап убирает `nginx_node_purge`
- acme-учётка ищется в `.Mounts` контейнера (раньше искалась в несуществующем `.Config.Mounts` — учётка не переносилась и продление ломалось)

```json
{
  "target": "de5",
  "nginx_adopt_action": "inspect"
}
```

```json
{
  "target": "de5",
  "nginx_adopt_action": "migrate",
  "nginx_old_dir": "/home/anatoliy/fallback"
}
```

## `nginx_move` (переезд на другую ноду; тот же домен, DNS переключить руками)

Соглашение: `move` = переезд (`adopt` — на месте). Серты и учётка едут tarball'ом через контроллер (приватные ключи — `no_log`; staging-каталог и архивы на источнике и контроллере удаляются в `always`, в том числе при ошибке).

- `target` — исходная нода (строго один хост); `nginx_move_dest` (цель в inventory, обязательно, строго один хост, ≠ источнику)
- `nginx_move_action: inspect` (отчёт+план) / `move`; `nginx_move_confirmed: true` — обязательно для `move`
- остальные поля — как в adopt (контейнер/old_dir относятся к источнику, `dir` — уже к цели)
- порядок: поднимаем цель (проверки: running, `:80`, сокет, серты, issuer, ufw) → только потом гасим источник (stop+rename, каталоги целы); провал на цели — источник не тронут (плей вывода источника теперь явно проверяет успех цели)
- `nginx_move_purge_backup: true` — удалить бэкап-контейнеры источника `*-moved-bak-*` после успеха; `false` — оставить для отката

## `nginx_proxy` (nginx впереди на 443, путь → Xray, остальное — заглушка)

- `nginx_domain`, `nginx_email`, `nginx_html`, `nginx_staging`, `nginx_force_issue`, `nginx_open_ports` — как в `nginx_fallback`; `nginx_dir` (пусто — `/opt/nginx_proxy`)
- `nginx_proxy_path: /xray` — путь до Xray: `/` + буквы, цифры, `. _ ~ / -`
- `nginx_proxy_upstream: http://unix:/dev/shm/xray.sock` — `http(s)://unix:/путь`, `http(s)://host:port[/path]` или `http(s)://[ipv6]:port[/path]`. Значения проверяются строго: они попадают в конфиг nginx, и `;`/пробел дописали бы свои директивы
- `nginx_real_ip_from` (через запятую или по строке; пусто — дефолт) — доверенные прокси/CDN, от которых брать реальный IP из `X-Forwarded-For`. Раньше стояло `set_real_ip_from 0.0.0.0/0` — любой клиент подделывал свой IP заголовком
- до Xray идёт `upstream` с keepalive-пулом (`proxy_http_version 1.1`, `Connection ""`); `listen 443 ssl` + `http2 on` (nginx ≥ 1.25.1); `sendfile on` для `tcp_nopush`
- конфиг — `templates/nginx/nginx_proxy.conf.template.j2` (Jinja для upstream/real_ip, `${...}` подставляет nginx из env)

## `nginx_node_update` / `nginx_proxy_update`

`docker compose pull` + `up -d`: пересоздаются только контейнеры с новым образом, по одной ноде (`serial: 1`); затем проверка, что web-контейнер запущен, `nginx -t`, у заглушки — сокет и его права. Раньше каждый прогон делал `down/up` на всём флоте, а `changed` всегда был `false`. Поле `nginx_dir` (пусто — дефолт).

## `nginx_node_purge` / `nginx_proxy_purge`

- `nginx_purge_action` / `nginx_proxy_purge_action`: `inspect` / `purge`; `*_confirm: true` — обязательно для `purge`; `*_confirmed: true` — для нескольких хостов
- `nginx_node_purge` находит только бэкапы заглушки: контейнеры `*-(adopt|move|moved)-bak-<ts>` из образов `nginx`/`neilpang/acme.sh` (adopt сохраняет старые имена) и каталоги `*.adopt-bak-*`/`*.move-bak-*` под `/opt`, `/srv`, `/root`, `/home` с nginx/acme.sh в compose, кроме стеков `nginx_proxy`. Бэкапы CrowdSec/Remnawave не трогаются
- `nginx_proxy_purge` — только `nginx-proxy-(web|acme)-*-bak-*` и каталоги с `nginx-proxy-web` в compose; сам `nginx_proxy` бэкапов не создаёт
- удаляются все найденные; `*_container` / `*_dir` (через запятую или по строке) — только указанные, чужие имена и небезопасные пути отклоняются
- повторный прогон безопасен (источника с исходным именем уже нет → discovery упадёт с понятным текстом)
