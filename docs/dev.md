# Локальная проверка и контрибьюшн

Требуется установленный `ansible` (например `pip install ansible-core`).
`target` обязателен для host-шаблонов (дефолта нет) — для проверок подставляем `-e '{"target":"all"}'`. Исключения: `remnawave_node_add` работает только с панелью, а `remnawave_node_remove` может работать без `target` при `scope=panel`.

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
ansible-playbook --syntax-check playbooks/crowdsec_node_adopt.yml -e '{"target":"all"}'
ansible-playbook --syntax-check playbooks/crowdsec_node_move.yml -e '{"target":"all"}'
ansible-playbook --syntax-check playbooks/docker.yml -e '{"target":"all"}'
ansible-playbook --syntax-check playbooks/bbr.yml -e '{"target":"all"}'
ansible-playbook --syntax-check playbooks/cleanup.yml -e '{"target":"all"}'
ansible-playbook --syntax-check playbooks/rsyslog.yml -e '{"target":"all"}'
ansible-playbook --syntax-check playbooks/set_hostname.yml -e '{"target":"all"}'
ansible-playbook --syntax-check playbooks/remnawave_node_add.yml
ansible-playbook --syntax-check playbooks/remnawave_node_deploy.yml -e '{"target":"all"}'
ansible-playbook --syntax-check playbooks/remnawave_node_config.yml -e '{"target":"all"}'
ansible-playbook --syntax-check playbooks/remnawave_node_update.yml -e '{"target":"all"}'
ansible-playbook --syntax-check playbooks/remnawave_node_move.yml -e '{"target":"all"}'
ansible-playbook --syntax-check playbooks/remnawave_node_remove.yml -e '{"target":"all"}'
ansible-playbook --syntax-check playbooks/nginx_fallback.yml -e '{"target":"all"}'
ansible-playbook --syntax-check playbooks/nginx_adopt.yml -e '{"target":"all"}'
ansible-playbook --syntax-check playbooks/nginx_move.yml -e '{"target":"all"}'
ansible-playbook --syntax-check playbooks/diagnostics.yml -e '{"target":"all"}'
ansible-playbook --syntax-check playbooks/ipv6.yml -e '{"target":"all"}'
ansible-galaxy collection install -r requirements.yml
```

Правила для новых шаблонов:

- новый плейбук → запись в `semaphore/templates.json` (survey: `target` первым, человеческие Title, `default_value` до `values`) + подраздел в доке своей зоны;
- `src` в `template`/`copy` — только через `{{ playbook_dir }}/../templates/...` или `{{ playbook_dir }}/../files/...` (относительные пути резолвятся от каталога плейбука, а не корня репо; `--syntax-check` это не ловит — только живой прогон);
- парные `*_adopt`/`*_move` плейбуки: общие блоки (discovery/render/ufw-check/rename-backup) — держать побайтово одинаковыми внутри пары (`remnawave_node_deploy` — референс вывода render);
- `README.md` не трогаем (только дерево `docs/`, если появился новый файл);
- JSON-примеры в доках — тот же формат, что survey-поля в UI.
