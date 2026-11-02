# Вкладка System: базовое состояние хостов

## `playbooks/base.yml`

- `base_timezone: Etc/UTC` (String)
- `base_packages` (Text: один пакет на строку или через запятую; дефолт `python3, curl, btop, ufw`)

```json
{
  "target": "stage",
  "base_timezone": "Europe/Berlin"
}
```

## `playbooks/set_hostname.yml`

- `set_hostname_action: apply` (Enum; inspect — только отчёт: итоговый /etc/hosts + вердикт, ничего не пишет)
- `set_hostname_name: ""` (String; пусто — взять имя из target/inventory: один хост — имя хоста, группа — каждому по его inventory-имени)
- `set_hostname_domain: ""` (String; пусто — без FQDN, `127.0.1.1 host`; задан — `127.0.1.1 host.example.com host`)
- `set_hostname_restart_rsyslog: true` (Enum) — чтобы свежие логи пошли с новым именем

Что делает:

- короткое имя (kernel + `/etc/hostname`) через hostnamectl; имя валидируется `^[a-z0-9][a-z0-9-]{0,62}$` — инвентарные имена с точками/паттернами (`all:!de5`) не примутся, задай explicit
- хирургически нормализует `/etc/hosts`: сносит все строки со старым/новым коротким именем и FQDN (включая дубль хостера на `127.0.0.1`), посторонние записи (зеркала, внутренние сети) не трогает, вставляет одну каноническую `127.0.1.1 ...` сразу после `localhost`; бэкап `/etc/hosts.bak-<timestamp>` перед правкой
- гарды: `localhost`-записи обязательны и не затрагиваются; самозапись резолвится только в 127.x (защита от NAT-ловушки с публичным IP вместо `127.0.1.1`); повторный прогон — no-op

```json
{
  "target": "vps-prod-01"
}
```

Группа — каждому хосту его inventory-имя:

```json
{
  "target": "prod"
}
```

Hostname — это идентификатор (приглашение, journal/syslog, дефолтные имена нод в других шаблонах); на SSH-подключение, ключи, Docker и порты не влияет. PTR у хостера останется `vmXXXX...` — для нод не важно. После переустановки ОС у хостера имя вернётся к `vmXXXX` — просто перезапусти шаблон.

## `playbooks/docker.yml` (только Debian)

- `docker_users` (Text: юзеры в группу docker, один на строку или через запятую)
- `docker_verify: true` -> `false` чтобы пропустить `hello-world`
- `docker_version: ""` (String, например `5:27.*` — пин Engine+CLI; пусто — latest; `update` с dist-апгрейдом пин перетрёт)

```json
{
  "target": "stage",
  "docker_users": "debian"
}
```

## `playbooks/bbr.yml` (перезагрузка не нужна, применяется сразу)

- `bbr_enabled: true` -> `false` чтобы откатить на `cubic + fq_codel` (Enum)
- legacy `/etc/sysctl.d/10-bbr-fq_codel.conf` от `deb_scripts` удаляется, чтобы не было двух файлов на одни ключи
- на контейнерных VPS (OpenVZ/LXC) без своего ядра упадёт — там BBR включается на хосте провайдера

```json
{
  "target": "all",
  "bbr_enabled": true
}
```

## `playbooks/ipv6.yml` (sysctl, без ребута для применения запрета)

- `ipv6_state: disabled` / `enabled` (Enum, обязательно) — пишет `/etc/sysctl.d/99-ansible-ipv6.conf` (`all/default.disable_ipv6`). Loopback не трогается (`lo` остаётся с `::1`, иначе ломаются сервисы на localhost по IPv6); отказ, если `ansible_host` — IPv6 или SSH-сессия реально идёт по IPv6
- `ipv6_confirmed: false` -> `true` чтобы менять сразу на нескольких хостах (Enum)
- гард: отказ при подключении по IPv6 (иначе отрубишь себе SSH); уже поднятые интерфейсы держат адреса до ребута — полное снятие/возврат IPv6 может потребовать ребут (шаблон `reboot`)

```json
{
  "target": "vps-prod-01",
  "ipv6_state": "disabled"
}
```

## `playbooks/update.yml`

- `apt_upgrade: dist` (или `safe`)
- `apt_autoremove: true`
- `apt_autoclean: true`
- `reboot_if_required: false` -> `true` для авторебута
- `update_confirmed: false` -> `true` чтобы разрешить авторебут сразу на нескольких хостах (нужен только с `reboot_if_required: true`)
- `apt_lock_timeout: 600` — сколько секунд ждать dpkg lock (на свежей ноде его держит unattended-upgrades)
- перед upgrade всегда выполняется `dpkg --configure -a` (донастройка оборванного dpkg; если мёртв по-настоящему — упадёт с его текстом)
- ребут идёт по одному хосту (`throttle: 1`), а не всем флотом одновременно

## `playbooks/cleanup.yml`

- `journal_max_age: 14d` (String), `journal_max_size: 500M` (String)
- `docker_prune: false` -> `true` чтобы чистить docker: `docker image prune -a`, `network prune`, `builder prune` (неиспользуемые образы, сети и build cache; скипается если докера нет; Enum). Остановленные контейнеры **не** удаляются — раньше `docker system prune` сносил и намеренно остановленные ноды, и бэкап-контейнеры после move/adopt
- `docker_prune_volumes: false` -> `true` чтобы чистить и volumes (опасно; Enum)
- `docker_prune_until: ""` (String, например `72h` — prune только старше; пусто — без фильтра)
- `apt_clean: true` (Enum)
- `cleanup_confirmed: false` -> `true` чтобы разрешить снос docker volumes (без него чистятся только образы, сети и build cache)

```json
{
  "target": "stage"
}
```

Только journal без докера:

```json
{
  "target": "vps-prod-01",
  "docker_prune": false,
  "journal_max_size": "200M"
}
```

## `playbooks/reboot.yml` (на несколько хостов — только с `reboot_confirmed=true`)

- `reboot_msg: "Reboot via Semaphore"`
- `reboot_timeout: 600` (секунд ждать возвращения хоста)
- `reboot_connect_timeout: 30`
- `reboot_pre_delay: 5`, `reboot_post_delay: 15`
- `reboot_only_if_required: false` -> `true` чтобы пропустить ребут без `/var/run/reboot-required` (для расписаний; Enum)
- `reboot_confirmed: false` -> `true` чтобы разрешить ребут сразу нескольких хостов (для одного не нужен; Enum)

Перезагрузка через Semaphore Extra vars:

```json
{
  "target": "vps-prod-01"
}
```

Группа с увеличенным таймаутом:

```json
{
  "target": "prod",
  "reboot_timeout": 900
}
```
