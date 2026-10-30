# Ansible for Semaphore UI

Публичный template-репозиторий для управления несколькими VPS (Debian)
через Semaphore UI: плоские плейбуки + compose для Semaphore
+ сидинг task templates одной командой (`update_templates` → `Run`).

Принципы:
- Inventory ведётся в UI Semaphore, в репо его нет.
- Секреты ведутся в UI Semaphore (Key Store / Environment), в репо их нет.
- Плейбуки универсальные: хост/группа подставляется через `target` или `Limit`.
- Точки входа — плоские `playbooks/`; общая логика Remnawave вынесена в `roles/remnanode` и `roles/remnawave_panel`.
- Новый шаблон → подраздел в доке своей зоны (см. Доки ниже), README не трогаем.

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
compose.yml          # semaphore:v2.19.12 + sqlite; UI на 127.0.0.1 (SEMAPHORE_BIND)
.env.example         # свои креды -> .env (в git не коммитить)
playbooks/           # плоские плейбуки, все требуют явный target
roles/
  remnanode/         # discovery/render/up ноды Remnawave (используется плейбуками remnawave_*)
  remnawave_panel/   # API панели: health, auth, keygen
scripts/
  hello.sh               # пример shell-задачи
  syntax_check.sh        # --syntax-check всех плейбуков (локально и в CI)
  diagnostics.sh         # свои пробы ноды (facts/DNS/DPI/speed, без внешних тянучек)
  semaphore_bootstrap.py # сидинг шаблонов в UI (stdlib, без pip)
templates/
  crowdsec/          # j2 для ноды: compose.yml, .env, acquis.yaml, конфиг баунсера (upstream + iptables_chains)
  remnawave/         # j2 для ноды: compose.yml, .env, logrotate
  nginx/             # j2: compose fallback/proxy, .env, конфиг nginx_proxy
files/
  nginx/             # конфиг заглушки fallback (envsubst-шаблон nginx)
.github/workflows/   # CI: yamllint, ansible-lint, shellcheck, syntax-check
semaphore/
  templates.json # источник правды: шаблоны + survey_vars + views (см. Доки)
docs/
  QUICKSTART.md      # полный гайд на 10 минут: compose + сидинг шаблонов
  semaphore-ui.md    # подключение Semaphore: проект, репозиторий, токен, inventory
  run.md             # ping, run_cmd, run_script (вкладка Run)
  observability.md   # logs, health, diagnostics, rsyslog
  diagnostics.md     # гибридная диагностика: свои пробы + pinned upstream
  system.md          # base, docker, bbr, ipv6, update, cleanup, reboot
  security.md        # init_node, firewall, fail2ban, модель доверия Semaphore
  crowdsec.md        # register/node/update/unregister/adopt/move/purge
  remnawave.md       # node_add/deploy/config/update/move/remove/purge + группа remnawave_vars
  nginx.md           # fallback-заглушка, nginx_proxy, LE-серт, adopt/move/update/purge
  dev.md             # локальная проверка плейбуков
  # GIF по шагам гайда (1920x1080) лежат в релизе media-v1, не в git
```

## Подключение Semaphore UI

Коротко: репозиторий (`Access Key: None`) → SSH-ключ в Key Store →
inventory `prod_inventory` → группа `service_vars` с `SEMAPHORE_TOKEN` →
`update_templates` → `Run`. Подробный чеклист — [docs/semaphore-ui.md](docs/semaphore-ui.md),
гайд с картинками — [docs/QUICKSTART.md](docs/QUICKSTART.md).

## Универсальный target

Все плейбуки требуют явный `target` (дефолта нет — без него задача падает с ошибкой, а не едет на весь флот):

```yaml
hosts: "{{ target }}"
```

Варианты запуска (поле обязательно в диалоге `Run`):
- Всё (осознанно): `all`.
- Группа: в Task Template поле `Limit = prod` или Extra vars `{"target": "prod"}`.
- Один хост: `Limit = vps-prod-01` или `{"target": "vps-prod-01"}`.
- Исключить: `Limit = all:!de5` или Extra vars `{"target": "all:!de5"}` (все, кроме хоста; так же `de1,de2` — несколько через запятую).

`Limit` и `target` можно комбинировать, приоритет у `Limit` (стандартный ansible `--limit`).

## Survey-переменные: основы

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

В доках ниже те же значения показаны JSON'ом для краткости —
в UI каждое поле заполняется отдельно; raw JSON работает через API/schedules.

## Доки

- [docs/QUICKSTART.md](docs/QUICKSTART.md) — гайд на 10 минут: стенд + сидинг + тестовый ping.
- [docs/semaphore-ui.md](docs/semaphore-ui.md) — чеклист подключения.
- [docs/run.md](docs/run.md) — ping, run_cmd, run_script.
- [docs/observability.md](docs/observability.md) — logs, health, diagnostics, rsyslog.
- [docs/system.md](docs/system.md) — base, docker, bbr, ipv6, update, cleanup, reboot.
- [docs/security.md](docs/security.md) — init_node, firewall, fail2ban.
- [docs/crowdsec.md](docs/crowdsec.md) — register/node/update/unregister.
- [docs/remnawave.md](docs/remnawave.md) — node_add/update + группа `remnawave_vars`.
- [docs/nginx.md](docs/nginx.md) — Selfsteal-заглушка + LE-серт.
- [docs/dev.md](docs/dev.md) — локальная проверка плейбуков.
