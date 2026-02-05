from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


DEFAULT_CHECK_URL = "https://icity.ly/friends"
DEFAULT_BASE_URL = "https://icity.ly"
SHANGHAI_TZ = timezone(timedelta(hours=8))
DEFAULT_QUIET_START = "00:00"
DEFAULT_QUIET_END = "09:00"


@dataclass(frozen=True)
class Post:
    post_id: str
    url: str
    author_name: Optional[str]
    author_username: Optional[str]
    content: Optional[str]
    time_text: Optional[str]
    time_title: Optional[str]
    location: Optional[str]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_iso(s: str) -> Optional[datetime]:
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except Exception:
        return None


def shanghai_now() -> datetime:
    return datetime.now(timezone.utc).astimezone(SHANGHAI_TZ)


def minutes_to_hhmm(minutes: int) -> str:
    minutes = minutes % (24 * 60)
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def log(level: str, message: str) -> None:
    ts = shanghai_now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}][{level}] {message}", file=sys.stderr, flush=True)


class MonitorStopped(RuntimeError):
    def __init__(self, message: str, exit_code: int = 1):
        super().__init__(message)
        self.exit_code = exit_code


def hhmm_to_minutes(value: str) -> int:
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", value or "")
    if not m:
        raise RuntimeError(f"时间格式必须为 HH:MM：{value!r}")
    hour = int(m.group(1))
    minute = int(m.group(2))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise RuntimeError(f"时间超出范围：{value!r}")
    return hour * 60 + minute


def in_quiet_window(dt: datetime, start_minutes: int, end_minutes: int) -> bool:
    minutes = dt.hour * 60 + dt.minute
    if start_minutes < end_minutes:
        return start_minutes <= minutes < end_minutes
    if start_minutes > end_minutes:
        return minutes >= start_minutes or minutes < end_minutes
    return False


def seconds_until_quiet_end(dt: datetime, start_minutes: int, end_minutes: int) -> int:
    if not in_quiet_window(dt, start_minutes, end_minutes):
        return 0

    end_hour = end_minutes // 60
    end_minute = end_minutes % 60
    today_end = dt.replace(hour=end_hour, minute=end_minute, second=0, microsecond=0)

    if start_minutes < end_minutes:
        target = today_end
    else:
        minutes = dt.hour * 60 + dt.minute
        if minutes < end_minutes:
            target = today_end
        else:
            target = today_end + timedelta(days=1)

    seconds = int((target - dt).total_seconds())
    return max(0, seconds)


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def read_cookie_file(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
    except FileNotFoundError:
        raise RuntimeError(f"Cookie 文件不存在：{path}")

    raw = raw.strip().strip('"').strip("'")
    if not raw:
        raise RuntimeError(f"Cookie 文件为空：{path}")

    if raw.lower().startswith("cookie:"):
        raw = raw.split(":", 1)[1].strip()

    raw = "".join(line.strip() for line in raw.splitlines() if line.strip())
    if not raw:
        raise RuntimeError(f"Cookie 解析为空：{path}")
    return raw


def load_state(path: str) -> dict:
    if not os.path.exists(path):
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        backup = f"{path}.bak-{int(time.time())}"
        try:
            os.replace(path, backup)
        except Exception:
            pass
        return {}


def save_state(path: str, state: dict) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)

    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp_path, path)


def load_config_file(path: Optional[str]) -> dict:
    if not path:
        return {}
    if not os.path.exists(path):
        raise RuntimeError(f"配置文件不存在：{path}")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"配置文件 JSON 解析失败：{path}（{e}）")
    if not isinstance(data, dict):
        raise RuntimeError(f"配置文件必须是 JSON Object：{path}")
    return data


def looks_like_login_page(resp_url: str, html: str) -> bool:
    try:
        path = urlparse(resp_url).path or ""
    except Exception:
        path = ""
    if "login" in path:
        return True

    lower = html.lower()
    if 'type="password"' in lower or "name=\"password\"" in lower:
        return True
    if "/login" in lower and ("登录" in html or "log in" in lower or "login" in lower):
        return True
    return False


