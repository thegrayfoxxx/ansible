# Semaphore UI: подключение

Чеклист первичного подключения (детальный гайд с картинками — [QUICKSTART.md](QUICKSTART.md)).

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
   см. [QUICKSTART.md](QUICKSTART.md) (шаг 9–10: `update_templates` → `Run`).
   Соответствие шаблонов плейбукам лежит в `semaphore/templates.json`.
