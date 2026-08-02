"""阶段 B：读 SERP 报表 → 抓取/跟跳转 → 规则打标 → 入库。"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / "data" / "pipeline.db"
DEFAULT_CSV = ROOT / "data" / "serp_sample.csv"
# 打标偏速度：挂死站别等太久（垃圾站常超时）
DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=4.0)
DEFAULT_WORKERS = 8
MAX_SCRIPT_FETCH = 3

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
FETCH_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
}

RE_LOCATION_ASSIGN = re.compile(
    r"""(?:window\.)?location(?:\.href|\.replace)?\s*=\s*['"]([^'"]+)['"]""",
    re.I,
)
RE_LOCATION_REPLACE = re.compile(
    r"""location\.replace\(\s*['"]([^'"]+)['"]\s*\)""",
    re.I,
)
RE_SETTIMEOUT = re.compile(r"setTimeout\s*\(", re.I)
RE_PUSHSTATE = re.compile(r"history\.pushState\s*\(", re.I)
RE_POPSTATE = re.compile(r"popstate", re.I)

GAMBLING_WORDS = [
    "博彩", "赌场", "娱乐城", "开元", "葡京", "威尼斯人", "加拿大28",
    "六合彩", "时时彩", "彩票", "棋牌", "百家乐", "赌博", "投注",
]
USDT_WORDS = ["usdt", "trc20", "erc20", "泰达币", "稳定币充值"]
TG_PATTERNS = [
    re.compile(r"t\.me/", re.I),
    re.compile(r"telegram\.me/", re.I),
    re.compile(r"telegram", re.I),
    re.compile(r"飞机群|TG群|加.?TG", re.I),
]
# 成人/色情：偏标题与导流文案常见说法，避免过宽（如单独「成人」）
ADULT_WORDS = [
    "黄色网站", "黄网", "色情网站", "色情片", "色情视频", "色情直播", "色情导航",
    "成人视频", "成人直播", "成人网站", "成人片", "成人电影", "成人内容",
    "A片", "a片", "黄片", "毛片", "裸聊", "约炮", "无码", "有码",
    "AV女优", "性爱视频", "性爱直播", "十八禁", "18禁",
    "pornhub", "xvideos", "xnxx", "onlyfans", "javlibrary", "javdb",
]
ADULT_PATTERNS = [
    re.compile(r"\bxxx\b", re.I),
    re.compile(r"\bporn\b", re.I),
    re.compile(r"\bnsfw\b", re.I),
    re.compile(r"黄色|色情|成人[视直网电片]", re.I),
]


@dataclass
class SerpRow:
    keyword: str
    rank: Optional[int]
    url: str
    title: str = ""
    fetched_at: str = ""


@dataclass
class ProcessResult:
    keyword: str
    rank_no: Optional[int]
    serp_url: str
    title: str
    fetched_at: str
    final_url: str = ""
    is_js_redirect: bool = False
    jump_script: str = ""
    page_type: str = "unknown"
    tags: list[str] = field(default_factory=list)
    has_tg: bool = False
    has_usdt: bool = False
    has_gambling: bool = False
    has_adult: bool = False
    confidence: float = 0.0
    evidence: str = ""
    raw_excerpt: str = ""
    processed_at: str = ""
    backend: str = "httpx"


def load_serp_csv(path: Path) -> list[SerpRow]:
    rows: list[SerpRow] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for raw in reader:
            url = (raw.get("url") or "").strip()
            if not url or url.startswith("#"):
                continue
            rank_raw = (raw.get("rank") or "").strip()
            rows.append(
                SerpRow(
                    keyword=(raw.get("keyword") or "").strip(),
                    rank=int(rank_raw) if rank_raw.isdigit() else None,
                    url=url,
                    title=(raw.get("title") or "").strip(),
                    fetched_at=(raw.get("fetched_at") or "").strip(),
                )
            )
    return rows


def _abs_url(base: str, href: str) -> str:
    return urljoin(base, href)


def _alt_schemes(url: str) -> list[str]:
    out = [url]
    if url.startswith("http://"):
        out.append("https://" + url[len("http://") :])
    elif url.startswith("https://"):
        out.append("http://" + url[len("https://") :])
    # 去重保序
    seen = set()
    uniq = []
    for u in out:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq


def fetch_http(url: str, client: httpx.Client) -> tuple[str, str, str]:
    """返回 (final_http_url, html, error)。只跟 HTTP 重定向，不执行 JS。"""
    last_err = ""
    for cand in _alt_schemes(url):
        for _ in range(2):
            try:
                r = client.get(cand, follow_redirects=True)
                if r.status_code >= 400:
                    last_err = f"HTTP {r.status_code}"
                    continue
                text = r.text or ""
                if not text.strip():
                    last_err = "空响应"
                    continue
                return str(r.url), text, ""
            except Exception as e:  # noqa: BLE001
                last_err = f"{type(e).__name__}: {e}"
                continue
    return url, "", last_err or "抓取失败"


def classify_from_serp_meta(row: SerpRow, err: str) -> ProcessResult:
    """页面打不开时，仍用关键词+标题打成人/博彩等标签。"""
    blob = f"{row.keyword}\n{row.title}"
    has_tg, has_usdt, has_gambling, has_adult = text_signals(blob)
    tags: list[str] = ["抓取失败"]
    if has_adult:
        tags.append("疑似成人")
    if has_gambling:
        tags.append("博彩")
    if has_usdt:
        tags.append("USDT")
    if has_tg:
        tags.append("TG")

    if has_adult and has_gambling:
        page_type = "抓取失败·疑似成人/博彩"
    elif has_adult:
        page_type = "抓取失败·疑似成人"
    elif has_gambling:
        page_type = "抓取失败·博彩"
    else:
        page_type = "抓取失败"

    return ProcessResult(
        keyword=row.keyword,
        rank_no=row.rank,
        serp_url=row.url,
        title=row.title,
        fetched_at=row.fetched_at,
        final_url=row.url,
        page_type=page_type,
        tags=tags,
        has_tg=has_tg,
        has_usdt=has_usdt,
        has_gambling=has_gambling,
        has_adult=has_adult,
        confidence=0.35 if (has_adult or has_gambling) else 0.15,
        evidence=f"页面不可达，已按 SERP 标题/关键词标记；原因: {err}",
        processed_at=datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S"),
        backend="serp-meta",
    )


def extract_external_scripts(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html or "", "html.parser")
    out = []
    for s in soup.find_all("script"):
        src = s.get("src")
        if src:
            out.append(_abs_url(base_url, src))
    return out


def text_signals(blob: str) -> tuple[bool, bool, bool, bool]:
    low = blob.lower()
    has_tg = any(p.search(blob) for p in TG_PATTERNS)
    has_usdt = any(w in low for w in USDT_WORDS)
    has_gambling = any(
        w.lower() in low if w.isascii() else w in blob for w in GAMBLING_WORDS
    )
    has_adult = any(
        w.lower() in low if w.isascii() else w in blob for w in ADULT_WORDS
    ) or any(p.search(blob) for p in ADULT_PATTERNS)
    return has_tg, has_usdt, has_gambling, has_adult


def _find_js_jump(js: str, *, shell_hint: bool) -> tuple[str, str]:
    """返回 (target, evidence_msg)；无则 ('', '')。"""
    if not js:
        return "", ""
    has_timeout = bool(RE_SETTIMEOUT.search(js))
    m = RE_LOCATION_ASSIGN.search(js) or RE_LOCATION_REPLACE.search(js)
    if has_timeout and m:
        return m.group(1), f"setTimeout+location → {m.group(1)}"
    if m and shell_hint:
        return m.group(1), f"location 跳转 → {m.group(1)}"
    return "", ""


def analyze_js_redirect(
    html: str,
    base_url: str,
    client: httpx.Client,
    *,
    fetch_landing: bool = True,
    max_scripts: int = MAX_SCRIPT_FETCH,
) -> dict:
    """静态分析：壳页 + 外链 JS 里的 setTimeout/location。"""
    evidence = []
    jump_script = ""
    target = ""
    scripts = extract_external_scripts(html, base_url)
    soup = BeautifulSoup(html or "", "html.parser")
    inline = "\n".join(
        s.get_text() or ""
        for s in soup.find_all("script")
        if not s.get("src")
    )

    body_text = (soup.body.get_text(" ", strip=True) if soup.body else "")[:500]
    title = (soup.title.get_text(strip=True) if soup.title else "")
    shell_hint = (
        len(body_text) < 40
        or "加载" in title
        or "loading" in title.lower()
        or bool(soup.find("meta", attrs={"name": "robots", "content": re.compile("noindex", re.I)}))
    )
    if shell_hint and scripts:
        evidence.append("壳页特征(正文少/加载中/noindex)+外链脚本")

    # 先看内联，命中就不再拉外链脚本
    target, msg = _find_js_jump(inline, shell_hint=shell_hint)
    if target:
        jump_script = "(inline)"
        evidence.append(msg)
    else:
        fetched: dict[str, str] = {}

        def _get_js(src: str) -> tuple[str, str]:
            try:
                return src, client.get(src).text
            except Exception:  # noqa: BLE001
                return src, ""

        srcs = scripts[: max(0, max_scripts)]
        if srcs:
            # 少量并发拉脚本
            with ThreadPoolExecutor(max_workers=min(3, len(srcs))) as pool:
                for src, js in pool.map(lambda u: _get_js(u), srcs):
                    fetched[src] = js

        for src in srcs:
            t, msg = _find_js_jump(fetched.get(src, ""), shell_hint=shell_hint)
            if t:
                target, jump_script = t, src
                evidence.append(msg)
                break

    landing_html = ""
    final_url = base_url
    if target and fetch_landing:
        target_abs = _abs_url(base_url, target)
        final_url, landing_html, err = fetch_http(target_abs, client)
        if err:
            evidence.append(f"落地抓取失败: {err}")
            final_url = target_abs
        else:
            if RE_PUSHSTATE.search(landing_html) and RE_POPSTATE.search(landing_html):
                evidence.append("落地页含 pushState+popstate(后退劫持)")
    elif target:
        final_url = _abs_url(base_url, target)

    return {
        "final_url": final_url if target else base_url,
        "is_js_redirect": bool(target),
        "jump_script": jump_script,
        "evidence": evidence,
        "landing_html": landing_html,
        "shell_hint": shell_hint,
    }


async def try_crawl4ai(url: str) -> Optional[dict]:
    try:
        from crawl4ai import AsyncWebCrawler, CrawlerRunConfig  # type: ignore
    except Exception:
        return None

    try:
        config = CrawlerRunConfig(wait_until="networkidle", delay_before_return_html=1.0)
    except TypeError:
        config = None

    async with AsyncWebCrawler() as crawler:
        if config is not None:
            result = await crawler.arun(url=url, config=config)
        else:
            result = await crawler.arun(url=url)

    final = getattr(result, "url", None) or url
    html = getattr(result, "html", None) or ""
    md = getattr(result, "markdown", None) or ""
    redirected = str(final).rstrip("/") != url.rstrip("/")
    return {
        "final_url": str(final),
        "html": html,
        "markdown": str(md)[:4000],
        "is_browser_redirect": redirected,
        "backend": "crawl4ai",
    }


def classify(row: SerpRow, analysis: dict, page_blob: str) -> ProcessResult:
    has_tg, has_usdt, has_gambling, has_adult = text_signals(page_blob)
    tags: list[str] = []
    evidence = list(analysis.get("evidence") or [])

    is_js = bool(analysis.get("is_js_redirect"))
    if is_js:
        tags.append("JS延迟跳转")
    if analysis.get("shell_hint"):
        tags.append("入口壳站")
    if any("popstate" in e for e in evidence):
        tags.append("后退劫持")
    if has_adult:
        tags.append("疑似成人")
        evidence.append("命中成人/色情关键词")
    if has_gambling:
        tags.append("博彩")
    if has_usdt:
        tags.append("USDT")
    if has_tg:
        tags.append("TG")

    if is_js and analysis.get("shell_hint"):
        page_type = "跳转壳站"
        confidence = 0.9
    elif is_js:
        page_type = "客户端跳转"
        confidence = 0.75
    elif has_adult:
        page_type = "疑似成人"
        confidence = 0.72
    elif has_gambling:
        page_type = "博彩内容站"
        confidence = 0.7
    else:
        page_type = "普通站"
        confidence = 0.55

    # 规则先判；预留 LLM 钩子（有 OPENAI_API_KEY 时可扩展）
    return ProcessResult(
        keyword=row.keyword,
        rank_no=row.rank,
        serp_url=row.url,
        title=row.title,
        fetched_at=row.fetched_at,
        final_url=analysis.get("final_url") or row.url,
        is_js_redirect=is_js,
        jump_script=analysis.get("jump_script") or "",
        page_type=page_type,
        tags=tags,
        has_tg=has_tg,
        has_usdt=has_usdt,
        has_gambling=has_gambling or ("博彩" in tags),
        has_adult=has_adult or ("疑似成人" in tags),
        confidence=confidence,
        evidence="; ".join(evidence),
        raw_excerpt=page_blob[:800],
        processed_at=datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S"),
        backend=analysis.get("backend") or "httpx",
    )


def process_one(
    row: SerpRow,
    client: httpx.Client,
    prefer_crawl4ai: bool,
    *,
    fetch_landing: bool = True,
    max_scripts: int = MAX_SCRIPT_FETCH,
) -> ProcessResult:
    backend = "httpx"
    html = ""
    final_from_browser = ""
    md = ""

    if prefer_crawl4ai:
        import asyncio

        try:
            c4 = asyncio.run(try_crawl4ai(row.url))
        except Exception:  # noqa: BLE001
            c4 = None
        if c4:
            backend = "crawl4ai"
            html = c4.get("html") or ""
            md = c4.get("markdown") or ""
            final_from_browser = c4.get("final_url") or ""

    err = ""
    if not html:
        _, html, err = fetch_http(row.url, client)
        if err:
            # 多数失败是站已失效/超时；仍按搜索标题打成人/博彩
            return classify_from_serp_meta(row, err)

    analysis = analyze_js_redirect(
        html,
        row.url,
        client,
        fetch_landing=fetch_landing,
        max_scripts=max_scripts,
    )
    analysis["backend"] = backend
    if final_from_browser and not analysis["is_js_redirect"]:
        # 浏览器已跳到别处
        if final_from_browser.rstrip("/") != row.url.rstrip("/"):
            analysis["is_js_redirect"] = True
            analysis["final_url"] = final_from_browser
            analysis["evidence"] = list(analysis.get("evidence") or []) + ["Crawl4AI 最终 URL 变化"]

    landing = analysis.get("landing_html") or ""
    # 落地页广告文案常在后半段，抽可见文本再拼，避免只扫到 head
    visible = ""
    for chunk in (html, landing):
        if not chunk:
            continue
        soup = BeautifulSoup(chunk, "html.parser")
        visible += "\n" + soup.get_text(" ", strip=True)[:8000]
    blob = "\n".join(
        [row.keyword, row.title, html[:6000], landing[:12000], visible, md]
    )
    result = classify(row, analysis, blob)
    result.backend = backend
    return result


def _new_client() -> httpx.Client:
    return httpx.Client(
        headers=FETCH_HEADERS,
        timeout=DEFAULT_TIMEOUT,
        follow_redirects=True,
        verify=False,  # 垃圾站证书常坏
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
    )


def process_rows(
    rows: list[SerpRow],
    *,
    prefer_crawl4ai: bool = False,
    workers: int = DEFAULT_WORKERS,
    fetch_landing: bool = True,
    max_scripts: int = MAX_SCRIPT_FETCH,
    on_done: Optional[Callable[[int, int, ProcessResult], None]] = None,
) -> list[ProcessResult]:
    """并发打标；按完成顺序回调 on_done(done, total, result)。"""
    total = len(rows)
    if total == 0:
        return []

    # Crawl4AI 内部 asyncio，并发不安全，强制串行
    if prefer_crawl4ai:
        workers = 1

    workers = max(1, min(int(workers or DEFAULT_WORKERS), 16))
    results: list[ProcessResult] = []
    done = 0

    def work(row: SerpRow) -> ProcessResult:
        with _new_client() as client:
            return process_one(
                row,
                client,
                prefer_crawl4ai,
                fetch_landing=fetch_landing,
                max_scripts=max_scripts,
            )

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(work, row): row for row in rows}
        for fut in as_completed(futs):
            r = fut.result()
            results.append(r)
            done += 1
            if on_done:
                on_done(done, total, r)
    return results


def init_sqlite(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS serp_results (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          keyword TEXT NOT NULL,
          rank_no INTEGER,
          serp_url TEXT NOT NULL,
          title TEXT,
          fetched_at TEXT,
          final_url TEXT,
          is_js_redirect INTEGER DEFAULT 0,
          jump_script TEXT,
          page_type TEXT,
          tags_json TEXT,
          has_tg INTEGER DEFAULT 0,
          has_usdt INTEGER DEFAULT 0,
          has_gambling INTEGER DEFAULT 0,
          has_adult INTEGER DEFAULT 0,
          confidence REAL,
          evidence TEXT,
          raw_excerpt TEXT,
          processed_at TEXT,
          backend TEXT,
          UNIQUE(keyword, serp_url)
        )
        """
    )
    cols = {row[1] for row in conn.execute("PRAGMA table_info(serp_results)")}
    if "has_adult" not in cols:
        conn.execute(
            "ALTER TABLE serp_results ADD COLUMN has_adult INTEGER DEFAULT 0"
        )
    conn.commit()
    return conn


