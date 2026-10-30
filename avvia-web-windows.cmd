@echo off
cd /d "%~dp0"
if not exist dist\index.html (
  echo Prima esegui npm run build:web
  pause
  exit /b 1
)
set WEB_HOST=0.0.0.0
set WEB_PORT=8000
echo Apri http://localhost:8000 sul PC.
echo Sull'iPhone usa http://IP-DEL-PC:8000, sulla stessa rete Wi-Fi.
echo Lascia aperta questa finestra. Per fermare premi Ctrl+C.
call npm run serve:web
pause
