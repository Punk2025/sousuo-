"""阶段 A：Playwright 自动搜百度并抽取自然结果链接。"""

from __future__ import annotations

import os
import platform
import subprocess
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


# 百度自身噪声
_BAIDU_NOISE = (
    "baidu.com",
    "bdstatic.com",
    "baiducontent.com",
    "bcebos.com",
    "baidubce.com",
    "baidu.com.hk",
)

# 抓取时自动跳过的大型平台 / 大公司域名（后缀匹配）
MAJOR_SKIP_DOMAINS = (
    # 视频
    "iqiyi.com",
    "qiyi.com",
    "iqiyi.cn",
    "youku.com",
    "tudou.com",
    "v.qq.com",
    "video.qq.com",
    "film.qq.com",
    "mgtv.com",
    "pptv.com",
    "miguvideo.com",
    "bilibili.com",
    "b23.tv",
    "douyin.com",
    "iesdouyin.com",
    "ixigua.com",
    "kuaishou.com",
    "acfun.cn",
    # 门户 / 资讯大厂
    "qq.com",  # 含腾讯系多数子域；视频已单独列出，整站大厂一并避开
    "sohu.com",
    "sina.com.cn",
    "sina.cn",
    "weibo.com",
    "weibo.cn",
    "163.com",
    "126.com",
    "yeah.net",
    "ifeng.com",
    "toutiao.com",
    "zhihu.com",
    "zhihu.cn",
    # 电商 / 支付 / 云
    "taobao.com",
    "tmall.com",
    "alibaba.com",
    "aliyun.com",
    "alipay.com",
    "jd.com",
    "jd.hk",
    "pinduoduo.com",
    "yangkeduo.com",
    "suning.com",
    # 出行 / 本地生活
    "ctrip.com",
    "qunar.com",
    "meituan.com",
    "dianping.com",
    "ele.me",
    # 其他常见大站
    "xiaohongshu.com",
    "xhs.cn",
    "mi.com",
    "huawei.com",
    "vmall.com",
)


def _host_of(url: str) -> str:
    host = (urlparse(url).netloc or "").lower().strip()
    if host.startswith("www."):
        host = host[4:]
    return host


def _host_matches(host: str, suffix: str) -> bool:
    return host == suffix or host.endswith("." + suffix)


def _is_baidu_noise(url: str) -> bool:
    host = _host_of(url)
    if not host:
        return True
    return any(_host_matches(host, n) for n in _BAIDU_NOISE)


def is_major_skip_domain(url: str) -> bool:
    """是否应在报表中跳过（百度噪声 + 爱奇艺/腾讯等大厂）。"""
    if _is_baidu_noise(url):
        return True
    host = _host_of(url)
    if not host:
        return True
    return any(_host_matches(host, n) for n in MAJOR_SKIP_DOMAINS)


def _is_skipped_result(url: str) -> bool:
    return is_major_skip_domain(url)


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


def _set_window_state(page, state: str) -> None:
    """通过 CDP 控制窗口：minimized / normal。失败则静默忽略。"""
    try:
        cdp = page.context.new_cdp_session(page)
        info = cdp.send("Browser.getWindowForTarget")
        window_id = info.get("windowId")
        if not window_id:
            return
        cdp.send(
            "Browser.setWindowBounds",
            {"windowId": window_id, "bounds": {"windowState": state}},
        )
    except Exception:  # noqa: BLE001
        pass


def _bring_browser_front() -> None:
    """macOS：把 Chromium / Chrome for Testing 拉到前台（验证码时用）。"""
    if platform.system() != "Darwin":
        return
    script = """
    tell application "System Events"
      set names to {"Chromium", "Chrome for Testing", "Google Chrome for Testing", "Google Chrome"}
      repeat with n in names
        if exists process n then
          set frontmost of process n to true
          return
        end if
      end repeat
    end tell
    """
    try:
        subprocess.run(
            ["osascript", "-e", script],
            check=False,
            capture_output=True,
            timeout=5,
        )
    except Exception:  # noqa: BLE001
        pass


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
    默认有界面但后台最小化；遇验证码再拉到前台。Cookie 持久化。
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

    _force_local_browsers_path()
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
    skipped_major = 0
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    try:
        with sync_playwright() as p:
            launch_args = [
                "--disable-blink-features=AutomationControlled",
                "--window-position=80,80",
            ]
            # Linux 可启动即最小化；macOS 用 CDP 再压下去
            if platform.system() == "Linux":
                launch_args.append("--start-minimized")

            context = p.chromium.launch_persistent_context(
                user_data_dir=str(PROFILE_DIR),
                headless=headless,
                locale="zh-CN",
                viewport={"width": 1280, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
                args=launch_args,
            )
            page = context.pages[0] if context.pages else context.new_page()
            page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )

            # 有界面：尽快最小化，少抢当前工作窗口
            if not headless:
                page.wait_for_timeout(200)
                _set_window_state(page, "minimized")

            # 先暖首页拿 Cookie，再搜
            page.goto("https://www.baidu.com/", wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(800)
            if not headless:
                _set_window_state(page, "minimized")
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
                # 验证码：恢复窗口并拉到前台，等人过完再继续
                _set_window_state(page, "normal")
                _bring_browser_front()
                try:
                    page.wait_for_selector(
                        "#content_left h3 a, #content_left .c-container",
                        timeout=captcha_wait_ms,
                    )
                    captcha = False
                    _set_window_state(page, "minimized")
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

            # 多抓一些候选，过滤大厂域名后仍尽量凑满 limit
            fetch_n = min(50, max(limit * 3, limit + 15))
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
                fetch_n,
            )

            for row in raw or []:
                url = (row.get("url") or "").strip()
                title_t = (row.get("title") or "").strip()
                if not url or not title_t:
                    continue
                real = _resolve_baidu_link(page, url)
                # 跳过百度噪声 + 爱奇艺/腾讯视频等大厂域名
                if _is_skipped_result(real):
                    skipped_major += 1
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
        "skipped_major": skipped_major,
    }


def _resolve_baidu_link(page, url: str) -> str:
    if "baidu.com/link" not in url:
        return url
    try:
        resp = page.request.get(url, max_redirects=8, timeout=10000)
        final = resp.url
        if final and "baidu.com/link" not in final and not _is_skipped_result(final):
            return final
    except Exception:  # noqa: BLE001
        pass
    return url