def upsert_sqlite(conn: sqlite3.Connection, r: ProcessResult) -> None:
    conn.execute(
        """
        INSERT INTO serp_results (
          keyword, rank_no, serp_url, title, fetched_at, final_url,
          is_js_redirect, jump_script, page_type, tags_json,
          has_tg, has_usdt, has_gambling, has_adult, confidence, evidence,
          raw_excerpt, processed_at, backend
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(keyword, serp_url) DO UPDATE SET
          rank_no=excluded.rank_no,
          title=excluded.title,
          final_url=excluded.final_url,
          is_js_redirect=excluded.is_js_redirect,
          jump_script=excluded.jump_script,
          page_type=excluded.page_type,
          tags_json=excluded.tags_json,
          has_tg=excluded.has_tg,
          has_usdt=excluded.has_usdt,
          has_gambling=excluded.has_gambling,
          has_adult=excluded.has_adult,
          confidence=excluded.confidence,
          evidence=excluded.evidence,
          raw_excerpt=excluded.raw_excerpt,
          processed_at=excluded.processed_at,
          backend=excluded.backend
        """,
        (
            r.keyword,
            r.rank_no,
            r.serp_url,
            r.title,
            r.fetched_at,
            r.final_url,
            int(r.is_js_redirect),
            r.jump_script,
            r.page_type,
            json.dumps(r.tags, ensure_ascii=False),
            int(r.has_tg),
            int(r.has_usdt),
            int(r.has_gambling),
            int(r.has_adult),
            r.confidence,
            r.evidence,
            r.raw_excerpt,
            r.processed_at,
            r.backend,
        ),
    )
    conn.commit()


