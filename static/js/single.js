// 单目标物: 5 Tab 表单 (绑定 state.scalars) + 3 可编辑表 + calc/report/drafts/download 接线。
import { getConstants, calcSingle, reportSingle, draftsList, draftsLoad, draftsSave, draftsDelete, aiParse, aiConfigStatus, solvAlpha, limsTrace } from './api.js';
import { state as S, set } from './state.js';
import { scalarDefaults, editorSeeds, applySingle, toSingle } from './drafts.js';
import { createGrid } from './grid.js';
import { kindOptions, volOptions, parseVesselNominal } from './vessel.js';
import { round_dp, round_sf, roundC, concStr, volStr, resultStr } from './util.js';
import { el, cardTitle, bindInput, bindSelect, bindRadio, bindCheckbox, downloadBlob, showPreview, cellSelect, cellInput, singleRowTable } from './ui.js';
import { setupDraftUI } from './draftui.js';
import { blendVuseKit } from './blend.js';
import { aiMethodKit } from './ai_method.js';
const { syncBlendVuse, resetBlendVuse, updateBlendVsumNote, renderVuseField } = blendVuseKit({
  vk: "blend_vk", vv: "blend_vv", vvCustom: "blend_vv_custom", vuse: "blend_vuse", rowsPath: "rows.blend",
});

const aiMethod = aiMethodKit({ mode: "single", render: () => renderT1() });

const MKIND = [{ value: "single", label: "单一溶剂" }, { value: "mixed", label: "混合试剂" }, { value: "multi", label: "多次定容" }];
const REAG_LABELS = { s: "试剂名称", k: "量器类型", v: "规格 (mL)", vi: "体积 (mL)", a: "膨胀系数 α" };
const MSOURCE = [{ value: "solid", label: "纯品称量" }, { value: "liquid_dilute", label: "高浓液标" }];
const MCERT = [{ value: "relative", label: "相对式 Urel(%)·k" }, { value: "absolute", label: "绝对式 浓度·U·k" }];
const MCM = [{ value: "外标法", label: "外标法" }, { value: "内标法", label: "内标法" }];
const BAL_IDS = ["CK-SB294-CG", "CK-SB295-CG", "CK-SB005-CG", "CK-SB030-FCM", "CK-SB032-EN"];
const INSTRUMENTS = ["液相质谱串联联用仪", "高效液相色谱仪", "气相色谱-质谱联用仪", "电感耦合等离子体质谱仪（ICPMS）", "紫外分光光度计", "气相色谱仪", "电感耦合等离子体发射光谱仪"];

export async function init() {
  const meta = await getConstants();
  set("meta", meta);
  S().scalars = { ...scalarDefaults(meta.baseline_params) };
  const name = decodeURIComponent(location.hash.slice(1));
  if (name) {
    try { const d = await draftsLoad(name); d._name = name; applySingle(d, S()); S().currentDraft = name; }
    catch { /* 草稿不存在 → 用默认空表 */ S().editors = editorSeeds(meta.baseline_params, meta); }
  } else {
    S().editors = editorSeeds(meta.baseline_params, meta);
  }
  const draftUI = setupDraftUI({
    sig: () => toSingle(S()),
    save: (name) => draftsSave(name, toSingle(S())),
    defaultName: () => S().scalars.analyte || "新草稿",
    list: draftsList, load: loadDraft, del: draftsDelete,
    reset: () => window.__newDraft(),
  });
  aiMethod.applyPending();
  aiMethod.renderStdLookup();
  renderT1(); renderT2(meta); renderT3(meta); renderT4(meta); renderT5(meta);
  wireCalcReport();
  draftUI.markClean();
  aiConfigStatus().then(c => {
    document.getElementById("meta-status").textContent =
      "AI " + (c.configured ? `✓ ${c.model}` : "✗ " + (c.missing.join("/") || "未配置"));
  }).catch(() => {});
}

// ---- 工具条: 草稿箱 popover ----
async function loadDraft(name) {
  const d = await draftsLoad(name); d._name = name;
  applySingle(d, S());
  location.hash = "#" + name;
  location.reload();
}

