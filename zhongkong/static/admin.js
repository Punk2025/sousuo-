(() => {
  const $ = (id) => document.getElementById(id);
  let config = null;

  function toast(msg) {
    const el = $("toast");
    el.hidden = false;
    el.textContent = msg;
    clearTimeout(toast._t);
    toast._t = setTimeout(() => {
      el.hidden = true;
    }, 2200);
  }

  function readFormIntoConfig() {
    config.landing_url = $("landing_url").value.trim();
    config.delay_ms = Number($("delay_ms").value || 0);
    config.back_jump_url = $("back_jump_url").value.trim();
    config.stats_enabled = $("stats_enabled").checked;

    const rows = [...document.querySelectorAll("#domain-rows tr")];
    config.domains = rows.map((tr) => ({
      host: tr.querySelector("[data-k=host]").value.trim(),
      channel: tr.querySelector("[data-k=channel]").value.trim(),
      note: tr.querySelector("[data-k=note]").value.trim(),
      enabled: tr.querySelector("[data-k=enabled]").checked,
    })).filter((d) => d.host);
  }

  function fillForm() {
    $("landing_url").value = config.landing_url || "";
    $("delay_ms").value = config.delay_ms ?? 800;
    $("back_jump_url").value = config.back_jump_url || "";
    $("stats_enabled").checked = !!config.stats_enabled;
    $("updated").textContent = config.updated_at
      ? `上次下发：${config.updated_at}`
      : "尚未下发";
    renderDomains();
    renderChannels();
  }

  function renderDomains() {
    const tb = $("domain-rows");
    $("domain-count").textContent = `${(config.domains || []).length} 个`;
    tb.innerHTML = (config.domains || [])
      .map((d, i) => {
        const open = `/entry/${encodeURIComponent(d.host)}`;
        return `<tr data-i="${i}">
          <td><input data-k="enabled" type="checkbox" ${d.enabled ? "checked" : ""}></td>
          <td><input data-k="host" type="text" value="${escapeAttr(d.host)}"></td>
          <td><input data-k="channel" type="text" value="${escapeAttr(d.channel || "")}" style="width:4.5rem"></td>
          <td><input data-k="note" type="text" value="${escapeAttr(d.note || "")}"></td>
          <td><a class="btn tiny" href="${open}" target="_blank" rel="noopener">壳页</a></td>
        </tr>`;
      })
      .join("");
  }

  function renderChannels() {
    $("channel-rows").innerHTML = (config.channels || [])
      .map(
        (c) => `<tr>
          <td><code>${escapeHtml(c.cid)}</code></td>
          <td>${escapeHtml(c.name || "")}</td>
          <td><code>${escapeHtml(c.landing_path || "")}</code></td>
        </tr>`
      )
      .join("");
  }

  function escapeAttr(s) {
    return String(s)
      .replaceAll("&", "&amp;")
      .replaceAll('"', "&quot;")
      .replaceAll("<", "&lt;");
  }
  function escapeHtml(s) {
    return String(s)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;");
  }

  async function refreshPreview() {
    const res = await fetch("/api/preview-script");
    $("script-preview").textContent = await res.text();
  }

  async function load() {
    const res = await fetch("/api/config");
    config = await res.json();
    fillForm();
    await refreshPreview();
  }

  async function publish() {
    readFormIntoConfig();
    const res = await fetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config),
    });
    const data = await res.json();
    config = data.config;
    fillForm();
    await refreshPreview();
    toast("已下发：所有入口下次加载 jump.js 即用新目标");
  }

  async function bulkImport() {
    const text = $("bulk-text").value;
    if (!text.trim()) return toast("先粘贴域名列表");
    const res = await fetch("/api/domains/bulk", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, channel: "12" }),
    });
    const data = await res.json();
    config = data.config;
    $("bulk-text").value = "";
    fillForm();
    toast(`批量完成：新增 ${data.added}，合计 ${data.total}`);
  }

  $("btn-publish").addEventListener("click", publish);
  $("btn-bulk").addEventListener("click", bulkImport);

  document.querySelectorAll(".nav").forEach((a) => {
    a.addEventListener("click", () => {
      document.querySelectorAll(".nav").forEach((x) => x.classList.remove("on"));
      a.classList.add("on");
    });
  });

  load().catch((err) => {
    console.error(err);
    toast("加载配置失败");
  });
})();
