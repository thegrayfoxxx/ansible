# Quickstart

Поднимите свой Semaphore и за 10 минут получите все task templates из этого репо.
В конце у вас будет: работающий Semaphore в Docker + готовые шаблоны
(например `ping` и `run_cmd` — полный список живёт в `semaphore/templates.json`
и пополняется)
и успешный тестовый прогон `ping`.

Проверено на `semaphoreui/semaphore:v2.19.12`.

## Что понадобится

- `docker compose` и доступ в интернет (Docker Hub + ваш git-хостинг).
- `git` и `python3` — только для полного варианта установки и запасного пути без UI.
- Ваши хосты и SSH-ключ — для сидинга (шаг 10) хватит `None`, для тестового `ping` (шаг 11) нужен реальный ключ в inventory.

## Шаг 0. Запуск

**Вариант A — минимальный, без git** (плейбуки и шаблоны Semaphore
подтянет сам из GitHub, локальная копия репо не нужна):

```bash
mkdir ansible-semaphore && cd ansible-semaphore
curl -O https://raw.githubusercontent.com/thegrayfoxxx/ansible/main/compose.yml
curl -O https://raw.githubusercontent.com/thegrayfoxxx/ansible/main/.env.example
cp .env.example .env && nano .env   # свои пароли + ключ шифрования
docker compose up -d                # http://localhost:3000
```

**Вариант B — полный, с git** (код под рукой: локальные прогоны,
правки, контрибьюшн):

```bash
git clone https://github.com/thegrayfoxxx/ansible.git && cd ansible
cp .env.example .env && nano .env   # свои пароли + ключ шифрования
docker compose up -d                # http://localhost:3000
```

Откройте `.env` и задайте три вещи:

| Переменная | Что это |
|---|---|
| `SEMAPHORE_ADMIN_PASSWORD` | Пароль админа (по умолчанию `changeme` — смените) |
| `SEMAPHORE_ACCESS_KEY_ENCRYPTION` | Ключ шифрования секретов в БД, сгенерируйте: `head -c32 /dev/urandom \| base64` |
| `SEMAPHORE_PORT` | Внешний порт UI (по умолчанию `3000`; внутренний всегда 3000). Если меняете — подставляйте свой порт вместо `3000` во всех командах и URL ниже |

Файл `.env` уже в `.gitignore` — в репозиторий он не попадёт.

Проверка: `curl -s http://localhost:3000/api/ping` должен вернуть `pong`,
а в браузере открыться страница логина `http://localhost:3000`.

Дальше всё в браузере: логин → проект → репозиторий → API-токен →
группа `service_vars` → key store → inventory `prod_inventory` →
приложение Python → шаблон `update_templates` → `Run`.
Подробности — ниже по шагам.

## Шаг 1. Логин

Зайдите как `admin` с паролем из `.env` — откроется страница логина
`http://localhost:3000`.

