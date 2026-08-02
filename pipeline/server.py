#!/usr/bin/env python3
"""搜索管线后台：看结果、贴 SERP 报表、一键跑阶段 B。"""

from __future__ import annotations

import csv
import io
import sqlite3
import threading
from datetime import date
from pathlib import Path
from urllib.parse import quote, urlparse

from flask import Flask, Response, jsonify, redirect, render_template, request

import baidu_serp
import phase_b_process as pipeline
import report_table
import search_history

# 覆盖 Cursor 注入的沙箱 Playwright 路径
baidu_serp._force_local_browsers_path()

ROOT = Path(__file__).resolve().parent
DB = ROOT / "data" / "pipeline.db"
CSV_PATH = ROOT / "data" / "serp_working.csv"
SAMPLE_CSV = ROOT / "data" / "serp_sample.csv"

app = Flask(__name__, template_folder="templates", static_folder="static")

_job_lock = threading.Lock()
_job = {
    "running": False,
    "log": [],
    "last_error": "",
    "errors": [],  # 仅报错：[{time, keyword, message}]
    "phase": "idle",  # idle|baidu|report|tagging|done|error
    "phase_label": "空闲",
    "current": 0,
    "total": 0,
    "percent": 0,
    "detail": "",
    "keyword": "",
    "kw_index": 0,
    "kw_total": 0,
    "mode": "single",  # single|batch
}


def _push_error(message: str, keyword: str = "") -> None:
    from datetime import datetime, timezone

    msg = (message or "").strip()
    if not msg:
        return
    # 友好提示：浏览器路径问题
    tip = ""
    if "Executable doesn't exist" in msg or "playwright install" in msg.lower():
        tip = "浏览器未就绪：请在本机终端执行 python3 -m playwright install chromium 后，用 ./start.sh 重启后台。"
    entry = {
        "time": datetime.now(timezone.utc).astimezone().strftime("%H:%M:%S"),
        "keyword": keyword or _job.get("keyword") or "",
        "message": msg[:500],
        "tip": tip,
    }
    errs = list(_job.get("errors") or [])
    errs.append(entry)
    _job["errors"] = errs[-30:]
    _job["last_error"] = msg[:500]


def _set_progress(
    *,
    running: bool | None = None,
    phase: str | None = None,
    phase_label: str | None = None,
    current: int | None = None,
    total: int | None = None,
    percent: int | None = None,
    detail: str | None = None,
    keyword: str | None = None,
    last_error: str | None = None,
    log_line: str | None = None,
    kw_index: int | None = None,
    kw_total: int | None = None,
    mode: str | None = None,
) -> None:
    with _job_lock:
        if running is not None:
            _job["running"] = running
        if phase is not None:
            _job["phase"] = phase
        if phase_label is not None:
            _job["phase_label"] = phase_label
        if current is not None:
            _job["current"] = current
        if total is not None:
            _job["total"] = total
        if percent is not None:
            _job["percent"] = max(0, min(100, int(percent)))
        if detail is not None:
            _job["detail"] = detail
        if keyword is not None:
            _job["keyword"] = keyword
        if kw_index is not None:
            _job["kw_index"] = kw_index
        if kw_total is not None:
            _job["kw_total"] = kw_total
        if mode is not None:
            _job["mode"] = mode
        if log_line is not None:
            logs = list(_job.get("log") or [])
            logs.append(log_line)
            _job["log"] = logs[-80:]
        if last_error is not None:
            if last_error:
                _push_error(last_error, keyword or _job.get("keyword") or "")
            else:
                _job["last_error"] = ""


def db_conn() -> sqlite3.Connection:
    pipeline.init_sqlite(DB)
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    return conn


def ensure_working_csv() -> None:
    if not CSV_PATH.exists():
        CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
        # 空工作区起步；示例数据不再自动灌入当前报表
        CSV_PATH.write_text(
            "keyword,rank,url,title,fetched_at\n",
            encoding="utf-8",
        )


