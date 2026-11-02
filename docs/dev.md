# Локальная проверка и контрибьюшн

Требуется установленный `ansible` (например `pip install ansible-core ansible-lint yamllint shellcheck-py`).
`target` обязателен для host-шаблонов (дефолта нет) — для проверок подставляем `-e '{"target":"all"}'`. Исключения: `remnawave_node_add` работает только с панелью, а `remnawave_node_remove` может работать без `target` при `scope=panel`.

```bash
ansible-galaxy collection install -r requirements.yml
scripts/syntax_check.sh          # --syntax-check всех playbooks/*.yml
yamllint .
ansible-lint
shellcheck scripts/*.sh
python3 -m py_compile scripts/semaphore_bootstrap.py
```

Это же гоняет CI (`.github/workflows/lint.yml`) на каждый push и PR. `syntax_check.sh` подставляет `target=all` и `*_move_dest=localhost` (их требуют `*_move`), поэтому новый плейбук проверяется без правки списка.

Правила для новых шаблонов:

- новый плейбук → запись в `semaphore/templates.json` (survey: `target` первым, человеческие Title, `default_value` до `values`) + подраздел в доке своей зоны;
- `src` в `template`/`copy` — только через `{{ playbook_dir }}/../templates/...` или `{{ playbook_dir }}/../files/...` (относительные пути резолвятся от каталога плейбука, а не корня репо; `--syntax-check` это не ловит — только живой прогон);
- парные `*_adopt`/`*_move` плейбуки: общие блоки (discovery/render/ufw-check/rename-backup) — держать побайтово одинаковыми внутри пары (`remnawave_node_deploy` — референс вывода render);
- `README.md` не трогаем (только дерево `docs/`, если появился новый файл);
- JSON-примеры в доках — тот же формат, что survey-поля в UI.
