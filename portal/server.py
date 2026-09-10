#!/usr/bin/env python3
"""心屿社区 · 本地内容后台（管理 H5 导航等，不含分流跳转）。"""

from __future__ import annotations

import json
import os
import secrets
import time
import uuid
from functools import wraps
from pathlib import Path

from flask import (
    Flask,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "content.json"
STATIC_ROOT = ROOT  # 静态栏目页仍在 portal/ 下

app = Flask(
    __name__,
    template_folder=str(ROOT / "templates"),
    static_folder=str(ROOT / "static"),
    static_url_path="/static",
)
app.secret_key = os.environ.get("PORTAL_SECRET", "xinyu-portal-dev-key")

# 本地演示密码：可用环境变量覆盖
ADMIN_PASS = os.environ.get("PORTAL_ADMIN_PASS", "admin123")


def _load() -> dict:
    if not DATA.exists():
        return {
            "site": {},
            "banner": {},
            "icons": [],
            "hot": [],
            "tags": [],
        }
    return json.loads(DATA.read_text(encoding="utf-8"))


def _save(data: dict) -> None:
    DATA.parent.mkdir(parents=True, exist_ok=True)
    DATA.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            if request.path.startswith("/api/"):
                return jsonify({"ok": False, "error": "未登录"}), 401
            return redirect(url_for("admin_login", next=request.path))
        return fn(*args, **kwargs)

    return wrapper


@app.get("/")
def home():
    return send_from_directory(STATIC_ROOT, "index.html")


@app.get("/nav/")
@app.get("/nav")
def nav_page():
    data = _load()
    return render_template("nav.html", data=data, ts=int(time.time()))


@app.get("/nav/nav.css")
def nav_css():
    return send_from_directory(ROOT / "nav", "nav.css")


@app.get("/admin/login")
def admin_login():
    if session.get("admin"):
        return redirect(url_for("admin_home"))
    return render_template("login.html")


@app.post("/admin/login")
def admin_login_post():
    password = (request.form.get("password") or "").strip()
    if password == ADMIN_PASS:
        session["admin"] = True
        session["csrf"] = secrets.token_hex(16)
        return redirect(url_for("admin_home"))
    return render_template("login.html", error="密码错误"), 401


@app.post("/admin/logout")
@login_required
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


@app.get("/admin/")
@login_required
def admin_home():
    data = _load()
    stats = {
        "icons": len(data.get("icons") or []),
        "hot": len(data.get("hot") or []),
        "tags": len(data.get("tags") or []),
        "updated": time.strftime(
            "%Y-%m-%d %H:%M",
            time.localtime(DATA.stat().st_mtime if DATA.exists() else time.time()),
        ),
    }
    return render_template(
        "admin.html",
        data=data,
        stats=stats,
        csrf=session.get("csrf", ""),
    )


@app.get("/api/content")
def api_content_public():
    """前台可读（H5 / 调试）。"""
    return jsonify({"ok": True, "data": _load()})


@app.get("/api/admin/content")
@login_required
def api_admin_content():
    return jsonify({"ok": True, "data": _load()})


@app.put("/api/admin/content")
@login_required
def api_admin_content_save():
    body = request.get_json(force=True, silent=True) or {}
    if body.get("csrf") != session.get("csrf"):
        return jsonify({"ok": False, "error": "CSRF 校验失败"}), 403
    data = body.get("data")
    if not isinstance(data, dict):
        return jsonify({"ok": False, "error": "数据格式错误"}), 400
    # 规范化 id
    for key in ("icons", "hot", "tags"):
        items = data.get(key) or []
        if not isinstance(items, list):
            return jsonify({"ok": False, "error": f"{key} 必须是数组"}), 400
        for it in items:
            if not isinstance(it, dict):
                continue
            if not it.get("id"):
                it["id"] = uuid.uuid4().hex[:8]
    _save(data)
    return jsonify({"ok": True})


# 静态栏目目录
@app.get("/intro/")
@app.get("/news-feed/")
@app.get("/section-compare/")
@app.get("/hot-posts/")
@app.get("/user-qa/")
@app.get("/about/")
def section_pages():
    folder = request.path.strip("/")
    return send_from_directory(STATIC_ROOT / folder, "index.html")


@app.get("/robots.txt")
def robots():
    return send_from_directory(STATIC_ROOT, "robots.txt")


@app.get("/sitemap.xml")
def sitemap():
    return send_from_directory(STATIC_ROOT, "sitemap.xml")


if __name__ == "__main__":
    port = int(os.environ.get("PORTAL_PORT", "8767"))
    print(f"心屿内容站 → http://127.0.0.1:{port}/")
    print(f"后台管理   → http://127.0.0.1:{port}/admin/")
    print(f"H5 导航    → http://127.0.0.1:{port}/nav/")
    print(f"默认密码   → {ADMIN_PASS}")
    app.run(host="127.0.0.1", port=port, debug=False)