def _prepare_new_search(title: str = "") -> dict | None:
    """新搜索前：把当前报表归档到「搜索记录」，再清空工作区。"""
    archived = search_history.archive_current(
        ROOT, csv_path=CSV_PATH, db_path=DB, title=title
    )
    search_history.clear_workspace(CSV_PATH, DB)
    return archived


@app.get("/")
def home():
    return redirect("/admin/")


@app.get("/admin/")
def admin():
    ensure_working_csv()
    return render_template("admin.html")


@app.get("/admin/history/")
def admin_history():
    return render_template("history.html")


@app.get("/api/stats")
def api_stats():
    conn = db_conn()
    total = conn.execute("SELECT COUNT(*) AS c FROM serp_results").fetchone()["c"]
    shells = conn.execute(
        "SELECT COUNT(*) AS c FROM serp_results WHERE is_js_redirect=1"
    ).fetchone()["c"]
    gambling = conn.execute(
        "SELECT COUNT(*) AS c FROM serp_results WHERE has_gambling=1"
    ).fetchone()["c"]
    try:
        adult = conn.execute(
            "SELECT COUNT(*) AS c FROM serp_results WHERE has_adult=1"
        ).fetchone()["c"]
    except sqlite3.OperationalError:
        adult = 0
    conn.close()
    return jsonify(
        {
            "total": total,
            "js_redirect": shells,
            "gambling": gambling,
            "adult": adult,
            "csv_path": str(CSV_PATH),
            "job": _job,
        }
    )


@app.get("/api/results")
def api_results():
    q = (request.args.get("q") or "").strip()
    only_jump = request.args.get("jump") == "1"
    only_gambling = request.args.get("gambling") == "1"
    only_adult = request.args.get("adult") == "1"
    sql = "SELECT * FROM serp_results WHERE 1=1"
    params: list = []
    if q:
        sql += " AND (keyword LIKE ? OR serp_url LIKE ? OR final_url LIKE ? OR page_type LIKE ?)"
        like = f"%{q}%"
        params.extend([like, like, like, like])
    if only_jump:
        sql += " AND is_js_redirect=1"
    if only_gambling:
        sql += " AND has_gambling=1"
    if only_adult:
        sql += " AND has_adult=1"
    sql += " ORDER BY processed_at DESC, id DESC LIMIT 500"
    conn = db_conn()
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    conn.close()
    return jsonify({"rows": rows})


@app.get("/api/csv")
def api_get_csv():
    ensure_working_csv()
    return jsonify({"text": CSV_PATH.read_text(encoding="utf-8")})


@app.post("/api/csv")
def api_save_csv():
    body = request.get_json(force=True, silent=True) or {}
    text = str(body.get("text") or "")
    # 基本校验
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or "url" not in reader.fieldnames:
        return jsonify({"ok": False, "error": "CSV 需包含 url 列（建议 keyword,rank,url,title,fetched_at）"}), 400
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    CSV_PATH.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
    count = sum(1 for _ in csv.DictReader(io.StringIO(text)) if (_.get("url") or "").strip())
    return jsonify({"ok": True, "count": count})


def _normalize_url(raw: str) -> str:
    u = raw.strip().strip('"').strip("'")
    if not u:
        return ""
    if u.startswith("www."):
        u = "http://" + u
    if not u.startswith(("http://", "https://")):
        # 允许用户只贴域名
        if "." in u and " " not in u:
            u = "http://" + u
        else:
            return ""
    parsed = urlparse(u)
    if not parsed.netloc:
        return ""
    return u


def _write_keyword_csv(
    keyword: str,
    rows: list[tuple[str, str]],
    *,
    replace: bool = True,
    clear_all: bool = False,
) -> int:
    """
    replace=True: 去掉同关键词旧行再写入（默认）
    replace=False: 保留全部旧行并追加
    clear_all=True: 清空整个报表再写
    """
    today = date.today().isoformat()
    fieldnames = ["keyword", "rank", "url", "title", "fetched_at"]
    kept: list[dict] = []
    if clear_all:
        kept = []
    elif CSV_PATH.exists():
        for old in csv.DictReader(CSV_PATH.open("r", encoding="utf-8-sig")):
            if not (old.get("url") or "").strip():
                continue
            old_kw = (old.get("keyword") or "").strip()
            if replace and old_kw == keyword:
                continue
            kept.append(
                {
                    "keyword": old_kw,
                    "rank": old.get("rank") or "",
                    "url": old.get("url") or "",
                    "title": old.get("title") or "",
                    "fetched_at": old.get("fetched_at") or "",
                }
            )

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for row in kept:
        writer.writerow(row)

    written = 0
    for i, (url, title) in enumerate(rows, 1):
        writer.writerow(
            {
                "keyword": keyword,
                "rank": i,
                "url": url,
                "title": title,
                "fetched_at": today,
            }
        )
        written += 1
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    CSV_PATH.write_text(buf.getvalue(), encoding="utf-8")
    return written