// ---- ① 总述 ----
function renderT1() {
  const c = document.getElementById("t1"); c.innerHTML = "";
  const hdr = el("div", "card"); hdr.append(cardTitle("页眉信息"));
  const hg = el("div", "grid-3");
  bindInput(hg, "报告编号 (Reference)", "meta_ref");
  bindInput(hg, "日期 (Date)", "meta_date");
  bindInput(hg, "编制人 (Author)", "meta_author");
  hdr.appendChild(hg);

  const u = el("div", "card"); u.append(cardTitle("结果单位设置"));
  const ug = el("div", "grid-3");
  bindSelect(ug, "单位", "unit", meta().unit_options.map(x => ({ value: x, label: x })), { on: () => renderT5(meta()) });   // 单位变 → ⑤ 标签(含单位)+ 理论目标物含量 + 测定值 w 重算
  bindSelect(ug, "结果修约方式", "round_mode", [{ value: "有效数字", label: "有效数字" }, { value: "小数位数", label: "小数位数" }], { on: recompSpike });
  bindInput(ug, "位数", "round_nd", { type: "number", attrs: { step: 1, min: 0 }, on: recompSpike });
  u.appendChild(ug);

  const env = el("div", "card"); env.append(cardTitle("测量环境"));
  const eg = el("div", "grid-2");
  bindInput(eg, "环境温度 (℃)", "env_temp", { type: "number", attrs: { step: 1 } });
  bindInput(eg, "温差 Δτ (℃)", "dtau", { type: "number", attrs: { step: 1 } });
  env.appendChild(eg);

  const topRow = el("div", "grid-3"); topRow.append(hdr, u, env); c.appendChild(topRow);

  const m = el("div", "card"); m.append(cardTitle("方法信息"));
  const mg = el("div", "grid-2");
  bindInput(mg, "报告标题", "title", { attrs: { placeholder: "ISO 17234-2:2011 高效液相色谱法测定染色皮革中4-氨基偶氮苯含量的不确定度评估" } });
  bindInput(mg, "测量依据/标准号", "basis", { attrs: { placeholder: "ISO 14362-1：2017《纺织品—偶氮染料衍生的某些芳香胺的测定方法》" } });
  const mg2 = el("div", "grid-4");
  bindInput(mg2, "仪器", "instrument", { datalist: INSTRUMENTS }); bindInput(mg2, "目标物", "analyte");
  bindInput(mg2, "基质", "matrix"); bindInput(mg2, "标准品", "std_name");
  m.appendChild(mg); m.appendChild(mg2); c.appendChild(m);

  const pf = el("div", "card"); pf.append(cardTitle("前处理"));
  bindInput(pf, "前处理流程", "prep_flow", { textarea: true, attrs: { rows: 4 } });
  const aiBtn = el("button", "ai-btn"); aiBtn.type = "button"; aiBtn.textContent = "🤖 AI 自动填充 m/V/INFL";
  aiBtn.onclick = aiApply;
  pf.appendChild(aiBtn);
  const aiMsg = el("div", "ai-msg"); aiMsg.id = "ai-msg"; pf.appendChild(aiMsg);
  c.appendChild(pf);
}
function balanceMPEmg(m) { return m <= 50 ? 0.5 : m <= 200 ? 1.0 : 1.5; }
function deriveBalanceTol() {  // m_sample 变 → d 重取 I级 MPE (写状态; 不重渲免丢焦点)
  const m = parseFloat(S().scalars.m_sample_raw);
  if (isFinite(m)) S().scalars.balance_tol_mg = balanceMPEmg(m);
}
async function aiApply() {
  const msg = document.getElementById("ai-msg");
  msg.textContent = "🏃 AI 解析中…"; msg.className = "ai-msg";
  const r = await aiParse(S().scalars.prep_flow || "");
  if (r.error) { msg.textContent = "❌ " + r.error; return; }
  Object.assign(S().scalars, r.scalars);
  if (r.scalars.balance_tol_mg == null) deriveBalanceTol();
  if (S().scalars.makeup_mode === "multi") S().rows.reag = r.rows.reag;
  if (S().scalars.makeup_mode === "mixed") S().rows.blend = r.rows.blend;
  renderT1(); renderT2(meta()); renderT3(meta());
  const m2 = document.getElementById("ai-msg");
  m2.innerHTML = (r.filled.length ? "<b>已填:</b> " + r.filled.join("、") : "⚠ AI 未识别出称样/定容信息") +
    (r.info ? "<br><b>重复性影响量:</b> " + r.info : "") +
    (r.notes.length ? "<br><i>" + r.notes.join(" / ") + "</i>" : "");
}

