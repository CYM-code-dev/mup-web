// 样液定容 混合试剂: 使用规格 (实际定容体积) + ΣVi 实时关系 (>, =, <)。
// single / multi 共用, 仅标量键与 rows 路径不同 (传 {vk,vv,vvCustom,vuse,rowsPath})。
// 容量瓶/单标吸量管 (flask/pip_s) 满刻度 → 使用规格=量器规格(锁); 其他默认=量器规格可改。
import { state as S } from './state.js';
import { el, bindInput } from './ui.js';

const FLASK_LIKE = (k) => k === "flask" || k === "pip_s";

export function blendVuseKit({ vk, vv, vvCustom, vuse, rowsPath }) {
  const rows = () => rowsPath.split(".").reduce((o, k) => (o == null ? o : o[k]), S()) || [];
  const nominal = () => {
    const bvv = S().scalars[vv];
    if (bvv === "自定义") { const c = parseFloat(S().scalars[vvCustom]); return isFinite(c) ? c : null; }
    return bvv != null && bvv !== "" ? parseFloat(bvv) : null;
  };
  // 草稿载入/用户手改保留已有值 (flask 强制跟随); 量器类型/规格变更 → resetBlendVuse 重新默认
  const syncBlendVuse = () => {
    const vn = nominal();
    if (FLASK_LIKE(S().scalars[vk]) || S().scalars[vuse] == null) S().scalars[vuse] = vn;
  };
  const resetBlendVuse = () => { S().scalars[vuse] = null; syncBlendVuse(); };
  const updateBlendVsumNote = (note) => {
    note = note || document.getElementById("blend-vsum-note"); if (!note) return;
    const vsum = rows().reduce((s, r) => s + (Number(r.vi) || 0), 0);
    const vu = S().scalars[vuse];
    const v = vu != null && vu !== "" && isFinite(Number(vu)) ? Number(vu) : null;
    if (vsum <= 0) { note.textContent = "填各试剂体积后显示 ΣVi 与使用规格的关系"; note.className = "muted"; return; }
    if (v == null) { note.textContent = `ΣVi = ${vsum.toFixed(2)} mL  (请填使用规格)`; note.className = "muted"; return; }
    const diff = vsum - v;
    if (Math.abs(diff) < 1e-9) { note.className = "ok"; note.textContent = `ΣVi = ${vsum.toFixed(2)} mL  =  使用规格 ${v} mL  ✓ 一致`; }
    else if (diff > 0) { note.className = "warn"; note.textContent = `ΣVi = ${vsum.toFixed(2)} mL  >  使用规格 ${v} mL  ⚠ 超出 ${diff.toFixed(2)} mL`; }
    else { note.className = "warn"; note.textContent = `ΣVi = ${vsum.toFixed(2)} mL  <  使用规格 ${v} mL  ⚠ 少 ${(-diff).toFixed(2)} mL`; }
  };
  // 使用规格字段 (ΣVi 提示由 createGrid 在 +新增行 右侧渲染); 返回 input
  const renderVuseField = (parent) => {
    const inp = bindInput(parent, "使用规格 (mL)", vuse, {
      type: "number",
      attrs: FLASK_LIKE(S().scalars[vk]) ? { disabled: true } : { min: 0.1, step: "any" },
      on: () => updateBlendVsumNote(),
    });
    return inp;
  };
  return { syncBlendVuse, resetBlendVuse, updateBlendVsumNote, renderVuseField };
}