def _parse_keywords(text: str) -> list[str]:
    out: list[str] = []
    seen = set()
    for line in (text or "").splitlines():
        kw = line.strip()
        if not kw or kw.startswith("#"):
            continue
        # 也支持逗号/空格分隔一行多个
        parts = [p.strip() for p in kw.replace("，", ",").split(",") if p.strip()]
        if len(parts) == 1 and " " not in parts[0]:
            candidates = parts
        elif len(parts) > 1:
            candidates = parts
        else:
            candidates = [kw]
        for c in candidates:
            if c not in seen:
                seen.add(c)
                out.append(c)
    return out


def _decode_upload(raw: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _parse_keywords_csv(text: str) -> list[str]:
    """CSV：优先 keyword/关键词/kw 列，否则第一列。"""
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    rows = [row for row in reader if any((c or "").strip() for c in row)]
    if not rows:
        return []

    header = [(c or "").strip().lower() for c in rows[0]]
    key_aliases = {"keyword", "keywords", "kw", "关键词", "关键字", "词", "搜索词"}
    col = -1
    for i, h in enumerate(header):
        if h in key_aliases:
            col = i
            break

    out: list[str] = []
    seen: set[str] = set()
    start = 0
    if col >= 0:
        start = 1
    else:
        # 首行不像表头就当数据；像表头但无匹配列则用第一列并跳过首行
        first = (rows[0][0] if rows[0] else "").strip().lower()
        if first in key_aliases or first in {"name", "名称", "title"}:
            col = 0
            start = 1
        else:
            col = 0
            start = 0

    for row in rows[start:]:
        if col >= len(row):
            continue
        kw = (row[col] or "").strip()
        if not kw or kw.startswith("#"):
            continue
        if kw not in seen:
            seen.add(kw)
            out.append(kw)
    return out


def _parse_keywords_file(filename: str, raw: bytes) -> list[str]:
    text = _decode_upload(raw)
    name = (filename or "").lower()
    if name.endswith(".csv"):
        return _parse_keywords_csv(text)
    # .txt 及其它纯文本
    return _parse_keywords(text)


@app.post("/api/keywords/import")
def api_keywords_import():
    """上传 .txt / .csv，解析为关键词列表（填入批量框用）。"""
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"ok": False, "error": "请选择 .txt 或 .csv 文件"}), 400
    name = f.filename
    lower = name.lower()
    if not (lower.endswith(".txt") or lower.endswith(".csv")):
        return jsonify({"ok": False, "error": "仅支持 .txt / .csv"}), 400
    raw = f.read()
    if not raw:
        return jsonify({"ok": False, "error": "文件为空"}), 400
    if len(raw) > 2 * 1024 * 1024:
        return jsonify({"ok": False, "error": "文件过大（上限 2MB）"}), 400

    keywords = _parse_keywords_file(name, raw)
    if not keywords:
        return jsonify({"ok": False, "error": "未解析到关键词"}), 400
    return jsonify(
        {
            "ok": True,
            "filename": name,
            "count": len(keywords),
            "keywords": keywords,
            "text": "\n".join(keywords),
        }
    )


