// 检测标准编号 → AI 自动填充方法信息 + 结果单位/修约/前处理, 并按 target_mode 自动切换单/多目标物模式。
// 多方法标准: AI 返回 methods 数组, 侧边栏出现「方法」下拉, 切换即重填该方法对应的单位/修约/前处理。
// 单/多模式共用; 跨模式切换走 sessionStorage 暂存 + reload (新模式 init 里 applyPending 套用)。
import { state as S } from './state.js';
import { el, bindInput } from './ui.js';
import { aiParseMethod } from './api.js';

const PENDING = 'aiMethodPending';
const STD_KEYS = ['title', 'basis', 'instrument', 'matrix', 'analyte'];

// 标准级标量 (各方法通用) → 目标模式键 (multi 加 mu_ 前缀; 仅单模式有 std_name)
function mapStd(ag, mode) {
  const pre = mode === 'multi' ? 'mu_' : '';
  const out = {};
  for (const k of STD_KEYS) if (ag[k] != null && ag[k] !== '') out[pre + k] = ag[k];
  if (mode !== 'multi' && ag.std_name) out.std_name = ag.std_name;
  return out;
}

// 单个方法 → 目标模式键 (round_nd 自动 +1, 即比标准规定多保留一位)
function mapMethod(m, mode) {
  const pre = mode === 'multi' ? 'mu_' : '';
  const out = {};
  if (m && m.prep_flow) out[pre + 'prep_flow'] = m.prep_flow;
  if (m && m.unit) out[pre + 'unit'] = m.unit;
  if (m && m.round_mode) out[pre + 'round_mode'] = m.round_mode;
  if (m && m.round_nd != null && m.round_nd !== '') out[pre + 'round_nd'] = Number(m.round_nd) + 1;
  return out;
}

function statusHtml(filled, notes, nMethods) {
  let s = (filled && filled.length ? '<b>已填:</b> ' + filled.join('、') : '⚠ AI 未识别出方法信息');
  if (nMethods > 1) s += `<br>共 ${nMethods} 个方法, 已填首个; 可在上方「方法」下拉切换。`;
  if (notes && notes.length) s += '<br><i>' + notes.join(' / ') + '</i>';
  return s;
}

export function aiMethodKit({ mode, render }) {
  let methods = [];
  let selIdx = 0;
  let pendingMsg = null;

  async function apply() {
    const msg = document.getElementById('ai-method-msg');
    if (msg) { msg.textContent = '🏃 AI 解析中…'; msg.className = 'ai-msg'; }
    const stdNo = S().scalars.method_std_no || '';
    let r;
    try { r = await aiParseMethod(stdNo); }
    catch (e) { if (msg) msg.textContent = '❌ ' + e.message; return; }
    if (r.error) { if (msg) msg.textContent = '❌ ' + r.error; return; }
    methods = Array.isArray(r.methods) ? r.methods : [];
    selIdx = 0;
    const target = r.target_mode || mode;
    const scalars = { ...mapStd(r.scalars || {}, target), ...mapMethod(methods[0], target) };
    if (target !== mode) {                       // 切换模式: 暂存映射好的标量+methods, 改 mode, reload
      sessionStorage.setItem(PENDING, JSON.stringify({ std_no: stdNo, scalars, methods, selIdx: 0, filled: r.filled, notes: r.notes }));
      sessionStorage.setItem('mode', target);
      location.hash = ''; location.reload();
      return;
    }
    Object.assign(S().scalars, scalars);
    renderStdLookup();                            // 多方法时显示「方法」下拉
    render();
    const m2 = document.getElementById('ai-method-msg');
    if (m2) m2.innerHTML = statusHtml(r.filled, r.notes, methods.length);
  }

  function selectMethod(i) {                     // 切「方法」下拉: 重填该方法的单位/修约/前处理 (不重调 AI)
    selIdx = i;
    const m = methods[i];
    if (!m) return;
    Object.assign(S().scalars, mapMethod(m, mode));
    render();
  }

  function applyPending() {                      // init 调用: 套用跨模式 reload 暂存的填充 (须在 renderT1 前)
    const raw = sessionStorage.getItem(PENDING);
    if (!raw) return;
    sessionStorage.removeItem(PENDING);
    try {
      const p = JSON.parse(raw);
      Object.assign(S().scalars, p.scalars || {});
      if (p.std_no != null) S().scalars.method_std_no = p.std_no;
      methods = Array.isArray(p.methods) ? p.methods : [];
      selIdx = p.selIdx || 0;
      pendingMsg = (p.filled || p.notes || methods.length > 1) ? { filled: p.filled || [], notes: p.notes || [], nMethods: methods.length } : null;
    } catch { /* 忽略损坏的暂存 */ }
  }

  function renderStdLookup() {
    const host = document.getElementById('side-std-lookup');
    if (!host) return;
    host.innerHTML = '';
    const inp = bindInput(host, '检测标准编号', 'method_std_no', { attrs: { placeholder: 'GB/T 2912.1' } });
    inp.closest('.field').querySelector('label').style.fontStyle = 'italic';
    const btn = el('button', 'ai-btn'); btn.type = 'button';
    btn.textContent = '🤖 AI 自动填充'; btn.onclick = apply;
    host.appendChild(btn);
    if (methods.length > 1) {                     // 多方法 → 「方法」下拉
      const w = el('div', 'field');
      const lab = el('label'); lab.textContent = '方法'; w.appendChild(lab);
      const sel = el('select');
      methods.forEach((m, i) => {
        const o = el('option'); o.value = i; o.textContent = m.name || ('方法' + (i + 1));
        if (i === selIdx) o.selected = true; sel.appendChild(o);
      });
      sel.onchange = () => selectMethod(Number(sel.value));
      w.appendChild(sel); host.appendChild(w);
    }
    const msg = el('div', 'ai-msg'); msg.id = 'ai-method-msg'; host.appendChild(msg);
    if (pendingMsg) { msg.innerHTML = statusHtml(pendingMsg.filled, pendingMsg.notes, pendingMsg.nMethods); pendingMsg = null; }
  }

  return { apply, applyPending, renderStdLookup };
}
