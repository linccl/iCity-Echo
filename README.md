# iCity Friends Monitor

使用 **Cookie 维持登录 + 定时抓取 /friends 页面** 的方式，检测 iCity 朋友页是否有新动态，并 **合并推送** 到通知渠道（当前支持飞书群机器人）。

## 1) 安装依赖

### 快速方式（推荐）

macOS / Linux：

```bash
bash scripts/install.sh
```

Windows（PowerShell）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install.ps1
```

### 手动方式

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2) 准备 Cookie

1. 浏览器登录 iCity，打开 `https://icity.ly/friends`
2. DevTools → Network → 找到 `friends` 请求 → Request Headers → 复制完整 `cookie:` 字段
3. 将 cookie 字符串写入 `cookie.txt`（只保留一行；可以包含 `cookie:` 前缀，脚本会自动剥离）

建议将 `cookie.txt` 权限设置为仅自己可读（Linux）：

```bash
chmod 600 cookie.txt
```

## 3) 运行

### 快速启动（推荐）

macOS / Linux：

```bash
bash scripts/quickstart.sh
```

Windows（PowerShell）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\quickstart.ps1
```

### 方式 A：配置文件（推荐）

复制示例配置并填写 webhook（注意：`channels` 里必须且只能启用 1 个渠道；目前仅支持 `feishu`）：

```bash
cp config.example.json config.json
```

在 `config.json` 里设置定时参数（上海时区 00:00-09:00 不执行）：

- `schedule.enabled=true`：默认进入循环模式（常驻）
- `schedule.interval_minutes`：每隔多少分钟检查一次

首次运行建议用 `--once` 初始化 `state.json`（不会推送消息）：

```bash
python3 icity_friends_monitor.py --once
```

循环运行（按配置定时执行）：

```bash
python3 icity_friends_monitor.py
```

### 方式 B：命令行参数（兼容旧用法）

```bash
python3 icity_friends_monitor.py --webhook "https://open.feishu.cn/open-apis/bot/v2/hook/xxx" --once
```

后续运行检测到新动态会合并推送：

```bash
python3 icity_friends_monitor.py --webhook "https://open.feishu.cn/open-apis/bot/v2/hook/xxx" --once
```

只打印不发送（用于调试）：

```bash
python3 icity_friends_monitor.py --webhook "https://open.feishu.cn/open-apis/bot/v2/hook/xxx" --once --dry-run
```

## 4) 定时任务

### Ubuntu (cron)

每 10 分钟执行一次：

```bash
*/10 * * * * /usr/bin/python3 /path/to/iCity-Echo/icity_friends_monitor.py --cookie-file /path/to/iCity-Echo/cookie.txt --state-file /path/to/iCity-Echo/state.json --webhook "https://open.feishu.cn/open-apis/bot/v2/hook/xxx" --once >> /path/to/iCity-Echo/monitor.log 2>&1
```

### Windows (schtasks)

示例（按需调整路径与转义）：

```bat
schtasks /Create /SC MINUTE /MO 10 /TN "iCityFriendsMonitor" /TR "python C:\path\to\iCity-Echo\icity_friends_monitor.py --cookie-file C:\path\to\iCity-Echo\cookie.txt --state-file C:\path\to\iCity-Echo\state.json --webhook https://open.feishu.cn/open-apis/bot/v2/hook/xxx --once"
```