def extract_post_id(href: str) -> Optional[str]:
    m = re.search(r"/a/([^/?#]+)", href)
    if not m:
        return None
    return m.group(1)


def first_link_with_activity_id(root):
    for a in root.find_all("a", href=True):
        href = a.get("href") or ""
        if extract_post_id(href):
            return a
    return None


def parse_posts(html: str, base_url: str) -> list[Post]:
    soup = BeautifulSoup(html, "html.parser")

    items = soup.select("ul.activities li.activity-item")
    if not items:
        items = soup.select("li.activity-item")

    posts: list[Post] = []
    seen_ids: set[str] = set()

    for li in items:
        time_link = li.find("a", class_="time-link", href=True)
        if time_link is not None and not extract_post_id(time_link.get("href") or ""):
            time_link = None

        if time_link is None:
            time_link = first_link_with_activity_id(li)

        if time_link is None:
            continue

        href = time_link.get("href") or ""
        post_id = extract_post_id(href)
        if not post_id or post_id in seen_ids:
            continue
        seen_ids.add(post_id)

        url = urljoin(base_url, href)

        user_link = li.find("a", class_="user-link", href=True)
        author_name = None
        author_username = None
        if user_link is not None:
            strong = user_link.find("strong")
            if strong is not None:
                author_name = normalize_whitespace(strong.get_text(" ", strip=True))
            username = user_link.find("span", class_="username")
            if username is not None:
                author_username = normalize_whitespace(username.get_text(" ", strip=True))

        content = None
        content_div = li.find("div", class_="activity-content")
        if content_div is not None:
            content = normalize_whitespace(content_div.get_text(" ", strip=True))

        time_text = normalize_whitespace(time_link.get_text(" ", strip=True)) or None
        time_title = time_link.get("title")
        if time_title is not None:
            time_title = normalize_whitespace(time_title)

        location = None
        location_span = li.find("span", class_="location")
        if location_span is not None:
            location = normalize_whitespace(location_span.get_text(" ", strip=True))

        posts.append(
            Post(
                post_id=post_id,
                url=url,
                author_name=author_name,
                author_username=author_username,
                content=content,
                time_text=time_text,
                time_title=time_title,
                location=location,
            )
        )

    if posts:
        return posts

    # fallback: 尝试直接从整页提取 /a/<id> 链接（结构变更时兜底）
    for a in soup.find_all("a", href=True):
        href = a.get("href") or ""
        if not extract_post_id(href):
            continue
        post_id = extract_post_id(href)
        if not post_id or post_id in seen_ids:
            continue
        seen_ids.add(post_id)
        posts.append(
            Post(
                post_id=post_id,
                url=urljoin(base_url, href),
                author_name=None,
                author_username=None,
                content=None,
                time_text=None,
                time_title=None,
                location=None,
            )
        )

    return posts


def format_author(post: Post) -> str:
    if post.author_name and post.author_username:
        return f"{post.author_name} {post.author_username}"
    if post.author_name:
        return post.author_name
    if post.author_username:
        return post.author_username
    return "未知用户"


def truncate(text: str, max_len: int) -> str:
    text = normalize_whitespace(text)
    if len(text) <= max_len:
        return text
    return text[: max(0, max_len - 1)] + "…"


def build_update_message(new_posts: list[Post], total_new: int, max_show: int, unknown_total: bool = False) -> str:
    return f"【iCity 新动态】新增 {total_new} 条"


def feishu_success(resp_json: object) -> bool:
    if not isinstance(resp_json, dict):
        return False
    if resp_json.get("StatusCode") == 0:
        return True
    if resp_json.get("code") == 0:
        return True
    return False


def send_feishu_text(session: requests.Session, webhook: str, text: str, timeout: int) -> None:
    payload = {"msg_type": "text", "content": {"text": text}}
    resp = session.post(webhook, json=payload, timeout=timeout)
    if resp.status_code != 200:
        raise RuntimeError(f"飞书推送失败：HTTP {resp.status_code}")
    try:
        data = resp.json()
    except Exception:
        raise RuntimeError("飞书推送失败：返回非 JSON")
    if not feishu_success(data):
        raise RuntimeError(f"飞书推送失败：{data}")


