# Ansible for Semaphore UI

Публичный template-репозиторий для управления несколькими VPS (Debian)
через Semaphore UI: плоские плейбуки + compose для Semaphore
+ сидинг task templates одной командой (`update_templates` → `Run`).

Принципы:
- Inventory ведётся в UI Semaphore, в репо его нет.
- Секреты ведутся в UI Semaphore (Key Store / Environment), в репо их нет.
- Плейбуки универсальные: хост/группа подставляется через `target` или `Limit`.
- `roles/` пока не заводим, только плоские `playbooks/`.

## Quickstart

Репо публичное: плейбуки + шаблоны в одном месте. Шаблоны лежат как файл
`semaphore/templates.json` и заливаются в UI скриптом (идемпотентно, по имени).

Что получается в итоге:

![overview](https://github.com/thegrayfoxxx/ansible/releases/download/media-v1/00-overview.gif)

Два варианта установки:

```bash
# A — минимальный, без git (плейбуки Semaphore подтянет сам):
mkdir ansible-semaphore && cd ansible-semaphore
curl -O https://raw.githubusercontent.com/thegrayfoxxx/ansible/main/compose.yml
curl -O https://raw.githubusercontent.com/thegrayfoxxx/ansible/main/.env.example
cp .env.example .env && nano .env   # свои пароли + ключ шифрования
docker compose up -d                # http://localhost:3000
```

```bash
# B — полный, с git (код под рукой):
git clone https://github.com/thegrayfoxxx/ansible.git && cd ansible
cp .env.example .env && nano .env   # свои пароли + ключ шифрования
docker compose up -d                # http://localhost:3000
```

Полный гайд на 10 минут — [docs/QUICKSTART.md](docs/QUICKSTART.md):
проект, репозиторий, токен + `service_vars`, key store,
inventory `prod_inventory`, шаблон `update_templates` → `Run` → все шаблоны
+ тестовый `ping`. Там же: обновление шаблонов, troubleshooting и FAQ.

## Структура

```text
ansible.cfg
requirements.yml
compose.yml          # semaphore:v2.19.12 + sqlite для чужого
.env.example         # свои креды -> .env (в git не коммитить)
playbooks/
  ping.yml       # проверка связи
  update.yml     # apt update + upgrade, опционально reboot
  base.yml       # timezone + base packages
  run_script.yml # запуск скриптов из scripts/
  run_cmd.yml    # произвольная команда
  logs.yml       # просмотр логов: journal или файл, read-only
  reboot.yml     # перезагрузка хостов
  init_node.yml  # инит новой ноды: ключи + sshd
  firewall.yml   # ufw: правила + опциональное включение
  fail2ban.yml   # fail2ban + sshd jail (systemd backend)
  docker.yml     # установка Docker Engine + compose plugin
  bbr.yml        # TCP BBR + fq (выкл — откат на cubic + fq_codel)
  cleanup.yml    # чистка диска: apt, journal, docker prune
  rsyslog.yml    # rsyslog + опциональный форвардинг
scripts/
  hello.sh               # пример shell-задачи
  semaphore_bootstrap.py # сидинг шаблонов в UI (stdlib, без pip)
semaphore/
  templates.json # источник правды: 15 шаблонов + survey_vars + views (Run, System, Security, Observability, Service)
docs/
  QUICKSTART.md  # полный гайд на 10 минут: compose + сидинг шаблонов
  # GIF по шагам гайда (1920x1080) лежат в релизе media-v1, не в git
```

## Semaphore UI: подключение

1. Project -> Repositories: подключить этот репозиторий (`Access Key: None`, репо публичное).
2. Key Store: добавить SSH-ключ (`ansible_user`, обычно `debian`/`admin`/`root`).
3. Inventory -> New Inventory с именем `prod_inventory`:
   - тип static (простой INI), вести в UI (`[prod]`/`[stage]` внутри — это Ansible-группы, не путать с именем inventory и группой `prod_vars`).
   - Пример:

```ini
[prod]
vps-prod-01 ansible_host=203.0.113.10 ansible_user=debian ansible_port=22

[stage]
vps-stage-01 ansible_host=203.0.113.20 ansible_user=debian ansible_port=22
```

4. Environment: вручную только `service_vars` с секретом `SEMAPHORE_TOKEN`
   (группу `prod_vars` и остальные из `semaphore/templates.json` создаст скрипт сидинга).
   - `ANSIBLE_HOST_KEY_CHECKING=False` уже задан в `ansible.cfg`, дополнительно не нужен.
   - Остальные секреты (пароли, токены) добавлять как JSON / Environment Variables.
5. Task Templates: не создавать вручную — они заливаются скриптом,
   см. [docs/QUICKSTART.md](docs/QUICKSTART.md) (шаг 9–10: `update_templates` → `Run`).
   Соответствие шаблонов плейбукам лежит в `semaphore/templates.json`.

## Универсальный target

Все плейбуки используют:

```yaml
hosts: "{{ target | default('all') }}"
```

Варианты запуска:
- Всё: ничего не указывать (`target=all` по умолчанию).
- Группа: в Task Template поле `Limit = prod` или Extra vars `{"target": "prod"}`.
- Один хост: `Limit = vps-prod-01` или `{"target": "vps-prod-01"}`.

`Limit` и `target` можно комбинировать, приоритет у `Limit` (стандартный ansible `--limit`).

## Переменные и типы survey-полей в Semaphore UI

Переменные задаются через Survey variables шаблона (типы String, Integer, Text, Enum, Secret) и уезжают
в Ansible как `--extra-vars`. Важно: списки и словари приезжают **строками**, плейбуки сами приводят их
к нужному типу — оба способа ввода работают:

- **Способ 1 (рекомендуемый): Text-поле, по одному элементу на строку.**
  ```
  ssh-ed25519 AAAA... first
  ssh-ed25519 BBBB... second
  ```
- **Способ 2: String-поле, через запятую.**
  ```
  ssh-ed25519 AAAA... first, ssh-ed25519 BBBB... second
  ```

Словари (`*_env`) — Text-поле с JSON-объектом: `{"FOO": "1"}`.
Bool'ы (`use_shell`, `allow_fail`, `skip_sshd`...) — Enum со значениями `true`/`false` или String.
Числа (`reboot_timeout`, `cmd_tail`) — Integer.

`playbooks/update.yml`:
- `apt_upgrade: dist` (или `safe`)
- `apt_autoremove: true`
- `apt_autoclean: true`
- `reboot_if_required: false` -> `true` для авторебута

`playbooks/base.yml`:
- `base_timezone: Etc/UTC` (String)
- `base_packages` (Text: один пакет на строку или через запятую; дефолт `python3, curl, btop, ufw`)

`playbooks/run_script.yml`:
- `script_src: scripts/hello.sh` (String; обязательно, путь от корня репо, резолвится через `playbook_dir`)
- `script_args: ""` (String, опционально)
- `script_env` (Text с JSON-объектом, опционально; например `{"FOO": "1"}`)
- `script_become: true` -> `false` чтобы запустить без sudo (Enum)

Передавать через survey-поля шаблона (ниже те же значения показаны JSON'ом для краткости —
в UI каждое поле заполняется отдельно; raw JSON работает через API/schedules):

```json
{
  "target": "stage",
  "base_timezone": "Europe/Berlin"
}
```

Запуск скрипта через Semaphore Extra vars:

```json
{
  "target": "stage",
  "script_src": "scripts/hello.sh"
}
```

С аргументами, env и без sudo:

```json
{
  "target": "vps-prod-01",
  "script_src": "scripts/hello.sh",
  "script_args": "--foo bar",
  "script_env": {"FOO": "1"},
  "script_become": false
}
```

`playbooks/run_cmd.yml`:
- `cmd: "df -h"` (String, обязательно)
- `use_shell: true` -> `false` для строгого `command` без shell (Enum)
- `cmd_chdir: ""` (String, опционально, рабочая папка)
- `cmd_env` (Text с JSON-объектом, опционально; например `{"FOO": "1"}`)
- `cmd_become: true` -> `false` чтобы запустить без sudo (Enum)
- `cmd_tail: 0` (Integer, опционально, показать только последние N строк stdout/stderr)
- `allow_fail: false` -> `true` чтобы не фейлить хост при rc != 0 (rc виден в выводе; Enum)

Запуск команды через Semaphore Extra vars:

```json
{
  "target": "vps-prod-01",
  "cmd": "df -h"
}
```

С shell-пайпом, chdir, env и без sudo:

```json
{
  "target": "stage",
  "cmd": "ls -la /opt | grep app",
  "use_shell": true,
  "cmd_chdir": "/opt",
  "cmd_env": {"FOO": "1"},
  "cmd_become": false
}
```

Обновление docker-контейнеров с коротким хвостом лога:

```json
{
  "target": "prod",
  "cmd": "cd /opt/app && docker compose pull && docker compose up -d",
  "cmd_tail": 20
}
```

По гетерогенным хостам без фейла всего таска (rc виден в выводе):

```json
{
  "target": "all",
  "cmd": "cd /opt/app && docker compose up -d",
  "allow_fail": true,
  "cmd_tail": 15
}
```

`playbooks/logs.yml` (read-only, дефолт `target=all` безопасен):
- `log_source: journal` -> `file` для хвоста файла (Enum)
- `log_file: /var/log/syslog` (только для `source=file`, String)
- `log_unit: ""` (только journal, например `ssh`; пусто — все юниты)
- `log_priority: info` (только journal: уровень и срочнее; Enum)
- `log_since: "-1h"` (только journal: `-30min`, `today`, `2026-10-01`)
- `log_lines: 200` (Integer, guard `1..2000`)
- `log_grep: ""` (String, regex-фильтр, например `error|fail`)
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

`playbooks/reboot.yml` (без подтверждения — аккуратнее с `target=all`):
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

`playbooks/init_node.yml` (инит новой ноды — первый прогон строго с `Limit` на одну тестовую ноду):
- `ssh_user: root` (String; юзер должен существовать)
- `ssh_keys` (Text, обязательно; один публичник на строку или через запятую; чужие ключи не трогаются)
- `sshd_permit_root_login: prohibit-password` (String)
- `sshd_pubkey_auth: "yes"`, `sshd_password_auth: "no"`, `sshd_permit_empty: "no"` (String)
- `skip_sshd: false` -> `true` чтобы добавить только ключи без правок sshd (для bootstrap по паролю; Enum)
- `ansible_user`, `ansible_password` (Secret), `ansible_port` (Integer) — кастомные креды подключения из полей шаблона, бьют креды инвентаря (все optional, без дефолтов; пусто — используются инвентарные). Приватный ключ через поля не передать — кастомные ключи по-прежнему через Key Store

Инит новой ноды: survey-поля `target=new-node-01`, `ssh_user=root`, `ssh_keys` (Text):
```
ssh-ed25519 AAAA... semaphore-ansible
```

Несколько ключей другому юзеру (`ssh_user=debian`, `ssh_keys` через запятую):
```
ssh-ed25519 AAAA... first, ssh-ed25519 BBBB... second
```

Bootstrap ноды где есть только пароль — способ 1 (рекомендуемый, без смены Key в инвентаре):
1. Добавить хост в inventory как обычно (SSH-ключ в `User Credentials`).
2. Этап 1 — только ключи, креды из полей шаблона: `{"target": "new-node-01", "ssh_user": "root", "ssh_keys": [...], "skip_sshd": true, "ansible_user": "root", "ansible_password": "<пароль>"}`.
3. Вручную проверить новый ключ: `ssh -i ~/.ssh/semaphore-ansible root@IP`.
4. Этап 2 — те же поля без `ansible_password` (уже по ключу из инвентаря): прогнать без `skip_sshd` (hardening + reload + проверка связи).

Способ 2 (старый, Key Store типа Login With Password):
1. Добавить хост в inventory (`ansible_user: root`), Task Template `init_node` с парольным Key.
2. Этап 1 — только ключи: `{"target": "new-node-01", "ssh_user": "root", "ssh_keys": [...], "skip_sshd": true}`.
3. Вручную проверить новый ключ: `ssh -i ~/.ssh/semaphore-ansible root@IP`.
4. Этап 2 — сменить Key темплейта на SSH-ключ, прогнать без `skip_sshd` (hardening + reload + проверка связи уже по ключу).
5. Парольный Key для этой ноды больше не нужен — удалить/ротировать пароль.

`playbooks/firewall.yml` (первый прогон строго с `Limit` на одну тестовую ноду):
- `fw_allow` (Text, одно правило на строку: `22/tcp`, `80/tcp`)
- `fw_enable: false` -> `true` чтобы ВКЛЮЧИТЬ ufw (guard не даст включить без `22/tcp` в списке)

Только правила, без включения:

```json
{
  "target": "vps-stage-01",
  "fw_allow": "22/tcp\n80/tcp\n443/tcp"
}
```

Включение (после проверки правил выше):

```json
{
  "target": "vps-stage-01",
  "fw_allow": "22/tcp\n80/tcp\n443/tcp",
  "fw_enable": true
}
```

`playbooks/fail2ban.yml` (первый прогон строго с `Limit` на одну тестовую ноду):
- `fail2ban_enabled: true` -> `false` чтобы остановить и отключить сервис (Enum)
- `fail2ban_bantime: 1d`, `fail2ban_maxretry: 5` (findtime зафиксирован `1h`)
- `fail2ban_ignoreip` (String, через пробел; свои IP дописать, иначе возможен самобан)
- backend `systemd` (читает journal, не зависит от файловых логов), banaction дефолтный

```json
{
  "target": "vps-stage-01",
  "fail2ban_ignoreip": "127.0.0.1/8 203.0.113.5"
}
```

`playbooks/docker.yml` (только Debian):
- `docker_users` (Text: юзеры в группу docker, один на строку или через запятую)
- `docker_verify: true` -> `false` чтобы пропустить `hello-world`
- `docker_version: ""` (String, например `5:27.*` — пин Engine+CLI; пусто — latest; `update` с dist-апгрейдом пин перетрёт)

```json
{
  "target": "stage",
  "docker_users": "debian"
}
```

`playbooks/bbr.yml` (перезагрузка не нужна, применяется сразу):
- `bbr_enabled: true` -> `false` чтобы откатить на `cubic + fq_codel` (Enum)
- legacy `/etc/sysctl.d/10-bbr-fq_codel.conf` от `deb_scripts` удаляется, чтобы не было двух файлов на одни ключи
- на контейнерных VPS (OpenVZ/LXC) без своего ядра упадёт — там BBR включается на хосте провайдера

```json
{
  "target": "all",
  "bbr_enabled": true
}
```

`playbooks/cleanup.yml`:
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

`playbooks/rsyslog.yml`:
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

## Локальная проверка

Требуется установленный `ansible` (например `pip install ansible-core`):

```bash
ansible-playbook --syntax-check playbooks/ping.yml
ansible-playbook --syntax-check playbooks/update.yml
ansible-playbook --syntax-check playbooks/base.yml
ansible-playbook --syntax-check playbooks/run_script.yml
ansible-playbook --syntax-check playbooks/run_cmd.yml
ansible-playbook --syntax-check playbooks/logs.yml
ansible-playbook --syntax-check playbooks/reboot.yml
ansible-playbook --syntax-check playbooks/init_node.yml
ansible-playbook --syntax-check playbooks/firewall.yml
ansible-playbook --syntax-check playbooks/fail2ban.yml
ansible-playbook --syntax-check playbooks/docker.yml
ansible-playbook --syntax-check playbooks/bbr.yml
ansible-playbook --syntax-check playbooks/cleanup.yml
ansible-playbook --syntax-check playbooks/rsyslog.yml
ansible-galaxy collection install -r requirements.yml
```
