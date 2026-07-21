// 共享 UI helpers (single.js / multi.js 复用) — 绑定写回 S.scalars[key]
import { state as S } from './state.js';

export function el(tag, cls) { const e = document.createElement(tag); if (cls) e.className = cls; return e; }
export function cardTitle(t) { const h = el("h3"); h.textContent = t; return h; }

export function bindInput(parent, label, key, { type = "text", attrs = {}, on, textarea, datalist = null, pct = false } = {}) {
  const w = el("div", "field"); const lab = el("label"); lab.textContent = label;
  const inp = textarea ? el("textarea") : el("input");
  if (!textarea) inp.type = type;
  Object.assign(inp, attrs);
  // pct=true: 框里填/显示百分数, scalars[key] 仍存小数 (引擎按小数算). 见 single.js 纯度/U(p).
  const _sv = S().scalars[key];
  inp.value = pct && typeof _sv === "number" ? _sv * 100 : (_sv ?? "");
  inp.onchange = () => { let v = type === "number" ? (inp.value === "" ? null : parseFloat(inp.value)) : inp.value; if (pct && v != null) v = v / 100; S().scalars[key] = v; on && on(v); };
  if (datalist) {
    const dl = el("datalist"); dl.id = `${key}-dl`;
    datalist.forEach(o => { const op = el("option"); op.value = o; dl.appendChild(op); });
    inp.setAttribute("list", dl.id); w.appendChild(dl);
  }
  w.appendChild(lab); w.appendChild(inp); parent.appendChild(w); return inp;
}
export function bindSelect(parent, label, key, opts, { on } = {}) {
  const w = el("div", "field"); const lab = el("label"); lab.textContent = label;
  const sel = el("select");
  opts.forEach(o => { const op = el("option"); op.value = o.value; op.textContent = o.label; sel.appendChild(op); });
  sel.value = S().scalars[key] ?? opts[0]?.value;
  sel.onchange = () => { S().scalars[key] = sel.value; on && on(sel.value); };
  w.appendChild(lab); w.appendChild(sel); parent.appendChild(w); return sel;
}
export function bindRadio(parent, label, key, opts, { on } = {}) {
  const w = el("div", "field"); if (label) { const lab = el("label"); lab.textContent = label; w.appendChild(lab); }
  const row = el("span", "radio-row");
  opts.forEach(o => { const id = `${key}-${o.value}`; const r = el("input"); r.type = "radio"; r.name = key; r.id = id; r.value = o.value;
    if (String(S().scalars[key]) === String(o.value)) r.checked = true;
    r.onchange = () => { S().scalars[key] = o.value; on && on(o.value); };
    const pair = el("label"); pair.htmlFor = id; pair.style.display = "inline-flex"; pair.style.alignItems = "center"; pair.style.gap = ".3rem";
    pair.appendChild(r); pair.append(o.label);
    row.appendChild(pair); });
  w.appendChild(row); parent.appendChild(w); return w;
}
export function bindCheckbox(parent, label, key, { on } = {}) {
  const w = el("div", "field"); w.style.flexDirection = "row"; w.style.alignItems = "center"; w.style.gap = ".4rem";
  const inp = el("input"); inp.type = "checkbox"; inp.checked = !!S().scalars[key];
  inp.onchange = () => { S().scalars[key] = inp.checked; on && on(inp.checked); };
  const lab = el("label"); lab.textContent = label; w.appendChild(inp); w.appendChild(lab); parent.appendChild(w); return inp;
}

