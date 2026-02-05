@echo off
setlocal enableextensions

cd /d "%~dp0.."

set "PY_CMD="
where py >nul 2>&1
if %errorlevel%==0 (
  set "PY_CMD=py -3"
) else (
  where python >nul 2>&1
  if %errorlevel%==0 set "PY_CMD=python"
)

if not defined PY_CMD (
  echo Python not found (install Python 3.9+ or ensure py/python is in PATH). 1>&2
  exit /b 2
)

if not exist ".venv\\Scripts\\python.exe" (
  echo Creating virtual env: .venv
  %PY_CMD% -m venv .venv
)

if not exist ".venv\\Scripts\\python.exe" (
  echo Virtual env creation failed: .venv\\Scripts\\python.exe not found. 1>&2
  exit /b 2
)

echo Installing dependencies: requirements.txt
".venv\\Scripts\\python.exe" -m pip install -r requirements.txt
echo Done.
