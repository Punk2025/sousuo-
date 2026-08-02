(() => {
  const $ = (id) => document.getElementById(id);

  function toast(msg) {
    const el = $("toast");
    el.hidden = false;
    el.textContent = msg;
    clearTimeout(toast._t);
    toast._t = setTimeout(() => {
      el.hidden = true;
    }, 2200);
  }

  function esc(s) {
    return String(s ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  let selectedId = "";

  async function loadList() {
    const data = await (await fetch("/api/history")).json();
    const items = data.items || [];
    $("hist-count").textContent = String(items.length);
    const ul = $("hist-list");
    if (!items.length) {
      ul.innerHTML = `<li class="muted">暂无归档。发起新搜索时，当前报表会自动保存到这里。</li>`;
      return;
    }
    ul.innerHTML = items
      .map((it) => {
        const kws = (it.keywords || []).slice(0, 4).join("、");
        const more = (it.keywords || []).length > 4 ? "…" : "";
        return `<li class="hist-item${it.id === selectedId ? " on" : ""}" data-id="${esc(it.id)}">
          <strong>${esc(it.title || it.id)}</strong>
          <span class="muted">${esc(it.created_at || "")} · ${esc(it.count ?? 0)} 条</span>
          <span class="muted hist-kws">${esc(kws)}${more}</span>
        </li>`;
      })
      .join("");

    ul.querySelectorAll(".hist-item").forEach((el) => {
      el.onclick = () => openDetail(el.dataset.id);
    });
  }

  async function openDetail(hid) {
    selectedId = hid;
    await loadList();
    const data = await (await fetch(`/api/history/${encodeURIComponent(hid)}`)).json();
    if (!data.ok) {
      $("hist-detail").innerHTML = `<p class="muted">${esc(data.error || "加载失败")}</p>`;
      return;
    }
    const meta = data.meta || {};
    const rows = data.rows || [];
    const table =
      rows.length === 0
        ? `<p class="muted">无表格快照</p>`
        : `<div class="table-wrap"><table>
            <thead><tr>
              <th>关键词</th><th>排名</th><th>名称</th><th>域名</th><th>分类</th><th>入口</th><th>最终</th>
            </tr></thead>
            <tbody>
            ${rows
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
              .join("")}
            </tbody></table></div>`;

    $("hist-detail").innerHTML = `
      <div class="card-h">
        <h2>${esc(meta.title || hid)}</h2>
        <span class="tag">${esc(meta.count ?? rows.length)} 条</span>
      </div>
      <p class="help">${esc(meta.created_at || "")} · ${(meta.keywords || []).map(esc).join("、") || "—"}</p>
      <div class="row-actions" style="margin-bottom:0.8rem">
        <a class="btn" href="/api/history/${encodeURIComponent(hid)}/report.html" target="_blank">打开 HTML</a>
        <a class="btn" href="/api/history/${encodeURIComponent(hid)}/serp.csv">下载 CSV</a>
        <button type="button" class="btn danger" id="btn-del">删除</button>
      </div>
      ${table}
    `;
    $("btn-del").onclick = async () => {
      if (!confirm("确定删除这条搜索记录？")) return;
      const res = await fetch(`/api/history/${encodeURIComponent(hid)}`, {
        method: "DELETE",
      });
      const out = await res.json();
      if (!res.ok) return toast(out.error || "删除失败");
      selectedId = "";
      $("hist-detail").innerHTML = `<p class="muted">左侧选择一条记录</p>`;
      await loadList();
      toast("已删除");
    };
  }

  $("btn-refresh").onclick = () => loadList().then(() => toast("已刷新"));
  loadList();
})();
