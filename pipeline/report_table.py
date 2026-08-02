"""把抓取/打标结果整理成表格字段，便于导出 Excel。"""

from __future__ import annotations

import csv
import html
import io
import sqlite3
from pathlib import Path
from urllib.parse import urlparse


def domain_of(url: str) -> str:
    if not url:
        return ""
    try:
        host = urlparse(url).netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:  # noqa: BLE001
        return ""


def build_table_rows(db_path: Path, csv_path: Path | None = None) -> list[dict]:
    """
    主交付以 SERP CSV 报表为准（先出报表）。
    若同 URL 已打标，则补充分类 / 最终链接。
    """
    tagged: dict[str, sqlite3.Row] = {}
    if db_path.exists():
        import phase_b_process as pipeline

        pipeline.init_sqlite(db_path).close()
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            for r in conn.execute(
                """
                SELECT keyword, rank_no, title, serp_url, final_url, page_type,
                       is_js_redirect, has_gambling, has_adult, has_tg, has_usdt
                FROM serp_results
                ORDER BY id
                """
            ):
                key = f"{(r['keyword'] or '').strip()}|{(r['serp_url'] or '').strip()}"
                tagged[key] = r
        finally:
            conn.close()

    rows: list[dict] = []
    if csv_path and csv_path.exists():
        with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                url = (r.get("url") or "").strip()
                if not url:
                    continue
                keyword = (r.get("keyword") or "").strip()
                title = (r.get("title") or "").strip()
                dom = domain_of(url)
                final = url
                cat = "SERP结果"
                t = tagged.get(f"{keyword}|{url}")
                if t:
                    final = (t["final_url"] or "").strip() or url
                    if not title:
                        title = (t["title"] or "").strip()
                    cat = (t["page_type"] or "已打标").strip()
                    flags = []
                    if t["is_js_redirect"]:
                        flags.append("JS跳转")
                    if t["has_adult"]:
                        flags.append("疑似成人")
                    if t["has_gambling"]:
                        flags.append("博彩")
                    if t["has_tg"]:
                        flags.append("TG")
                    if t["has_usdt"]:
                        flags.append("USDT")
                    if flags:
                        cat = f"{cat} / {'+'.join(flags)}"
                    dom = domain_of(final) or dom
                rows.append(
                    {
                        "关键词": keyword,
                        "排名": (r.get("rank") or "").strip(),
                        "名称": title or dom or url,
                        "域名": dom,
                        "分类": cat,
                        "入口链接": url,
                        "最终链接": final,
                    }
                )
        if rows:
            return rows

    # 仅有打标库、无 CSV 时回退
    for r in tagged.values():
        serp = (r["serp_url"] or "").strip()
        final = (r["final_url"] or "").strip() or serp
        title = (r["title"] or "").strip()
        dom = domain_of(final) or domain_of(serp)
        cat = (r["page_type"] or "未分类").strip()
        rows.append(
            {
                "关键词": r["keyword"] or "",
                "排名": r["rank_no"] if r["rank_no"] is not None else "",
                "名称": title or dom or serp,
                "域名": dom,
                "分类": cat,
                "入口链接": serp,
                "最终链接": final,
            }
        )
    return rows

def to_csv_text(rows: list[dict]) -> str:
    fields = ["关键词", "排名", "名称", "域名", "分类", "入口链接", "最终链接"]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return buf.getvalue()


def to_html_table(rows: list[dict], title: str = "搜索报表") -> str:
    def link(url: str) -> str:
        if not url:
            return ""
        u = html.escape(url, quote=True)
        t = html.escape(url)
        return f'<a href="{u}" target="_blank" rel="noopener">{t}</a>'

    body = []
    for r in rows:
        body.append(
            "<tr>"
            f"<td>{html.escape(str(r.get('关键词') or ''))}</td>"
            f"<td>{html.escape(str(r.get('排名') or ''))}</td>"
            f"<td>{html.escape(str(r.get('名称') or ''))}</td>"
            f"<td>{html.escape(str(r.get('域名') or ''))}</td>"
            f"<td>{html.escape(str(r.get('分类') or ''))}</td>"
            f"<td>{link(str(r.get('入口链接') or ''))}</td>"
            f"<td>{link(str(r.get('最终链接') or ''))}</td>"
            "</tr>"
        )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 24px; color: #122; }}
    h1 {{ font-size: 20px; margin: 0 0 12px; }}
    p {{ color: #666; margin: 0 0 16px; }}
    table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
    th, td {{ border: 1px solid #ddd; padding: 8px 10px; vertical-align: top; text-align: left; }}
    th {{ background: #f4f7fb; position: sticky; top: 0; }}
    a {{ color: #0b6bcb; word-break: break-all; }}
    tr:nth-child(even) {{ background: #fafbfc; }}
  </style>
</head>
<body>
  <h1>{html.escape(title)}</h1>
  <p>共 {len(rows)} 条。链接可直接点击；也可用 Excel「打开」本文件或复制表格。</p>
  <table>
    <thead>
      <tr>
        <th>关键词</th><th>排名</th><th>名称</th><th>域名</th>
        <th>分类</th><th>入口链接</th><th>最终链接</th>
      </tr>
    </thead>
    <tbody>
      {''.join(body) if body else '<tr><td colspan="7">暂无数据</td></tr>'}
    </tbody>
  </table>
</body>
</html>
"""
