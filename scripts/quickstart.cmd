@echo off
setlocal enableextensions enabledelayedexpansion

cd /d "%~dp0.."

if not exist ".venv\\Scripts\\python.exe" (
  echo Virtual env not found, installing dependencies...
  call "%~dp0install.cmd"
  if errorlevel 1 exit /b %errorlevel%
)

if not exist "config.json" (
  copy /Y "config.example.json" "config.json" >nul
  echo Generated config.json. Please fill in Feishu webhook and enable exactly one channel (enabled=true). 1>&2
  exit /b 2
)

if not exist "cookie.txt" (
  echo Missing cookie.txt: paste your browser Cookie into cookie.txt (single line). 1>&2
  exit /b 2
)
for %%A in ("cookie.txt") do set "COOKIE_SIZE=%%~zA"
if "!COOKIE_SIZE!"=="0" (
  echo cookie.txt is empty: paste your browser Cookie into cookie.txt (single line). 1>&2
  exit /b 2
)

findstr /C:"hook/xxx" config.json >nul 2>&1
if %errorlevel%==0 (
  echo Please fill in a real Feishu webhook in config.json (do not keep hook/xxx placeholder). 1>&2
  exit /b 2
)

set "HAS_ONCE="
set "HAS_LOOP="
for %%A in (%*) do (
  if "%%~A"=="--once" set "HAS_ONCE=1"
  if "%%~A"=="--loop" set "HAS_LOOP=1"
)

if not defined HAS_ONCE if not defined HAS_LOOP (
  findstr /C:"\"interval_minutes\"" config.json >nul 2>&1
  if errorlevel 1 (
    echo config.json missing schedule.interval_minutes (minutes). Please configure it before starting. 1>&2
    exit /b 2
  )
)

echo Starting monitor (Ctrl+C to exit)...
if defined HAS_ONCE (
  ".venv\\Scripts\\python.exe" icity_friends_monitor.py %*
  exit /b %errorlevel%
)
if defined HAS_LOOP (
  ".venv\\Scripts\\python.exe" icity_friends_monitor.py %*
  exit /b %errorlevel%
)

".venv\\Scripts\\python.exe" icity_friends_monitor.py --loop %*
exit /b %errorlevel%
