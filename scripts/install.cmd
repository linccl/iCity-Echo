@echo off
setlocal enableextensions

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
set "PY_CMD="
where py >nul 2>&1
if %errorlevel%==0 (
  set "PY_CMD=py -3"
) else (
  where python >nul 2>&1
  if %errorlevel%==0 set "PY_CMD=python"
)

if not defined PY_CMD (
  call :fail "Python not found (install Python 3.9+ or ensure py/python is in PATH)."
)

if not exist ".venv\\Scripts\\python.exe" (
  echo Creating virtual env: .venv
  %PY_CMD% -m venv .venv
)

if not exist ".venv\\Scripts\\python.exe" (
  call :fail "Virtual env creation failed: .venv\\Scripts\\python.exe not found."
)

echo Installing dependencies: requirements.txt
".venv\\Scripts\\python.exe" -m pip install -r requirements.txt
echo Done.

if "%FROM_EXPLORER%"=="1" (
  echo.
  pause
)
