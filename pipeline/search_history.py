"""搜索记录归档：新搜索前把当前报表存档，主页面只显示本次。"""

from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import report_table


def _now_id() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y%m%d_%H%M%S")


def history_dir(root: Path) -> Path:
    d = root / "data" / "history"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _count_csv_rows(csv_path: Path) -> int:
    if not csv_path.exists():
        return 0
    text = csv_path.read_text(encoding="utf-8-sig")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return max(0, len(lines) - 1) if lines else 0


def archive_current(
    root: Path,
    *,
    csv_path: Path,
    db_path: Path,
    title: str = "",
) -> dict | None:
    """若当前有报表，归档到 history/；返回归档元信息。无数据则返回 None。"""
    n = _count_csv_rows(csv_path)
    if n <= 0:
        return None

    hid = _now_id()
    folder = history_dir(root) / hid
    folder.mkdir(parents=True, exist_ok=True)

    rows = report_table.build_table_rows(db_path, csv_path)
    keywords = sorted({(r.get("关键词") or "").strip() for r in rows if r.get("关键词")})
    meta = {
        "id": hid,
        "created_at": datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S"),
        "title": title or ("、".join(keywords[:5]) + ("…" if len(keywords) > 5 else "")),
        "keywords": keywords,
        "count": len(rows) or n,
    }

    shutil.copy2(csv_path, folder / "serp.csv")
    (folder / "table.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (folder / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # HTML 快照，方便以后直接打开点链接
    (folder / "report.html").write_text(
        report_table.to_html_table(rows, title=f"搜索记录 {meta['created_at']}"),
        encoding="utf-8",
    )
    return meta


def clear_workspace(csv_path: Path, db_path: Path) -> None:
    """清空当前工作区（主页面不再显示旧数据）。"""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.write_text("keyword,rank,url,title,fetched_at\n", encoding="utf-8")
    if db_path.exists():
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute("DELETE FROM serp_results")
            conn.commit()
        finally:
            conn.close()


def list_history(root: Path) -> list[dict]:
    items = []
    base = history_dir(root)
    for folder in sorted(base.iterdir(), reverse=True):
        if not folder.is_dir():
            continue
        meta_path = folder / "meta.json"
        if not meta_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        meta["id"] = folder.name
        items.append(meta)
    return items


def load_history(root: Path, hid: str) -> dict | None:
    folder = history_dir(root) / hid
    meta_path = folder / "meta.json"
    table_path = folder / "table.json"
    if not meta_path.exists():
        return None
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    rows = []
    if table_path.exists():
        rows = json.loads(table_path.read_text(encoding="utf-8"))
    return {
        "meta": meta,
        "rows": rows,
        "has_html": (folder / "report.html").exists(),
        "has_csv": (folder / "serp.csv").exists(),
    }


def delete_history(root: Path, hid: str) -> bool:
    folder = history_dir(root) / hid
    if not folder.exists() or not folder.is_dir():
        return False
    shutil.rmtree(folder)
    return True