// ---- ② 样液定容 ----
function renderT2(meta) {
  const c = document.getElementById("t2"); c.innerHTML = "";
  const bal = el("div", "card"); bal.append(cardTitle("称量 / 天平"));
  const bg = el("div", "grid-4");
  bindInput(bg, "天平设备编号", "balance_id", { datalist: BAL_IDS, on: (v) => { if (BAL_IDS.includes(v)) { S().scalars.balance_tol_mg = 0.5; renderT2(meta); } } });
  bindInput(bg, "称样量 m (g)", "m_sample_raw", { on: deriveBalanceTol });
  bindInput(bg, "称量次数", "n_weighings", { type: "number", attrs: { step: 1 } });
  bindInput(bg, "示值允差 d (mg)", "balance_tol_mg", { type: "number", attrs: { step: 0.1 } });
  bal.appendChild(bg); c.appendChild(bal);
  const card = el("div", "card"); card.append(cardTitle("样液定容 urel(V)"));
  const modeWrap = el("div"); bindRadio(modeWrap, "定容模式", "makeup_mode", MKIND, { on: () => { renderT2(meta); renderT3(meta); } });
  card.appendChild(modeWrap);
  const branch = el("div", "branch");
  const mode = S().scalars.makeup_mode;
  if (mode === "mixed") {
    syncBlendVuse();
    renderReagentTable(branch, "blend", meta);
  } else if (mode === "multi") {
    renderReagentTable(branch, "reag", meta);
  } else {
    branch.appendChild(singleRowTable([
      { label: "量器类型", el: cellSelect(kindOptions(meta), "vessel_kind", () => renderT2(meta)) },
      { label: "量器规格 (mL)", el: cellSelect(volOptions(meta, S().scalars.vessel_kind), "vessel_vol_sel", () => renderT2(meta)) },
      { label: "定容试剂", el: cellSelect([...meta.solvents.map(s => ({ value: s.name_cn, label: s.name_cn })), { value: "自定义", label: "自定义" }], "solvent_preset", (v) => {
        const sol = meta.solvents.find(s => s.name_cn === v);
        if (sol) {
          S().scalars.makeup_solvent_val = sol.name_cn; S().scalars.alpha_val = sol.alpha;
          S().scalars.stock_solvent_preset = v; S().scalars.stock_solvent = sol.name_cn; S().scalars.stock_alpha = sol.alpha;
        }
        renderT2(meta); renderT3(meta);
      }) },
      { label: "试剂名称", el: cellInput("makeup_solvent_val") },
      { label: "膨胀系数 α", el: cellInput("alpha_val", "number") },
    ]));
    if (S().scalars.vessel_vol_sel === "自定义") {
      const cg = el("div", "grid-2");
      bindInput(cg, "量器规格 (mL)", "vessel_vol_custom", { type: "number", attrs: { min: 0.1, step: 1 }, on: syncSpikeVol });
      bindInput(cg, "允差 (mL)", "vessel_tol_custom", { type: "number" });
      branch.appendChild(cg);
    }
    if (["pip_g", "cylinder"].includes(S().scalars.vessel_kind)) {
      bindInput(branch, "实际定容体积 V (mL)", "vuv", { type: "number", on: syncSpikeVol });
    }
  }
  card.appendChild(branch); c.appendChild(card);
  updateBlendVsumNote();
  renderDensity(meta, c);
  syncSpikeVol();
}
// 试剂行改为可编辑表格 (混合试剂 blend / 多次定容 reag): +/− 增删行, 行数=rows.length → 同步 blend_n/n_reag
// 多次定容: 规格(v)=按量器类型下拉标准规格; 量器=容量瓶/单标吸量管(flask/pip_s)时 体积(vi)=规格(v) 并锁定
const FLASK_LIKE = (k) => k === "flask" || k === "pip_s";
function reagCols(prefix, meta) {
  const onSolvent = (r) => { const sol = meta.solvents.find(x => x.name_cn === r.s); if (sol) r.a = sol.alpha; };
  const syncVol = (r) => { if (FLASK_LIKE(r.k) && r.v != null && r.v !== "") r.vi = Number(r.v); };
  const cols = [
    { key: "s", type: "select", label: "试剂名称", options: [...meta.solvents.map(s => s.name_cn), "自定义"], onSet: onSolvent },
    { key: "vi", type: "number", label: "体积 (mL)", step: "any", readOnly: (r) => FLASK_LIKE(r.k) },
    { key: "a", type: "number", label: "膨胀系数 α", step: "any" },
  ];
  if (prefix === "reag") cols.splice(1, 0,
    { key: "k", type: "select", label: "量器类型", options: kindOptions(meta), onSet: syncVol },
    { key: "v", type: "select", label: "规格 (mL)", options: (r) => volOptions(meta, r.k).filter(o => o.value !== "自定义"), onSet: syncVol });
  return cols;
}
function stockFlaskCell(meta) {
  const sel = el("select");
  meta.volumes.flask.forEach(v => { const o = el("option"); o.value = String(v); o.textContent = `${v} mL (±${meta.glass_tolerance[`flask@${v}`]})`; sel.appendChild(o); });
  sel.value = S().scalars.stock_flask_s != null ? String(S().scalars.stock_flask_s) : "";
  sel.onchange = () => { S().scalars.stock_flask_s = sel.value; renderT3(meta); };
  return sel;
}
function sampleVesselLeads(meta) {
  const vk = el("select");
  kindOptions(meta).forEach(o => { const op = el("option"); op.value = o.value; op.textContent = o.label; vk.appendChild(op); });
  vk.value = S().scalars.blend_vk || "";
  vk.onchange = () => { S().scalars.blend_vk = vk.value; resetBlendVuse(); renderT2(meta); };
  const vvWrap = el("div");
  const vv = el("select");
  volOptions(meta, S().scalars.blend_vk).forEach(o => { const op = el("option"); op.value = o.value; op.textContent = o.label; vv.appendChild(op); });
  vv.value = S().scalars.blend_vv || "";
  vv.onchange = () => { S().scalars.blend_vv = vv.value; resetBlendVuse(); renderT2(meta); };
  vvWrap.appendChild(vv);
  if (S().scalars.blend_vv === "自定义") {
    const c1 = el("input"); c1.type = "number"; c1.placeholder = "规格"; c1.min = 0.1; c1.step = 1; c1.value = S().scalars.blend_vv_custom ?? ""; c1.style.width = "5rem";
    c1.onchange = () => { S().scalars.blend_vv_custom = c1.value === "" ? null : parseFloat(c1.value); resetBlendVuse(); updateBlendVsumNote(); syncSpikeVol(); };
    const c2 = el("input"); c2.type = "number"; c2.placeholder = "允差"; c2.value = S().scalars.blend_vv_tol_custom ?? ""; c2.style.width = "5rem";
    c2.onchange = () => { S().scalars.blend_vv_tol_custom = c2.value === "" ? null : parseFloat(c2.value); };
    vvWrap.appendChild(c1); vvWrap.appendChild(c2);
  }
  const vuse = el("input"); vuse.type = "number";
  if (FLASK_LIKE(S().scalars.blend_vk)) vuse.disabled = true; else { vuse.min = 0.1; vuse.step = "any"; }
  vuse.value = S().scalars.blend_vuse ?? "";
  vuse.onchange = () => { S().scalars.blend_vuse = vuse.value === "" ? null : parseFloat(vuse.value); updateBlendVsumNote(); syncSpikeVol(); };
  return [
    { header: "量器类型", cell: vk },
    { header: "量器规格 V (mL)", cell: vvWrap },
    { header: "使用规格 (mL)", cell: vuse },
  ];
}
const REAG_COUNT_KEY = { blend: "blend_n", reag: "n_reag", stock_blend: "stbl_n" };
function renderReagentTable(parent, prefix, meta) {
  const countKey = REAG_COUNT_KEY[prefix];
  const rows = S().rows[prefix];
  while (rows.length < 2) rows.push({});
  if (prefix === "reag") rows.forEach(r => { if (FLASK_LIKE(r.k) && r.v != null && r.v !== "") r.vi = Number(r.v); });
  S().scalars[countKey] = rows.length;
  const gh = el("div"); parent.appendChild(gh);
  createGrid(gh, {
    columns: reagCols(prefix, meta), rows, ctx: meta,
    noteId: prefix === "blend" ? "blend-vsum-note" : (prefix === "stock_blend" ? "stock-vsum-note" : null),
    lead: prefix === "blend" ? () => sampleVesselLeads(meta) : (prefix === "stock_blend" ? () => [{ header: "储备液容量瓶 (mL)", cell: stockFlaskCell(meta) }] : null),
    onChange: (rs) => {
      S().scalars[countKey] = rs.length;
      if (prefix === "blend") { renderT3(meta); updateBlendVsumNote(); syncSpikeVol(); }   // 样液 → 触发储备液跟随 + ΣVi 关系刷新 + ⑤定容体积跟随
      else if (prefix === "reag") { renderT3(meta); syncSpikeVol(); }   // 多次定容 → 触发储备液跟随 + ⑤定容体积跟随(ΣVi)
      else if (prefix === "stock_blend") { S().scalars.stock_blend_custom = true; updateStockVsumNote(); }  // 储备液手改 → 锁定 + 刷新 ΣVi 关系
    },
  });
}

