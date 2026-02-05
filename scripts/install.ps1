$ErrorActionPreference = "Stop"

$RootDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RootDir

function Get-PythonCommand {
  if (Get-Command py -ErrorAction SilentlyContinue) { return @("py", "-3") }
  if (Get-Command python -ErrorAction SilentlyContinue) { return @("python") }
  throw "未找到 Python，请先安装 Python 3.9+。"
}

$PythonCmd = Get-PythonCommand

if (-not (Test-Path ".venv")) {
  Write-Host "创建虚拟环境：.venv"
  & $PythonCmd -m venv .venv
}

$VenvPython = Join-Path $RootDir ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
  Write-Host "虚拟环境不完整，尝试重新创建 .venv"
  Remove-Item -Recurse -Force ".venv"
  & $PythonCmd -m venv .venv
}

Write-Host "安装依赖：requirements.txt"
& $VenvPython -m pip install -r requirements.txt
Write-Host "完成。"