def print_result(r: ProcessResult) -> None:
    print("-" * 60)
    print(f"[{r.rank_no}] {r.keyword} | {r.page_type} | conf={r.confidence}")
    print(f"  SERP : {r.serp_url}")
    print(f"  FINAL: {r.final_url}")
    print(
        f"  JS跳转={r.is_js_redirect}  成人={r.has_adult}  "
        f"博彩={r.has_gambling}  TG={r.has_tg}  USDT={r.has_usdt}"
    )
    print(f"  标签: {', '.join(r.tags) or '-'}")
    print(f"  证据: {r.evidence or '-'}")
    print(f"  后端: {r.backend}")


def main() -> int:
    parser = argparse.ArgumentParser(description="阶段 B：处理 SERP 报表")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV, help="阶段 A 导出的 CSV")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite 路径（默认可先跑通）")
    parser.add_argument("--limit", type=int, default=0, help="只处理前 N 条，0=全部")
    parser.add_argument("--crawl4ai", action="store_true", help="若已安装则优先用 Crawl4AI")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help="并发数（默认 8）")
    parser.add_argument(
        "--fast",
        action="store_true",
        help="快速模式：少拉脚本、不跟落地页",
    )
    parser.add_argument("--json-out", type=Path, default=None, help="额外导出 JSON 结果")
    args = parser.parse_args()

    if not args.csv.exists():
        print(f"找不到 CSV: {args.csv}", file=sys.stderr)
        return 1

    rows = load_serp_csv(args.csv)
    if args.limit:
        rows = rows[: args.limit]
    print(f"读取 {len(rows)} 条 → {args.csv}（workers={args.workers}）")

    conn = init_sqlite(args.db)
    results: list[ProcessResult] = []

    def _on_done(done: int, total: int, r: ProcessResult) -> None:
        print(f"[{done}/{total}] {r.serp_url}")
        upsert_sqlite(conn, r)
        print_result(r)
        results.append(r)

    process_rows(
        rows,
        prefer_crawl4ai=args.crawl4ai,
        workers=args.workers,
        fetch_landing=not args.fast,
        max_scripts=2 if args.fast else MAX_SCRIPT_FETCH,
        on_done=_on_done,
    )

    conn.close()
    print("=" * 60)
    print(f"已写入 SQLite: {args.db}")
    print("查询示例: sqlite3 data/pipeline.db \"SELECT keyword,page_type,final_url,has_gambling FROM serp_results;\"")

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps([asdict(r) for r in results], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"JSON: {args.json_out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
