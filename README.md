# Ansible for Semaphore UI

Публичный template-репозиторий для управления несколькими VPS (Debian)
через Semaphore UI: плоские плейбуки + compose для Semaphore
+ сидинг task templates одной командой (`00-bootstrap` → `Run`).

Принципы:
- Inventory ведётся в UI Semaphore, в репо его нет.
- Секреты ведутся в UI Semaphore (Key Store / Environment), в репо их нет.
- Плейбуки универсальные: хост/группа подставляется через `target` или `Limit`.
- `roles/` пока не заводим, только плоские `playbooks/`.

## Quickstart

Репо публичное: плейбуки + шаблоны в одном месте. Шаблоны лежат как файл
`semaphore/templates.json` и заливаются в UI скриптом (идемпотентно, по имени):

```bash
git clone <this-repo> && cd ansible
cp .env.example .env && nano .env  # свои пароли + ключ шифрования
docker compose up -d               # http://localhost:3000
```

Полный гайд на 10 минут — [docs/QUICKSTART.md](docs/QUICKSTART.md):
проект, ключ, репозиторий, inventory `main`, группа `empty`, токен,
шаблон `00-bootstrap` → `Run` → 7 шаблонов + тестовый `ping`.
Там же: обновление шаблонов, troubleshooting и FAQ.

## Структура

```text
ansible.cfg
requirements.yml
compose.yml          # semaphore:latest + sqlite для чужого
.env.example         # свои креды -> .env (в git не коммитить)
playbooks/
  ping.yml       # проверка связи
  update.yml     # apt update + upgrade, опционально reboot
  base.yml       # timezone + base packages
  run_script.yml # запуск скриптов из scripts/
  run_cmd.yml    # произвольная команда
  reboot.yml     # перезагрузка хостов
  init.yml       # инит новой ноды: ключи + sshd
scripts/
  hello.sh               # пример shell-задачи
  semaphore_bootstrap.py # сидинг шаблонов в UI (stdlib, без pip)
semaphore/
  templates.json # источник правды: 7 шаблонов + survey_vars
docs/
  QUICKSTART.md  # полный гайд на 10 минут: compose + сидинг шаблонов
  gifs/          # 11 GIF 1920x1080 по шагам гайда (~46 МБ)
```

## Semaphore UI: подключение

1. Project -> Repositories: подключить этот репозиторий.
2. Key Store: добавить SSH-ключ (`ansible_user`, обычно `debian`/`admin`/`root`).
3. Inventory -> New Inventory:
   - тип static (простой INI), вести в UI.
   - Пример:

```ini
[prod]
vps-prod-01 ansible_host=203.0.113.10 ansible_user=debian ansible_port=22

[stage]
vps-stage-01 ansible_host=203.0.113.20 ansible_user=debian ansible_port=22
```

4. Environment -> New Environment:
   - `ANSIBLE_HOST_KEY_CHECKING=False` уже задан в `ansible.cfg`, дополнительно не нужен.
   - Секреты (пароли, токены) добавлять как JSON / Environment Variables.
5. Task Templates: не создавать вручную — они заливаются скриптом,
   см. [docs/QUICKSTART.md](docs/QUICKSTART.md) (шаг 8–9: `00-bootstrap` → `Run`).
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
- `base_packages` (Text: один пакет на строку или через запятую; дефолт `python3, sudo, curl, htop`)

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

`playbooks/reboot.yml` (без подтверждения — аккуратнее с `target=all`):
- `reboot_msg: "Reboot via Semaphore"`
- `reboot_timeout: 600` (секунд ждать возвращения хоста)
- `reboot_connect_timeout: 30`
- `reboot_pre_delay: 5`, `reboot_post_delay: 15`

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

`playbooks/init.yml` (инит новой ноды — первый прогон строго с `Limit` на одну тестовую ноду):
- `ssh_user: root` (String; юзер должен существовать)
- `ssh_keys` (Text, обязательно; один публичник на строку или через запятую; чужие ключи не трогаются)
- `sshd_permit_root_login: prohibit-password` (String)
- `sshd_pubkey_auth: "yes"`, `sshd_password_auth: "no"`, `sshd_permit_empty: "no"` (String)
- `skip_sshd: false` -> `true` чтобы добавить только ключи без правок sshd (для bootstrap по паролю; Enum)

Инит новой ноды: survey-поля `target=new-node-01`, `ssh_user=root`, `ssh_keys` (Text):
```
ssh-ed25519 AAAA... semaphore-ansible
```

Несколько ключей другому юзеру (`ssh_user=debian`, `ssh_keys` через запятую):
```
ssh-ed25519 AAAA... first, ssh-ed25519 BBBB... second
```

Bootstrap ноды где есть только пароль (Key Store типа Login With Password):
1. Добавить хост в inventory (`ansible_user: root`), Task Template `init` с парольным Key.
2. Этап 1 — только ключи: `{"target": "new-node-01", "ssh_user": "root", "ssh_keys": [...], "skip_sshd": true}`.
3. Вручную проверить новый ключ: `ssh -i ~/.ssh/semaphore-ansible root@IP`.
4. Этап 2 — сменить Key темплейта на SSH-ключ, прогнать без `skip_sshd` (hardening + reload + проверка связи уже по ключу).
5. Парольный Key для этой ноды больше не нужен — удалить/ротировать пароль.

## Локальная проверка

Требуется установленный `ansible` (например `pip install ansible-core`):

```bash
ansible-playbook --syntax-check playbooks/ping.yml
ansible-playbook --syntax-check playbooks/update.yml
ansible-playbook --syntax-check playbooks/base.yml
ansible-playbook --syntax-check playbooks/run_script.yml
ansible-playbook --syntax-check playbooks/run_cmd.yml
ansible-playbook --syntax-check playbooks/reboot.yml
ansible-playbook --syntax-check playbooks/init.yml
ansible-galaxy collection install -r requirements.yml
```
