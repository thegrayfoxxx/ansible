# Вкладка Security: доступ и защита

## `playbooks/init_node.yml` (инит новой ноды — строго один хост за прогон, enforced плейбуком)

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

## `playbooks/firewall.yml` (первый прогон строго с `Limit` на одну тестовую ноду)

- `fw_allow` (Text, одно правило на строку): `22/tcp` — всем; `2096/tcp from 203.0.113.10` — только с указанного IP (остальным закрыто дефолтным `deny` = DROP, stealth; отдельного reject/RST нет и не нужен)
- `fw_enable: false` -> `true` чтобы ВКЛЮЧИТЬ ufw (guard требует порт SSH-подключения из inventory — обычно `22/tcp`)
- `fw_confirmed: false` -> `true` чтобы разрешить ВКЛЮЧЕНИЕ сразу на нескольких хостах (для одного не нужен)

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
