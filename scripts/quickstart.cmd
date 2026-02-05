@echo off
setlocal enableextensions enabledelayedexpansion

cd /d "%~dp0.."

if not exist ".venv\\Scripts\\python.exe" (
  echo 未检测到虚拟环境，先安装依赖…
  call "%~dp0install.cmd"
  if errorlevel 1 exit /b %errorlevel%
)

if not exist "config.json" (
  copy /Y "config.example.json" "config.json" >nul
  echo 已生成 config.json，请填写飞书 webhook，并确保 channels 里仅启用 1 个渠道^（enabled=true^）。 1>&2
  exit /b 2
)

if not exist "cookie.txt" (
  echo 缺少 cookie.txt：请将浏览器抓到的 Cookie 粘贴到 cookie.txt（一行）。 1>&2
  exit /b 2
)
for %%A in ("cookie.txt") do set "COOKIE_SIZE=%%~zA"
if "!COOKIE_SIZE!"=="0" (
  echo cookie.txt 为空：请将浏览器抓到的 Cookie 粘贴到 cookie.txt（一行）。 1>&2
  exit /b 2
)

findstr /C:"hook/xxx" config.json >nul 2>&1
if %errorlevel%==0 (
  echo 请在 config.json 填写真实的飞书 webhook^（不要保留 hook/xxx 占位符^）。 1>&2
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
    echo config.json 缺少 schedule.interval_minutes（分钟），请先配置后再启动。 1>&2
    exit /b 2
  )
)

echo 启动监控（退出用 Ctrl+C）…
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
