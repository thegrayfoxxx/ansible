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

## `playbooks/update.yml`

- `apt_upgrade: dist` (или `safe`)
- `apt_autoremove: true`
- `apt_autoclean: true`
- `reboot_if_required: false` -> `true` для авторебута
- перед upgrade всегда выполняется `dpkg --configure -a` (донастройка оборванного dpkg; если мёртв по-настоящему — упадёт с его текстом)

## `playbooks/cleanup.yml`

- `journal_max_age: 14d` (String), `journal_max_size: 500M` (String)
- `docker_prune: true` (скипается если докера нет; Enum)
- `docker_prune_volumes: false` -> `true` чтобы чистить и volumes (опасно; Enum)
- `docker_prune_until: ""` (String, например `72h` — prune только старше; пусто — без фильтра)
- `apt_clean: true` (Enum)

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

## `playbooks/reboot.yml` (без подтверждения — аккуратнее с `target=all`)

- `reboot_msg: "Reboot via Semaphore"`
- `reboot_timeout: 600` (секунд ждать возвращения хоста)
- `reboot_connect_timeout: 30`
- `reboot_pre_delay: 5`, `reboot_post_delay: 15`
- `reboot_only_if_required: false` -> `true` чтобы пропустить ребут без `/var/run/reboot-required` (для расписаний; Enum)

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