// 储备液混合试剂: ΣVi 与容量瓶关系提示 (>, =, <); 容量瓶即定容目标, 无需 vuse。
function updateStockVsumNote(note) {
  note = note || document.getElementById("stock-vsum-note"); if (!note) return;
  const rows = S().rows.stock_blend || [];
  const vsum = rows.reduce((s, r) => s + (Number(r.vi) || 0), 0);
  const flask = parseFloat(S().scalars.stock_flask_s);
  const v = isFinite(flask) && flask > 0 ? flask : null;
  const lay = "flex:1 1 auto;text-align:right;line-height:1.2;";
  if (vsum <= 0) { note.style.cssText = lay; note.className = "muted"; note.textContent = "填各试剂体积后显示 ΣVi 与容量瓶关系"; return; }
  if (v == null) { note.style.cssText = lay; note.className = "muted"; note.textContent = `ΣVi = ${vsum.toFixed(2)} mL`; return; }
  const diff = vsum - v;
  note.style.cssText = lay;
  if (Math.abs(diff) < 1e-9) { note.className = "ok"; note.textContent = `ΣVi = ${vsum.toFixed(2)} mL  =  容量瓶 ${v} mL  ✓ 一致`; }
  else if (diff > 0) { note.className = "warn"; note.textContent = `ΣVi = ${vsum.toFixed(2)} mL  >  容量瓶 ${v} mL  ⚠ 超出 ${diff.toFixed(2)} mL`; }
  else { note.className = "warn"; note.textContent = `ΣVi = ${vsum.toFixed(2)} mL  <  容量瓶 ${v} mL  ⚠ 少 ${(-diff).toFixed(2)} mL`; }
}

// 高浓液标: 移取量器 / 移取体积 / 储备液容量瓶 三者关系检查 (移取体积不得超量器满刻度, 亦不得超容量瓶)。
function updateStockPipNote(note) {
  note = note || document.getElementById("stock-pip-note"); if (!note) return;
  note.textContent = ""; note.style.color = "";
  const s = S().scalars;
  if (s.stock_source !== "liquid_dilute") return;
  const pv = Number(s.pip_vol_actual);
  if (!(pv > 0)) return;
  const nom = parseVesselNominal(s.pip_vessel);
  const flask = parseFloat(s.stock_flask_s);
  const warns = [];
  if (nom && pv > nom + 1e-9) warns.push(`移取体积 ${pv} mL 超过 ${s.pip_vessel}(${nom} mL)`);
  if (isFinite(flask) && flask > 0 && pv > flask + 1e-9) warns.push(`移取体积 ${pv} mL 超过 储备液容量瓶 ${flask} mL`);
  if (warns.length) { note.textContent = "⚠ " + warns.join("；"); note.style.color = "#c00"; }
}