// 单行表格 (单一溶剂等: 表头 + 一行控件), 控件直绑 S.scalars[key]
export function cellSelect(opts, key, on) {
  const s = el("select");
  opts.forEach(o => { const op = el("option"); op.value = o.value; op.textContent = o.label; s.appendChild(op); });
  s.value = S().scalars[key] ?? "";
  s.onchange = () => { S().scalars[key] = s.value; on && on(s.value); };
  return s;
}
export function cellInput(key, type, on, { pct = false, datalist = null, attrs = {} } = {}) {
  const i = el("input"); if (type) i.type = type; Object.assign(i, attrs);
  // pct=true: 框里填/显示百分数, scalars[key] 存小数 (同 bindInput 纯度/U(p)).
  const _sv = S().scalars[key];
  i.value = pct && typeof _sv === "number" ? _sv * 100 : (_sv ?? "");
  i.onchange = () => { let v = type === "number" ? (i.value === "" ? null : parseFloat(i.value)) : i.value; if (pct && v != null) v = v / 100; S().scalars[key] = v; on && on(v); };
  if (!datalist) return i;
  const dl = el("datalist"); dl.id = `${key}-dl-cell`;
  datalist.forEach(o => { const op = el("option"); op.value = o; dl.appendChild(op); });
  i.setAttribute("list", dl.id);
  const wrap = el("span"); wrap.style.display = "contents"; wrap.append(i, dl); return wrap;   // display:contents → input 仍按 td 直系子元素布局
}
export function singleRowTable(cols) {
  const tbl = el("table", "grid");
  const thead = el("thead"); const hr = el("tr");
  cols.forEach(c => { const th = el("th"); th.textContent = c.label; hr.appendChild(th); });
  thead.appendChild(hr); tbl.appendChild(thead);
  const tbody = el("tbody"); const r = el("tr");
  cols.forEach(c => { const td = el("td"); td.appendChild(c.el); r.appendChild(td); });
  tbody.appendChild(r); tbl.appendChild(tbody);
  return tbl;
}

export async function downloadBlob(path, body, fname) {
  const res = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!res.ok) { alert("导出失败: " + (await res.text())); return; }
  const blob = await res.blob(); const url = URL.createObjectURL(blob);
  const a = el("a"); a.href = url; a.download = fname; a.click(); URL.revokeObjectURL(url);
}

// 报告预览弹层 (原生; 复用单/多目标物) — md 渲染成 Word 风格 HTML
export function showPreview(md) {
  let ov = document.getElementById("preview-overlay");
  if (!ov) {
    ov = el("div"); ov.id = "preview-overlay";
    const close = el("button"); close.type = "button"; close.className = "preview-close"; close.textContent = "✕";
    const box = el("div"); box.className = "preview-box";
    const doc = el("div"); doc.className = "preview-doc";
    box.appendChild(doc); ov.append(close, box); document.body.appendChild(ov);
    const hide = () => ov.classList.remove("open");
    close.onclick = hide;
    ov.addEventListener("click", e => { if (e.target === ov) hide(); });
    document.addEventListener("keydown", e => { if (e.key === "Escape") hide(); });
  }
  ov.querySelector(".preview-doc").innerHTML = mdToHtml(md || "(空报告)");
  ov.classList.add("open");
}

// ponytail: 零依赖 md→HTML, 只覆盖 gen_report 产出的构造 (标题/加粗小节/pipe 表/表标题/块级&行内公式/鱼骨占位)
const _esc = s => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const _GREEK = { tau: "τ", alpha: "α", beta: "β", gamma: "γ", Delta: "Δ", Sigma: "Σ", sigma: "σ", mu: "μ", rho: "ρ", theta: "θ", pi: "π", lambda: "λ" };

