// 草稿箱 UI (模式无关): 标题后显示草稿名+脏标记(*); 工具栏单个「🗂 草稿 ▾」菜单
// 内含 保存/另存为/新建 + 草稿列表(调用/逐个删除)。
// sig/save/list/load/del/reset/defaultName 由各模式注入。
import { state } from './state.js';

let savedSig = null;
function sigOf(p) { const q = { ...p }; delete q._saved_at; return JSON.stringify(q); }   // 去时间戳, 否则永远 dirty

export function setupDraftUI({ sig, save, defaultName, list, load, del, reset }) {
  const S = state;
  const nameEl = document.getElementById("draft-name");
  const menuBtn = document.getElementById("btn-drafts");
  if (menuBtn) menuBtn.disabled = false;

  function dirty() { return savedSig != null && sigOf(sig()) !== savedSig; }
  function refresh() {
    if (!nameEl) return;
    const sc = S().scalars || {};
    const author = (sc.mu_meta_author || sc.meta_author || "").trim();   // multi: mu_meta_author; single: meta_author
    nameEl.textContent = (S().currentDraft || "新草稿") + "/" + (author || "xxx") + (dirty() ? " *" : "");
  }
  function markClean() { savedSig = sigOf(sig()); refresh(); }

  async function saveAsName(initial) {
    const name = prompt("另存为，输入名称：", initial);
    if (!name) return;
    try { await save(name); S().currentDraft = name; location.hash = "#" + encodeURIComponent(name); markClean(); }
    catch (e) { alert("保存失败: " + e.message); }
  }
  async function doSave() {
    if (S().currentDraft) { try { await save(S().currentDraft); markClean(); } catch (e) { alert("保存失败: " + e.message); } }
    else await saveAsName(defaultName());   // 未命名 → 走另存
  }
  function doNew() {
    if (dirty() && !confirm("当前草稿有未保存的修改，确定新建并丢弃吗？")) return;
    reset();
  }

  // ---- 草稿菜单 popover: 动作 + 列表 ----
  let pop = null;
  function closePop() {
    if (pop && pop.parentNode) pop.parentNode.removeChild(pop);
    pop = null;
    document.removeEventListener("mousedown", onOutside, true);
  }
  function onOutside(e) { if (pop && !pop.contains(e.target) && e.target !== menuBtn) closePop(); }
  async function fillList(target) {
    let names = []; try { names = await list(); } catch {}
    target.innerHTML = "";
    if (!names.length) { target.innerHTML = '<div class="dp-empty">(暂无草稿)</div>'; return; }
    names.forEach(n => {
      const row = document.createElement("div"); row.className = "dp-row";
      const lb = document.createElement("button"); lb.className = "dp-load" + (n === S().currentDraft ? " cur" : ""); lb.textContent = n;
      lb.onclick = () => { closePop(); load(n); };
      const db = document.createElement("button"); db.className = "dp-del"; db.title = "删除"; db.textContent = "🗑";
      db.onclick = async () => {
        if (!confirm(`删除草稿「${n}」？不可恢复。`)) return;
        try { await del(n); } catch (e) { alert("删除失败: " + e.message); return; }
        if (S().currentDraft === n) { S().currentDraft = null; markClean(); }
        fillList(target);
      };
      row.append(lb, db); target.appendChild(row);
    });
  }
  function openPop() {
    if (pop) { closePop(); return; }
    pop = document.createElement("div"); pop.className = "draft-pop";
    const act = (label, fn) => {
      const b = document.createElement("button"); b.className = "dp-act"; b.textContent = label;
      b.onclick = () => { closePop(); fn(); };
      pop.appendChild(b);
    };
    act("💾  保存", doSave);
    act("📄  另存为", () => saveAsName(S().currentDraft || defaultName()));
    act("✨  新建", doNew);
    const sep = document.createElement("div"); sep.className = "dp-sep"; pop.appendChild(sep);
    const lw = document.createElement("div"); lw.className = "dp-list"; lw.innerHTML = '<div class="dp-empty">加载中…</div>'; pop.appendChild(lw);
    const r = menuBtn.getBoundingClientRect();
    pop.style.left = r.left + "px"; pop.style.top = (r.bottom + 6) + "px";
    document.body.appendChild(pop);
    setTimeout(() => document.addEventListener("mousedown", onOutside, true), 0);
    fillList(lw);
  }
  if (menuBtn) menuBtn.onclick = (e) => { e.stopPropagation(); openPop(); };

  setInterval(refresh, 1000);   // 轮询覆盖全部改动路径(手填/AI/粘贴/溯源/重算)
  return { markClean, refresh };
}
