@echo off
setlocal enableextensions enabledelayedexpansion

cd /d "%~dp0.."

set "FROM_EXPLORER=0"
echo %CMDCMDLINE% | findstr /I /C:" /c " >nul 2>&1 && set "FROM_EXPLORER=1"

goto :main

:fail
echo %~1 1>&2
if "%FROM_EXPLORER%"=="1" (
  echo.
  pause
)
exit /b 2

:main
if not exist ".venv\\Scripts\\python.exe" (
  echo Virtual env not found, installing dependencies...
  call "%~dp0install.cmd"
  if errorlevel 1 exit /b %errorlevel%
)

if not exist "config.json" (
  copy /Y "config.example.json" "config.json" >nul
  call :fail "Generated config.json. Please fill in Feishu webhook and enable exactly one channel (enabled=true)."
)

if not exist "cookie.txt" (
  call :fail "Missing cookie.txt: paste your browser Cookie into cookie.txt (single line)."
)
for %%A in ("cookie.txt") do set "COOKIE_SIZE=%%~zA"
if "!COOKIE_SIZE!"=="0" (
  call :fail "cookie.txt is empty: paste your browser Cookie into cookie.txt (single line)."
)

findstr /C:"hook/xxx" config.json >nul 2>&1
if %errorlevel%==0 (
  call :fail "Please fill in a real Feishu webhook in config.json (do not keep hook/xxx placeholder)."
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
    call :fail "config.json missing schedule.interval_minutes (minutes). Please configure it before starting."
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