// ---- ③ 标准溶液 ----
function renderT3(meta) {
  const c = document.getElementById("t3"); c.innerHTML = "";
  let workGrid;   // 工作液网格句柄: 纯品称量字段变化时局部刷新首行母液浓度
  // 储备液混合试剂默认跟随样液定容 blend; 体积按储备液容量瓶等比缩放(保 ratio, 总量=容量瓶); 手改过/载入已有值 → stock_blend_custom 锁
  if (S().scalars.makeup_mode === "mixed" && !S().scalars.stock_blend_custom) {
    const blend = S().rows.blend || [];
    const flask = parseFloat(S().scalars.stock_flask_s);
    const vtot = blend.reduce((s, r) => s + (Number(r.vi) || 0), 0);
    const sc = (isFinite(flask) && flask > 0 && vtot > 0) ? flask / vtot : 1;
    S().rows.stock_blend = blend.map(r => ({
      ...r,
      vi: (r.vi == null || r.vi === "") ? r.vi : Math.round(Number(r.vi) * sc * 1e2) / 1e2,
    }));
    S().scalars.stbl_n = S().scalars.blend_n || 2;
    S().scalars.stock_makeup_mode = "mixed";
  }
  // 多次定容 → 储备液跟随其试剂 (动态): 同一试剂→单一溶剂; 多种试剂→混合试剂, 各试剂 vi 按容量瓶等比缩放; 手改过/载入已有值 → stock_blend_custom 锁
  else if (S().scalars.makeup_mode === "multi" && !S().scalars.stock_blend_custom) {
    const agg = []; const idx = new Map();
    for (const r of (S().rows.reag || [])) {
      if (!r.s) continue;
      const vi = Number(r.vi) || 0;
      if (idx.has(r.s)) idx.get(r.s).vi += vi;
      else { const o = { s: r.s, vi, a: r.a }; idx.set(r.s, o); agg.push(o); }
    }
    if (agg.length === 1) {
      S().scalars.stock_makeup_mode = "single";
      S().scalars.stock_solvent_preset = agg[0].s;
      S().scalars.stock_solvent = agg[0].s;
      S().scalars.stock_alpha = agg[0].a;
    } else if (agg.length >= 2) {
      const flask = parseFloat(S().scalars.stock_flask_s);
      const vtot = agg.reduce((s, r) => s + r.vi, 0);
      const sc = (isFinite(flask) && flask > 0 && vtot > 0) ? flask / vtot : 1;
      S().rows.stock_blend = agg.map(r => ({ s: r.s, vi: Math.round(r.vi * sc * 1e2) / 1e2, a: r.a }));
      S().scalars.stbl_n = agg.length;
      S().scalars.stock_makeup_mode = "mixed";
    }
  }
  renderTrace(meta, c);
  const card = el("details", "card"); card.open = S().stock_open !== false;
  card.addEventListener("toggle", () => { S().stock_open = card.open; });
  const stockSum = el("summary"); stockSum.textContent = "标准溶液 urel(C)"; card.append(stockSum);
  bindRadio(card, "储备液来源", "stock_source", MSOURCE, { on: () => renderT3(meta) });
  const stock = S().scalars.stock_source;
  const sw = el("div", "branch");
  if (stock === "solid") {
    sw.appendChild(singleRowTable([
      { label: "标准品纯度 p (%)", el: cellInput("purity", "number", () => workGrid && workGrid.render(), { pct: true }) },
      { label: "U(p) (%)", el: cellInput("U_purity", "number", null, { pct: true }) },
      { label: "包含因子 k", el: cellInput("k_purity", "number", null, { attrs: { step: 1 } }) },
      { label: "天平设备编号", el: cellInput("stock_balance_id", null, null, { datalist: BAL_IDS }) },
      { label: "标品称量 m_std (g)", el: cellInput("m_std", "number", () => workGrid && workGrid.render()) },
      { label: "示值允差 d (mg)", el: cellInput("stock_balance_tol_mg", "number", null, { attrs: { step: 0.1 } }) },
    ]));
  } else {
    // 高浓液标: 证书信息整合为单行表 (模式作下拉格); 两模式都采集证书浓度, 单位可选→内部换算 mg/L
    const cm = S().scalars.cert_mode;
    const cunit = S().scalars.C_cert_unit || "mg/L";
    sw.appendChild(singleRowTable([
      { label: "证书不确定度", el: cellSelect(MCERT, "cert_mode", () => renderT3(meta)) },
      { label: "证书浓度", el: cellInput("C_cert", "number", () => workGrid && workGrid.render()) },
      { label: "证书浓度单位", el: cellSelect((meta.conc_unit_options || ["mg/L"]).map(u => ({ value: u, label: u })), "C_cert_unit", () => renderT3(meta)) },
      { label: cm === "relative" ? "证书 Urel (%)" : `扩展不确定度 U (${cunit})`,
        el: cellInput(cm === "relative" ? "Urel_cert" : "U_abs", "number") },
      { label: "包含因子 k", el: cellInput("k_cert", "number") },
      { label: "移取量器", el: cellSelect(meta.pip_opts.map(s => ({ value: s, label: s })), "pip_vessel", v => { const nv = volStr(parseVesselNominal(v)); if (nv != null) S().scalars.pip_vol_actual = nv; renderT3(meta); }) },   // 选量器→自动填满刻度体积 + 刷新母液浓度
      { label: "移取体积 (mL)", el: cellInput("pip_vol_actual", "number", v => { const s = volStr(v); if (s != null) S().scalars.pip_vol_actual = s; renderT3(meta); }) },   // 手输 → ≥0.01 保留 2 位小数 (volStr, 同量器联动/工作液列); 重渲回显 + 刷母液浓度/三者检查
    ]));
    const pn = el("div"); pn.id = "stock-pip-note"; pn.className = "muted"; pn.style.cssText = "text-align:right;line-height:1.2;margin-top:.3rem;";
    sw.appendChild(pn);
  }
  card.appendChild(sw);
  // 储备液定容
  const mk = el("div", "branch");
  bindRadio(mk, "储备液定容试剂", "stock_makeup_mode", [{ value: "single", label: "单一溶剂" }, { value: "mixed", label: "混合试剂" }], { on: () => { S().scalars.stock_blend_custom = true; renderT3(meta); } });
  if (S().scalars.stock_makeup_mode === "mixed") {
    renderReagentTable(mk, "stock_blend", meta);
  } else {
    mk.appendChild(singleRowTable([
      { label: "储备液容量瓶 (mL)", el: cellSelect(meta.volumes.flask.map(v => ({ value: String(v), label: `${v} mL (±${meta.glass_tolerance[`flask@${v}`]})` })), "stock_flask_s", () => { if (workGrid) workGrid.render(); updateStockPipNote(); }) },
      { label: "定容试剂", el: cellSelect([...meta.solvents.map(s => ({ value: s.name_cn, label: s.name_cn })), { value: "自定义", label: "自定义" }], "stock_solvent_preset", (v) => {
        const sol = meta.solvents.find(s => s.name_cn === v);
        if (sol) { S().scalars.stock_solvent = sol.name_cn; S().scalars.stock_alpha = sol.alpha; }
        renderT3(meta);
      }) },
      { label: "试剂名称", el: cellInput("stock_solvent") },
      { label: "膨胀系数 α", el: cellInput("stock_alpha", "number") },
    ]));
  }
  card.appendChild(mk);
  // 工作液稀释链表
  const wc = el("details", "card"); wc.open = S().work_open !== false;
  wc.addEventListener("toggle", () => { S().work_open = wc.open; });
  const workSum = el("summary"); workSum.textContent = "中间液及工作液 (稀释链)"; wc.append(workSum);
  const chkRow = el("div"); chkRow.style.cssText = "display:flex;gap:1.2rem;flex-wrap:wrap";
  const bindCheckbox2 = (label, key, opts) => bindCheckbox(chkRow, label, key, opts);
  bindCheckbox2("工作液定容试剂与储备液一致", "work_same_solvent", { on: () => renderT3(meta) });
  bindCheckbox2("逐级稀释", "work_serial_dilute", { on: () => renderT3(meta) });
  wc.appendChild(chkRow);
  if (!S().scalars.work_same_solvent) {
    const wg = el("div", "grid-3");
    bindSelect(wg, "工作液定容试剂", "work_solvent_preset", [...meta.solvents.map(s => ({ value: s.name_cn, label: s.name_cn })), { value: "自定义", label: "自定义" }], {
      on: (v) => { const sol = meta.solvents.find(s => s.name_cn === v); if (sol) { S().scalars.work_solvent = sol.name_cn; S().scalars.work_alpha = sol.alpha; } renderT3(meta); }
    });
    bindInput(wg, "试剂名称", "work_solvent");
    bindInput(wg, "膨胀系数 α (1/℃)", "work_alpha", { type: "number" });
    wc.appendChild(wg);
  }
  const gh = el("div"); gh.id = "grid-work";
  for (const r of S().editors.work_df) if (!("定容量器" in r)) r["定容量器"] = WORK_FLASK_DEFAULT;   // 初始/加载缺省 → 默认容量瓶
  wc.appendChild(gh); c.appendChild(card); updateStockVsumNote(); updateStockPipNote(); c.appendChild(wc);
  workGrid = createGrid(gh, workGridCfg(meta));
  updateWorkNote(S().editors.work_df);
}
const WORK_FLASK_DEFAULT = "10 mL 容量瓶(A)(±0.02)";   // 定容量器列默认值 (合法选项, 见 _FLASK_OPTS)
function workGridCfg(meta) {
  const sc = S().scalars;
  const serial = !!sc.work_serial_dilute;   // 逐级稀释: 下行母液浓度 = 上行目标浓度
  const solid = sc.stock_source === "solid"; // 纯品称量: 首行母液浓度 = 储备液浓度(自动算)
  const liquid = sc.stock_source === "liquid_dilute"; // 高浓液标: 首行母液浓度 = 证书浓度(自动算)
  return {
    columns: [
      { key: "母液浓度(mg/L)", type: "text", label: "母液浓度(mg/L)",
        editable: r => { const i = S().editors.work_df.indexOf(r);
          if (i === 0 && (solid || liquid)) return false;   // 纯品/液标: 首行=储备液或证书浓度, 只读
          return serial ? i === 0 : true; },               // 逐级稀释仅首行可编; 非逐级全可编
        computed: (r, ctx) => { const rs = ctx.editors.work_df, i = rs.indexOf(r);
          if (i === 0 && solid) return solidStockConc();
          if (i === 0 && liquid) return liquidStockConc();
          if (serial && i > 0) return rs[i - 1]["目标浓度(mg/L)"];   // 逐级稀释: 取上行目标浓度
          return r["母液浓度(mg/L)"]; },
        onSet: r => { const s = concStr(r["母液浓度(mg/L)"]); if (s != null) r["母液浓度(mg/L)"] = s; } },
      { key: "移取量器", type: "select", label: "移取量器", options: meta.pip_opts,
        onSet: r => { const v = volStr(parseVesselNominal(r["移取量器"])); if (v != null) r["移取体积(mL)"] = v; } },   // 选量器→自动填满刻度体积
      { key: "移取体积(mL)", type: "number", label: "移取体积(mL)", step: "any",
        onSet: r => { const s = volStr(r["移取体积(mL)"]); if (s != null) r["移取体积(mL)"] = s; } },
      { key: "定容量器", type: "select", label: "定容量器", options: meta.flask_opts, seed: WORK_FLASK_DEFAULT },
      { key: "目标浓度(mg/L)", label: "目标浓度(mg/L)", computed: r => targetStr(r["母液浓度(mg/L)"], r["移取体积(mL)"], parseVesselNominal(r["定容量器"])) },
    ],
    rows: S().editors.work_df, dynamic: true, ctx: S(),
    noteId: "work-note",
    onChange: rows => { updateWorkNote(rows); if (S().scalars.curve_method === "外标法" && S().scalars.curve_link_chain) renderT4(meta); },   // 移取体积 vs 量器规格 一致性 + 联动稀释链时刷新曲线点
  };
}
function updateWorkNote(rows) {
  const n = document.getElementById("work-note");
  if (!n) return;
  const warns = [];
  rows.forEach((r, i) => {
    const vol = Number(r["移取体积(mL)"]), nom = parseVesselNominal(r["移取量器"]);
    const fnom = parseVesselNominal(r["定容量器"]);
    if (isFinite(vol) && nom && vol > nom + 1e-9)
      warns.push(`行${i + 1}: 移取体积 ${vol} 超过 ${r["移取量器"]}(${nom}mL)`);
    if (isFinite(vol) && fnom && vol > fnom + 1e-9)
      warns.push(`行${i + 1}: 移取体积 ${vol} 超过 定容量器(${fnom}mL)`);
  });
  n.textContent = warns.length ? "⚠ " + warns.join("；") : "";
  n.style.color = warns.length ? "#c00" : "";
}
function targetStr(c, v, fnom) {
  if (c == null || v == null || !fnom) return null;
  return concStr(Number(c) * Number(v) / Number(fnom));
}
// 纯品称量储备液浓度 (mg/L) = m_std(g)·purity·1e6 / 储备液容量瓶(mL); purity 已存为小数 → 结果即 mg/L
function solidStockConc() {
  const s = S().scalars;
  const m = Number(s.m_std), p = Number(s.purity), v = Number(s.stock_flask_s);
  return (m > 0 && p > 0 && v > 0) ? concStr(m * p * 1e6 / v) : null;
}
// 高浓液标储备液浓度 (mg/L) = 证书浓度(mg/L) × 移取体积 / 储备液容量瓶; 移取体积或容量瓶空 → 暂不算 (留空, 补全后自动生成)
function liquidStockConc() {
  const s = S().scalars;
  const exp = ((S().meta || {}).conc_unit_exp || {})[s.C_cert_unit || "mg/L"] ?? 0;
  const cMgL = Number(s.C_cert) * Math.pow(10, exp);
  const pv = Number(s.pip_vol_actual);
  const fv = Number(s.stock_flask_s);
  return (cMgL > 0 && pv > 0 && fv > 0) ? concStr(cMgL * pv / fv) : null;
}

