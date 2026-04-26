#!/usr/bin/env bash
# Daphne ASGI server (Faz 3+). Django HTTP runserver'la paralel çalışır:
# Django :8010 (HTTP/REST), Daphne :8011 (WebSocket).
#
# Auto-reload yok: Daphne 4.2.1 CLI `--reload` bayrağını desteklemiyor
# (ROADMAP 6b-v reload deneme, exit code 2). Kod değişikliklerinde
# manuel restart: bu script'i Ctrl+C ile durdur, tekrar çalıştır.
set -e
cd "$(dirname "$0")/.."
source venv/Scripts/activate
mkdir -p logs
exec daphne -b 127.0.0.1 -p 8011 \
  --access-log logs/daphne_access.log \
  config.asgi:application > logs/daphne_stdout.log 2>&1
