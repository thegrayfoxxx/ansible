# Диагностика ноды: своё + pinned upstream

Гибрид: свои пробы (`scripts/diagnostics.sh`, ноль внешних зависимостей кроме
apt-пакетов) + чужое точечно (скачивание с пином SHA256, запуск, вывод в лог).
Меню, SVG-альбомы, заливки на imgdb и спонсорские блоки upstream — не едут.

## `playbooks/diagnostics.yml`

- `diag_suite`: `core` (дефолт; только своё) / `censor` / `streaming` / `bench_full` / `net_ru` / `all` (Enum)
- `diag_iperf_server: ""` (куда мерить iperf3/ping из своего скрипта, например IP панели)
- `diag_panel_url: ""` (HTTP-проверка панели своим скриптом)
- `diag_full: false` -> `true` (длинные fio/iperf/sysbench: 30с вместо 10–15с)
- `diag_confirmed: false` -> `true` для `bench_full`/`all` сразу на нескольких хостах (Enum)

Что входит в сюиты:

- `core`: свой скрипт — факты (CPU/RAM/диск/ОС/ядро/virt/BBR/IPv4/IPv6/ASN), DNS (системный + 1.1.1.1/8.8.8.8/77.88.8.8/9.9.9.9), DoH, Telegram DC, SNI-пробы (дифференциально: один IP, разные SNI), HTTP generate_204 + панель, sysbench, fio, iperf+ping до `diag_iperf_server`
- `censor`: censorcheck `--mode geoblock` + `--mode dpi`, tlab censorcheck
- `streaming`: IPCheck `-E -n` (стриминг-анлоки + качество IP; AGPL — только запуск, файл в репо не вендорим)
- `bench_full`: YABS `-4` (тянет свои fio/iperf/geekbench бинарники, минут 10–30) + bench.sh (Ookla)
- `net_ru`: RU speedtest (iperf3) + tlab bench (апстрим с rate-limit: повтор чаще ~5–10 мин = rc=1, это норма и не фейлит плейбук)

```json
{
  "target": "vps-prod-01",
  "diag_suite": "core",
  "diag_panel_url": "https://panel.example.com"
}
```

Полный прогон с длинными бенчами:

```json
{
  "target": "vps-prod-01",
  "diag_suite": "all",
  "diag_full": true,
  "diag_iperf_server": "203.0.113.10"
}
```

## Репин upstream (когда checksum упал)

Чужие скрипты качаются по URL ветки + `sha256` в `vars` плейбука (`diag_pin_*`).
Апстрим обновился — `get_url` упадёт на checksum (fail-closed, так задумано):

```bash
# 1. скачать новый, 2. отдать sha в vars плейбука diag_pin_<name>_sha:
curl -sL https://yabs.sh | sha256sum
```

Править только sha-строку своего пина, URL не трогать. После репина — тестовый
прогон сюита на stage перед продом.