![логин](https://github.com/thegrayfoxxx/ansible/releases/download/media-v1/01-login.gif)

## Шаг 2. Создание проекта

Пустой инстанс сразу предложит создать проект — назовите его `ansible`
и нажмите `Create`.

Как узнать ID проекта: откройте проект — цифра в адресе
(`http://localhost:3000/project/1/...`) и есть ID. У первого проекта это `1`,
он понадобится на шаге 10.

![создание проекта](https://github.com/thegrayfoxxx/ansible/releases/download/media-v1/02-new-project.gif)

## Шаг 3. Repository

`Repositories -> New Repository`:

- `Name`: `ansible` — имя важно, его ищет `semaphore/templates.json`;
- `URL or path`: `https://github.com/thegrayfoxxx/ansible.git`
  (или URL своего форка);
- `Branch / Tag`: `main`;
- `Access Key`: `None` (репозиторий публичный).

Нажмите `Create`. Репозиторий появится в списке — клонирование произойдёт
при первом запуске задачи, сейчас проверять нечего.

![создание репозитория](https://github.com/thegrayfoxxx/ansible/releases/download/media-v1/03-new-repository.gif)

## Шаг 4. API-токен

Меню пользователя справа сверху -> `API Tokens -> New Token`:
имя например `bootstrap`, `Expires: Never`, `Create`.
**Токен показывается один раз — скопируйте его сразу.**
Если потеряли — удалите и выпустите новый, это штатно.

> Безопасность: токены Semaphore — пользовательские, без скоупа на проект.
> Чей токен лежит в секретах — теми правами обладают задачи. Не кладите сюда
> токен админа «на всякий случай»: достаточно пользователя с ролью не выше
> `manager` на этот проект. В логах задач токен не светится (скрипт его
> не печатает), но в рантайме он доступен окружению задачи.

![выпуск API-токена](https://github.com/thegrayfoxxx/ansible/releases/download/media-v1/04-api-token.gif)

## Шаг 5. Variable Group service_vars

Группу `prod_vars` (и любые другие из `semaphore/templates.json`) скрипт сидинга
создаёт сам пустыми при первом `Run` — руками делать ничего не надо,
секреты доложите туда позже через UI по мере нужды. Вручную создаётся только
`service_vars` — ей нужен токен с шага 4, который знаете только вы.

Положите токен в секрет, чтобы не вводить его при каждом `Run`:
`Variable Groups -> New Group` с именем `service_vars`, вкладка `Secrets`
-> добавить секрет типа `env`: имя `SEMAPHORE_TOKEN`, значение — ваш токен,
`Save`. Группа прицепится к `update_templates` автоматически при сидинге
(она так и записана в `semaphore/templates.json`).

![создание service_vars](https://github.com/thegrayfoxxx/ansible/releases/download/media-v1/05-new-service-vars.gif)

## Шаг 6. Key Store

Откройте `Key Store`. Встроенный ключ `None` уже на месте — его достаточно
для сидинга (шаг 10). Свой SSH-ключ для доступа на VPS добавьте здесь же
через `New Key` (понадобится на шаге 7 как `User Credentials`, без него
тестовый `ping` на шаге 11 упадёт с `unreachable`).

![key store](https://github.com/thegrayfoxxx/ansible/releases/download/media-v1/06-keystore.gif)

## Шаг 7. Inventory prod_inventory

`Inventory -> New Inventory -> Ansible Inventory`:

- `Name`: `prod_inventory` — имя важно, его ищет `semaphore/templates.json`;
- `Type`: `Static`;
- `User Credentials`: ваш SSH-ключ с шага 6 (`None` хватит только для сидинга
  на шаге 10, для тестового `ping` на шаге 11 нужен реальный ключ);
- в редактор вставьте свои хосты в INI-формате, например:

```ini
[stage]
vps-stage-01 ansible_host=203.0.113.20 ansible_user=debian ansible_port=22
```

Имена `[stage]` / `[prod]` внутри редактора — это Ansible-группы хостов,
не путать с именем самого inventory (`prod_inventory`) и группой переменных
`prod_vars`.

Нажмите `Create`. Должна появиться строка `prod_inventory / static`.

![создание inventory](https://github.com/thegrayfoxxx/ansible/releases/download/media-v1/07-new-inventory.gif)

## Шаг 8. Включите приложение Python

Откройте `Task Templates -> New template`. Если в меню есть только
`Ansible Playbook`, `Bash Script` и остальные, а `Python Script` нет —
это нормально: приложение выключено по умолчанию.

В том же меню выберите `Applications` — откроется страница приложений.
Найдите строку `Python Script` и включите тумблер. Вернитесь в
`Task Templates -> New template` — пункт `Python Script` появится.

![включение Python](https://github.com/thegrayfoxxx/ansible/releases/download/media-v1/08-enable-python.gif)

## Шаг 9. Шаблон update_templates

`Task Templates -> New template -> Python Script`, заполните:

- `Name`: `update_templates`;
- `Repository`: `ansible`;
- `Script Filename`: `scripts/semaphore_bootstrap.py`;
- `Variable Groups`: `service_vars` — **обязательно**, иначе скрипту неоткуда взять токен;
- `Survey Variables` (кнопка `+ Add variable`, каждого по одному):
  - `Name: token`, `Title: API Token`, `Type: Secret`, **без** галочки `Required`
    (пустое поле — токен берётся из секрета `SEMAPHORE_TOKEN`;
    заполненное вручную — разовый override);
  - `Name: project_id`, `Title: Project ID`, `Type: String` (по умолчанию),
    галочка `Required`.

Нажмите `Create`. Это единственный шаблон, который создаётся руками, —
остальные создаст он сам.

![создание update_templates](https://github.com/thegrayfoxxx/ansible/releases/download/media-v1/09-create-bootstrap.gif)

## Шаг 10. Run — сидинг шаблонов

Откройте `update_templates -> Run`, введите `project_id`
с шага 2 (например `1`); поле `token` оставьте пустым — возьмётся из секрета.
Нажмите `Run`. (На видео ниже показан вариант с ручным вводом токена —
это разовый override, он тоже работает.)

Успешный лог заканчивается строкой вида:

```text
[update] ping (id=1, playbooks/ping.yml)
...
done: created=7 updated=0 unchanged=0 dry_run=False
```

![запуск update_templates](https://github.com/thegrayfoxxx/ansible/releases/download/media-v1/10-run-bootstrap.gif)

(при первом запуске — все `created`, при повторных — все `updated`).
В `Task Templates` теперь все шаблоны из `semaphore/templates.json`
(например `ping` и `run_cmd`, плюс служебный `update_templates`) —
у всех inventory `prod_inventory`, репозиторий `ansible`, группа `prod_vars`.

Так выглядит страница групп после сидинга (`prod_vars` создана скриптом):

![группы после сидинга](https://github.com/thegrayfoxxx/ansible/releases/download/media-v1/11-env-group.gif)

Повторный `Run` — это и есть обновление: скрипт сверяет записи по имени,
создаёт недостающие (`POST`) и обновляет изменившиеся (`PUT`),
включая самого себя. После `git pull` с новыми шаблонами
просто нажмите `Run` ещё раз.

Вкладки (Views): шаблоны раскладываются по вкладкам согласно полю `view`
в `semaphore/templates.json` (`Base`, `Ad-hoc`, `Onboarding`, `Service`).
Недостающие вкладки скрипт создаёт сам. Новую вкладку завести так:
добавить `"view": "Новое имя"` нужным шаблонам в JSON и нажать `Run`.

Запасной путь без UI (тот же скрипт локально, нужен только `python3`
и клон репозитория — вариант установки B):

```bash
SEMAPHORE_URL=http://localhost:3000/api SEMAPHORE_TOKEN=xxx SEMAPHORE_PROJECT_ID=1 \
  python3 scripts/semaphore_bootstrap.py --dry-run   # что изменится
SEMAPHORE_URL=http://localhost:3000/api SEMAPHORE_TOKEN=xxx SEMAPHORE_PROJECT_ID=1 \
  python3 scripts/semaphore_bootstrap.py              # применить
```

## Шаг 11. Проверка: тестовый ping

Требуется inventory `prod_inventory` с реальным SSH-ключом (см. шаг 7) —
с `None` в `User Credentials` хосты будут `unreachable`.

`ping -> Run`: поле `Target` уже предзаполнено дефолтом (`all`) —
можно оставить как есть или ввести группу/хост из своего inventory
(например `stage`). `Run`. Успех — `ok=1 unreachable=0 failed=0` в выводе.

![запуск ping](https://github.com/thegrayfoxxx/ansible/releases/download/media-v1/12-run-ping.gif)

Готово — стенд рабочий. Дальше смотрите `README.md`: описание переменных
и survey-полей каждого плейбука.

> Осторожно с `init_node` и `reboot`: первый прогон `init_node` — строго с `Limit`
> на одну тестовую ноду (подробности в `README.md`), а `reboot` не спрашивает
> подтверждения — не запускайте его на `all` без нужды.

## Обновление шаблонов

> Миграция со старых имен: раньше были inventory `main`, группа `prod`,
> `service-secrets`, шаблоны `update-templates` и `init`. Скрипт ищет строго
> `prod_inventory`, `prod_vars`, `service_vars`, `update_templates`
> и `init_node` — старые записи он не переименует сам: проще переименовать
> шаблоны в UI и нажать `Run` (история задач сохранится), группы
> и inventory создать с новыми именами (шаги 5 и 7, `prod_vars` создастся
> сам при `Run`), а старые дубли удалить в UI руками. Скрипт лишнее не удаляет.

1. Заберите свежие `playbooks/` и `semaphore/templates.json`: вариант B —
   `git pull`, вариант A — Semaphore сам подтянет свежий код репозитория
   при запуске (репозиторий-то внешний);
2. `Run` на `update_templates` — шаблоны обновляются;
3. ничего лишнего скрипт не удаляет: переименованный шаблон оставит старый
   дубль — удалите его в UI руками.

## Troubleshooting

| Симптом | Причина и лечение |
|---|---|
| `Inventory "prod_inventory" not found in project. Known: ...` | В проекте нет inventory с таким именем. Создайте с именем из `semaphore/templates.json` (раздел `defaults`) или поправьте JSON под свои имена и перезапустите задачу |
| `Repository "ansible" not found` | То же самое для репозитория |
| Задача `update_templates` падает на клонировании репозитория | Проверьте URL репозитория: репозиторий публичный, `Access Key` должен быть `None` |
| В `New template` нет `Python Script` | Включите приложение на странице `Applications` (шаг 8) |
| `Environment "service_vars" not found in project. Known: ...` | Не создана группа из шага 5. Создайте `service_vars` с секретом `SEMAPHORE_TOKEN` и перезапустите задачу (уже созданное не сломается — скрипт докатит остаток) |
| Потеряли API-токен | Токены не показываются повторно: удалите старый, выпустите новый **и обновите секрет `SEMAPHORE_TOKEN` в группе `service_vars`** |
| `PUT .../templates/N -> HTTP 400` на старой версии скрипта | Обновите `scripts/semaphore_bootstrap.py` (`git pull`): свежий скрипт передаёт `id` в теле `PUT`, этого требует API |

## FAQ

- **Почему не Terraform-провайдер?** Официальный провайдер не умеет
  `text`-переменные (а у нас `ssh_keys`, `*_env` — именно `text`) и тянет
  `tfstate`. API-скрипт на stdlib проще для чужого человека.
- **Можно ли хранить inventory в репозитории?** Да, но тогда секреты
  соединений уедут в git. Принцип этого репо: inventory и секреты живут
  в UI, в git их нет.
- **sqlite vs postgres?** В `compose.yml` — sqlite: один контейнер,
  годится для homelab и демо. Бекап — копией volume `semaphore-data`
  при остановленном контейнере. Для продакшна переключитесь на postgres —
  шаблоны и скрипт менять не нужно.
