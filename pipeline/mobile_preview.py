"""用 Playwright 按 iPhone 设备参数打开链接，模拟 Chrome 手机模式筛站。

Playwright sync API 必须在同一线程使用，因此用专用工作线程持有浏览器。
"""

from __future__ import annotations

import queue
import threading
from typing import Any

import baidu_serp

_cmd_q: queue.Queue = queue.Queue()
_worker_started = False
_worker_lock = threading.Lock()


def _iphone_kwargs(playwright) -> dict:
    for name in (
        "iPhone 15 Pro",
        "iPhone 14 Pro",
        "iPhone 13 Pro",
        "iPhone 12 Pro",
        "iPhone 13",
        "iPhone 12",
    ):
        if name in playwright.devices:
            return dict(playwright.devices[name])
    return {
        "viewport": {"width": 393, "height": 852},
        "user_agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 "
            "Mobile/15E148 Safari/604.1"
        ),
        "device_scale_factor": 3,
        "is_mobile": True,
        "has_touch": True,
    }


def _worker_main() -> None:
    baidu_serp._force_local_browsers_path()
    from playwright.sync_api import sync_playwright

    pw = None
    browser = None
    context = None

    def ensure_context():
        nonlocal pw, browser, context
        if context is not None:
            try:
                _ = context.pages
                return context
            except Exception:  # noqa: BLE001
                context = None
                browser = None

        if pw is None:
            pw = sync_playwright().start()

        device = _iphone_kwargs(pw)
        device.pop("default_browser_type", None)

        browser = pw.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(**device)
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        return context

    def do_close():
        nonlocal pw, browser, context
        try:
            if context:
                context.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            if browser:
                browser.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            if pw:
                pw.stop()
        except Exception:  # noqa: BLE001
            pass
        context = None
        browser = None
        pw = None

    while True:
        job = _cmd_q.get()
        op = job.get("op")
        box: dict[str, Any] = job["box"]
        done: threading.Event = job["done"]
        try:
            if op == "close":
                do_close()
                box["result"] = {"ok": True}
            elif op == "open":
                urls = job.get("urls") or []
                timeout_ms = int(job.get("timeout_ms") or 45000)
                cleaned: list[str] = []
                seen: set[str] = set()
                for raw in urls:
                    u = (raw or "").strip()
                    if not u or u in seen:
                        continue
                    if not u.startswith(("http://", "https://")):
                        continue
                    seen.add(u)
                    cleaned.append(u)
                if not cleaned:
                    box["result"] = {
                        "ok": False,
                        "opened": 0,
                        "error": "没有可打开的链接",
                    }
                else:
                    errors: list[str] = []
                    opened = 0
                    try:
                        ctx = ensure_context()
                    except Exception as e:  # noqa: BLE001
                        box["result"] = {
                            "ok": False,
                            "opened": 0,
                            "error": f"无法启动手机模拟浏览器：{e}",
                        }
                    else:
                        for u in cleaned:
                            try:
                                page = ctx.new_page()
                                page.goto(
                                    u,
                                    wait_until="domcontentloaded",
                                    timeout=timeout_ms,
                                )
                                opened += 1
                            except Exception as e:  # noqa: BLE001
                                errors.append(f"{u[:80]} → {e}")
                        try:
                            baidu_serp._bring_browser_front()
                        except Exception:  # noqa: BLE001
                            pass
                        box["result"] = {
                            "ok": opened > 0,
                            "opened": opened,
                            "total": len(cleaned),
                            "errors": errors[:8],
                            "error": (
                                ""
                                if opened
                                else (errors[0] if errors else "全部打开失败")
                            ),
                        }
            else:
                box["result"] = {"ok": False, "error": f"未知操作：{op}"}
        except Exception as e:  # noqa: BLE001
            box["result"] = {"ok": False, "opened": 0, "error": str(e)}
        finally:
            done.set()


def _ensure_worker() -> None:
    global _worker_started
    with _worker_lock:
        if _worker_started:
            return
        t = threading.Thread(target=_worker_main, name="mobile-preview", daemon=True)
        t.start()
        _worker_started = True


def _run(op: str, **kwargs) -> dict:
    _ensure_worker()
    box: dict[str, Any] = {}
    done = threading.Event()
    _cmd_q.put({"op": op, "box": box, "done": done, **kwargs})
    if not done.wait(timeout=180):
        return {"ok": False, "opened": 0, "error": "手机模拟打开超时（180s）"}
    return box.get("result") or {"ok": False, "error": "无结果"}


def open_urls_mobile(urls: list[str], *, timeout_ms: int = 45000) -> dict:
    """在手机模拟浏览器里打开一组链接（每个 URL 一个标签）。"""
    return _run("open", urls=list(urls), timeout_ms=timeout_ms)


def close_mobile_preview() -> dict:
    """关闭手机模拟浏览器。"""
    return _run("close")
