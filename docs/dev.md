# Локальная проверка и контрибьюшн

Требуется Python 3.13+ и `uv`. Зависимости проверок объявлены в `pyproject.toml` и закреплены в `uv.lock`.
`target` обязателен для host-шаблонов (дефолта нет) — для проверок подставляем `-e '{"target":"all"}'`. Исключения: `remnawave_node_add` работает только с панелью, а `remnawave_node_remove` может работать без `target` при `scope=panel`.

```bash
uv sync --locked
uv run --locked ansible-galaxy collection install -r requirements.yml
git ls-files -z -- '*.yml' '*.yaml' | xargs -0 uv run --locked yamllint
uv run --locked shellcheck scripts/*.sh
uv run --locked python -m py_compile scripts/semaphore_bootstrap.py
uv run --locked python -m unittest discover -s tests -v  # init_node: SSH probe + откат конфигурации
uv run --locked scripts/syntax_check.sh  # --syntax-check всех playbooks/*.yml
uv run --locked ansible-lint
```

Это же гоняет CI (`.github/workflows/lint.yml`) на Python 3.13 на каждый push и PR. `uv.lock` обеспечивает одинаковые версии Python-инструментов локально и в CI; версии Ansible-коллекций закреплены отдельно в `requirements.yml`. `syntax_check.sh` подставляет `target=all` и `*_move_dest=localhost` (их требуют `*_move`), поэтому новый плейбук проверяется без правки списка.

Правила для новых шаблонов:

- новый плейбук → запись в `semaphore/templates.json` (survey: `target` первым, человеческие Title, `default_value` до `values`) + подраздел в доке своей зоны;
- `src` в `template`/`copy` — только через `{{ playbook_dir }}/../templates/...` или `{{ playbook_dir }}/../files/...` (относительные пути резолвятся от каталога плейбука, а не корня репо; `--syntax-check` это не ловит — только живой прогон);
- парные `*_adopt`/`*_move` плейбуки: общие блоки (discovery/render/ufw-check/rename-backup) — держать побайтово одинаковыми внутри пары (`remnawave_node_deploy` — референс вывода render);
- `README.md` не трогаем (только дерево `docs/`, если появился новый файл);
- JSON-примеры в доках — тот же формат, что survey-поля в UI.
