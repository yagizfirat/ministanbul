@echo off
REM Mini Istanbul 3D — dev stack launcher
REM 4 PowerShell pencere acar: Django, Daphne, Celery worker, Celery beat.
REM Memurai Windows servisi, ayri baslatmaya gerek yok.
REM Vite dev server'i ayri baslat: cd frontend && npm run dev

set BACKEND=%~dp0..\backend

start "Django"  powershell -NoExit -ExecutionPolicy Bypass -Command "cd '%BACKEND%'; .\venv\Scripts\Activate.ps1; python manage.py runserver 8010"
start "Daphne"  powershell -NoExit -ExecutionPolicy Bypass -Command "cd '%BACKEND%'; .\venv\Scripts\Activate.ps1; daphne -b 127.0.0.1 -p 8011 config.asgi:application"
start "Worker"  powershell -NoExit -ExecutionPolicy Bypass -Command "cd '%BACKEND%'; .\venv\Scripts\Activate.ps1; celery -A config worker --pool=solo -l INFO"
start "Beat"    powershell -NoExit -ExecutionPolicy Bypass -Command "cd '%BACKEND%'; .\venv\Scripts\Activate.ps1; celery -A config beat -l INFO"
