# Вкладка Security: доступ и защита

## `playbooks/init_node.yml` (инит новой ноды — строго один хост за прогон, enforced плейбуком)

- `ssh_user: root` (String; юзер должен существовать)
- `ssh_keys` (Text, обязательно; один публичник на строку или через запятую; чужие ключи не трогаются). Запятая считается разделителем только перед типом ключа (`ssh-*`, `ecdsa-*`, `sk-*`), поэтому `from="10.0.0.1,10.0.0.2" ssh-ed25519 ...` не ломается; ключи с опциями (`restrict,command=...`) передавай по одному на строку
- `sshd_permit_root_login: prohibit-password` (String)
- `sshd_pubkey_auth: "yes"`, `sshd_password_auth: "no"`, `sshd_permit_empty: "no"` (String)
- `init_node_allow_user_mismatch: false` -> `true` — разрешить отключение паролей, когда подключение идёт по паролю под другим пользователем, чем `ssh_user` (по умолчанию плейбук отказывается: после reload войти будет нельзя)
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

Как применяется hardening:

- если `sshd_config` подключает `sshd_config.d/*.conf` (Debian 12+, Ubuntu 22.04+), настройки пишутся в `/etc/ssh/sshd_config.d/00-ansible.conf`. У sshd побеждает первое найденное значение, а cloud-init кладёт `50-cloud-init.conf` с `PasswordAuthentication yes` — правка самого `sshd_config` в этом случае не действует;
- без `Include` — по-старому, `lineinfile` в `sshd_config`;
- после записи весь конфиг проверяется `sshd -t` (при ошибке drop-in откатывается), после reload эффективные значения сверяются с `sshd -T`;
- перед проверкой связи соединение сбрасывается (`meta: reset_connection`), иначе проверка шла через открытый ControlMaster-сокет и проходила даже со сломанным логином.

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

## `playbooks/firewall.yml` (первый прогон строго с `Limit` на одну тестовую ноду)

- `fw_allow` (Text, одно правило на строку): `22/tcp` — всем; `2096/tcp from 203.0.113.10` — только с указанного IP (остальным закрыто дефолтным `deny` = DROP, stealth; отдельного reject/RST нет и не нужен)
- `fw_enable: false` -> `true` чтобы ВКЛЮЧИТЬ ufw (guard требует порт SSH-подключения из inventory — обычно `22/tcp`)
- `fw_confirmed: false` -> `true` чтобы разрешить ВКЛЮЧЕНИЕ сразу на нескольких хостах (для одного не нужен)
- `fw_delete` (Text, формат как у `fw_allow`) — удалить правила. Правило SSH удалить нельзя
- `fw_ssh_restricted_ok: false` -> `true` — подтвердить, что SSH открыт только с IP контроллера (`22/tcp from IP`). Guard требует правило SSH именно по TCP: `22/udp` его не проходит

> Docker публикует порты контейнеров (`ports:`) через свои цепочки iptables в обход UFW: `ufw deny` их не закрывает. Для таких портов слушай на `127.0.0.1` или фильтруй в цепочке `DOCKER-USER` (это делает баунсер CrowdSec, см. `docs/crowdsec.md`).

Только правила, без включения:

```json
{
  "target": "vps-stage-01",
  "fw_allow": "22/tcp\n80/tcp\n443/tcp"
}
```

Порт VPN-агента только с IP панели (остальным — DROP по дефолту):

```json
{
  "target": "vps-stage-01",
  "fw_allow": "22/tcp\n2096/tcp from 203.0.113.10"
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

## `playbooks/fail2ban.yml` (первый прогон строго с `Limit` на одну тестовую ноду)

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

## Модель доверия Semaphore

- **Запуск шаблона = выполнение кода на контроллере.** Значения survey/extra vars Ansible шаблонизирует как Jinja: строка `{{ lookup('pipe', 'cat /etc/passwd') }}` в любом текстовом поле выполнится внутри контейнера Semaphore, где лежат SSH-ключи ко всем хостам. Проверка внутри плейбука это не ловит — значение шаблонизируется раньше, чем его можно проверить. Поэтому права **Task Runner** и выше в проекте давай только тем, кому доверяешь доступ ко всем нодам; для остальных — роль **Guest** (только просмотр).
- `run_cmd`/`run_script` по определению выполняют произвольные команды — права на эти шаблоны равны root на целевых хостах.
- UI слушает `127.0.0.1:3000` (`SEMAPHORE_BIND` в `.env`). Наружу — через SSH-туннель (`ssh -L 3000:127.0.0.1:3000 controller`) или reverse proxy с TLS. Docker публикует порты в обход UFW, поэтому `0.0.0.0` по HTTP означает «открыто всем».
- `ansible.cfg`: `host_key_checking = True` + `StrictHostKeyChecking=accept-new` — новый хост принимается при первом подключении, смена ключа известного хоста останавливает прогон. После переустановки ноды: `ssh-keygen -R <host>` в контейнере Semaphore (или удалить строку из его `known_hosts`).
- Креды CrowdSec лежат в JSON группы инвентаря в открытом виде; надёжнее хранить их в **Secrets** окружения Semaphore (см. `docs/crowdsec.md`).
