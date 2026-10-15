# Вкладка Nginx: Selfsteal-заглушка + LE-серт (Xray уже стоит отдельно)

Один шаблон `nginx_fallback`: поднимает `fallback-web` (nginx в docker терминирует stolen-TLS на unix-сокете) и `acme.sh` (выпуск/продление LE через http-01). Xray (хостовая Remnanode / свой docker) сюда не входит — он шлёт невалидный трафик в сокет. Ручного создания шаблона не нужно — приезжает через `update_templates`.

Предусловия на ноде: `docker` (шаблон `docker` — иначе `fail`), Debian/Ubuntu, свободный `:80` (иначе http-01 не пройдёт; `:443` не проверяем — это вотчина Xray).

## Первый деплой (серта ещё нет — норма)

Плейбук сам разруливает курицу-и-яйцо (nginx не стартует без сертов):

1. кладёт файлы (`compose.yml`, `.env`, `fallback.conf.template`, `index.html` из survey);
2. если LE-серта нет — генерит временный self-signed на 2 дня, чтобы nginx встал и отдал `:80`;
3. `up -d` → ждёт сокет `/dev/shm/nginx.sock` → `chmod 666` (иначе не-root Xray не подключится; после ребута хоста сокет пересоздаётся — плейбук чинит права при каждом прогоне);
4. `acme.sh --issue --webroot` → `--install-cert` → `nginx -s reload`;
5. проверки: `nginx -t`, контейнеры running. Успешный `--issue` сам по себе доказывает, что `:80` доступен снаружи (LE достучался).

`:443` плейбук не проверяет — порт оживает после установки Xray.

## `nginx_fallback`

- `nginx_domain` (String, обязательно; plain hostname без схемы и слэшей)
- `nginx_email` (String; обязателен для первого выпуска — LE-аккаунт; когда серт уже есть, можно пустым)
- `nginx_html` (Text, обязательно; свой `index.html` целиком — файл из репо не берём)
- `nginx_dir` (String; папка проекта на ноде, пусто — `/opt/nginx`)
- `nginx_staging: false` -> `true` для обкатки на staging LE без рейт-лимитов (потом перепрогнать с `false` для боевого серта; staging-серт браузерами не доверен; переход staging→prod плейбук определяет сам по issuer и перевыпускает без флага)
- `nginx_force_issue: false` -> `true` чтобы перевыпустить серт принудительно (жрёт лимиты LE: 5 дубликатов в неделю — только по нужде)
- `nginx_open_ports: false` -> `true` чтобы открыть `80,443/tcp` в ufw, если он есть (нет — скип с warning)
- сокет всегда `/dev/shm/nginx.sock` (`0666`); контейнеры фиксированы (`fallback-web`, `fallback-acme`); логи `json-file 10m × 3`
- смена домена оставляет мусор `letsencrypt/live/<старый>` — чистится руками

```json
{
  "target": "de1",
  "nginx_domain": "de1.example.com",
  "nginx_email": "admin@example.com",
  "nginx_html": "<!DOCTYPE html>...",
  "nginx_staging": true
}
```

Повторный прогон (обновить заглушку, серт уже есть):

```json
{
  "target": "de1",
  "nginx_domain": "de1.example.com",
  "nginx_html": "<!DOCTYPE html>..."
}
```