@app.post("/api/search-prepare")
def api_search_prepare():
    """兼容：手动粘贴网址写入报表。"""
    body = request.get_json(force=True, silent=True) or {}
    keyword = str(body.get("keyword") or "").strip()
    urls_text = str(body.get("urls") or "")
    replace = bool(body.get("replace", True))
    if not keyword:
        return jsonify({"ok": False, "error": "请输入关键词"}), 400

    baidu_url = f"https://www.baidu.com/s?wd={quote(keyword)}"
    urls: list[tuple[str, str]] = []
    for line in urls_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        nu = _normalize_url(parts[0])
        if nu:
            urls.append((nu, parts[1] if len(parts) > 1 else ""))

    written = _write_keyword_csv(keyword, urls, replace=replace) if urls else 0
    return jsonify(
        {
            "ok": True,
            "keyword": keyword,
            "baidu_url": baidu_url,
            "written": written,
            "note": "已按手动粘贴写入（备用）。主流程请用「自动抓取」。",
            "csv": CSV_PATH.read_text(encoding="utf-8") if CSV_PATH.exists() else "",
        }
    )


@app.post("/api/baidu-auto")
def api_baidu_auto():
    """主流程：关键词 → Playwright 自动搜百度 → 写入 CSV 报表。"""
    from baidu_serp import scrape_baidu_serp

    body = request.get_json(force=True, silent=True) or {}
    keyword = str(body.get("keyword") or "").strip()
    limit = int(body.get("limit") or 20)
    headless = bool(body.get("headless", False))
    if not keyword:
        return jsonify({"ok": False, "error": "请输入关键词"}), 400

    with _job_lock:
        if _job["running"] and _job.get("phase") == "tagging":
            return jsonify({"ok": False, "error": "打标任务进行中，请稍候"}), 409

    archived = _prepare_new_search(title=f"新搜「{keyword}」前归档")

    _set_progress(
        running=True,
        phase="baidu",
        phase_label="① 搜索百度",
        current=0,
        total=limit,
        percent=8,
        detail=f"正在打开百度搜索「{keyword}」…",
        keyword=keyword,
        last_error="",
        mode="single",
        log_line=(
            f"上次结果已归档 → {archived['id']}；开始搜索：{keyword}"
            if archived
            else f"开始自动搜索：{keyword}"
        ),
    )

    try:
        result = scrape_baidu_serp(keyword, limit=limit, headless=headless)
        items = result.get("items") or []
        _set_progress(
            phase="report",
            phase_label="② 写入报表",
            current=len(items),
            total=max(len(items), 1),
            percent=35,
            detail=f"抓到 {len(items)} 条，正在写入 CSV…",
            log_line=f"百度返回 {len(items)} 条",
        )
        rows = [(it["url"], it.get("title") or "") for it in items]
        written = (
            _write_keyword_csv(keyword, rows, replace=True, clear_all=True)
            if rows
            else 0
        )

        ok = bool(result.get("ok")) and written > 0
        if ok:
            _set_progress(
                running=False,
                phase="report",
                phase_label="② 报表已就绪",
                current=written,
                total=written,
                percent=40,
                detail=f"已写入 {written} 条，可进入打标",
                log_line=f"报表写入完成：{written} 条",
            )
        else:
            err = result.get("error") or "未抓到结果"
            _set_progress(
                running=False,
                phase="error",
                phase_label="搜索失败",
                percent=0,
                detail=err,
                last_error=err,
                log_line=f"失败：{err}",
            )

        return jsonify(
            {
                "ok": ok,
                "keyword": keyword,
                "baidu_url": result.get("baidu_url"),
                "written": written,
                "items": items,
                "captcha": bool(result.get("captcha")),
                "error": result.get("error") or "",
                "archived": archived,
                "note": (
                    f"已自动抓取并写入 {written} 条"
                    if written
                    else (result.get("error") or "未抓到结果")
                ),
                "csv": CSV_PATH.read_text(encoding="utf-8") if CSV_PATH.exists() else "",
                "progress": dict(_job),
            }
        )
    except Exception as e:  # noqa: BLE001
        _set_progress(
            running=False,
            phase="error",
            phase_label="搜索失败",
            percent=0,
            detail=str(e),
            last_error=str(e),
            log_line=f"异常：{e}",
        )
        return jsonify({"ok": False, "error": str(e)}), 500