// ---- LIMS 工作液溯源 ----
function renderTrace(meta, container) {
  const card = el("details", "card");
  card.open = S().trace_open !== false;
  card.addEventListener("toggle", () => { S().trace_open = card.open; });
  const sum = el("summary"); sum.textContent = "溯源自动填充"; card.append(sum);
  const fld = el("div", "field field-inline");
  const lab = el("label"); lab.textContent = "工作液编号 (如 D-9203)";
  lab.style.flex = "0 0 auto";   // 长标签按内容宽 (.field-inline>label 默认 6.5rem 会溢出)
  const inp = el("input"); inp.value = S().scalars._trace_code ?? "";
  inp.onchange = () => { S().scalars._trace_code = inp.value; };
  const btn = el("button", "ai-btn"); btn.type = "button"; btn.textContent = "溯源填充";
  btn.onclick = applyTrace;
  fld.append(lab, inp, btn);
  card.appendChild(fld);
  const fb = S().trace_fb;
  if (fb) {
    const f = el("div", "ai-msg");
    const parts = [];
    (fb.errors || []).forEach(e => parts.push("❌ " + e));
    if ((fb.filled || []).length) parts.push("✓ 已填: " + fb.filled.join("、"));
    (fb.notes || []).forEach(n => parts.push("• " + n));
    if ((fb.manual || []).length) parts.push("⚠ 需手补: " + fb.manual.join("、"));
    if (fb.chain) parts.push("溯源链: " + fb.chain);
    f.innerHTML = parts.join("<br>");
    card.appendChild(f);
  }
  container.appendChild(card);
}
async function applyTrace() {
  S().trace_fb = { errors: ["溯源中…"] };
  renderT3(meta());
  let r;
  try { r = await limsTrace(S().scalars._trace_code || ""); }
  catch (e) { S().trace_fb = { errors: ["请求失败: " + e.message] }; renderT3(meta()); return; }
  if (r.error) { S().trace_fb = { errors: [r.error] }; renderT3(meta()); return; }
  Object.assign(S().scalars, r.scalars);
  if (r.work_df && r.work_df.length) S().editors.work_df = r.work_df;
  S().trace_fb = r.feedback;
  renderT3(meta());
}

