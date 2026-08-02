(() => {
  const $ = (id) => document.getElementById(id);
  let activeKeyword = "";
  let pollTimer = null;
  let localProgressTimer = null;
  let lastActivityKey = "";

  function nowTime() {
    return new Date().toLocaleTimeString("zh-CN", { hour12: false });
  }

  function tickClock() {
    if ($("clock")) $("clock").textContent = nowTime();
  }
  tickClock();
  setInterval(tickClock, 1000);

  /** @param {string} msg @param {"info"|"ok"|"err"|"warn"} [type] */
  function toast(msg, type = "info") {
    const stack = $("toast-stack");
    if (!stack) {
      const el = $("toast");
      if (el) {
        el.hidden = false;
        el.textContent = msg;
      }
      return;
    }
    const item = document.createElement("div");
    item.className = `toast-item ${type}`;
    item.textContent = msg;
    stack.appendChild(item);
    setTimeout(() => {
      item.style.opacity = "0";
      item.style.transition = "opacity 0.25s";
      setTimeout(() => item.remove(), 260);
    }, type === "err" ? 4200 : 2600);
  }

  /** @param {string} msg @param {"idle"|"ok"|"err"|"run"|"warn"} [tone] */
  function pushActivity(msg, tone = "idle") {
    const ul = $("activity-list");
    if (!ul) return;
    const key = `${tone}|${msg}`;
    if (key === lastActivityKey) return;
    lastActivityKey = key;
    const li = document.createElement("li");
    li.className = `act ${tone}`;
    li.innerHTML = `<time>${esc(nowTime())}</time><span>${esc(msg)}</span>`;
    ul.prepend(li);
    while (ul.children.length > 40) ul.lastElementChild?.remove();
  }

  function setFeedback({ title, msg, tone = "idle", pill }) {
    const strip = $("feedback-strip");
    if (!strip) return;
    strip.dataset.tone = tone;
    $("fb-pill").textContent = pill || (
      tone === "run" ? "进行中"
        : tone === "ok" ? "成功"
          : tone === "err" ? "失败"
            : tone === "warn" ? "注意"
              : "空闲"
    );
    $("fb-title").textContent = title || "准备就绪";
    $("fb-msg").textContent = msg || "";
    $("fb-meta").textContent = `上次更新：${nowTime()}`;

    const sideTone = tone === "idle" ? "idle" : tone === "run" ? "run" : tone === "ok" ? "ok" : tone === "warn" ? "warn" : "err";
    $("side-dot").className = `pulse-dot ${sideTone}`;
    $("side-state").textContent =
      tone === "run" ? "运行中"
        : tone === "ok" ? "已完成"
          : tone === "err" ? "有错误"
            : tone === "warn" ? "需注意"
              : "空闲";
    $("side-hint").textContent = (msg || title || "等待操作").slice(0, 42);
  }

  function setBanner(id, text, tone = "info") {
    const el = $(id);
    if (!el) return;
    el.textContent = text;
    el.dataset.tone = tone;
  }

  function esc(s) {
    return String(s ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function setActiveKeyword(kw) {
    activeKeyword = (kw || "").trim();
    $("active-kw").textContent = activeKeyword
      ? `当前关键词：${activeKeyword}`
      : "当前关键词：未选择";
    if (activeKeyword) $("q").value = activeKeyword;
  }

  function setSerpLog(lines) {
    $("serp-log").textContent = Array.isArray(lines) ? lines.join("\n") : String(lines);
  }

  function renderErrors(errors) {
    const list = Array.isArray(errors) ? errors : [];
    const card = $("error-card");
    const ul = $("error-list");
    if (!list.length) {
      card.hidden = true;
      ul.innerHTML = "";
      return;
    }
    card.hidden = false;
    ul.innerHTML = list
      .slice()
      .reverse()
      .map((e) => {
        const tip = e.tip ? `<div class="err-tip">${esc(e.tip)}</div>` : "";
        const kw = e.keyword ? `<span class="err-kw">${esc(e.keyword)}</span>` : "";
        return `<li>
          <div><span class="err-time">${esc(e.time || "")}</span>${kw}</div>
          <div class="err-msg">${esc(e.message || "")}</div>
          ${tip}
        </li>`;
      })
      .join("");
  }

  function renderProgress(p) {
    const phase = p.phase || "idle";
    const percent = Number(p.percent || 0);
    const current = Number(p.current || 0);
    const total = Number(p.total || 0);
    const label = p.phase_label || "空闲";
    const detail = p.detail || "等待开始";

    $("prog-phase").textContent = label;
    $("prog-detail").textContent = detail;
    $("prog-pct").textContent = `${percent}%`;
    $("prog-fill").style.width = `${percent}%`;
    const kwIndex = Number(p.kw_index || 0);
    const kwTotal = Number(p.kw_total || 0);
    if (p.mode === "batch" && kwTotal) {
      $("prog-count").textContent =
        `词 ${kwIndex}/${kwTotal}` + (total ? ` · 项 ${current}/${total}` : "");
    } else {
      $("prog-count").textContent = total ? `${current} / ${total}` : `${current} / -`;
    }
    $("prog-kw").textContent = p.keyword
      ? p.mode === "batch"
        ? `当前词：${p.keyword}`
        : `关键词：${p.keyword}`
      : "";

    const card = $("progress-card");
    card.classList.toggle("active", !!p.running);
    card.classList.toggle("done", phase === "done" || (phase === "report" && !p.running));
    card.classList.toggle("error", phase === "error");

    const badge = $("live-badge");
    if (p.running) {
      badge.textContent = "LIVE";
      badge.className = "live-badge run";
    } else if (phase === "error") {
      badge.textContent = "ERR";
      badge.className = "live-badge err";
    } else if (phase === "done" || (phase === "report" && !p.running)) {
      badge.textContent = "OK";
      badge.className = "live-badge ok";
    } else {
      badge.textContent = "IDLE";
      badge.className = "live-badge idle";
    }

    if (p.running) {
      setFeedback({
        title: label,
        msg: detail,
        tone: "run",
        pill: "进行中",
      });
      pushActivity(`${label} · ${detail}`, "run");
      if (phase === "baidu" || phase === "report") {
        setBanner("search-banner", detail, "run");
        $("search-tag").textContent = "搜索中…";
      }
      if (phase === "tagging") {
        setBanner("tag-banner", detail, "run");
      }
    } else if (phase === "error") {
      setFeedback({
        title: label || "失败",
        msg: p.last_error || detail,
        tone: "err",
      });
      pushActivity(`${label}：${p.last_error || detail}`, "err");
    } else if (phase === "done" || (phase === "report" && !p.running && percent > 0)) {
      setFeedback({
        title: label,
        msg: detail,
        tone: "ok",
      });
      pushActivity(`${label} · ${detail}`, "ok");
      if (phase === "report" || phase === "done") {
        setBanner("search-banner", detail || "报表已就绪，可导出", "ok");
        $("search-tag").textContent = "报表就绪";
        setBanner("export-banner", "报表可导出 HTML / CSV；需要再去打标。", "ok");
      }
      if (phase === "done" && (p.phase_label || "").includes("完成")) {
        setBanner("tag-banner", detail || "打标完成", "ok");
      }
    }

    const order = ["baidu", "report", "done", "tagging"];
    let idx = order.indexOf(phase);
    if (phase === "error" || phase === "idle") idx = -1;
    if (phase === "report" && !p.running) idx = order.indexOf("done");
    document.querySelectorAll("#steps-bar li").forEach((li) => {
      li.classList.remove("on", "done", "err");
      const key = li.dataset.phase;
      const liIdx = order.indexOf(key);
      if (phase === "error") {
        if (key === "baidu" || key === "tagging") li.classList.add("err");
        return;
      }
      if (idx < 0) return;
      if (phase === "tagging") {
        if (key === "baidu" || key === "report" || key === "done") li.classList.add("done");
        if (key === "tagging") li.classList.add("on");
        return;
      }
      if (liIdx < idx) li.classList.add("done");
      else if (liIdx === idx) li.classList.add("on");
    });

    if (p.running && phase === "tagging") {
      $("job-state").textContent = `${percent}%`;
      $("job-state").classList.add("run");
    } else if (!p.running) {
      $("job-state").textContent =
        phase === "done" ? "完成" : phase === "error" || p.last_error ? "失败" : "空闲";
      if (phase !== "tagging") $("job-state").classList.remove("run");
      if (phase === "done") $("job-state").classList.remove("run");
    }

    renderErrors(p.errors || []);
  }

  function pulseBaiduProgress(keyword) {
    let n = 8;
    clearInterval(localProgressTimer);
    localProgressTimer = setInterval(() => {
      n = Math.min(32, n + 2);
      renderProgress({
        running: true,
        phase: "baidu",
        phase_label: "① 搜索百度",
        percent: n,
        current: 0,
        total: Number($("serp-limit").value || 20),
        detail: "浏览器正在访问百度（若有验证码请在弹窗完成）…",
        keyword,
      });
    }, 900);
  }

  async function loadStats() {
    const s = await (await fetch("/api/stats")).json();
    if ($("s-total")) $("s-total").textContent = s.total;
    $("s-jump").textContent = s.js_redirect;
    $("s-adult").textContent = s.adult ?? 0;
    $("s-gamble").textContent = s.gambling;
    if (s.job) renderProgress(s.job);
    if (s.job?.running) {
      $("btn-run").disabled = true;
      $("btn-auto").disabled = true;
    } else if (!$("btn-auto").dataset.busy) {
      $("btn-run").disabled = false;
      $("btn-auto").disabled = false;
    }
    if (s.job?.log?.length) $("job-log").textContent = s.job.log.join("\n");
  }

  async function loadCsv() {
    const data = await (await fetch("/api/csv")).json();
    $("csv-text").value = data.text || "";
  }

  function domainOf(url) {
    try {
      return new URL(url).hostname.replace(/^www\./, "");
    } catch {
      return "";
    }
  }

  function clearWorkspaceUI(msg) {
    $("csv-text").value = "keyword,rank,url,title,fetched_at\n";
    $("table-rows").innerHTML =
      `<tr><td colspan="7" class="muted">${esc(msg || "新搜索进行中，上次结果已进「搜索记录」")}</td></tr>`;
    $("rows").innerHTML =
      `<tr><td colspan="7" class="muted">${esc(msg || "等待本次搜索结果…")}</td></tr>`;
    if ($("s-report")) $("s-report").textContent = "0";
    $("s-total").textContent = "0";
    $("s-jump").textContent = "0";
    $("s-adult").textContent = "0";
    $("s-gamble").textContent = "0";
    setBanner("export-banner", msg || "工作区已清空，等待新报表…", "warn");
  }

  async function loadExportTable() {
    const data = await (await fetch("/api/table")).json();
    const tb = $("table-rows");
    const n = data.rows?.length || 0;
    if ($("s-report")) $("s-report").textContent = String(n);
    if (!n) {
      tb.innerHTML = `<tr><td colspan="7" class="muted">暂无表格数据：先搜索出报表</td></tr>`;
      setBanner("export-banner", "尚无报表。完成搜索后这里会显示可导出表格。", "idle");
      return;
    }
    setBanner("export-banner", `当前报表 ${n} 条，可导出 HTML / CSV。`, "ok");
    tb.innerHTML = data.rows
      .map((r) => {
        const entry = r["入口链接"] || "";
        const finalu = r["最终链接"] || "";
        return `<tr>
          <td>${esc(r["关键词"])}</td>
          <td>${esc(r["排名"])}</td>
          <td>${esc(r["名称"])}</td>
          <td><code>${esc(r["域名"])}</code></td>
          <td><span class="badge">${esc(r["分类"])}</span></td>
          <td><a href="${esc(entry)}" target="_blank" rel="noopener">${esc(entry)}</a></td>
          <td><a href="${esc(finalu)}" target="_blank" rel="noopener">${esc(finalu)}</a></td>
        </tr>`;
      })
      .join("");
  }

  async function loadResults() {
    const q = $("q").value.trim();
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if ($("f-jump").checked) params.set("jump", "1");
    if ($("f-adult").checked) params.set("adult", "1");
    if ($("f-gamble").checked) params.set("gambling", "1");
    const data = await (await fetch("/api/results?" + params)).json();
    const tb = $("rows");
    if (!data.rows.length) {
      tb.innerHTML = `<tr><td colspan="7" class="muted">暂无打标结果：先出报表再点「开始打标」</td></tr>`;
      return;
    }
    tb.innerHTML = data.rows
      .map((r) => {
        const finalu = r.final_url || r.serp_url || "";
        const name = (r.title || "").trim() || domainOf(finalu) || finalu;
        const badgeClass = r.is_js_redirect
          ? "danger"
          : String(r.page_type || "").includes("失败")
            ? "warn"
            : r.has_adult
              ? "warn"
              : "ok";
        return `<tr>
          <td>${esc(r.keyword)}</td>
          <td>${esc(r.rank_no ?? "")}</td>
          <td><span class="badge ${badgeClass}">${esc(r.page_type)}</span></td>
          <td><code>${esc(domainOf(finalu))}</code></td>
          <td>${esc(name)}</td>
          <td><a href="${esc(finalu)}" target="_blank" rel="noopener">${esc(finalu)}</a></td>
          <td class="muted" style="max-width:14rem">${esc(r.evidence || "-")}</td>
        </tr>`;
      })
      .join("");
  }

  async function refreshAll() {
    await Promise.all([loadStats(), loadResults(), loadExportTable()]);
  }

  async function startRun() {
    const keyword = $("only-kw").checked && activeKeyword ? activeKeyword : "";
    const workers = Math.min(16, Math.max(1, Number($("tag-workers").value || 8)));
    const fast = $("tag-fast").checked;
    const res = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        limit: Number($("limit").value || 0),
        crawl4ai: $("crawl4ai").checked,
        keyword,
        workers,
        fast,
      }),
    });
    const data = await res.json();
    if (!res.ok) {
      toast(data.error || "启动失败", "err");
      pushActivity(data.error || "打标启动失败", "err");
      return;
    }
    const tip = keyword
      ? `开始打标「${keyword}」·并发${workers}`
      : `已开始打标·并发${workers}${fast ? "·快速" : ""}`;
    toast(tip, "info");
    pushActivity(tip, "run");
    setBanner("tag-banner", tip, "run");
    renderProgress({
      running: true,
      phase: "tagging",
      phase_label: "③ 打标分析",
      percent: 42,
      current: 0,
      total: 0,
      detail: "排队中…",
      keyword,
    });
    pollJob();
  }

  async function autoSearch(e) {
    if (e) e.preventDefault();
    const keyword = $("keyword").value.trim();
    if (!keyword) {
      toast("请输入关键词", "warn");
      return;
    }

    $("btn-auto").disabled = true;
    $("btn-batch").disabled = true;
    $("btn-auto").dataset.busy = "1";
    setActiveKeyword(keyword);
    clearWorkspaceUI("新搜索进行中，上次结果已进「搜索记录」");
    setSerpLog([
      `关键词：${keyword}`,
      "上次结果已归档到「搜索记录」",
      "正在启动浏览器自动搜索百度…",
      "若弹出验证码，请在 Chromium 窗口内完成验证",
    ]);
    $("search-hint").textContent = "抓取中，请稍候…";
    toast(`正在搜索「${keyword}」…`, "info");
    pushActivity(`开始单词搜索：${keyword}`, "run");
    setBanner("search-banner", `正在搜索「${keyword}」，请留意弹出的浏览器窗口`, "run");
    pulseBaiduProgress(keyword);

    try {
      const res = await fetch("/api/baidu-auto", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          keyword,
          limit: Number($("serp-limit").value || 20),
          headless: $("headless").checked,
        }),
      });
      clearInterval(localProgressTimer);
      const data = await res.json();
      if (data.progress) renderProgress(data.progress);
      if (data.baidu_url) {
        const a = $("baidu-link");
        a.href = data.baidu_url;
        a.hidden = false;
      }
      if (data.csv) $("csv-text").value = data.csv;

      if (!data.ok || !data.written) {
        const lines = [
          data.error || "未抓到结果",
          data.captcha ? "原因：百度安全验证" : "",
          "可展开下方「备用」手动粘贴网址，或完成验证后重试自动抓取",
        ].filter(Boolean);
        setSerpLog(lines);
        $("search-hint").textContent = data.note || data.error || "抓取失败";
        setBanner("search-banner", data.error || "抓取失败，可手动粘贴网址重试", "err");
        renderProgress({
          running: false,
          phase: "error",
          phase_label: "搜索失败",
          percent: 0,
          current: 0,
          total: 0,
          detail: data.error || "未抓到结果",
          keyword,
          last_error: data.error,
        });
        toast(data.error || "抓取失败", "err");
        pushActivity(`搜索失败：${data.error || "未抓到结果"}`, "err");
        return;
      }

      const preview = (data.items || [])
        .slice(0, 8)
        .map((it) => `${it.rank}. ${it.title} — ${it.url}`);
      setSerpLog([`成功写入 ${data.written} 条`, "", ...preview]);
      $("search-hint").textContent = data.note;
      const okMsg = data.archived
        ? `报表已生成 ${data.written} 条；上次已进搜索记录`
        : `报表已生成 ${data.written} 条（未自动打标）`;
      toast(okMsg, "ok");
      pushActivity(okMsg, "ok");
      setBanner("search-banner", okMsg, "ok");
      await refreshAll();
      location.hash = "#export";
    } catch (err) {
      clearInterval(localProgressTimer);
      setSerpLog([`请求失败: ${err}`]);
      setBanner("search-banner", `请求失败：${err}`, "err");
      renderProgress({
        running: false,
        phase: "error",
        phase_label: "搜索失败",
        percent: 0,
        detail: String(err),
        keyword,
        last_error: String(err),
      });
      toast("自动抓取失败", "err");
      pushActivity(`请求失败：${err}`, "err");
    } finally {
      clearInterval(localProgressTimer);
      delete $("btn-auto").dataset.busy;
      $("btn-auto").disabled = false;
      $("btn-batch").disabled = false;
    }
  }

  async function batchSearch() {
    let text = $("keywords-batch").value.trim();
    const single = $("keyword").value.trim();
    if (!text && single) text = single;
    if (!text) {
      toast("请在批量框里一行填一个关键词", "warn");
      return;
    }

    $("btn-batch").disabled = true;
    $("btn-auto").disabled = true;
    clearWorkspaceUI("批量新搜索进行中，上次结果已进「搜索记录」");
    setSerpLog(["批量任务已提交…", "上次结果已归档", "将按队列逐个搜索百度", text]);
    $("search-hint").textContent = "批量进行中，看上方进度条「词 x/y」…";
    setBanner("search-banner", "批量搜索进行中，请关注顶部进度与操作反馈", "run");
    pushActivity("批量出报表已提交", "run");

    try {
      const res = await fetch("/api/baidu-batch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          keywords: text,
          limit: Number($("serp-limit").value || 20),
          headless: $("headless").checked,
          auto_process: false,
          tag_limit: Number($("limit").value || 0),
          crawl4ai: $("crawl4ai").checked,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        toast(data.error || "批量启动失败", "err");
        pushActivity(data.error || "批量启动失败", "err");
        setBanner("search-banner", data.error || "批量启动失败", "err");
        return;
      }
      setActiveKeyword(data.keywords?.[0] || "");
      setSerpLog([
        `已开始批量出报表：共 ${data.count} 个词`,
        data.archived
          ? `上次结果已归档 → ${data.archived.id}`
          : "工作区已清空",
        "完成后可在「表格报表」导出；历史在「搜索记录」",
        "",
        ...(data.keywords || []).map((k, i) => `${i + 1}. ${k}`),
      ]);
      toast(`批量出报表：${data.count} 个词`, "ok");
      pushActivity(`批量出报表：${data.count} 个词`, "run");
      pollJob();
    } catch (err) {
      toast(`批量失败：${err}`, "err");
      pushActivity(`批量失败：${err}`, "err");
    } finally {
      const job = await (await fetch("/api/job")).json();
      if (!job.running) {
        $("btn-batch").disabled = false;
        $("btn-auto").disabled = false;
      }
    }
  }

  $("search-form").addEventListener("submit", autoSearch);
  $("btn-batch").onclick = batchSearch;

  $("btn-clear-activity").onclick = () => {
    $("activity-list").innerHTML =
      `<li class="act idle"><time>${esc(nowTime())}</time><span>已清空操作反馈</span></li>`;
    lastActivityKey = "";
    toast("已清空操作反馈", "info");
  };

  $("kw-file").addEventListener("change", () => {
    $("btn-import-kw").disabled = !$("kw-file").files?.length;
    const f = $("kw-file").files?.[0];
    $("import-hint").textContent = f
      ? `已选：${f.name}`
      : "CSV 用「关键词」列或第一列；TXT 一行一个";
    if (f) pushActivity(`已选择文件：${f.name}`, "idle");
  });

  $("btn-import-kw").onclick = async () => {
    const file = $("kw-file").files?.[0];
    if (!file) return toast("请先选择文件", "warn");
    const fd = new FormData();
    fd.append("file", file);
    $("btn-import-kw").disabled = true;
    try {
      const res = await fetch("/api/keywords/import", { method: "POST", body: fd });
      const data = await res.json();
      if (!res.ok || !data.ok) {
        toast(data.error || "导入失败", "err");
        pushActivity(data.error || "导入失败", "err");
        return;
      }
      $("keywords-batch").value = data.text || (data.keywords || []).join("\n");
      $("import-hint").textContent = `已导入 ${data.count} 个词（${data.filename}）`;
      toast(`已导入 ${data.count} 个关键词`, "ok");
      pushActivity(`导入 ${data.count} 个关键词 ← ${data.filename}`, "ok");
      setBanner("search-banner", `已导入 ${data.count} 个词，可点「批量出报表」`, "ok");
    } catch (err) {
      toast(`导入失败：${err}`, "err");
      pushActivity(`导入失败：${err}`, "err");
    } finally {
      $("btn-import-kw").disabled = !$("kw-file").files?.length;
    }
  };

  $("btn-write").onclick = async () => {
    const keyword = $("keyword").value.trim();
    if (!keyword) return toast("请输入关键词", "warn");
    const res = await fetch("/api/search-prepare", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        keyword,
        urls: $("paste-urls").value,
        replace: true,
      }),
    });
    const data = await res.json();
    if (!res.ok) return toast(data.error || "失败", "err");
    setActiveKeyword(keyword);
    if (data.csv) $("csv-text").value = data.csv;
    renderProgress({
      running: false,
      phase: "report",
      phase_label: "② 报表已就绪",
      percent: 40,
      current: data.written || 0,
      total: data.written || 0,
      detail: `备用写入 ${data.written || 0} 条`,
      keyword,
    });
    toast(data.written ? `备用写入 ${data.written} 条` : "没有识别到网址", data.written ? "ok" : "warn");
    pushActivity(data.written ? `备用写入 ${data.written} 条` : "没有识别到网址", data.written ? "ok" : "warn");
    await refreshAll();
  };

  $("btn-clear-errors").onclick = async () => {
    await fetch("/api/errors/clear", { method: "POST" });
    renderErrors([]);
    toast("已清除报错", "info");
    pushActivity("已清除报错提醒", "idle");
  };

  $("btn-refresh-table").onclick = () =>
    loadExportTable().then(() => {
      toast("表格已刷新", "ok");
      pushActivity("表格已刷新", "ok");
    });

  $("btn-refresh").onclick = () =>
    refreshAll().then(() => {
      toast("已刷新全部", "ok");
      pushActivity("手动刷新全部数据", "ok");
    });

  $("btn-save-csv").onclick = async () => {
    const res = await fetch("/api/csv", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: $("csv-text").value }),
    });
    const data = await res.json();
    if (!res.ok) return toast(data.error || "保存失败", "err");
    toast(`报表已保存（${data.count} 条 URL）`, "ok");
    pushActivity(`CSV 已保存 ${data.count} 条`, "ok");
  };

  $("btn-run").onclick = async () => {
    await fetch("/api/csv", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: $("csv-text").value }),
    });
    await startRun();
  };

  function pollJob() {
    clearInterval(pollTimer);
    pollTimer = setInterval(async () => {
      const job = await (await fetch("/api/job")).json();
      renderProgress(job);
      $("job-log").textContent = (job.log || []).join("\n") || "…";
      if (job.running) {
        $("btn-run").disabled = true;
        $("btn-auto").disabled = true;
      } else {
        clearInterval(pollTimer);
        $("btn-run").disabled = false;
        $("btn-auto").disabled = false;
        $("btn-batch").disabled = false;
        await loadCsv();
        await refreshAll();
        const fail = job.last_error || job.phase === "error";
        const doneMsg =
          job.phase === "tagging" || job.phase_label?.includes("打标")
            ? "打标完成"
            : job.mode === "batch"
              ? "报表已生成，可导出"
              : "完成";
        toast(fail ? "任务失败" : doneMsg, fail ? "err" : "ok");
        pushActivity(fail ? `任务失败：${job.last_error || job.detail || ""}` : doneMsg, fail ? "err" : "ok");
        if (!fail && job.log?.length) {
          setSerpLog(job.log.slice(-30));
        }
        if (!fail && (job.phase === "done" || job.phase === "report")) {
          location.hash = "#export";
        }
      }
    }, 600);
  }

  ["q", "f-jump", "f-adult", "f-gamble"].forEach((id) => {
    $(id).addEventListener("input", () => loadResults());
    $(id).addEventListener("change", () => loadResults());
  });

  document.querySelectorAll(".nav").forEach((a) => {
    a.addEventListener("click", () => {
      document.querySelectorAll(".nav").forEach((x) => x.classList.remove("on"));
      a.classList.add("on");
    });
  });

  setFeedback({
    title: "准备就绪",
    msg: "输入关键词开始搜索，或导入 txt/csv 批量出报表",
    tone: "idle",
  });

  loadCsv()
    .then(refreshAll)
    .then(async () => {
      const job = await (await fetch("/api/job")).json();
      renderProgress(job);
      if (job.running) {
        pushActivity("检测到任务仍在运行，继续跟踪进度", "run");
        pollJob();
      } else {
        pushActivity("控制面板已就绪", "idle");
      }
    });
})();
