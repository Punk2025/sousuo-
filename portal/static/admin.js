(() => {
  const boot = window.__BOOT__ || { site: {}, banner: {}, icons: [], hot: [], tags: [] };
  const state = JSON.parse(JSON.stringify(boot));
  let dirty = false;

  const $ = (id) => document.getElementById(id);
  const csrf = document.getElementById("app").dataset.csrf || "";

  function toast(msg) {
    const el = $("toast");
    el.hidden = false;
    el.textContent = msg;
    clearTimeout(toast._t);
    toast._t = setTimeout(() => { el.hidden = true; }, 2200);
  }

  function markDirty(v = true) {
    dirty = v;
    const pill = $("save-state");
    pill.textContent = v ? "有未保存修改" : "已同步";
    pill.className = "pill " + (v ? "dirty" : "ok");
  }

  function uid() {
    return Math.random().toString(16).slice(2, 10);
  }

  // panels
  document.querySelectorAll("[data-panel]").forEach((a) => {
    a.addEventListener("click", (e) => {
      e.preventDefault();
      const name = a.dataset.panel;
      document.querySelectorAll(".nav").forEach((n) => n.classList.toggle("on", n === a));
      document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("on", p.id === "panel-" + name));
      const titles = { dash: "总览", site: "站点 / Banner", icons: "宫格入口", hot: "热门列表", tags: "快捷标签" };
      $("page-title").textContent = titles[name] || "后台";
    });
  });

  function fillSite() {
    $("site-name").value = state.site?.name || "";
    $("site-badge").value = state.site?.badge || "";
    $("site-search").value = state.site?.search_placeholder || "";
    $("site-notice").value = state.site?.notice || "";
    $("banner-title").value = state.banner?.title || "";
    $("banner-sub").value = state.banner?.subtitle || "";
  }

  ["site-name", "site-badge", "site-search", "site-notice", "banner-title", "banner-sub"].forEach((id) => {
    $(id).addEventListener("input", () => {
      state.site = state.site || {};
      state.banner = state.banner || {};
      state.site.name = $("site-name").value.trim();
      state.site.badge = $("site-badge").value.trim();
      state.site.search_placeholder = $("site-search").value.trim();
      state.site.notice = $("site-notice").value.trim();
      state.banner.title = $("banner-title").value.trim();
      state.banner.subtitle = $("banner-sub").value.trim();
      markDirty();
    });
  });

  function rowInput(value, cls, onChange) {
    const input = document.createElement("input");
    input.type = "text";
    input.value = value || "";
    if (cls) input.className = cls;
    input.addEventListener("input", () => onChange(input.value));
    return input;
  }

  function renderIcons() {
    const body = $("icons-body");
    body.innerHTML = "";
    (state.icons || []).forEach((it, idx) => {
      const tr = document.createElement("tr");
      const tdText = document.createElement("td");
      const tdLabel = document.createElement("td");
      const tdHref = document.createElement("td");
      const tdColor = document.createElement("td");
      const tdAct = document.createElement("td");

      tdText.appendChild(rowInput(it.text, "w-sm", (v) => { it.text = v; markDirty(); }));
      tdLabel.appendChild(rowInput(it.label, "", (v) => { it.label = v; markDirty(); }));
      tdHref.appendChild(rowInput(it.href, "", (v) => { it.href = v; markDirty(); }));

      const sel = document.createElement("select");
      sel.className = "w-color";
      for (let i = 1; i <= 8; i++) {
        const c = "c" + i;
        const opt = document.createElement("option");
        opt.value = c;
        opt.textContent = c;
        if ((it.color || "c1") === c) opt.selected = true;
        sel.appendChild(opt);
      }
      sel.addEventListener("change", () => { it.color = sel.value; markDirty(); });
      tdColor.appendChild(sel);

      const del = document.createElement("button");
      del.type = "button";
      del.className = "btn danger";
      del.textContent = "删";
      del.onclick = () => {
        state.icons.splice(idx, 1);
        markDirty();
        renderIcons();
      };
      tdAct.appendChild(del);

      tr.append(tdText, tdLabel, tdHref, tdColor, tdAct);
      body.appendChild(tr);
    });
  }

  function renderHot() {
    const body = $("hot-body");
    body.innerHTML = "";
    (state.hot || []).forEach((it, idx) => {
      const tr = document.createElement("tr");
      const cells = [
        rowInput(it.title, "", (v) => { it.title = v; markDirty(); }),
        rowInput(it.desc, "", (v) => { it.desc = v; markDirty(); }),
        rowInput(it.href, "", (v) => { it.href = v; markDirty(); }),
      ].map((el) => {
        const td = document.createElement("td");
        td.appendChild(el);
        return td;
      });

      const tdTop = document.createElement("td");
      const chk = document.createElement("input");
      chk.type = "checkbox";
      chk.checked = !!it.top;
      chk.addEventListener("change", () => { it.top = chk.checked; markDirty(); });
      tdTop.appendChild(chk);

      const tdAct = document.createElement("td");
      const del = document.createElement("button");
      del.type = "button";
      del.className = "btn danger";
      del.textContent = "删";
      del.onclick = () => {
        state.hot.splice(idx, 1);
        markDirty();
        renderHot();
      };
      tdAct.appendChild(del);

      tr.append(...cells, tdTop, tdAct);
      body.appendChild(tr);
    });
  }

  function renderTags() {
    const body = $("tags-body");
    body.innerHTML = "";
    (state.tags || []).forEach((it, idx) => {
      const tr = document.createElement("tr");
      const tdL = document.createElement("td");
      const tdH = document.createElement("td");
      const tdA = document.createElement("td");
      tdL.appendChild(rowInput(it.label, "", (v) => { it.label = v; markDirty(); }));
      tdH.appendChild(rowInput(it.href, "", (v) => { it.href = v; markDirty(); }));
      const del = document.createElement("button");
      del.type = "button";
      del.className = "btn danger";
      del.textContent = "删";
      del.onclick = () => {
        state.tags.splice(idx, 1);
        markDirty();
        renderTags();
      };
      tdA.appendChild(del);
      tr.append(tdL, tdH, tdA);
      body.appendChild(tr);
    });
  }

  $("btn-add-icon").onclick = () => {
    state.icons = state.icons || [];
    state.icons.push({ id: uid(), label: "新入口", text: "新", href: "/", color: "c1" });
    markDirty();
    renderIcons();
  };
  $("btn-add-hot").onclick = () => {
    state.hot = state.hot || [];
    state.hot.push({ id: uid(), title: "新热门", desc: "描述", href: "/", top: false });
    markDirty();
    renderHot();
  };
  $("btn-add-tag").onclick = () => {
    state.tags = state.tags || [];
    state.tags.push({ id: uid(), label: "新标签", href: "/" });
    markDirty();
    renderTags();
  };

  $("btn-save").onclick = async () => {
    try {
      const res = await fetch("/api/admin/content", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ csrf, data: state }),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || "保存失败");
      markDirty(false);
      toast("已保存，可刷新 /nav/ 查看");
    } catch (err) {
      toast(String(err.message || err));
    }
  };

  fillSite();
  renderIcons();
  renderHot();
  renderTags();
  markDirty(false);
})();
