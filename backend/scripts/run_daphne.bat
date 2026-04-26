@echo off
REM Daphne ASGI server (Faz 3+). Django HTTP runserver'la paralel calisir:
REM Django :8010 (HTTP/REST), Daphne :8011 (WebSocket).
REM
REM Auto-reload yok: Daphne 4.2.1 CLI --reload bayragini desteklemiyor
REM (ROADMAP 6b-v reload deneme, exit code 2). Kod degisikliklerinde
REM manuel restart: Ctrl+C ile durdur, tekrar calistir.
cd /d %~dp0..
call venv\Scripts\activate
if not exist logs mkdir logs
daphne -b 127.0.0.1 -p 8011 ^
  --access-log logs\daphne_access.log ^
  config.asgi:application > logs\daphne_stdout.log 2>&1