def resolve_channel(args_webhook: Optional[str], config: dict) -> dict:
    webhook = (args_webhook or "").strip()
    if webhook:
        return {"type": "feishu", "webhook": webhook}

    channels = config.get("channels")
    if channels is None:
        channels = []
    if not isinstance(channels, list):
        raise RuntimeError("配置项 channels 必须是数组")
    if not channels:
        raise RuntimeError("未配置通知渠道：请设置 --webhook 或在 config.json 的 channels 中启用 1 个渠道")

    enabled = [c for c in channels if isinstance(c, dict) and c.get("enabled") is True]
    if len(enabled) != 1:
        raise RuntimeError("channels 里必须且只能启用 1 个渠道（enabled=true）")

    channel = enabled[0]
    ch_type = (channel.get("type") or "").strip()
    if not ch_type:
        raise RuntimeError("启用的渠道缺少 type")

    if ch_type == "feishu":
        wh = (channel.get("webhook") or "").strip()
        if not wh:
            raise RuntimeError("飞书渠道缺少 webhook")
        return {"type": "feishu", "webhook": wh}

    raise RuntimeError(f"暂不支持的渠道类型：{ch_type}")


def send_notification(session: requests.Session, channel: dict, text: str, timeout: int) -> None:
    ch_type = channel.get("type")
    if ch_type == "feishu":
        send_feishu_text(session, channel["webhook"], text, timeout)
        return
    raise RuntimeError(f"暂不支持的渠道类型：{ch_type}")


def should_send_alert(state: dict, alert_type: str, cooldown_seconds: int) -> bool:
    alert = state.get("last_alert")
    if not isinstance(alert, dict):
        return True
    if alert.get("type") != alert_type:
        return True
    at = alert.get("at")
    if not isinstance(at, str):
        return True
    dt = parse_iso(at)
    if dt is None:
        return True
    return (datetime.now(timezone.utc) - dt).total_seconds() >= cooldown_seconds


def set_alert(state: dict, alert_type: str, detail: str) -> None:
    state["last_alert"] = {"type": alert_type, "at": now_iso(), "detail": truncate(detail, 200)}


def fetch_html(session: requests.Session, url: str, cookie: str, timeout: int) -> requests.Response:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Cookie": cookie,
    }
    return session.get(url, headers=headers, timeout=timeout)


