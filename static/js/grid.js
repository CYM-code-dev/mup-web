// 可编辑表格组件 (覆盖 work/points/spike 三种; 派生列写回行 → 保 draft 往返 + 后端读取)。
// recompute/写回: 每次 edit/add/remove 后, 对每个 computed 列 row[key]=computed(row,ctx), 再重渲。

function el(tag, cls) { const e = document.createElement(tag); if (cls) e.className = cls; return e; }

export function createGrid(container, { columns, rows, dynamic = true, ctx = null, onChange = null, noteId = null, tableClass = null, foot = null, lead = null }) {
  function cols() { return typeof columns === "function" ? columns() : columns; }

  function recompute() {
    for (const r of rows) {
      for (const c of cols()) {
        if (c.computed) {
          try { r[c.key] = c.computed(r, ctx); } catch { r[c.key] = null; }
        }
        if (!("seed" in c) && !(c.key in r)) r[c.key] = null;
      }
    }
  }

  function fmt(v, c) {
    if (v == null || (typeof v === "number" && !isFinite(v))) return "";
    if (c.format) return c.format(v);
    return String(v);
  }

  function makeCell(r, c, ri) {
    if (c.computed && !(typeof c.editable === "function" && c.editable(r))) {
      const o = el("output", "cell-out");
      o.value = fmt(r[c.key], c); o.readOnly = true;
      return o;
    }
    if (c.type === "check") {
      const cb = el("input"); cb.type = "checkbox";
      cb.checked = !!r[c.key];
      cb.onchange = () => { r[c.key] = cb.checked; touched(); };
      return cb;
    }
    if (c.type === "select") {
      const s = el("select");
      const empty = el("option"); empty.value = ""; empty.textContent = "—"; s.appendChild(empty);
      const opts = typeof c.options === "function" ? c.options(r) : (c.options || []);
      opts.forEach(o => {
        const op = el("option");
        const isObj = o != null && typeof o === "object";
        op.value = isObj ? o.value : o; op.textContent = isObj ? (o.label ?? o.value) : o;
        s.appendChild(op);
      });
      s.value = r[c.key] != null ? r[c.key] : "";
      s.onchange = () => { r[c.key] = s.value || null; c.onSet && c.onSet(r); touched(); };
      return s;
    }
    const inp = el("input");
    inp.type = c.type === "number" ? "number" : "text";
    if (c.step) inp.step = c.step;
    if (c.min != null) inp.min = c.min;
    if (c.max != null) inp.max = c.max;
    inp.value = r[c.key] != null ? r[c.key] : "";
    if (typeof c.readOnly === "function" && c.readOnly(r)) { inp.readOnly = true; inp.classList.add("ro"); }
    if (typeof c.options === "function") {   // datalist: 下拉选预设或手输 (如规格)
      const dlId = `gdl-${c.key}-${ri}`;
      inp.setAttribute("list", dlId);
      const dl = el("datalist"); dl.id = dlId;
      c.options(r).forEach(o => { const op = el("option"); op.value = o; dl.appendChild(op); });
      inp._dl = dl;
    }
    inp.onchange = () => {
      let v = inp.value;
      if (c.type === "number") v = v === "" ? null : parseFloat(v);
      r[c.key] = v; c.onSet && c.onSet(r); touched();
    };
    return inp;
  }

  function touched() { recompute(); render(); onChange && onChange(rows); }

  function render() {
    if (dynamic && !rows.length) rows.push({});   // 空表默认留一行空白 (recompute 会补各列 null)
    recompute();
    container.innerHTML = "";
    const tbl = el("table", "grid");
    if (tableClass) tbl.classList.add(tableClass);
    const leadCols = typeof lead === "function" ? (lead() || []) : [];
    const thead = el("thead"); const trh = el("tr");
    leadCols.forEach(lc => { const lth = el("th"); lth.textContent = lc.header; trh.appendChild(lth); });
    cols().forEach(c => {
      const th = el("th");
      if (c.type === "check") {
        const all = el("input"); all.type = "checkbox"; all.title = "全选/反选";
        all.checked = rows.length > 0 && rows.every(r => !!r[c.key]);
        all.onchange = () => { rows.forEach(r => r[c.key] = all.checked); touched(); };
        th.appendChild(all);
      } else { th.textContent = c.label || c.key; }
      trh.appendChild(th);
    });
    if (dynamic) { const th = el("th"); th.textContent = ""; trh.appendChild(th); }
    thead.appendChild(trh); tbl.appendChild(thead);
    const tbody = el("tbody");
    rows.forEach((r, ri) => {
      const tr = el("tr");
      if (leadCols.length && ri === 0) { leadCols.forEach(lc => { const ltd = el("td"); ltd.rowSpan = rows.length; ltd.appendChild(lc.cell); tr.appendChild(ltd); }); }
      cols().forEach((c, ci) => { const td = el("td"); const cell = makeCell(r, c, ri); cell.dataset.r = ri; cell.dataset.c = ci; cell.dataset.key = c.key; td.appendChild(cell); if (cell._dl) td.appendChild(cell._dl); tr.appendChild(td); });
      if (dynamic) {
        const td = el("td");
        const btn = el("button", "row-del"); btn.type = "button"; btn.textContent = "−";
        btn.onclick = () => { rows.splice(ri, 1); touched(); };
        td.appendChild(btn); tr.appendChild(td);
      }
      tbody.appendChild(tr);
    });
    tbl.appendChild(tbody); container.appendChild(tbl);
    if (dynamic) {
      const add = el("button", "row-add"); add.type = "button"; add.textContent = "+ 新增行";
      add.onclick = () => {
        const nr = {};
        cols().forEach(c => { nr[c.key] = c.computed ? null : ("seed" in c ? c.seed : (c.type === "number" ? null : "")); });
        rows.push(nr); touched();
      };
      const footEls = typeof foot === "function" ? (foot() || []) : [];
      if (noteId || footEls.length) {
        const bar = el("div"); bar.className = "grid-foot"; bar.style.cssText = "display:flex;align-items:center;gap:.6rem;margin-top:.3rem;flex-wrap:wrap";
        bar.appendChild(add);
        footEls.forEach(e => bar.appendChild(e));
        if (noteId) { const n = el("small"); n.id = noteId; n.className = "muted"; n.style.cssText = "flex:1 1 auto;text-align:right;line-height:1.2;"; bar.appendChild(n); }
        container.appendChild(bar);
      } else {
        container.appendChild(add);
      }
    }
  }

  // Excel/表格粘贴: 以当前焦点单元格为起点, 把剪贴板按行(换行)/列(制表符)铺开。
  function resolveVal(c, val) {
    if (val === "") return undefined; // 空白跳过, 不清空原值
    if (c.type === "number") { const n = parseFloat(val); return isNaN(n) ? undefined : n; }
    if (c.type === "select") {
      const opts = c.options || [];
      if (opts.includes(val)) return val;
      const m = opts.find(o => o && (o.includes(val) || val.includes(o))); // 模糊匹配量器名
      return m != null ? m : undefined;
    }
    return val;
  }
  function onPaste(e) {
    const ae = document.activeElement;
    const r0 = parseInt(ae && ae.dataset && ae.dataset.r);
    const c0 = parseInt(ae && ae.dataset && ae.dataset.c);
    if (isNaN(r0) || isNaN(c0)) return; // 非表格单元格 → 走默认粘贴
    const text = ((e.clipboardData && e.clipboardData.getData("text/plain")) || "").replace(/\r\n/g, "\n").replace(/\r/g, "\n");
    let lines = text.split("\n");
    if (lines.length && lines[lines.length - 1] === "") lines.pop(); // 去掉 Excel 末尾空行
    if (!lines.length) return;
    e.preventDefault();
    const all = cols();
    if (dynamic) { // 动态表: 行不够自动补
      while (rows.length < r0 + lines.length) {
        const nr = {};
        cols().forEach(c => { nr[c.key] = c.computed ? null : ("seed" in c ? c.seed : (c.type === "number" ? null : "")); });
        rows.push(nr);
      }
    }
    let changed = false;
    lines.forEach((line, i) => {
      const r = rows[r0 + i];
      if (!r) return;
      line.split("\t").forEach((raw, j) => {
        const c = all[c0 + j];
        if (!c || c.type === "check") return;                                   // 复选列跳过
        if (c.computed && !(typeof c.editable === "function" && c.editable(r))) return; // 只读 computed 列跳过 (按行可编性, 与 makeCell 一致)
        const v = resolveVal(c, raw.trim());
        if (v !== undefined) { r[c.key] = v; changed = true; }
      });
    });
    if (changed) touched();
  }
  container.addEventListener("paste", onPaste);

  render();
  return { render, get rows() { return rows; } };
}
