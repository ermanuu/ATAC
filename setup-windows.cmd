@echo off
setlocal
cd /d "%~dp0"
where node >nul 2>nul
if errorlevel 1 (
  echo Installa Node.js 24 LTS, poi riapri il terminale.
  exit /b 1
)
where py >nul 2>nul
if errorlevel 1 (
  echo Installa Python 3.12 o successivo con il launcher py.
  exit /b 1
)
call npm ci
if errorlevel 1 exit /b 1
if not exist .venv\Scripts\python.exe py -3 -m venv .venv
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe -m pip install -r server\requirements.txt
if errorlevel 1 exit /b 1
call npm run data:import
if errorlevel 1 (
  echo Download Roma Mobilita non riuscito. Leggi l'errore e riprova npm run data:import.
  exit /b 1
)
echo Installazione completata. Segui PROVA-IPHONE-WINDOWS.md per aprire l'app.