def _run_job(
    limit: int,
    use_crawl4ai: bool,
    keyword: str = "",
    *,
    workers: int = 8,
    fast: bool = False,
) -> None:
    try:
        ensure_working_csv()
        rows = pipeline.load_serp_csv(CSV_PATH)
        if keyword:
            rows = [r for r in rows if r.keyword == keyword]
            _set_progress(log_line=f"仅处理关键词「{keyword}」")
        if limit:
            rows = rows[:limit]
        total = len(rows)
        mode = "快速" if fast else "标准"
        _set_progress(
            running=True,
            phase="tagging",
            phase_label="③ 打标分析",
            current=0,
            total=total,
            percent=40,
            detail=f"准备处理 {total} 条（{mode}·并发 {workers}）",
            keyword=keyword,
            log_line=f"开始处理 {total} 条（{mode}·并发 {workers}）",
        )
        if total == 0:
            _set_progress(
                running=False,
                phase="done",
                phase_label="完成",
                percent=100,
                detail="没有待处理条目",
                log_line="无数据",
            )
            return

        conn = pipeline.init_sqlite(DB)

        def on_done(done: int, _total: int, r: pipeline.ProcessResult) -> None:
            pct = 40 + int(done / total * 60)
            pipeline.upsert_sqlite(conn, r)
            _set_progress(
                phase="tagging",
                phase_label="③ 打标分析",
                current=done,
                total=total,
                percent=pct,
                detail=f"[{done}/{total}] {r.page_type} · {r.serp_url}",
                log_line=(
                    f"[{done}/{total}] {r.page_type} | js={r.is_js_redirect} "
                    f"adult={r.has_adult} gambling={r.has_gambling} | {r.final_url}"
                ),
            )

        pipeline.process_rows(
            rows,
            prefer_crawl4ai=use_crawl4ai,
            workers=workers,
            fetch_landing=not fast,
            max_scripts=2 if fast else pipeline.MAX_SCRIPT_FETCH,
            on_done=on_done,
        )
        conn.close()
        _set_progress(
            running=False,
            phase="done",
            phase_label="④ 完成",
            current=total,
            total=total,
            percent=100,
            detail=f"全部完成，共 {total} 条",
            log_line="完成",
        )
    except Exception as e:  # noqa: BLE001
        _set_progress(
            running=False,
            phase="error",
            phase_label="打标失败",
            percent=0,
            detail=str(e),
            last_error=str(e),
            log_line=f"失败: {e}",
        )


@app.post("/api/run")
def api_run():
    body = request.get_json(force=True, silent=True) or {}
    limit = int(body.get("limit") or 0)
    use_crawl4ai = bool(body.get("crawl4ai"))
    keyword = str(body.get("keyword") or "").strip()
    workers = int(body.get("workers") or 8)
    fast = bool(body.get("fast", False))
    with _job_lock:
        if _job["running"]:
            return jsonify({"ok": False, "error": "已有任务在跑"}), 409
    _set_progress(
        running=True,
        phase="tagging",
        phase_label="③ 打标分析",
        current=0,
        total=0,
        percent=42,
        detail="排队中…",
        keyword=keyword,
        last_error="",
        log_line="排队中…",
        mode="single",
    )
    t = threading.Thread(
        target=_run_job,
        kwargs={
            "limit": limit,
            "use_crawl4ai": use_crawl4ai,
            "keyword": keyword,
            "workers": workers,
            "fast": fast,
        },
        daemon=True,
    )
    t.start()
    return jsonify({"ok": True})