def run_once(
    session: requests.Session,
    channel: dict,
    cookie: str,
    state: dict,
    *,
    state_file: str,
    cookie_file: str,
    check_url: str,
    base_url: str,
    timeout: int,
    max_notify: int,
    alert_cooldown_minutes: int,
    dry_run: bool,
    verbose: bool,
) -> int:
    if verbose:
        log("DEBUG", f"开始检查：{check_url}")
    try:
        resp = fetch_html(session, check_url, cookie, timeout)
    except Exception as e:
        detail = f"抓取失败：{e}"
        log("WARN", detail)
        cooldown = max(0, alert_cooldown_minutes) * 60
        if should_send_alert(state, "fetch_failed", cooldown):
            msg = f"【iCity 监控告警】{detail}\n"
            if dry_run:
                print(msg)
            else:
                try:
                    send_notification(session, channel, msg, timeout)
                except Exception as send_err:
                    log("WARN", f"告警推送失败：{send_err}")
            set_alert(state, "fetch_failed", detail)
            state["last_checked_at"] = now_iso()
            save_state(state_file, state)
        return 1

    html = resp.text or ""
    status = resp.status_code
    if status in (401, 403, 429):
        detail = f"HTTP {status}，url={resp.url}"
        if status == 429:
            msg = "【iCity 监控告警】触发限流（HTTP 429），脚本已停止。"
            alert_type = "rate_limited"
        elif status == 403:
            msg = "【iCity 监控告警】请求被拒绝（HTTP 403），脚本已停止。"
            alert_type = "forbidden"
        else:
            msg = "【iCity 监控告警】未授权/登录失效（HTTP 401），脚本已停止，请更新 Cookie 后重启。"
            alert_type = "unauthorized"

        log("WARN", detail)
        if dry_run:
            print(msg)
        else:
            try:
                send_notification(session, channel, msg, timeout)
            except Exception as send_err:
                log("WARN", f"告警推送失败：{send_err}")
        set_alert(state, alert_type, detail)
        state["last_checked_at"] = now_iso()
        save_state(state_file, state)
        raise MonitorStopped(msg, exit_code=1)

    if looks_like_login_page(resp.url, html):
        detail = f"跳转登录/未登录：HTTP {status}，url={resp.url}"
        msg = "【iCity 监控告警】检测到跳转登录/未登录，脚本已停止，请更新 Cookie 后重启。"
        log("WARN", detail)
        if dry_run:
            print(msg)
        else:
            try:
                send_notification(session, channel, msg, timeout)
            except Exception as send_err:
                log("WARN", f"告警推送失败：{send_err}")
        set_alert(state, "cookie_invalid", detail)
        state["last_checked_at"] = now_iso()
        save_state(state_file, state)
        raise MonitorStopped(msg, exit_code=1)

    if status != 200:
        detail = f"HTTP {status}，url={resp.url}"
        log("WARN", f"非预期响应：{detail}")
        cooldown = max(0, alert_cooldown_minutes) * 60
        if should_send_alert(state, "http_error", cooldown):
            msg = f"【iCity 监控告警】朋友页响应异常（HTTP {status}），稍后将继续重试。"
            if dry_run:
                print(msg)
            else:
                try:
                    send_notification(session, channel, msg, timeout)
                except Exception as send_err:
                    log("WARN", f"告警推送失败：{send_err}")
            set_alert(state, "http_error", detail)
        state["last_checked_at"] = now_iso()
        save_state(state_file, state)
        return 1

    posts = parse_posts(html, base_url)
    if not posts:
        detail = "解析失败：未找到任何动态条目（页面结构可能变更）"
        log("WARN", detail)
        cooldown = max(0, alert_cooldown_minutes) * 60
        if should_send_alert(state, "parse_failed", cooldown):
            msg = f"【iCity 监控告警】{detail}\n"
            if dry_run:
                print(msg)
            else:
                try:
                    send_notification(session, channel, msg, timeout)
                except Exception as send_err:
                    log("WARN", f"告警推送失败：{send_err}")
            set_alert(state, "parse_failed", detail)
        state["last_checked_at"] = now_iso()
        save_state(state_file, state)
        return 1

    if verbose:
        log("DEBUG", f"解析到动态 {len(posts)} 条")

    newest_id = posts[0].post_id
    last_id = state.get("last_id")

    if not isinstance(last_id, str) or not last_id:
        state["last_id"] = newest_id
        state["last_checked_at"] = now_iso()
        save_state(state_file, state)
        log("INFO", f"初始化 state：last_id={newest_id}")
        return 0

    current_ids = [p.post_id for p in posts]
    new_posts: list[Post] = []
    unknown_total = False
    if last_id in current_ids:
        idx = current_ids.index(last_id)
        if idx > 0:
            new_posts = posts[:idx]
    else:
        new_posts = posts[: max(1, max_notify)]
        unknown_total = True

    if not new_posts:
        state["last_checked_at"] = now_iso()
        save_state(state_file, state)
        log("INFO", f"无新动态（解析到 {len(posts)} 条）")
        return 0

    if unknown_total:
        log("WARN", "未在当前页面找到上次 last_id，按当前页面最新条目计数")
    log("INFO", f"发现新动态：新增 {len(new_posts)} 条")

    msg = build_update_message(
        new_posts,
        total_new=len(new_posts),
        max_show=max(1, max_notify),
        unknown_total=unknown_total,
    )

    if dry_run:
        print(msg)
    else:
        try:
            send_notification(session, channel, msg, timeout)
        except Exception as e:
            log("WARN", f"推送失败：{e}")
            return 1

    state["last_id"] = newest_id
    state["last_checked_at"] = now_iso()
    save_state(state_file, state)
    return 0


