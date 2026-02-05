$ErrorActionPreference = "Stop"

$RootDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RootDir

$VenvPython = Join-Path $RootDir ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
  Write-Host "未检测到虚拟环境，先安装依赖…"
  & powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "install.ps1")
}

if (-not (Test-Path "config.json")) {
  Copy-Item "config.example.json" "config.json" -Force
  Write-Host "已生成 config.json，请填写飞书 webhook，并确保 channels 里仅启用 1 个渠道（enabled=true）。"
  exit 2
}

if (-not (Test-Path "cookie.txt") -or ((Get-Item "cookie.txt").Length -eq 0)) {
  Write-Host "缺少 cookie.txt 或文件为空：请将浏览器抓到的 Cookie 粘贴到 cookie.txt（一行）。"
  exit 2
}

try {
  $cfg = Get-Content "config.json" -Raw | ConvertFrom-Json
} catch {
  Write-Host "config.json 解析失败：$($_.Exception.Message)"
  exit 2
}

$hasOnce = $args -contains "--once"
$hasLoop = $args -contains "--loop"

if (-not $cfg.channels) {
  Write-Host "config.json 缺少 channels：请按 config.example.json 配置，并启用 1 个渠道。"
  exit 2
}

$enabled = @($cfg.channels | Where-Object { $_ -and $_.enabled -eq $true })
if ($enabled.Count -ne 1) {
  Write-Host "config.json: channels 必须且只能启用 1 个渠道（enabled=true）。"
  exit 2
}

$ch = $enabled[0]
if (($ch.type -as [string]).Trim() -ne "feishu") {
  Write-Host "当前仅支持 feishu 渠道：请将启用的渠道 type 设置为 feishu。"
  exit 2
}

$webhook = (($ch.webhook -as [string]) ?? "").Trim()
if (-not $webhook -or $webhook.Contains("hook/xxx")) {
  Write-Host "请在 config.json 填写真实的飞书 webhook（不要保留 hook/xxx 占位符）。"
  exit 2
}

if (-not $hasOnce) {
  if (-not $cfg.schedule) {
    Write-Host "config.json 缺少 schedule：请配置 schedule.interval_minutes（分钟）。"
    exit 2
  }
  try {
    $iv = [int]$cfg.schedule.interval_minutes
  } catch {
    Write-Host "schedule.interval_minutes 必须是整数。"
    exit 2
  }
  if ($iv -le 0) {
    Write-Host "schedule.interval_minutes 必须 > 0。"
    exit 2
  }
}

Write-Host "启动监控（退出用 Ctrl+C）…"
if ($hasOnce -or $hasLoop) {
  & $VenvPython "icity_friends_monitor.py" @args
} else {
  & $VenvPython "icity_friends_monitor.py" "--loop" @args
}