def _run_batch(
    keywords: list[str],
    *,
    serp_limit: int,
    headless: bool,
    auto_tag: bool,
    tag_limit: int,
    use_crawl4ai: bool,
) -> None:
    from baidu_serp import scrape_baidu_serp

    kw_total = len(keywords)
    total_written = 0
    try:
        # 工作区已在 api_baidu_batch 里归档并清空；这里再兜底一次
        CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
        if not CSV_PATH.exists():
            CSV_PATH.write_text(
                "keyword,rank,url,title,fetched_at\n", encoding="utf-8"
            )
        _set_progress(
            running=True,
            mode="batch",
            phase="baidu",
            phase_label="① 批量搜百度",
            kw_index=0,
            kw_total=kw_total,
            current=0,
            total=kw_total,
            percent=1,
            detail=f"共 {kw_total} 个关键词",
            last_error="",
            log_line=f"批量任务开始，共 {kw_total} 词",
        )

        for idx, keyword in enumerate(keywords, 1):
            # 搜索阶段占总进度 0–70%
            base = int((idx - 1) / kw_total * 70)
            _set_progress(
                phase="baidu",
                phase_label=f"① 搜百度（词 {idx}/{kw_total}）",
                keyword=keyword,
                kw_index=idx,
                kw_total=kw_total,
                current=idx - 1,
                total=kw_total,
                percent=max(1, base + 2),
                detail=f"正在搜索「{keyword}」…",
                log_line=f"[{idx}/{kw_total}] 搜索：{keyword}",
            )
            result = scrape_baidu_serp(keyword, limit=serp_limit, headless=headless)
            items = result.get("items") or []
            rows = [(it["url"], it.get("title") or "") for it in items]
            # 追加写入（不清空）
            written = _write_keyword_csv(
                keyword, rows, replace=True, clear_all=False
            )
            total_written += written
            _set_progress(
                phase="report",
                phase_label=f"② 写报表（词 {idx}/{kw_total}）",
                current=idx,
                total=kw_total,
                percent=int(idx / kw_total * 70),
                detail=f"「{keyword}」写入 {written} 条（累计 {total_written}）",
                log_line=f"[{idx}/{kw_total}] 「{keyword}」→ {written} 条",
            )
            if not written:
                _set_progress(
                    log_line=(
                        f"[{idx}/{kw_total}] 「{keyword}」无结果："
                        f"{result.get('error') or '空'}"
                    )
                )

        if auto_tag and total_written > 0:
            _set_progress(
                phase="tagging",
                phase_label="③ 批量打标",
                percent=72,
                detail=f"开始打标，共约 {total_written} 条 URL",
                log_line="批量搜索结束，开始打标全部报表",
            )
            # keyword="" 表示处理 CSV 全部
            _run_job(
                tag_limit,
                use_crawl4ai,
                keyword="",
                workers=8,
                fast=True,
            )
        else:
            _set_progress(
                running=False,
                phase="done" if total_written else "error",
                phase_label="④ 完成" if total_written else "批量结束（无数据）",
                current=kw_total,
                total=kw_total,
                percent=100 if total_written else 0,
                detail=f"批量完成：{kw_total} 词，共 {total_written} 条链接",
                log_line=f"批量完成，写入 {total_written} 条",
                last_error="" if total_written else "所有词都未抓到结果",
            )
    except Exception as e:  # noqa: BLE001
        _set_progress(
            running=False,
            phase="error",
            phase_label="批量失败",
            percent=0,
            detail=str(e),
            last_error=str(e),
            log_line=f"批量异常：{e}",
        )


@app.post("/api/baidu-batch")
def api_baidu_batch():
    """多关键词排队：逐个搜百度 → 汇总报表 → 可选打标。"""
    body = request.get_json(force=True, silent=True) or {}
    text = str(body.get("keywords") or body.get("text") or "")
    keywords = _parse_keywords(text)
    if not keywords:
        return jsonify({"ok": False, "error": "请至少填一个关键词（一行一个）"}), 400

    serp_limit = int(body.get("limit") or 20)
    headless = bool(body.get("headless", False))
    auto_tag = bool(body.get("auto_process", False))  # 默认先出报表，不自动打标
    tag_limit = int(body.get("tag_limit") or 0)
    use_crawl4ai = bool(body.get("crawl4ai", False))

    with _job_lock:
        if _job["running"]:
            return jsonify({"ok": False, "error": "已有任务在跑"}), 409

    title = "、".join(keywords[:5]) + ("…" if len(keywords) > 5 else "")
    archived = _prepare_new_search(title=f"批量「{title}」前归档")

    t = threading.Thread(
        target=_run_batch,
        kwargs={
            "keywords": keywords,
            "serp_limit": serp_limit,
            "headless": headless,
            "auto_tag": auto_tag,
            "tag_limit": tag_limit,
            "use_crawl4ai": use_crawl4ai,
        },
        daemon=True,
    )
    t.start()
    return jsonify(
        {
            "ok": True,
            "count": len(keywords),
            "keywords": keywords,
            "archived": archived,
        }
    )


