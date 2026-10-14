# Локальная проверка и контрибьюшн

Требуется установленный `ansible` (например `pip install ansible-core`).
`target` обязателен везде (дефолта нет) — для проверок подставляем `-e '{"target":"all"}'`:

```bash
ansible-playbook --syntax-check playbooks/ping.yml -e '{"target":"all"}'
ansible-playbook --syntax-check playbooks/update.yml -e '{"target":"all"}'
ansible-playbook --syntax-check playbooks/base.yml -e '{"target":"all"}'
ansible-playbook --syntax-check playbooks/run_script.yml -e '{"target":"all"}'
ansible-playbook --syntax-check playbooks/run_cmd.yml -e '{"target":"all"}'
ansible-playbook --syntax-check playbooks/logs.yml -e '{"target":"all"}'
ansible-playbook --syntax-check playbooks/health.yml -e '{"target":"all"}'
ansible-playbook --syntax-check playbooks/reboot.yml -e '{"target":"all"}'
ansible-playbook --syntax-check playbooks/init_node.yml -e '{"target":"all"}'
ansible-playbook --syntax-check playbooks/firewall.yml -e '{"target":"all"}'
ansible-playbook --syntax-check playbooks/fail2ban.yml -e '{"target":"all"}'
ansible-playbook --syntax-check playbooks/crowdsec_register.yml -e '{"target":"all"}'
ansible-playbook --syntax-check playbooks/crowdsec_node.yml -e '{"target":"all"}'
ansible-playbook --syntax-check playbooks/crowdsec_node_update.yml -e '{"target":"all"}'
ansible-playbook --syntax-check playbooks/crowdsec_unregister.yml -e '{"target":"all"}'
ansible-playbook --syntax-check playbooks/docker.yml -e '{"target":"all"}'
ansible-playbook --syntax-check playbooks/bbr.yml -e '{"target":"all"}'
ansible-playbook --syntax-check playbooks/cleanup.yml -e '{"target":"all"}'
ansible-playbook --syntax-check playbooks/rsyslog.yml -e '{"target":"all"}'
ansible-playbook --syntax-check playbooks/remnawave_node_add.yml -e '{"target":"all"}'
ansible-playbook --syntax-check playbooks/remnawave_node_update.yml -e '{"target":"all"}'
ansible-galaxy collection install -r requirements.yml
```

Правила для новых шаблонов:

- новый плейбук → запись в `semaphore/templates.json` (survey: `target` первым, человеческие Title, `default_value` до `values`) + подраздел в доке своей зоны;
- `README.md` не трогаем (только дерево `docs/`, если появился новый файл);
- JSON-примеры в доках — тот же формат, что survey-поля в UI.
