"""阶段 A：Playwright 自动搜百度并抽取自然结果链接。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlparse


def _force_local_browsers_path() -> str:
    """Cursor 沙箱会注入 PLAYWRIGHT_BROWSERS_PATH 到空缓存，强制改回本机目录。"""
    home = Path.home() / "Library" / "Caches" / "ms-playwright"
    current = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "")
    sandboxish = (
        "cursor-sandbox-cache" in current
        or "/var/folders/" in current
        or not current
    )
    if home.exists() and (sandboxish or not Path(current).exists()):
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(home)
    return os.environ.get("PLAYWRIGHT_BROWSERS_PATH", str(home))


_force_local_browsers_path()

PROFILE_DIR = Path(__file__).resolve().parent / "data" / "browser_profile"


@dataclass
class SerpItem:
    rank: int
    url: str
    title: str


def _is_baidu_noise(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    if not host:
        return True
    noise = (
        "baidu.com",
        "bdstatic.com",
        "baiducontent.com",
        "bcebos.com",
        "baidubce.com",
        "baidu.com.hk",
    )
    return any(host == n or host.endswith("." + n) for n in noise)


def _looks_like_captcha(page) -> bool:
    title = page.title() or ""
    url = page.url or ""
    if "安全验证" in title:
        return True
    if "wappass.baidu.com" in url or "passport.baidu.com" in url:
        return True
    try:
        html = page.content()[:5000]
    except Exception:  # noqa: BLE001
        html = ""
    return "安全验证" in html and "content_left" not in html


def scrape_baidu_serp(
    keyword: str,
    *,
    limit: int = 20,
    headless: bool = False,
    timeout_ms: int = 60000,
    captcha_wait_ms: int = 120000,
) -> dict:
    """
    自动打开百度搜索并抽取结果。
    默认有界面（headless=False），更容易过验证；配置目录持久化 Cookie。
    """
    keyword = (keyword or "").strip()
    baidu_url = f"https://www.baidu.com/s?wd={quote(keyword)}&rn={min(max(limit, 10), 50)}"
    if not keyword:
        return {
            "ok": False,
            "items": [],
            "captcha": False,
            "error": "关键词为空",
            "baidu_url": baidu_url,
        }

    browsers_path = _force_local_browsers_path()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {
            "ok": False,
            "items": [],
            "captcha": False,
            "error": "未安装 playwright，请执行: pip install playwright && python -m playwright install chromium",
            "baidu_url": baidu_url,
        }

    items: list[SerpItem] = []
    captcha = False
    error = ""
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    try:
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(PROFILE_DIR),
                headless=headless,
                locale="zh-CN",
                viewport={"width": 1440, "height": 1100},
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
                args=["--disable-blink-features=AutomationControlled"],
            )
            page = context.pages[0] if context.pages else context.new_page()
            page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )

            # 先暖首页拿 Cookie，再搜
            page.goto("https://www.baidu.com/", wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(800)
            page.goto(baidu_url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(1500)

            if _looks_like_captcha(page):
                captcha = True
                if headless:
                    context.close()
                    return {
                        "ok": False,
                        "items": [],
                        "captcha": True,
                        "error": "无头模式触发百度验证码。请改用有界面自动抓取，或完成一次验证后重试。",
                        "baidu_url": baidu_url,
                    }
                # 有界面：等用户完成验证
                try:
                    page.wait_for_selector("#content_left h3 a, #content_left .c-container", timeout=captcha_wait_ms)
                    captcha = False
                except Exception:  # noqa: BLE001
                    context.close()
                    return {
                        "ok": False,
                        "items": [],
                        "captcha": True,
                        "error": "等待百度验证超时，请在弹出的浏览器里完成验证后重试。",
                        "baidu_url": baidu_url,
                    }

            try:
                page.wait_for_selector("#content_left", timeout=15000)
            except Exception:  # noqa: BLE001
                pass

            for _ in range(4):
                page.mouse.wheel(0, 1800)
                page.wait_for_timeout(350)

            raw = page.evaluate(
                """(limit) => {
                  const out = [];
                  const seen = new Set();
                  const push = (url, title) => {
                    url = (url || '').trim();
                    title = (title || '').trim();
                    if (!url || !title) return;
                    if (seen.has(url)) return;
                    seen.add(url);
                    out.push({ url, title });
                  };
                  const boxes = Array.from(document.querySelectorAll(
                    '#content_left .result, #content_left .c-container, #content_left > div[tpl], #content_left > div'
                  ));
                  for (const box of boxes) {
                    const mu = box.getAttribute('mu') || '';
                    const a = box.querySelector('h3 a') || box.querySelector('.c-title a') || box.querySelector('a');
                    const title = ((a && (a.innerText || a.textContent)) || '').trim();
                    if (mu) push(mu, title);
                    else if (a && a.href) push(a.href, title);
                    if (out.length >= limit) break;
                  }
                  return out.slice(0, limit);
                }""",
                limit,
            )

            for row in raw or []:
                url = (row.get("url") or "").strip()
                title_t = (row.get("title") or "").strip()
                if not url or not title_t:
                    continue
                real = _resolve_baidu_link(page, url)
                # mu 经常已是真实站；解析失败时若仍是百度跳转链则跳过
                if _is_baidu_noise(real):
                    continue
                items.append(SerpItem(rank=len(items) + 1, url=real, title=title_t))
                if len(items) >= limit:
                    break

            context.close()
    except Exception as e:  # noqa: BLE001
        error = str(e)

    return {
        "ok": len(items) > 0,
        "items": [{"rank": i.rank, "url": i.url, "title": i.title} for i in items],
        "captcha": captcha and not items,
        "error": error if not items else "",
        "baidu_url": baidu_url,
    }


def _resolve_baidu_link(page, url: str) -> str:
    if "baidu.com/link" not in url:
        return url
    try:
        resp = page.request.get(url, max_redirects=8, timeout=10000)
        final = resp.url
        if final and "baidu.com/link" not in final and not _is_baidu_noise(final):
            return final
    except Exception:  # noqa: BLE001
        pass
    return url