@app.get("/api/job")
def api_job():
    with _job_lock:
        return jsonify(_job)


@app.get("/api/errors")
def api_errors():
    with _job_lock:
        return jsonify({"errors": list(_job.get("errors") or [])})


@app.post("/api/errors/clear")
def api_errors_clear():
    with _job_lock:
        _job["errors"] = []
        _job["last_error"] = ""
    return jsonify({"ok": True})


@app.get("/api/table")
def api_table():
    """分好的表格数据：名称 / 域名 / 分类 / 链接。"""
    rows = report_table.build_table_rows(DB, CSV_PATH)
    return jsonify({"rows": rows, "count": len(rows)})


@app.get("/api/export.csv")
def api_export_csv():
    rows = report_table.build_table_rows(DB, CSV_PATH)
    text = report_table.to_csv_text(rows)
    out = ROOT / "data" / "报表_名称域名分类.csv"
    out.write_text(text, encoding="utf-8-sig")  # Excel 友好
    return Response(
        text,
        mimetype="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": "attachment; filename=serp_table.csv",
        },
    )


@app.get("/api/export.html")
def api_export_html():
    """带可点击链接的 HTML 表，可用浏览器打开或导入。"""
    rows = report_table.build_table_rows(DB, CSV_PATH)
    html_doc = report_table.to_html_table(rows)
    out = ROOT / "data" / "报表_可点击链接.html"
    out.write_text(html_doc, encoding="utf-8")
    return Response(
        html_doc,
        mimetype="text/html; charset=utf-8",
        headers={
            "Content-Disposition": "attachment; filename=serp_table.html",
        },
    )


@app.get("/api/history")
def api_history_list():
    return jsonify({"items": search_history.list_history(ROOT)})


@app.get("/api/history/<hid>")
def api_history_detail(hid: str):
    data = search_history.load_history(ROOT, hid)
    if not data:
        return jsonify({"ok": False, "error": "记录不存在"}), 404
    return jsonify({"ok": True, **data})


@app.delete("/api/history/<hid>")
def api_history_delete(hid: str):
    if not search_history.delete_history(ROOT, hid):
        return jsonify({"ok": False, "error": "记录不存在"}), 404
    return jsonify({"ok": True})


@app.get("/api/history/<hid>/report.html")
def api_history_html(hid: str):
    path = search_history.history_dir(ROOT) / hid / "report.html"
    if not path.exists():
        return jsonify({"ok": False, "error": "无 HTML 快照"}), 404
    return Response(path.read_text(encoding="utf-8"), mimetype="text/html; charset=utf-8")


@app.get("/api/history/<hid>/serp.csv")
def api_history_csv(hid: str):
    path = search_history.history_dir(ROOT) / hid / "serp.csv"
    if not path.exists():
        return jsonify({"ok": False, "error": "无 CSV"}), 404
    return Response(
        path.read_text(encoding="utf-8"),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=history_{hid}.csv"},
    )


@app.post("/api/workspace/clear")
def api_workspace_clear():
    """手动清空当前工作区（可选先归档）。"""
    body = request.get_json(force=True, silent=True) or {}
    archive = bool(body.get("archive", True))
    archived = None
    if archive:
        archived = search_history.archive_current(
            ROOT, csv_path=CSV_PATH, db_path=DB, title="手动归档"
        )
    search_history.clear_workspace(CSV_PATH, DB)
    return jsonify({"ok": True, "archived": archived})


if __name__ == "__main__":
    ensure_working_csv()
    pipeline.init_sqlite(DB)
    print("PLAYWRIGHT_BROWSERS_PATH=", __import__("os").environ.get("PLAYWRIGHT_BROWSERS_PATH"))
    print("搜索管线后台 → http://127.0.0.1:8878/admin/")
    app.run(host="127.0.0.1", port=8878, debug=False)