// ---- 密度计算器 (NIST → β; 库外溶剂 α 兜底) ----
function renderDensity(meta, container) {
  const card = el("details", "card");
  // ponytail: 原生 <details> 折叠; 默认收起(库外溶剂兜底工具), 有 β 结果或已填密度点时自动展开
  card.open = !!(S().dens_msg) || (S().dens || []).some(r => r["ρ(g/cm³)"] != null);
  const sum = el("summary"); sum.textContent = "🧪 NIST 密度 → β"; card.append(sum);
  if (!S().dens) S().dens = [{ "T℃": 15, "ρ(g/cm³)": null }, { "T℃": 20, "ρ(g/cm³)": null }, { "T℃": 25, "ρ(g/cm³)": null }];
  const g = el("div", "grid-2");
  const casInp = bindInput(g, "CAS 号 (如 110-54-3)", "nist_cas");
  const fetchBtn = el("button", "ai-btn"); fetchBtn.type = "button"; fetchBtn.textContent = "🔍 抓取并算 β";
  fetchBtn.onclick = async () => {
    const cas = (S().scalars.nist_cas || "").trim();
    if (!cas) { densMsg("先填 CAS 号"); return; }
    densMsg("抓取 NIST 中…");
    try { applyDensity(await solvAlpha({ cas })); }
    catch (e) { densMsg("❌ " + e.message); }
  };
  const casRow = el("div", "row-inline"); casRow.append(casInp, fetchBtn);
  g.lastChild.appendChild(casRow);
  card.appendChild(g);
  const gh = el("div"); gh.id = "grid-dens"; card.appendChild(gh);
  createGrid(gh, {
    columns: [
      { key: "T℃", type: "number", label: "T℃", step: 0.1 },
      { key: "ρ(g/cm³)", type: "number", label: "ρ(g/cm³)", step: "any" },
    ],
    rows: S().dens, dynamic: false, ctx: S(),
  });
  const msg = el("div", "ai-msg"); msg.id = "dens-msg"; msg.textContent = S().dens_msg || ""; card.appendChild(msg);
  container.appendChild(card);
}
function densMsg(t) { S().dens_msg = t; const m = document.getElementById("dens-msg"); if (m) m.textContent = t; }
function applyDensity(res) {
  if (res.points) S().dens = res.points.map(([T, r]) => ({ "T℃": T, "ρ(g/cm³)": r }));
  const mode = S().scalars.makeup_mode;
  if (mode === "single") {
    S().scalars.alpha_val = res.alpha;
    S().scalars.makeup_solvent_val = res.name;
    densMsg(`β = ${res.alpha.toPrecision(4)} /℃ 已填入上方 α(${res.name})。`);
  } else {
    densMsg(`β = ${res.alpha.toPrecision(4)} /℃(${res.name})。请手抄入对应试剂行的 α。`);
  }
  renderT2(meta());   // 密度卡在 T2; 重算后重开折叠显 β
}

// ---- ④ 曲线拟合 ----
function renderT4(meta) {
  const c = document.getElementById("t4"); c.innerHTML = "";
  const card = el("div", "card"); card.append(cardTitle("曲线拟合 urel(Q)"));
  const mrow = el("div", "row-inline"); mrow.style.flexWrap = "wrap"; mrow.style.alignItems = "flex-end";
  bindRadio(mrow, "曲线方法", "curve_method", MCM, { on: () => renderT4(meta) });
  bindCheckbox(mrow, "包含原点(0,0)参与拟合", "curve_include_origin");
  bindCheckbox(mrow, "强制过原点(0,0)", "curve_force_origin");
  if (S().scalars.curve_method === "外标法") {
    const cb = bindCheckbox(mrow, "联动稀释链", "curve_link_chain", { on: () => renderT4(meta) });
    cb.parentElement.style.marginLeft = "auto";   // 右对齐
  }
  card.appendChild(mrow);
  const gh = el("div"); gh.id = "grid-points"; card.appendChild(gh); c.appendChild(card);
  createGrid(gh, pointsGridCfg(meta));
}
function curveChainTargets() {
  return (S().editors.work_df || [])
    .map(r => Number(r["目标浓度(mg/L)"]))
    .filter(v => isFinite(v) && v > 0)
    .sort((a, b) => a - b);
}
function pointsGridCfg(meta) {
  const isIS = S().scalars.curve_method === "内标法";
  const linked = S().scalars.curve_method === "外标法" && S().scalars.curve_link_chain;
  const cols = [
    linked
      ? { key: "浓度mg/L", label: "浓度mg/L", computed: (r, ctx) => curveChainTargets()[ctx.editors.points_df.indexOf(r)] ?? null }
      : { key: "浓度mg/L", type: "number", label: "浓度mg/L", step: "any" },
    { key: "分析物峰面积", type: "number", label: "分析物峰面积", step: 1 },
  ];
  if (isIS) cols.push({ key: "内标峰面积", type: "number", label: "内标峰面积", step: 1 });
  return { columns: cols, rows: S().editors.points_df, dynamic: true, ctx: S() };
}