def run_loop(
    session: requests.Session,
    channel: dict,
    cookie: str,
    state: dict,
    *,
    interval_minutes: int,
    quiet_start_minutes: int,
    quiet_end_minutes: int,
    state_file: str,
    cookie_file: str,
    check_url: str,
    base_url: str,
    timeout: int,
    max_notify: int,
    alert_cooldown_minutes: int,
    dry_run: bool,
    verbose: bool,
) -> int:
    interval_seconds = max(1, interval_minutes) * 60
    quiet_range = f"{minutes_to_hhmm(quiet_start_minutes)}-{minutes_to_hhmm(quiet_end_minutes)}"
    log("INFO", f"进入循环模式：每 {interval_minutes} 分钟检查一次（上海时间 {quiet_range} 静默）")

    try:
        while True:
            now_sh = shanghai_now()
            if in_quiet_window(now_sh, quiet_start_minutes, quiet_end_minutes):
                sleep_seconds = seconds_until_quiet_end(now_sh, quiet_start_minutes, quiet_end_minutes)
                wake_at = now_sh + timedelta(seconds=sleep_seconds)
                log(
                    "INFO",
                    f"静默时段：上海 {now_sh.strftime('%H:%M')}，sleep {sleep_seconds}s 至 {wake_at.strftime('%H:%M')}",
                )
                time.sleep(sleep_seconds)
                continue

            try:
                run_once(
                    session,
                    channel,
                    cookie,
                    state,
                    state_file=state_file,
                    cookie_file=cookie_file,
                    check_url=check_url,
                    base_url=base_url,
                    timeout=timeout,
                    max_notify=max_notify,
                    alert_cooldown_minutes=alert_cooldown_minutes,
                    dry_run=dry_run,
                    verbose=verbose,
                )
            except MonitorStopped as e:
                log("WARN", f"{e}（已退出循环）")
                return e.exit_code
            if verbose:
                log("DEBUG", f"sleep {interval_seconds}s")
            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        log("INFO", "收到中断信号，退出。")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="监控 iCity 朋友页新动态并合并推送到通知渠道")
    parser.add_argument("--config", default=None, help="配置文件路径（JSON）；默认自动读取 ./config.json（若存在）")
    parser.add_argument("--cookie-file", default=None, help="包含完整 Cookie 字符串的文件路径（覆盖配置）")
    parser.add_argument("--state-file", default=None, help="状态文件路径（覆盖配置）")
    parser.add_argument("--webhook", default=None, help="飞书自定义机器人 Webhook（兼容旧用法；提供后忽略 channels 配置）")
    parser.add_argument("--check-url", default=None, help="朋友页 URL（覆盖配置）")
    parser.add_argument("--base-url", default=None, help="用于拼接相对链接的 base URL（覆盖配置）")
    parser.add_argument("--timeout", type=int, default=None, help="请求超时（秒，覆盖配置）")
    parser.add_argument("--max-notify", type=int, default=None, help="单次最多展示的动态条数（覆盖配置）")
    parser.add_argument("--alert-cooldown-minutes", type=int, default=None, help="告警推送冷却时间（分钟，覆盖配置）")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--once", action="store_true", help="仅执行一次并退出（静默时段直接退出）")
    mode_group.add_argument("--loop", action="store_true", help="循环执行（需要配置 schedule.interval_minutes 或提供 config.json）")
    parser.add_argument("--dry-run", action="store_true", help="只打印不发送（仍会更新 state）")
    parser.add_argument("--verbose", action="store_true", help="输出更多日志")
    args = parser.parse_args()

    config_path = args.config
    if config_path is None and os.path.exists("config.json"):
        config_path = "config.json"
    try:
        config = load_config_file(config_path)
    except Exception as e:
        print(str(e), file=sys.stderr)
        return 2

    cookie_file = args.cookie_file if args.cookie_file is not None else (config.get("cookie_file") or "cookie.txt")
    state_file = args.state_file if args.state_file is not None else (config.get("state_file") or "state.json")
    check_url = args.check_url if args.check_url is not None else (config.get("check_url") or DEFAULT_CHECK_URL)
    base_url = args.base_url if args.base_url is not None else (config.get("base_url") or DEFAULT_BASE_URL)
    timeout = args.timeout if args.timeout is not None else int(config.get("timeout", 15))
    max_notify = args.max_notify if args.max_notify is not None else int(config.get("max_notify", 8))
    alert_cooldown_minutes = (
        args.alert_cooldown_minutes
        if args.alert_cooldown_minutes is not None
        else int(config.get("alert_cooldown_minutes", 60))
    )

    schedule = config.get("schedule")
    if schedule is None:
        schedule = {}
    if not isinstance(schedule, dict):
        print("配置项 schedule 必须是对象", file=sys.stderr)
        return 2
    quiet_hours = schedule.get("quiet_hours")
    if quiet_hours is None:
        quiet_hours = {}
    if not isinstance(quiet_hours, dict):
        print("配置项 schedule.quiet_hours 必须是对象", file=sys.stderr)
        return 2

    try:
        quiet_start = str(quiet_hours.get("start") or DEFAULT_QUIET_START)
        quiet_end = str(quiet_hours.get("end") or DEFAULT_QUIET_END)
        quiet_start_minutes = hhmm_to_minutes(quiet_start)
        quiet_end_minutes = hhmm_to_minutes(quiet_end)
    except Exception as e:
        print(str(e), file=sys.stderr)
        return 2

    schedule_enabled = bool(schedule.get("enabled", False))
    want_loop = bool(args.loop or (not args.once and schedule_enabled))
    interval_minutes = schedule.get("interval_minutes")
    if want_loop:
        if interval_minutes is None:
            print("循环模式缺少配置：schedule.interval_minutes", file=sys.stderr)
            return 2
        try:
            interval_minutes = int(interval_minutes)
        except Exception:
            print("schedule.interval_minutes 必须是整数", file=sys.stderr)
            return 2
        if interval_minutes <= 0:
            print("schedule.interval_minutes 必须 > 0", file=sys.stderr)
            return 2

    if timeout <= 0:
        print("timeout 必须 > 0", file=sys.stderr)
        return 2
    if max_notify <= 0:
        print("max_notify 必须 > 0", file=sys.stderr)
        return 2

    if args.webhook is None:
        env_webhook = (os.getenv("FEISHU_WEBHOOK") or "").strip()
        if env_webhook and not config.get("channels"):
            args.webhook = env_webhook

    try:
        channel = resolve_channel(args.webhook, config)
    except Exception as e:
        print(str(e), file=sys.stderr)
        print("提示：可通过 --webhook 直接指定飞书机器人，或在 config.json 里配置 channels。", file=sys.stderr)
        return 2

    try:
        cookie = read_cookie_file(cookie_file)
    except Exception as e:
        print(str(e), file=sys.stderr)
        return 2

    state = load_state(state_file)
    state.setdefault("last_checked_at", None)

    session = requests.Session()

    now_sh = shanghai_now()
    if in_quiet_window(now_sh, quiet_start_minutes, quiet_end_minutes) and not want_loop:
        if args.verbose:
            print("静默时段（上海时间 00:00-09:00），本次不执行。", file=sys.stderr)
        return 0

    if not want_loop and not args.once and config_path and config.get("schedule") is None and args.verbose:
        print("未配置 schedule，默认单次执行；如需循环请在 config.json 增加 schedule 或使用 --loop。", file=sys.stderr)

    if want_loop:
        return run_loop(
            session,
            channel,
            cookie,
            state,
            interval_minutes=interval_minutes,
            quiet_start_minutes=quiet_start_minutes,
            quiet_end_minutes=quiet_end_minutes,
            state_file=state_file,
            cookie_file=cookie_file,
            check_url=check_url,
            base_url=base_url,
            timeout=timeout,
            max_notify=max_notify,
            alert_cooldown_minutes=alert_cooldown_minutes,
            dry_run=args.dry_run,
            verbose=args.verbose,
        )

    try:
        return run_once(
            session,
            channel,
            cookie,
            state,
            state_file=state_file,
            cookie_file=cookie_file,
            check_url=check_url,
            base_url=base_url,
            timeout=timeout,
            max_notify=max_notify,
            alert_cooldown_minutes=alert_cooldown_minutes,
            dry_run=args.dry_run,
            verbose=args.verbose,
        )
    except MonitorStopped as e:
        return e.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