// LaTeX → HTML (递归下降, 处理嵌套大括号). 覆盖 \frac \sqrt \bar \mathrm \sum \times \cdot 及 _{}^{}
function texToHtml(tex) {
  const readGroup = (s, i) => {           // s[i]==='{' → 返回 {txt, next}
    let depth = 0;
    for (let j = i; j < s.length; j++) {
      if (s[j] === "{") depth++;
      else if (s[j] === "}" && --depth === 0) return { txt: s.slice(i + 1, j), next: j + 1 };
    }
    return { txt: s.slice(i + 1), next: s.length };
  };
  const render = s => {
    let out = "", i = 0;
    while (i < s.length) {
      const c = s[i];
      if (c === "\\") {
        let j = i + 1, cmd = "";
        while (j < s.length && /[A-Za-z]/.test(s[j])) cmd += s[j++];
        if (cmd === "frac" && s[j] === "{") {
          const n = readGroup(s, j), d = readGroup(s, n.next);
          out += `<span class="frac"><span class="num">${render(n.txt)}</span><span class="den">${render(d.txt)}</span></span>`;
          i = d.next;
        } else if (cmd === "sqrt") {
          if (s[j] === "{") { const g = readGroup(s, j); out += `√<span class="sqrt">${render(g.txt)}</span>`; i = g.next; }
          else { out += `√<span class="sqrt">${render(s[j] || "")}</span>`; i = j + 1; }
        } else if (cmd === "bar" && s[j] === "{") { const g = readGroup(s, j); out += render(g.txt) + "̄"; i = g.next; }
        else if (cmd === "mathrm" && s[j] === "{") { const g = readGroup(s, j); out += g.txt; i = g.next; }
        else if (cmd === "sum") { out += "Σ"; i = j; }
        else if (cmd === "times") { out += "×"; i = j; }
        else if (cmd === "cdot") { out += "·"; i = j; }
        else if (_GREEK[cmd]) { out += _GREEK[cmd]; i = j; }
        else if (cmd === "") {  // \, \ 等非字母命令
          out += (s[j] === "," || s[j] === " ") ? " " : (s[j] || "");
          i = j + 1;
        } else { out += cmd; i = j; }   // 未知命令: 去掉反斜杠保留字面
      } else if (c === "_" || c === "^") {
        const tag = c === "_" ? "sub" : "sup", n = s[i + 1];
        if (n === "{") { const g = readGroup(s, i + 1); out += `<${tag}>${render(g.txt)}</${tag}>`; i = g.next; }
        else if (n === "\\") {
          let j = i + 2, cm = ""; while (j < s.length && /[A-Za-z]/.test(s[j])) cm += s[j++];
          out += `<${tag}>${render("\\" + cm)}</${tag}>`; i = j;
        } else { out += `<${tag}>${render(n || "")}</${tag}>`; i += 2; }
      } else { out += c; i++; }
    }
    return out;
  };
  return render(tex);
}

// 行内: 先 HTML 转义 → 行内公式 $...$ → 加粗 **...**
const _inline = line => line
  .replace(/\$([^$\n]+)\$/g, (m, t) => `<span class="math">${texToHtml(t)}</span>`)
  .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");

function mdToHtml(md) {
  const lines = md.replace(/\r/g, "").split("\n");
  const html = [];
  let buf = [];                                   // 段落缓冲 (连续非空行)
  const flush = () => { if (buf.length) { html.push(`<p>${buf.map(_inline).join("<br>")}</p>`); buf = []; } };
  let i = 0;
  while (i < lines.length) {
    const ln = lines[i];
    if (/^#{1,6} /.test(ln)) { const lvl = ln.match(/^#+/)[0].length; flush(); html.push(`<h${Math.min(lvl, 6)}>${_esc(ln.replace(/^#+\s*/, ""))}</h${Math.min(lvl, 6)}>`); }
    else if (/^\*\*.+\*\*$/.test(ln)) { flush(); html.push(`<p class="subhead">${_inline(ln.slice(2, -2))}</p>`); }
    else if (/^\$\$.+\$\$$/.test(ln)) { flush(); html.push(`<div class="math-display">${texToHtml(ln.replace(/^\$\$\s*/, "").replace(/\s*\$\$$/, ""))}</div>`); }
    else if (/^表\d+[\s．.、]/.test(ln)) { flush(); html.push(`<div class="cap">${_inline(ln)}</div>`); }
    else if (ln === "!cause_effect!") { flush(); html.push(`<div class="placeholder">[因果关系图 — 导出 .docx 后插入]</div>`); }
    else if (ln.startsWith("|")) {                // 连续 | 行 → 表格
      flush();
      const rows = [];
      while (i < lines.length && lines[i].startsWith("|")) { if (!/^\|[-:\s|]+\|$/.test(lines[i])) rows.push(lines[i]); i++; }
      i--;                                        // 抵消循环末尾 i++
      const cells = r => r.replace(/^\||\|$/g, "").split("|").map(c => _inline(c.trim()));
      const thead = cells(rows[0]).map(c => `<th>${c}</th>`).join("");
      const tbody = rows.slice(1).map(r => `<tr>${cells(r).map(c => `<td>${c}</td>`).join("")}</tr>`).join("");
      html.push(`<div class="tbl-wrap"><table><thead><tr>${thead}</tr></thead><tbody>${tbody}</tbody></table></div>`);
    }
    else if (ln.trim() === "") flush();
    else buf.push(ln);
    i++;
  }
  flush();
  return html.join("\n");
}