// ---- ⑤ 精密度 & 回收率 ----
function renderT5(meta) {
  const c = document.getElementById("t5"); c.innerHTML = "";
  const infl = el("div", "card");
  bindInput(infl, "重复性影响量(、分隔)", "influences");
  const _il = infl.querySelector("label"); if (_il) { _il.style.fontWeight = "700"; _il.style.color = "var(--ink)"; }
  c.appendChild(infl);
  const card = el("div", "card"); card.append(cardTitle("精密度 & 回收率"));
  const g = el("div", "grid-5");
  bindInput(g, "标液浓度 (mg/L)", "spike_std_conc", { type: "number", on: recompSpike });
  bindInput(g, "加标体积 (μL)", "spike_add_vol", { type: "number", on: recompSpike });
  const volInp = bindInput(g, "定容体积 V (mL)", "spike_vol", { type: "number", on: recompSpike });
  volInp.id = "in-spike-vol";
  const theorInp = bindInput(g, "理论加标 C₀ (mg/L)", "spike_theor", { type: "number" });
  theorInp.id = "in-spike-theor";
  const massInp = bindInput(g, `理论目标物含量 (${S().scalars.unit})`, "spike_add_mass", { type: "number" });
  massInp.id = "in-spike-mass";
  card.appendChild(g);
  c.appendChild(card);
  const gh = el("div"); gh.id = "grid-spike"; c.appendChild(gh);
  createGrid(gh, spikeGridCfg(meta));
  recompSpike();
}
function spikeGridCfg(meta) {
  const exp = meta.unit_exp[S().scalars.unit] ?? 0;
  const rm = S().scalars.round_mode; const nd = Number(S().scalars.round_nd);
  const rnd = rm === "有效数字" ? round_sf : round_dp;
  return {
    columns: [
      { key: "实测加标 C (mg/L)", type: "number", label: "实测加标 C (mg/L)", step: "any" },
      { key: "称样量 m (g)", type: "number", label: "称样量 m (g)", step: 0.0001 },
      { key: "回收率 R", label: "回收率 R", computed: r => (r["实测加标 C (mg/L)"] != null && S().scalars.spike_theor) ? round_sf(r["实测加标 C (mg/L)"] / S().scalars.spike_theor, 3) : null, format: v => resultStr(v, "有效数字", 3) },
      { key: "测定值 w", label: "测定值 w", computed: r => { const c = r["实测加标 C (mg/L)"], m = r["称样量 m (g)"]; return (c != null && m > 0) ? rnd(c * S().scalars.spike_vol / m * 10 ** exp, nd) : null; }, format: v => resultStr(v, rm, nd) },
    ],
    rows: S().editors.spike_df, dynamic: true, ctx: S(),
  };
}
// 定容体积 V (⑤ spike_vol 自动填充源): 镜像 engine_single 的 vessel_used_volume (single/mixed) / ΣVi (multi)
function makeupVolume() {
  const s = S().scalars;
  const n = x => { const v = Number(x); return (x === "" || x == null || !isFinite(v)) ? null : v; };
  if (s.makeup_mode === "multi") {
    const tot = (S().rows.reag || []).reduce((a, r) => a + (n(r && r.vi) || 0), 0);
    return tot > 0 ? tot : null;
  }
  if (s.makeup_mode === "mixed") {
    const vv = s.blend_vv === "自定义" ? n(s.blend_vv_custom) : n(s.blend_vv);
    return n(s.blend_vuse) ?? vv;
  }
  const vnom = s.vessel_vol_sel === "自定义" ? n(s.vessel_vol_custom) : n(s.vessel_vol_sel);
  if (vnom == null) return null;
  return ["pip_g", "cylinder"].includes(s.vessel_kind) ? (n(s.vuv) ?? vnom) : vnom;
}
// ② 定容信息变 → ⑤ 定容体积跟随 (同一瓶样液, V 相同; ②未填则不动 ⑤)
function syncSpikeVol() {
  const v = makeupVolume();
  if (v == null) return;
  S().scalars.spike_vol = v;
  const inp = document.getElementById("in-spike-vol"); if (inp) inp.value = v;
  recompSpike();
}
function recompSpike() {
  const s = S().scalars;
  const c0 = (s.spike_std_conc && s.spike_add_vol && s.spike_vol) ? s.spike_std_conc * s.spike_add_vol * 1e-3 / s.spike_vol : 0;
  if (s.spike_std_conc != null) s.spike_theor = roundC(c0);
  // 结果修约 (同 测定值 w): 有效数字→round_sf / 小数位数→round_dp, 位数 nd; 随 §1 修约设置变化
  const exp = meta().unit_exp[s.unit] ?? 0;
  const rnd = s.round_mode === "有效数字" ? round_sf : round_dp;
  const nd = Number(s.round_nd);
  const m = parseFloat(s.m_sample_raw);
  // 理论目标物含量 = C₀·V/m·10^exp (同模型 测定值 w=c·V/m·10^exp, 以理论 C₀ 代实测 c; m 取 ② 称样量)
  s.spike_add_mass = (c0 && s.spike_vol && isFinite(m) && m > 0) ? rnd(c0 * s.spike_vol / m * 10 ** exp, nd) : null;
  const ti = document.getElementById("in-spike-theor"); if (ti) ti.value = s.spike_theor ?? "";
  const mi = document.getElementById("in-spike-mass"); if (mi) mi.value = s.spike_add_mass != null ? resultStr(s.spike_add_mass, s.round_mode, s.round_nd) : "";
  const gh = document.getElementById("grid-spike");
  if (gh) createGrid(gh, spikeGridCfg(meta()));
}

// ---- calc / report / 草稿 / 下载 接线 ----
function collectState() { return { scalars: S().scalars, rows: S().rows, editors: S().editors }; }
function header() { const s = S().scalars; return { Reference: s.meta_ref, Date: s.meta_date, "Author(s)": s.meta_author }; }

function wireCalcReport() {
  const out = document.getElementById("calc-out");
  document.getElementById("btn-calc-test").textContent = "生成报告";
  document.getElementById("btn-calc-test").onclick = async () => {
    out.textContent = "计算中…";
    try {
      const body = { state: collectState(), header: header() };
      const r = await reportSingle(body);
      lastMd = r.md; lastResult = r.result;
      out.textContent = `U=${r.result.U?.toFixed(2)} ${S().scalars.unit}  urel_w=${r.result.urel_w?.toPrecision(4)}`;
      enableDownloads(body);
    } catch (e) { out.textContent = "❌ " + e.message; }
  };
}
let lastMd = null, lastResult = null;
function enableDownloads(body) {
  document.querySelectorAll(".dl").forEach(b => b.disabled = false);
  document.getElementById("dl-md").onclick = () => showPreview(lastMd);
  document.getElementById("dl-docx").onclick = () => {
    const parts = [S().scalars.meta_ref, S().scalars.title].map(x => (x || "").trim()).filter(Boolean);
    downloadBlob("/api/export/docx", body, (parts.join("_") || "不确定度评估") + ".docx");
  };
}
function meta() { return S().meta; }

// 草稿 保存 (暴露给工具条用)
window.__saveDraft = async (name) => { S().currentDraft = name; await draftsSave(name, toSingle(S())); };
window.__newDraft = () => { S().scalars = { ...scalarDefaults(meta().baseline_params) }; S().editors = editorSeeds(meta().baseline_params, meta()); S().rows = { reag: [], blend: [], stock_blend: [] }; location.hash = ""; location.reload(); };
