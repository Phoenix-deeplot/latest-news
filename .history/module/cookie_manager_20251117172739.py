# modules/cookie_manager.py
from pathlib import Path
import json
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError

STORAGE_PATH = Path("playwright_storage_state.json")
# 默认的“认为需要刷新”的阈值（秒），比如 60*60*6 = 6 小时
REFRESH_THRESHOLD_SECONDS = 60 * 60 * 6

def fetch_and_save_storage_state(url: str, headless: bool = True, timeout_ms: int = 30000) -> None:
    """
    用 Playwright 打开 url 并保存 storage_state（cookies + localStorage）到 STORAGE_PATH。
    若首次需要手动登录，建议把 headless=False，手动完成登录后关闭浏览器，函数会保存状态。
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, args=["--no-sandbox"])
        context_args = {}
        # 如果已有旧状态，可以复用避免重复登录（可注释掉以强制新建）
        if STORAGE_PATH.exists():
            context_args["storage_state"] = str(STORAGE_PATH)

        context = browser.new_context(**context_args)
        page = context.new_page()
        try:
            page.goto(url, timeout=timeout_ms)
            # 等待页面稳定加载（按需可改为等待某个选择器）
            try:
                page.wait_for_load_state("networkidle", timeout=timeout_ms)
            except PWTimeoutError:
                page.wait_for_load_state("domcontentloaded", timeout=5000)
            # 这里可以选择截屏或检查页面以确认登录完成
        finally:
            # 保存 storage state（包含 cookies 和 localStorage）
            try:
                context.storage_state(path=str(STORAGE_PATH))
            except Exception as e:
                print("warning: failed to save storage_state:", e)
            try:
                context.close()
            except Exception:
                pass
            try:
                browser.close()
            except Exception:
                pass

def load_storage_state() -> Optional[Dict[str, Any]]:
    """读取 storage_state.json 内容并返回 dict（或 None）。"""
    if not STORAGE_PATH.exists():
        return None
    try:
        return json.loads(STORAGE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None

def cookies_from_storage() -> Dict[str, str]:
    """
    从 storage_state.json 中抽取 cookie 为简单的字典 {name: value}。
    如果没有文件返回空 dict。
    """
    st = load_storage_state()
    if not st:
        return {}
    cookies = st.get("cookies") or st.get("cookies", [])
    result = {}
    for c in cookies:
        # c 是 dict，包含 name, value, expires, domain, path, etc.
        result[c.get("name")] = c.get("value")
    return result

def storage_state_latest_expires() -> Optional[int]:
    """
    返回 storage_state 中 cookie 的最大 expires（unix 秒）。如果没有 expires，返回 None。
    """
    st = load_storage_state()
    if not st:
        return None
    cookies = st.get("cookies", [])
    max_ex = None
    for c in cookies:
        ex = c.get("expires")
        if ex:
            try:
                ex = int(ex)
            except Exception:
                continue
            if max_ex is None or ex > max_ex:
                max_ex = ex
    return max_ex

def needs_refresh(threshold_seconds: int = REFRESH_THRESHOLD_SECONDS) -> bool:
    """
    判断是否需要刷新：当没有 storage_state 或 cookie 已过期或距过期小于 threshold_seconds 时返回 True。
    """
    max_ex = storage_state_latest_expires()
    if max_ex is None:
        # 没有 expires 信息或没有文件，认为需要刷新
        return True
    now_ts = int(time.time())
    if max_ex <= now_ts:
        return True
    # 如果离过期时间小于阈值，则需要提前刷新
    if (max_ex - now_ts) < threshold_seconds:
        return True
    return False

# 一个简单的循环刷新器（可在后台线程或单独进程中运行）
def periodic_refresh_loop(url: str, interval_seconds: int = 60 * 60 * 6, headless: bool = True, run_once: bool = False):
    """
    持续运行：每 interval_seconds 检查一次是否需要刷新（needs_refresh），如需刷新则调用 fetch_and_save_storage_state。
    run_once=True 时仅检查并刷新一次后返回。
    """
    while True:
        try:
            if needs_refresh():
                print(f"[cookie_manager] needs refresh, fetching {url} ...")
                fetch_and_save_storage_state(url, headless=headless)
                print("[cookie_manager] storage_state updated.")
            else:
                print("[cookie_manager] storage_state still valid; no refresh needed.")
        except Exception as e:
            print("[cookie_manager] refresh failed:", e)
        if run_once:
            break
        time.sleep(interval_seconds)

if __name__ == "__main__":
    # 简单命令行调用：第一次用 headless=False 手动登录（如需），之后可切换 headless=True
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True, help="登录或首页 URL, e.g. https://www.bloomberg.com")
    parser.add_argument("--headless", action="store_true", help="是否使用 headless 模式")
    parser.add_argument("--once", action="store_true", help="只运行一次检查/刷新")
    args = parser.parse_args()
    periodic_refresh_loop(args.url, interval_seconds=60*60*6, headless=(args.headless), run_once=args.once)
