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
  echo 未找到 Python^（建议安装 Python 3.9+，或确保 py/python 在 PATH 中^）。 1>&2
  exit /b 2
)

if not exist ".venv\\Scripts\\python.exe" (
  echo 创建虚拟环境：.venv
  %PY_CMD% -m venv .venv
)

if not exist ".venv\\Scripts\\python.exe" (
  echo 虚拟环境创建失败：.venv\\Scripts\\python.exe 不存在。 1>&2
  exit /b 2
)

echo 安装依赖：requirements.txt
".venv\\Scripts\\python.exe" -m pip install -r requirements.txt
echo 完成。
