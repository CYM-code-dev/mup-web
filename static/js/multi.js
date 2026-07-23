// 多目标物: 5 Tab (mu_ 标量 + 分组拓扑宽表 + 中间液/工作液 + Excel) + calc/report/drafts。
// 参数装配/校验留后端 (engine_multi.build_params_multi); 前端只发 v4 state (scalars+topo_rows+grp_params+meas+curve_meta)。
import { getConstants, reportMulti, draftsMultiList, draftsMultiLoad, draftsMultiSave, draftsMultiDelete, aiParseMulti, aiConfigStatus, solvAlpha, templateMultiDownload, templateMultiUpload } from './api.js';
import { state as S, set } from './state.js';
import { scalarDefaultsMulti, applyMulti, toMulti } from './drafts.js';
import { createGrid } from './grid.js';
import { kindOptions, volOptions, parseVesselNominal } from './vessel.js';
import { concStr, volStr, concRound, concFmt, concAvgFmt } from './util.js';
import { el, cardTitle, bindInput, bindSelect, bindRadio, bindCheckbox, downloadBlob, showPreview, cellSelect, cellInput, singleRowTable } from './ui.js';
import { setupDraftUI } from './draftui.js';
import { blendVuseKit } from './blend.js';
import { aiMethodKit } from './ai_method.js';
const { syncBlendVuse, resetBlendVuse, updateBlendVsumNote, renderVuseField } = blendVuseKit({
  vk: "mu_blend_vk", vv: "mu_blend_vv", vvCustom: "mu_blend_vv_custom", vuse: "mu_blend_vuse", rowsPath: "mu_rows.blend",
});

const MCM = [{ value: "外标法", label: "外标法" }, { value: "内标法", label: "内标法" }];
const BAL_IDS = ["CK-SB294-CG", "CK-SB295-CG", "CK-SB005-CG", "CK-SB030-FCM", "CK-SB032-EN"];
const INSTRUMENTS = ["液相质谱串联联用仪", "高效液相色谱仪", "气相色谱-质谱联用仪", "电感耦合等离子体质谱仪（ICPMS）", "紫外分光光度计", "气相色谱仪", "电感耦合等离子体发射光谱仪"];

export async function init() {
  const meta = await getConstants();
  set("meta", meta);
  S().scalars = { ...scalarDefaultsMulti(meta.baseline_params) };
  S().topo_rows = [{ 分组名: "纯品-1", 类型: "固体", 目标物: "" }, { 分组名: "液体-1", 类型: "液体", 目标物: "", "Urel%": null, "C_cert": null, "U_abs": null, "定容分组": "定容组1" }];
  S().grp_params = {}; S().ding = {}; S().meas = null; S().curve_meta = {};
  const name = decodeURIComponent(location.hash.slice(1));
  if (name) {
    try { const d = await draftsMultiLoad(name); d._name = name; applyMulti(d, S()); S().currentDraft = name; }
    catch { /* 草稿不存在 → 默认空 */ }
  }
  wireExcel();
  const draftUI = setupDraftUI({
    sig: () => toMulti(S()),
    save: (name) => draftsMultiSave(name, toMulti(S())),
    defaultName: () => S().scalars.mu_analyte || "多目标物草稿",
    list: draftsMultiList, load: loadDraftMulti, del: draftsMultiDelete,
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
function meta() { return S().meta; }
function gp(gn) { return S().grp_params[gn] || (S().grp_params[gn] = {}); }
function re3() { renderT3(meta()); }

// ---- 工具条: 草稿箱 + Excel ----
async function loadDraftMulti(name) {
  const d = await draftsMultiLoad(name); d._name = name;
  applyMulti(d, S()); location.hash = "#" + name; location.reload();
}
function wireExcel() {
  const btn = document.getElementById("btn-excel"); btn.disabled = false; btn.title = "Excel 模板下载/上传";
  btn.onclick = excelMenu;
}

// ---- ① 总述 ----
function renderT1() {
  const c = document.getElementById("t1"); c.innerHTML = "";
  const hdr = el("div", "card"); hdr.append(cardTitle("页眉信息"));
  const hg = el("div", "grid-3");
  bindInput(hg, "报告编号 (Reference)", "mu_meta_ref");
  bindInput(hg, "日期 (Date)", "mu_meta_date");
  bindInput(hg, "编制人 (Author)", "mu_meta_author");
  hdr.appendChild(hg);

  const u = el("div", "card"); u.append(cardTitle("结果单位设置"));
  const ug = el("div", "grid-3");
  bindSelect(ug, "单位", "mu_unit", meta().unit_options.map(x => ({ value: x, label: x })));
  bindSelect(ug, "结果修约方式", "mu_round_mode", [{ value: "有效数字", label: "有效数字" }, { value: "小数位数", label: "小数位数" }]);
  bindInput(ug, "位数", "mu_round_nd", { type: "number", attrs: { step: 1, min: 0 } });
  u.appendChild(ug);

  const env = el("div", "card"); env.append(cardTitle("测量环境"));
  const eg = el("div", "grid-2");
  bindInput(eg, "环境温度 (℃)", "mu_env_temp", { type: "number", attrs: { step: 1 } });
  bindInput(eg, "温差 Δτ (℃)", "mu_dtau", { type: "number", attrs: { step: 1 } });
  env.appendChild(eg);

  const topRow = el("div", "grid-3"); topRow.append(hdr, u, env); c.appendChild(topRow);

  const m = el("div", "card"); m.append(cardTitle("方法信息"));
  const mg = el("div", "grid-2");
  bindInput(mg, "报告标题", "mu_title", { attrs: { placeholder: "ISO 14362-1：2017 液相法测定纺织品中禁用偶氮染料含量的不确定度评估" } });
  bindInput(mg, "测量依据/标准号", "mu_basis", { attrs: { placeholder: "ISO 14362-1：2017《纺织品—偶氮染料衍生的某些芳香胺的测定方法》" } });
  const mg2 = el("div", "grid-3");
  bindInput(mg2, "仪器", "mu_instrument", { datalist: INSTRUMENTS }); bindInput(mg2, "基质", "mu_matrix"); bindInput(mg2, "多目标物总名称", "mu_analyte");
  m.appendChild(mg); m.appendChild(mg2); c.appendChild(m);

  const pf = el("div", "card"); pf.append(cardTitle("前处理"));
  bindInput(pf, "前处理流程", "mu_prep_flow", { textarea: true, attrs: { rows: 4 } });
  const aiBtn = el("button", "ai-btn"); aiBtn.type = "button"; aiBtn.textContent = "🤖 AI 自动填充 m/V/INFL";
  aiBtn.onclick = aiApply;
  pf.appendChild(aiBtn);
  const aiMsg = el("div", "ai-msg"); aiMsg.id = "ai-msg"; pf.appendChild(aiMsg);
  c.appendChild(pf);
}
function balanceMPEmg(m) { return m <= 50 ? 0.5 : m <= 200 ? 1.0 : 1.5; }
function deriveBalanceTol() {
  const m = parseFloat(S().scalars.mu_m_sample_raw);
  if (isFinite(m)) S().scalars.mu_balance_tol_mg = balanceMPEmg(m);
}
async function aiApply() {
  const msg = document.getElementById("ai-msg");
  msg.textContent = "🏃 AI 解析中…";
  const r = await aiParseMulti(S().scalars.mu_prep_flow || "");
  if (r.error) { msg.textContent = "❌ " + r.error; return; }
  Object.assign(S().scalars, r.scalars);
  if (r.mu_rows) S().mu_rows = r.mu_rows;
  if (r.scalars.mu_balance_tol_mg == null) deriveBalanceTol();
  renderT1(); renderT2(meta());
  msg.innerHTML = (r.filled.length ? "<b>已填:</b> " + r.filled.join("、") : "⚠ AI 未识别出称样/定容信息") +
    (r.info ? "<br><b>重复性影响量:</b> " + r.info : "") +
    (r.notes.length ? "<br><i>" + r.notes.join(" / ") + "</i>" : "");
}

// ---- ② 样液定容 (单一/混合/多次 + 试剂/α + NIST 密度) ----
const aiMethod = aiMethodKit({ mode: "multi", render: () => renderT1() });

const MMU = [{ value: "single", label: "单一溶剂" }, { value: "mixed", label: "混合试剂" }, { value: "multi", label: "多次定容" }];
function renderT2(meta) {
  const c = document.getElementById("t2"); c.innerHTML = "";
  const bal = el("div", "card"); bal.append(cardTitle("称量 / 天平"));
  const bg = el("div", "grid-4");
  bindInput(bg, "天平设备编号", "mu_balance_id", { datalist: BAL_IDS, on: (v) => { if (BAL_IDS.includes(v)) { S().scalars.mu_balance_tol_mg = 0.5; renderT2(meta); } } });
  bindInput(bg, "称样量 m (g)", "mu_m_sample_raw", { on: deriveBalanceTol });
  bindInput(bg, "称量次数", "mu_n_weighings", { type: "number", attrs: { step: 1 } });
  bindInput(bg, "示值允差 d (mg)", "mu_balance_tol_mg", { type: "number", attrs: { step: 0.1 } });
  bal.appendChild(bg); c.appendChild(bal);
  const card = el("div", "card"); card.append(cardTitle("样液定容 urel(V)"));
  const modeWrap = el("div"); bindRadio(modeWrap, "定容模式", "mu_makeup_mode", MMU, { on: () => { renderT2(meta); re3(); } });
  card.appendChild(modeWrap);
  const branch = el("div", "branch");
  const mode = S().scalars.mu_makeup_mode;
  if (mode === "mixed") {
    syncBlendVuse();
    renderReagentTable(branch, "blend", meta);
  } else if (mode === "multi") {
    renderReagentTable(branch, "reag", meta);
  } else {
    branch.appendChild(singleRowTable([
      { label: "量器类型", el: cellSelect(kindOptions(meta), "mu_vessel_kind", () => renderT2(meta)) },
      { label: "量器规格 (mL)", el: cellSelect(volOptions(meta, S().scalars.mu_vessel_kind), "mu_vessel_vol_sel", () => renderT2(meta)) },
      { label: "定容试剂", el: cellSelect([...meta.solvents.map(s => ({ value: s.name_cn, label: s.name_cn })), { value: "自定义", label: "自定义" }], "solvent_preset", (v) => {
        const sol = meta.solvents.find(s => s.name_cn === v);
        if (sol) {
          S().scalars.makeup_solvent_val = sol.name_cn; S().scalars.alpha_val = sol.alpha;
          for (const pfx of ["mu_stock", "mu_liq_stock"]) { S().scalars[pfx + "_solvent_preset"] = v; S().scalars[pfx + "_solvent"] = sol.name_cn; S().scalars[pfx + "_alpha"] = sol.alpha; }
        }
        renderT2(meta); re3();
      }) },
      { label: "试剂名称", el: cellInput("makeup_solvent_val") },
      { label: "膨胀系数 α", el: cellInput("alpha_val", "number") },
    ]));
  }
  card.appendChild(branch); c.appendChild(card);
  updateBlendVsumNote();
  renderDensity(meta, c);
}

// 试剂行改为可编辑表格 (混合试剂 blend / 多次定容 reag): +/− 增删行, 行数=rows.length → 同步 mu_blend_n/mu_n_reag
// 多次定容: 规格(v)支持下拉(按量器类型的标准规格)或手输; 量器=容量瓶/单标吸量管(flask/pip_s)时 体积(vi)=规格(v) 并锁定
const FLASK_LIKE = (k) => k === "flask" || k === "pip_s";
function muReagCols(prefix, meta) {
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
function muSampleVesselLeads(meta) {
  const vk = el("select");
  kindOptions(meta).forEach(o => { const op = el("option"); op.value = o.value; op.textContent = o.label; vk.appendChild(op); });
  vk.value = S().scalars.mu_blend_vk || "";
  vk.onchange = () => { S().scalars.mu_blend_vk = vk.value; resetBlendVuse(); renderT2(meta); };
  const vvWrap = el("div");
  const vv = el("select");
  volOptions(meta, S().scalars.mu_blend_vk).forEach(o => { const op = el("option"); op.value = o.value; op.textContent = o.label; vv.appendChild(op); });
  vv.value = S().scalars.mu_blend_vv || "";
  vv.onchange = () => { S().scalars.mu_blend_vv = vv.value; resetBlendVuse(); renderT2(meta); };
  vvWrap.appendChild(vv);
  if (S().scalars.mu_blend_vv === "自定义") {
    const c1 = el("input"); c1.type = "number"; c1.placeholder = "规格"; c1.min = 0.1; c1.step = 1; c1.value = S().scalars.mu_blend_vv_custom ?? ""; c1.style.width = "5rem";
    c1.onchange = () => { S().scalars.mu_blend_vv_custom = c1.value === "" ? null : parseFloat(c1.value); resetBlendVuse(); updateBlendVsumNote(); };
    const c2 = el("input"); c2.type = "number"; c2.placeholder = "允差"; c2.value = S().scalars.mu_blend_vv_tol_custom ?? ""; c2.style.width = "5rem";
    c2.onchange = () => { S().scalars.mu_blend_vv_tol_custom = c2.value === "" ? null : parseFloat(c2.value); };
    vvWrap.appendChild(c1); vvWrap.appendChild(c2);
  }
  const vuse = el("input"); vuse.type = "number";
  if (FLASK_LIKE(S().scalars.mu_blend_vk)) vuse.disabled = true; else { vuse.min = 0.1; vuse.step = "any"; }
  vuse.value = S().scalars.mu_blend_vuse ?? "";
  vuse.onchange = () => { S().scalars.mu_blend_vuse = vuse.value === "" ? null : parseFloat(vuse.value); updateBlendVsumNote(); };
  return [
    { header: "量器类型", cell: vk },
    { header: "量器规格 V (mL)", cell: vvWrap },
    { header: "使用规格 (mL)", cell: vuse },
  ];
}
const MU_REAG_COUNT_KEY = { blend: "mu_blend_n", reag: "mu_n_reag", mu_stock_blend: "mu_stock_blend_n", mu_liq_stock_blend: "mu_liq_stock_blend_n", mu_work_blend: "mu_work_blend_n" };
function renderReagentTable(parent, prefix, meta) {
  const countKey = MU_REAG_COUNT_KEY[prefix];
  const rows = S().mu_rows[prefix] || (S().mu_rows[prefix] = []);
  while (rows.length < 2) rows.push({});
  if (prefix === "reag") rows.forEach(r => { if (FLASK_LIKE(r.k) && r.v != null && r.v !== "") r.vi = Number(r.v); });  // 维持 vi=v 不变式
  S().scalars[countKey] = rows.length;
  const gh = el("div"); parent.appendChild(gh);
  createGrid(gh, {
    columns: muReagCols(prefix, meta), rows, ctx: meta,
    noteId: prefix === "blend" ? "blend-vsum-note" : null,
    lead: prefix === "blend" ? () => muSampleVesselLeads(meta) : null,
    onChange: (rs) => {
      S().scalars[countKey] = rs.length;
      if (prefix === "blend") { re3(); updateBlendVsumNote(); }
      else if (prefix === "reag") { re3(); }   // 多次定容 → 触发储备液跟随
      else if (prefix === "mu_stock_blend") { S().scalars.mu_stock_blend_custom = true; computeMuBlendAlpha("mu_stock"); syncMuStockFlask(meta); re3(); }   // 固体储备液手改 → 锁 + 刷 α + 容量瓶跟随 ΣVi + 重渲(刷提示)
      else if (prefix === "mu_liq_stock_blend") { S().scalars.mu_liq_stock_blend_custom = true; computeMuBlendAlpha("mu_liq_stock"); re3(); }   // 液体储备液手改 → 锁 + 刷 α + 重渲
      else if (prefix === "mu_work_blend") { computeMuBlendAlpha("mu_work"); re3(); }   // 工作液混合手改 → 刷 α(mu_work_alpha) + 重渲
    },
  });
}

// ---- 密度计算器 (NIST → β; 复用 single) ----
function renderDensity(meta, container) {
  const card = el("details", "card");
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
    try { applyDensity(await solvAlpha({ cas })); } catch (e) { densMsg("❌ " + e.message); }
  };
  const casRow = el("div", "row-inline"); casRow.append(casInp, fetchBtn);
  g.lastChild.appendChild(casRow); card.appendChild(g);
  const gh = el("div"); gh.id = "grid-dens"; card.appendChild(gh);
  createGrid(gh, { columns: [{ key: "T℃", type: "number", label: "T℃", step: 0.1 }, { key: "ρ(g/cm³)", type: "number", label: "ρ(g/cm³)", step: "any" }], rows: S().dens, dynamic: false, ctx: S() });
  const dm = el("div", "ai-msg"); dm.id = "dens-msg"; dm.textContent = S().dens_msg || ""; card.appendChild(dm);
  container.appendChild(card);
}
function densMsg(t) { S().dens_msg = t; const m = document.getElementById("dens-msg"); if (m) m.textContent = t; }
function applyDensity(res) {
  if (res.points) S().dens = res.points.map(([T, r]) => ({ "T℃": T, "ρ(g/cm³)": r }));
  S().scalars.alpha_val = res.alpha;
  S().scalars.makeup_solvent_val = res.name;
  densMsg(`β = ${res.alpha.toPrecision(4)} /℃ 已填入 α(${res.name})。`);
  renderT2(meta());
}

// ---- ③ 标准溶液 (固/液宽表 + 液体每组折叠 + 中间液/工作液) ----
function renderT3(meta) {
  const c = document.getElementById("t3"); c.innerHTML = "";
  // 储备液(固/液)混合试剂默认跟随样液 mu_blend (逐字复制配比; 组级容量瓶在宽表); 用户手改过/载入已有值 → 锁
  if (S().scalars.mu_makeup_mode === "mixed") {
    const blend = S().mu_rows.blend || [];
    for (const pfx of ["mu_stock", "mu_liq_stock"]) {
      if (S().scalars[pfx + "_blend_custom"]) continue;
      S().mu_rows[pfx + "_blend"] = blend.map(r => ({ ...r }));
      S().scalars[pfx + "_blend_n"] = S().scalars.mu_blend_n || 2;
      S().scalars[pfx + "_makeup_mode"] = "mixed";
    }
  }
  // 多次定容 → 储备液(固/液)跟随其试剂 (动态): 同一试剂→单一溶剂; 多种试剂→混合试剂 (固体按容量瓶等比缩放, 保比例); 用户手改过/载入已有值 → 锁
  else if (S().scalars.mu_makeup_mode === "multi") {
    const agg = []; const idx = new Map();
    for (const r of (S().mu_rows.reag || [])) {
      if (!r.s) continue;
      const vi = Number(r.vi) || 0;
      if (idx.has(r.s)) idx.get(r.s).vi += vi;
      else { const o = { s: r.s, vi, a: r.a }; idx.set(r.s, o); agg.push(o); }
    }
    if (agg.length >= 1) {
      for (const pfx of ["mu_stock", "mu_liq_stock"]) {
        if (S().scalars[pfx + "_blend_custom"]) continue;
        if (agg.length === 1) {
          S().scalars[pfx + "_makeup_mode"] = "single";
          S().scalars[pfx + "_solvent_preset"] = agg[0].s;
          S().scalars[pfx + "_solvent"] = agg[0].s;
          S().scalars[pfx + "_alpha"] = agg[0].a;
        } else {  // ≥2 种试剂 → 混合; 固体按容量瓶等比缩放(保比例, 总量=容量瓶); 无单一容量瓶 → 原值
          const vtot = agg.reduce((s, r) => s + r.vi, 0);
          let sc = 1;
          if (pfx === "mu_stock" && vtot > 0) {
            const fl = [...new Set(S().topo_rows.filter(r => r.类型 === "固体")
              .map(r => parseVesselNominal(r["储备液容量瓶(mL)"])).filter(v => v != null))];
            const flask = fl.length === 1 ? fl[0] : null;
            if (flask) sc = flask / vtot;
          }
          S().mu_rows[pfx + "_blend"] = agg.map(r => ({ s: r.s, vi: Math.round(r.vi * sc * 1e2) / 1e2, a: r.a }));
          S().scalars[pfx + "_blend_n"] = agg.length;
          S().scalars[pfx + "_makeup_mode"] = "mixed";
        }
      }
    }
  }
  // 单一溶剂 → 储备液(固/液)跟随样液单一溶剂 (模式 + 试剂); 手改过/载入已有值 → 锁
  else {
    for (const pfx of ["mu_stock", "mu_liq_stock"]) {
      if (S().scalars[pfx + "_blend_custom"]) continue;
      S().scalars[pfx + "_makeup_mode"] = "single";
      if (S().scalars.solvent_preset) S().scalars[pfx + "_solvent_preset"] = S().scalars.solvent_preset;
      if (S().scalars.makeup_solvent_val) S().scalars[pfx + "_solvent"] = S().scalars.makeup_solvent_val;
      if (S().scalars.alpha_val !== "" && S().scalars.alpha_val != null) S().scalars[pfx + "_alpha"] = S().scalars.alpha_val;
    }
  }
  const card = el("div", "card"); card.append(cardTitle("标准品分组拓扑"));
  const sw = el("div", "radio-row");
  bindCheckbox(sw, "固体标准品", "mu_show_solid", { on: re3 });
  bindCheckbox(sw, "液体标准品", "mu_show_liquid", { on: re3 });
  card.appendChild(sw);
  // 分组名单一类型 警告
  const warn = groupnameConflict();
  if (warn) { const w = el("div", "ai-msg"); w.textContent = "⚠ " + warn; card.appendChild(w); }
  c.appendChild(card);

  if (S().scalars.mu_show_solid) {
    const cs = el("details", "card"); cs.open = S().mu_solid_open !== false;
    cs.addEventListener("toggle", () => { S().mu_solid_open = cs.open; });
    const solidSum = el("summary"); solidSum.textContent = "固体标准品"; cs.append(solidSum);
    syncMuStockFlask(meta);                   // 先同步容量瓶状态 (不依赖渲染顺序)
    wideTable(cs, "solid", meta);             // 固体明细 (上)
    stockReagentBlock(cs, meta, "mu_stock");  // 储备液定容试剂 (下)
    c.appendChild(cs);
  }
  if (S().scalars.mu_show_liquid) {
    const cl = el("details", "card"); cl.open = S().mu_liquid_open !== false;
    cl.addEventListener("toggle", () => { S().mu_liquid_open = cl.open; });
    const liquidSum = el("summary"); liquidSum.textContent = "液体标准品"; cl.append(liquidSum);
    liquidFolds(cl, meta);
    stockReagentBlock(cl, meta, "mu_liq_stock");
    syncLiquidRows(); wideTable(cl, "liquid", meta);
    cl.appendChild(el("div")); // 折叠区占位
    c.appendChild(cl);
  }
  // 中间液及工作液
  const cw = el("details", "card"); cw.open = S().mu_work_open === true;
  cw.addEventListener("toggle", () => { S().mu_work_open = cw.open; });
  const workSum = el("summary"); workSum.textContent = "中间液及工作液"; cw.append(workSum);
  const wchk = el("div"); wchk.style.cssText = "display:flex;gap:1.2rem;flex-wrap:wrap";
  bindCheckbox(wchk, "逐级稀释", "mu_work_serial_dilute", { on: re3 });
  bindCheckbox(wchk, "工作液定容试剂与储备液一致", "mu_work_same_solvent", { on: re3 });
  cw.appendChild(wchk);
  if (!S().scalars.mu_work_same_solvent) {
    stockReagentBlock(cw, meta, "mu_work", "工作液定容试剂");
  }
  interWork(cw, meta);
  c.appendChild(cw);
}
// 储备液混合试剂: blend α 写回 <prefix>_alpha (后端读 mu_stock_alpha/mu_liq_stock_alpha)。
function computeMuBlendAlpha(prefix) {
  const rows = S().mu_rows[prefix + "_blend"] || [];
  const vtot = rows.reduce((s, r) => s + (Number(r.vi) || 0), 0);
  const va = rows.reduce((s, r) => s + (Number(r.vi) || 0) * (Number(r.a) || 0), 0);
  if (vtot > 0) S().scalars[prefix + "_alpha"] = va / vtot;
}
// 固体储备液 ΣVi 与各组容量瓶关系提示 (容量瓶在宽表, 按组): 单组或各组同规格 → 比对; 各组异规格 → 仅显 ΣVi。
function updateMuStockVsumNote(note) {
  note = note || document.getElementById("mu-stock-vsum-note"); if (!note) return;
  const rows = S().mu_rows.mu_stock_blend || [];
  const vsum = rows.reduce((s, r) => s + (Number(r.vi) || 0), 0);
  const flasks = [...new Set(S().topo_rows.filter(r => r.类型 === "固体")
    .map(r => parseVesselNominal(r["储备液容量瓶(mL)"])).filter(v => v != null))];
  const v = flasks.length === 1 ? flasks[0] : null;
  const lay = "flex:1;text-align:right;line-height:1.2;margin-top:.3rem;";
  if (vsum <= 0) { note.style.cssText = lay; note.className = "muted"; note.textContent = "填各试剂体积后显示 ΣVi 与容量瓶关系"; return; }
  if (v == null) { note.style.cssText = lay; note.className = "muted"; note.textContent = flasks.length > 1 ? `ΣVi = ${vsum.toFixed(2)} mL (各组容量瓶不同: ${flasks.join("/")} mL)` : `ΣVi = ${vsum.toFixed(2)} mL`; return; }
  const diff = vsum - v;
  note.style.cssText = lay;
  if (Math.abs(diff) < 1e-9) { note.className = "ok"; note.textContent = `ΣVi = ${vsum.toFixed(2)} mL  =  容量瓶 ${v} mL  ✓ 一致`; }
  else if (diff > 0) { note.className = "warn"; note.textContent = `ΣVi = ${vsum.toFixed(2)} mL  >  容量瓶 ${v} mL  ⚠ 超出 ${diff.toFixed(2)} mL`; }
  else { note.className = "warn"; note.textContent = `ΣVi = ${vsum.toFixed(2)} mL  <  容量瓶 ${v} mL  ⚠ 少 ${(-diff).toFixed(2)} mL`; }
}
// 液体储备液 ΣVi 与各定容分组容量瓶关系提示 (容量瓶在液体组折叠 flasks[dg]): 单一规格 → 比对; 多规格 → 仅显 ΣVi。
function updateMuLiqStockVsumNote(note) {
  note = note || document.getElementById("mu-liq-stock-vsum-note"); if (!note) return;
  const rows = S().mu_rows.mu_liq_stock_blend || [];
  const vsum = rows.reduce((s, r) => s + (Number(r.vi) || 0), 0);
  const flasks = [];
  S().topo_rows.forEach(r => {
    if (r.类型 !== "液体") return;
    const fl = gp((r.分组名 || "").trim())?.flasks?.[r.定容分组 || "定容组1"];
    if (fl && fl.flask_vol) flasks.push(fl.flask_vol);
  });
  const uniq = [...new Set(flasks)];
  const v = uniq.length === 1 ? uniq[0] : null;
  const lay = "flex:1;text-align:right;line-height:1.2;margin-top:.3rem;";
  if (vsum <= 0) { note.style.cssText = lay; note.className = "muted"; note.textContent = "填各试剂体积后显示 ΣVi 与容量瓶关系"; return; }
  if (v == null) { note.style.cssText = lay; note.className = "muted"; note.textContent = uniq.length > 1 ? `ΣVi = ${vsum.toFixed(2)} mL (各dg容量瓶不同: ${uniq.join("/")} mL)` : `ΣVi = ${vsum.toFixed(2)} mL`; return; }
  const diff = vsum - v;
  note.style.cssText = lay;
  if (Math.abs(diff) < 1e-9) { note.className = "ok"; note.textContent = `ΣVi = ${vsum.toFixed(2)} mL  =  容量瓶 ${v} mL  ✓ 一致`; }
  else if (diff > 0) { note.className = "warn"; note.textContent = `ΣVi = ${vsum.toFixed(2)} mL  >  容量瓶 ${v} mL  ⚠ 超出 ${diff.toFixed(2)} mL`; }
  else { note.className = "warn"; note.textContent = `ΣVi = ${vsum.toFixed(2)} mL  <  容量瓶 ${v} mL  ⚠ 少 ${(-diff).toFixed(2)} mL`; }
}

// 固体储备液容量瓶默认跟随 ΣVi: ΣVi 命中标准规格 → 填入各组容量瓶; 手改过 → mu_stock_flask_custom 锁, 停止跟随。
function syncMuStockFlask(meta) {
  if (S().scalars.mu_stock_flask_custom) return;
  const rows = S().mu_rows.mu_stock_blend || [];
  const vsum = rows.reduce((s, r) => s + (Number(r.vi) || 0), 0);
  if (vsum <= 0) return;
  const opt = meta.flask_opts.find(o => Math.abs((parseVesselNominal(o) ?? NaN) - vsum) < 1e-6);
  if (!opt) return;
  const nom = parseVesselNominal(opt);
  S().topo_rows.forEach(r => {
    if (r.类型 !== "固体") return;
    r["储备液容量瓶(mL)"] = opt;
    const gn = (r.分组名 || "").trim(); if (gn) gp(gn).flask_volume_mL = nom;
  });
}
// 储备液定容试剂 (单一/混合 → α; 全方法统一)。prefix=mu_stock(固)/mu_liq_stock(液)。
function stockReagentBlock(parent, meta, prefix, label = "储备液定容试剂") {
  const mk = el("div", "branch");
  const modeKey = prefix + "_makeup_mode";
  bindRadio(mk, label, modeKey,
    [{ value: "single", label: "单一溶剂" }, { value: "mixed", label: "混合试剂" }],
    { on: () => { S().scalars[prefix + "_blend_custom"] = true; renderT3(meta); } });
  if (S().scalars[modeKey] === "mixed") {
    // 固/液同一: 试剂配比表; blend α 静默写回 <prefix>_alpha (固体容量瓶在宽表, 由 onChange 跟随 ΣVi)
    computeMuBlendAlpha(prefix);
    renderReagentTable(mk, prefix + "_blend", meta);
  } else {
    mk.appendChild(singleRowTable([
      { label: "定容试剂", el: cellSelect([...meta.solvents.map(s => ({ value: s.name_cn, label: s.name_cn })), { value: "自定义", label: "自定义" }], prefix + "_solvent_preset", (v) => {
        const sol = meta.solvents.find(s => s.name_cn === v);
        if (sol) { S().scalars[prefix + "_solvent"] = sol.name_cn; S().scalars[prefix + "_alpha"] = sol.alpha; }
        renderT3(meta);
      }) },
      { label: "试剂名称", el: cellInput(prefix + "_solvent") },
      { label: "膨胀系数 α", el: cellInput(prefix + "_alpha", "number") },
    ]));
  }
  parent.appendChild(mk);
}
function groupnameConflict() {
  const sg = new Set(S().topo_rows.filter(r => r.类型 === "固体").map(r => r.分组名?.trim()).filter(Boolean));
  const lg = new Set(S().topo_rows.filter(r => r.类型 === "液体").map(r => r.分组名?.trim()).filter(Boolean));
  const both = [...sg].filter(x => lg.has(x));
  return both.length ? `分组名「${both.join(",")}」同时含固体与液体: 模型要求每分组名单一类型, 请拆分。` : "";
}

// 宽表 (固/液): 行 = topo_rows 中该类型; 加删操作 topo_rows; 编辑写回行
function wideTable(parent, kind, meta) {
  const kn = kind === "solid" ? "固体" : "液体";  // topo_rows.类型 存中文, kind 传英文 → 归一
  const rows = S().topo_rows.filter(r => r.类型 === kn);
  const det = el("details");
  if (kind === "liquid") {
    det.open = S().mu_liq_detail_open === true;   // 液体明细默认折叠 (仅会话内记忆展开, 刷新回折叠)
    det.addEventListener("toggle", () => { S().mu_liq_detail_open = det.open; });
    det.style.marginTop = "2rem";   // 储备液定容试剂 ↔ 液体明细 增加间距
  } else {
    det.open = true;
  }
  const sum = el("summary"); sum.textContent = kind === "solid"
    ? "固体明细"
    : "液体明细";
  det.appendChild(sum);
  const tbl = el("table", "grid");
  const thead = el("thead"); const trh = el("tr");
  const cols = kind === "solid"
    ? ["分组名", "目标物", "纯度p(%)", "U_purity(%)", "k_purity", "标品称量 m_std (g)", "标品天平编号", "标品天平 d (mg)", "储备液容量瓶(mL)"]
    : ["分组名", "目标物", "Urel%", "C_cert", "U_abs"];
  cols.forEach(t => { const th = el("th"); th.textContent = t; trh.appendChild(th); });
  { const th = el("th"); trh.appendChild(th); }
  thead.appendChild(trh); tbl.appendChild(thead);
  const tbody = el("tbody");
  let solidSeen = 0;
  S().topo_rows.forEach((r, idx) => {
    if (r.类型 !== kn) return;
    const tr = el("tr");
    if (kind === "solid") {
      groupNameCell(tr, r); cellText(tr, r, "目标物");
      cellNum(tr, r, "纯度p", true); cellNum(tr, r, "U_purity", true); cellNum(tr, r, "k_purity"); cellNum(tr, r, "m_std(g)");
      if (solidSeen === 0) {   // 方法级标品天平 → 合并单元格(跨所有固体组), 置于标品称量右侧
        const tdBid = el("td"); tdBid.rowSpan = rows.length;
        const bid = el("input"); bid.value = S().scalars.mu_solid_balance_id ?? ""; bid.setAttribute("list", "mu-solid-bal-dl");
        const dl = el("datalist"); dl.id = "mu-solid-bal-dl"; BAL_IDS.forEach(b => { const o = el("option"); o.value = b; dl.appendChild(o); });
        bid.onchange = () => { S().scalars.mu_solid_balance_id = bid.value; };
        const tdBd = el("td"); tdBd.rowSpan = rows.length;
        const bd = el("input"); bd.type = "number"; bd.step = 0.1; bd.value = S().scalars.mu_solid_bal_mg ?? "";
        bd.onchange = () => { S().scalars.mu_solid_bal_mg = bd.value === "" ? null : parseFloat(bd.value); };
        tdBid.append(bid, dl); tdBd.appendChild(bd); tr.append(tdBid, tdBd);
      }
      solidSeen++;
      // 储备液容量瓶 — 逐行独立: 各目标物可设不同规格 (组级 gp[gn].flask_volume_mL 取末次编辑行; engine 当前按组取一瓶)
      const td = el("td"); const sel = el("select");
      const empty = el("option"); empty.value = ""; empty.textContent = "—"; sel.appendChild(empty);
      meta.flask_opts.forEach(o => { const op = el("option"); op.value = op.textContent = o; sel.appendChild(op); });
      sel.value = r["储备液容量瓶(mL)"] || "";
      sel.onchange = () => {
        const v = sel.value || null; r["储备液容量瓶(mL)"] = v;
        const gn = (r.分组名 || "").trim();
        if (v && gn) { const nom = parseVesselNominal(v); if (nom) gp(gn).flask_volume_mL = nom; }   // 组级 flask_volume_mL ← 末次编辑行
        S().scalars.mu_stock_flask_custom = true;   // 手改容量瓶 → 锁, 停止 ΣVi 跟随
        re3();
      };
      td.appendChild(sel); tr.appendChild(td);
    } else {
      const liqOpts = [...new Set(S().topo_rows.filter(rr => rr.类型 === "液体").map(rr => (rr.分组名 || "").trim()).filter(Boolean))];
      const tdGn = el("td"); const gnSel = el("select");
      const gnEmpty = el("option"); gnEmpty.value = ""; gnEmpty.textContent = "—"; gnSel.appendChild(gnEmpty);
      liqOpts.forEach(g => { const op = el("option"); op.value = op.textContent = g; gnSel.appendChild(op); });
      gnSel.value = (r.分组名 || "").trim(); gnSel.onchange = () => { r.分组名 = gnSel.value; re3(); };
      tdGn.appendChild(gnSel); tr.appendChild(tdGn);
      cellText(tr, r, "目标物");
      // 证书列: 按组 cert_mode 显 / (relative→Urel%可填; absolute→C_cert/U_abs可填; 其他显/)
      const gn = (r.分组名 || "").trim(); const cm = gp(gn).cert_mode || "relative";
      certCell(tr, r, "Urel%", cm === "relative");
      certCell(tr, r, "C_cert", cm === "absolute");
      certCell(tr, r, "U_abs", cm === "absolute");
    }
    const td = el("td");
    if (kind === "solid") { const del = el("button", "row-del"); del.type = "button"; del.textContent = "−"; del.onclick = () => { S().topo_rows.splice(idx, 1); re3(); }; td.appendChild(del); }
    tr.appendChild(td);
    tbody.appendChild(tr);
  });
  tbl.appendChild(tbody); det.appendChild(tbl);
  if (kind === "liquid") {
    det.addEventListener("paste", (e) => {
      const ae = document.activeElement;
      if (!ae || ae.tagName !== "INPUT" || !tbl.contains(ae)) return;
      const startTd = ae.closest("td"); const startTr = ae.closest("tr");
      if (!startTd || !startTr) return;
      const text = (e.clipboardData?.getData("text/plain") || "").replace(/\r\n/g, "\n").replace(/\r/g, "\n");
      let lines = text.split("\n"); if (lines.length && lines[lines.length - 1] === "") lines.pop();
      if (!lines.length) return;
      e.preventDefault();
      const allRows = [...tbl.querySelectorAll("tbody tr")];
      const r0 = allRows.indexOf(startTr); const c0 = startTd.cellIndex;
      let changed = false;
      lines.forEach((line, i) => {
        const row = allRows[r0 + i]; if (!row) return;
        line.split("\t").forEach((raw, j) => {
          const cell = row.cells[c0 + j]; if (!cell) return;
          const inp = cell.querySelector("input"); if (!inp || inp.readOnly) return;
          const v = raw.trim(); if (v === "") return;
          inp.value = inp.type === "number" ? parseFloat(v) : v;
          inp.dispatchEvent(new Event("change", { bubbles: true })); changed = true;
        });
      });
      if (changed) re3();
    });
  }
  const addBar = el("div"); addBar.style.cssText = "display:flex;align-items:center;justify-content:space-between;gap:1rem;margin-top:1rem;flex-wrap:wrap;";
  if (kind === "solid") {
    const add = el("button", "row-add"); add.type = "button"; add.textContent = "+ 新增固体行";
    add.onclick = () => {
      S().topo_rows.push({ 分组名: "", 类型: kn, 目标物: "", "纯度p": null, "U_purity": null, "k_purity": 2, "m_std(g)": null, "储备液容量瓶(mL)": null });
      re3();
    };
    addBar.appendChild(add);
  }
  if (kind === "solid" && S().scalars.mu_stock_makeup_mode === "mixed") {
    const note = el("div"); note.id = "mu-stock-vsum-note"; note.className = "muted";
    note.style.cssText = "flex:1;text-align:right;line-height:1.2;";
    addBar.appendChild(note); updateMuStockVsumNote(note);
  }
  det.appendChild(addBar); parent.appendChild(det);
}
function cellText(tr, r, k) { const td = el("td"); const inp = el("input"); inp.type = "text"; inp.value = r[k] ?? ""; inp.onchange = () => { r[k] = inp.value; }; td.appendChild(inp); tr.appendChild(td); }
// 分组名变更: 旧名若不再被任何行使用 → 迁移 grp_params(保留中间液/工作液等数据)到新名, 并重渲 Tab③
function groupNameCell(tr, r) {
  const td = el("td"); const inp = el("input"); inp.type = "text";
  const oldGN = (r.分组名 || "").trim();
  inp.value = r.分组名 ?? "";
  inp.onchange = () => {
    const newGN = (inp.value || "").trim();
    // 跨类型撞名守卫: 固体组改名不得与液体组同名 (否则后端 _rows_to_groups 按名合并、kind 取首个 → 错类型处理)
    if (newGN && newGN !== oldGN && S().topo_rows.some(rr => rr.类型 === "液体" && (rr.分组名 || "").trim() === newGN)) {
      alert(`分组名「${newGN}」已被液体组占用, 请用其他名字`);
      inp.value = r.分组名; re3(); return;
    }
    r.分组名 = inp.value;
    if (oldGN && newGN && oldGN !== newGN && !S().topo_rows.some(rr => (rr.分组名 || "").trim() === oldGN) && S().grp_params[oldGN]) {
      S().grp_params[newGN] = S().grp_params[oldGN]; delete S().grp_params[oldGN];
    }
    re3();
  };
  td.appendChild(inp); tr.appendChild(td);
}
function cellNum(tr, r, k, pct = false) { const td = el("td"); const inp = el("input"); inp.type = "number"; inp.step = "any"; const _v = r[k]; inp.value = pct && typeof _v === "number" ? _v * 100 : (_v ?? ""); inp.onchange = () => { let v = inp.value === "" ? null : parseFloat(inp.value); if (pct && v != null) v = v / 100; r[k] = v; }; td.appendChild(inp); tr.appendChild(td); }
function certCell(tr, r, k, writable) {
  const td = el("td");
  if (writable) { const inp = el("input"); inp.type = "number"; inp.step = "any"; inp.value = r[k] ?? ""; inp.onchange = () => { r[k] = inp.value === "" ? null : parseFloat(inp.value); }; td.appendChild(inp); }
  else { const o = el("output", "cell-out"); o.value = "/"; td.appendChild(o); }
  tr.appendChild(td);
}

// 液体每组折叠: cert_mode/k_cert + 每定容分组(dg) 移液量器/移取体积/容量瓶
// 液体组定容表「组内物质数量」→ 同步 topo_rows: 每组液体行数 = n_substances
function syncLiquidRows() {
  const liqGroups = [...new Set(S().topo_rows.filter(r => r.类型 === "液体").map(r => (r.分组名 || "").trim()).filter(Boolean))];
  liqGroups.forEach(gn => {
    const g = gp(gn); const n = g.n_substances ?? 1;
    let cnt = S().topo_rows.filter(r => r.类型 === "液体" && (r.分组名 || "").trim() === gn).length;
    while (cnt < n) { S().topo_rows.push({ 分组名: gn, 类型: "液体", 目标物: "", "Urel%": null, "C_cert": null, "U_abs": null, "定容分组": "定容组1" }); cnt++; }
    while (cnt > n) { for (let i = S().topo_rows.length - 1; i >= 0; i--) { if (S().topo_rows[i].类型 === "液体" && (S().topo_rows[i].分组名 || "").trim() === gn) { S().topo_rows.splice(i, 1); break; } } cnt--; }
  });
}
function liquidFolds(parent, meta) {
  const liqGroups = [...new Set(S().topo_rows.filter(r => r.类型 === "液体").map(r => (r.分组名 || "").trim()).filter(Boolean))];
  const wrap = el("div", "branch"); wrap.style.marginTop = "1.2rem"; wrap.append(cardTitle("液体组定容"));
  const tbl = el("table", "grid");
  const thead = el("thead"); const trh = el("tr");
  ["分组", "组内物质数量", "证书式", "包含因子 k_cert", "移液量器", "移取体积 (mL)", "容量瓶", "定容分组"].forEach(t => { const th = el("th"); th.textContent = t; trh.appendChild(th); });
  { const th = el("th"); trh.appendChild(th); }
  thead.appendChild(trh); tbl.appendChild(thead);
  const tbody = el("tbody");
  liqGroups.forEach(gn => {
    const g = gp(gn); if (!g.cert_mode) g.cert_mode = "relative"; if (!g.flasks) g.flasks = {};
    const cmSel = el("select");
    [{ value: "relative", label: "相对式 Urel%·k" }, { value: "absolute", label: "绝对式 浓度·U·k" }].forEach(o => { const op = el("option"); op.value = o.value; op.textContent = o.label; cmSel.appendChild(op); });
    cmSel.value = g.cert_mode || "relative"; cmSel.onchange = () => { g.cert_mode = cmSel.value; re3(); };
    const kInp = el("input"); kInp.type = "number"; kInp.step = 1; kInp.value = g.k_cert ?? "";
    kInp.onchange = () => { g.k_cert = kInp.value === "" ? null : parseFloat(kInp.value); };
    const dgs = [...new Set(S().topo_rows.filter(r => r.类型 === "液体" && (r.分组名 || "").trim() === gn).map(r => r.定容分组 || "定容组1"))];
    (dgs.length ? dgs : [null]).forEach((dg, di) => {
      const tr = el("tr");
      if (di === 0) {
        const tdGn = el("td"); if (dgs.length > 1) tdGn.rowSpan = dgs.length;
        const gnInp = el("input"); gnInp.type = "text"; gnInp.value = gn;
        gnInp.onchange = () => {
          const newGN = gnInp.value.trim();
          if (newGN && newGN !== gn) {
            // 跨类型撞名守卫: 液体组改名不得与固体组同名
            if (S().topo_rows.some(rr => rr.类型 === "固体" && (rr.分组名 || "").trim() === newGN)) {
              alert(`分组名「${newGN}」已被固体组占用, 请用其他名字`);
              gnInp.value = gn; re3(); return;
            }
            S().topo_rows.forEach(r => { if (r.类型 === "液体" && (r.分组名 || "").trim() === gn) r.分组名 = newGN; });
            if (S().grp_params[gn]) { S().grp_params[newGN] = S().grp_params[gn]; delete S().grp_params[gn]; }
            if (S().ding) {   // feeds 按 分组名 键 → 改组名同步迁移各定容分组下的 feed 键
              for (const D in S().ding) { const f = S().ding[D].feeds; if (f && f[gn] && !f[newGN]) { f[newGN] = f[gn]; delete f[gn]; } }
            }
          }
          re3();
        };
        tdGn.appendChild(gnInp);
        const tdN = el("td"); if (dgs.length > 1) tdN.rowSpan = dgs.length;
        const nInp = el("input"); nInp.type = "number"; nInp.min = 1; nInp.step = 1; nInp.value = g.n_substances ?? 1; nInp.style.width = "3rem";
        nInp.onchange = () => { g.n_substances = Math.max(1, parseInt(nInp.value) || 1); re3(); };
        tdN.appendChild(nInp);
        const tdCm = el("td"); if (dgs.length > 1) tdCm.rowSpan = dgs.length; tdCm.appendChild(cmSel);
        const tdK = el("td"); if (dgs.length > 1) tdK.rowSpan = dgs.length; tdK.appendChild(kInp);
        tr.append(tdGn, tdN, tdCm, tdK);
      }
      if (dg == null) { tbody.appendChild(tr); return; }
      if (!g.flasks[dg]) g.flasks[dg] = { pip_vessel: null, pip_kind: null, pip_nominal: null, pip_vol: null, flask_vol: null };
      const fl = g.flasks[dg];
      const pipSel = el("select"); const pe = el("option"); pe.value = ""; pe.textContent = "—"; pipSel.appendChild(pe);
      meta.pip_opts.forEach(o => { const op = el("option"); op.value = op.textContent = o; pipSel.appendChild(op); });
      pipSel.value = fl.pip_vessel || ""; pipSel.onchange = () => { fl.pip_vessel = pipSel.value || null; if (pipSel.value) { const s = volStr(parseVesselNominal(pipSel.value)); if (s != null) { fl.pip_vol = s; volInp.value = s; } } };
      const volInp = el("input"); volInp.type = "number"; volInp.step = "any"; volInp.placeholder = "移取体积(mL)"; volInp.value = fl.pip_vol ?? "";
      volInp.onchange = () => {
        if (volInp.value === "") { fl.pip_vol = null; return; }
        const s = volStr(volInp.value);
        if (s != null) { fl.pip_vol = s; volInp.value = s; } else fl.pip_vol = parseFloat(volInp.value);
      };
      const flSel = el("select"); const fe = el("option"); fe.value = ""; fe.textContent = "—"; flSel.appendChild(fe);
      meta.flask_opts.forEach(o => { const op = el("option"); op.value = op.textContent = o; flSel.appendChild(op); });
      flSel.value = fl.flask_vessel || ""; flSel.onchange = () => { fl.flask_vessel = flSel.value || null; if (fl.flask_vessel) fl.flask_vol = parseVesselNominal(fl.flask_vessel); re3(); };
      const tdDg = el("td"); const dgInp = el("input"); dgInp.type = "text"; dgInp.value = dg; dgInp.placeholder = "定容分组";
      dgInp.onchange = () => {   // 改名: 全组 topo 行的定容分组 + flasks(储备液) 跟随; ding 袋(中间液/工作液)若旧名不再被引用则迁移
        const old = (dg ?? "").toString().trim(); const next = (dgInp.value ?? "").trim();
        if (old && next && old !== next) {
          S().topo_rows.forEach(r => { if (r.类型 === "液体" && (r.分组名 || "").trim() === gn && (r.定容分组 ?? "定容组1") === old) r.定容分组 = next; });
          if (g.flasks[old] && !g.flasks[next]) { g.flasks[next] = g.flasks[old]; delete g.flasks[old]; }
          const stillUsed = S().topo_rows.some(r => r.类型 === "液体" && (r.定容分组 || "定容组1") === old);
          if (!stillUsed && S().ding?.[old] && !S().ding[next]) { S().ding[next] = S().ding[old]; delete S().ding[old]; }
        }
        re3();
      };
      tdDg.appendChild(dgInp);
      const tdPip = el("td"); tdPip.appendChild(pipSel);
      const tdVol = el("td"); tdVol.appendChild(volInp);
      const tdFl = el("td"); tdFl.appendChild(flSel);
      tr.append(tdPip, tdVol, tdFl, tdDg);
      if (di === 0) {
        const tdDel = el("td"); if (dgs.length > 1) tdDel.rowSpan = dgs.length;
        const delBtn = el("button", "row-del"); delBtn.type = "button"; delBtn.textContent = "−"; delBtn.title = "删除该液体组";
        delBtn.onclick = () => {
          S().topo_rows = S().topo_rows.filter(r => !(r.类型 === "液体" && (r.分组名 || "").trim() === gn));
          delete S().grp_params[gn];
          if (S().ding) { for (const D in S().ding) { if (S().ding[D].feeds) delete S().ding[D].feeds[gn]; } }
          re3();
        };
        tdDel.appendChild(delBtn); tr.appendChild(tdDel);
      }
      tbody.appendChild(tr);
    });
  });
  tbl.appendChild(tbody); wrap.appendChild(tbl);
  const addBtn = el("button", "row-add"); addBtn.type = "button"; addBtn.textContent = "+ 新增液体组";
  addBtn.onclick = () => {
    let n = liqGroups.length + 1; let name = `液体-${n}`;
    while (S().topo_rows.some(r => r.类型 === "液体" && (r.分组名 || "").trim() === name)) name = `液体-${++n}`;
    S().topo_rows.push({ 分组名: name, 类型: "液体", 目标物: "", "Urel%": null, "C_cert": null, "U_abs": null, "定容分组": "定容组1" });
    re3();
  };
  const addBar = el("div"); addBar.style.cssText = "display:flex;align-items:center;gap:1rem;margin-top:.3rem;flex-wrap:wrap;";
  addBar.appendChild(addBtn);
  if (S().scalars.mu_liq_stock_makeup_mode === "mixed") {
    const note = el("div"); note.id = "mu-liq-stock-vsum-note"; note.className = "muted";
    note.style.cssText = "flex:1;text-align:right;line-height:1.2;";
    addBar.appendChild(note); updateMuLiqStockVsumNote(note);
  }
  wrap.appendChild(addBar); parent.appendChild(wrap);
}

// 固体目标物储备液(母液)浓度 (mg/L) = m_std(g)·纯度·1e6 / 储备液容量瓶(mL); 取自拓扑行 (单物质 solidStockConc 同源)
function solidStockConcMg(groupName, analyteName) {
  const r = S().topo_rows.find(r => r.类型 === "固体"
    && (r.分组名 || "").trim() === (groupName || "").trim()
    && (r.目标物 || "").trim() === (analyteName || "").trim());
  if (!r) return null;
  const m = Number(r["m_std(g)"]), p = Number(r["纯度p"]), fv = parseVesselNominal(r["储备液容量瓶(mL)"]);
  return (m > 0 && p > 0 && fv > 0) ? (m * p * 1e6 / fv) : null;
}

// 固体组中间液混合后各物质目标浓度均值 (mg/L, 显示串) = 各源 母液浓度×移取体积/容量瓶 修约后取均值。
// 混合中间液各物质浓度各异 → 取均值作工作液稀释链首行母液浓度的默认值 (用户可改)。
function interAvgTargetConc(dg, sources, feeds, flasks, dgPrefix) {
  const fNom = parseVesselNominal(flasks[dg]);
  if (!fNom) return null;
  const vals = sources.flatMap(src => (feeds[src] || [])
    .filter(fd => fd.dg === dg)
    .map(fd => {
      const stock = solidStockConcMg(dgPrefix, src);
      const p = Number(fd.pip_vol);
      return (stock != null && isFinite(p) && p > 0) ? concRound(stock * p / fNom) : null;
    }))
    .filter(v => v != null && isFinite(v));
  return vals.length ? concAvgFmt(vals) : null;
}

// 渲染一块中间液/工作液 (源→中间液表 + 工作液链). feeds/flasks/work 由调用方传:
//   固体 = grp_params[gn].inter(feeds/flasks) + .work;  液体 = 共享 ding[D](feeds/flasks/work)
// isSolid: 固体组额外显示 母液浓度(逐物质) + 目标浓度(逐物质, 混合中间液中各物质各自浓度) 两列
function renderPrepFold(parent, meta, title, feeds, flasks, work, sources, dgPrefix, gridIdPrefix, isSolid = false) {
  // feeds[src] 规范化为数组: 同一源可有多行移液记录; 兼容旧草稿的单对象结构
  sources.forEach(src => {
    const a = feeds[src];
    if (!a) feeds[src] = [{ dg: `${dgPrefix}-中`, pip_vessel: null, pip_vol: null }];
    else if (!Array.isArray(a)) feeds[src] = [a];
    feeds[src].forEach(fd => { if (!fd.dg) fd.dg = `${dgPrefix}-中`; });
  });
  const fold = el("div", "branch"); fold.append(cardTitle(title));
  if (sources.length) {
    const tbl = el("table", "grid");
    const thead = el("thead"); const trh = el("tr");
    const heads = ["源", "中间液分组"];
    if (isSolid) heads.push("母液浓度 (mg/L)");
    heads.push("移液量器", "移取体积 (mL)", "中间液容量瓶");
    if (isSolid) heads.push("目标浓度 (mg/L)");
    heads.push("");
    heads.forEach(t => { const th = el("th"); th.textContent = t; trh.appendChild(th); });
    thead.appendChild(trh); tbl.appendChild(thead);
    const tbody = el("tbody");
    // 按中间液分组(dg) 聚合源: 同 dg 排在一起 → 容量瓶合并为单一单元格; 组顺序=首次出现, 组内保源序
    // 同一源可有多行移液记录 (feeds[src] 为数组) → 展开后按 dg 聚合
    const ordered = sources.flatMap(src => feeds[src].map(fd => ({ src, fd })));
    // 固体: 工作液稀释链首行母液浓度默认 = 中间液各物质目标浓度均值 (用户未手改时跟随; 手改后锁定); 先于中间液表读取 → 目标浓度(合并)与首行一致
    if (isSolid) {
      for (const dg of [...new Set(ordered.map(o => o.fd.dg))]) {
        if (!work[dg]) work[dg] = [];
        const wr = work[dg];
        if (!wr.length) wr.push({});
        const r0 = wr[0];
        if (r0 && !r0._motherLocked) {
          const avg = interAvgTargetConc(dg, sources, feeds, flasks, dgPrefix);
          if (avg != null) r0["母液浓度(mg/L)"] = avg;
        }
      }
    }
    [...new Set(ordered.map(o => o.fd.dg))].forEach(dg => {
      const grp = ordered.filter(o => o.fd.dg === dg);
      // 固体: 目标浓度(合并) = 该中间液工作液稀释链首行母液浓度 (即中间液浓度, 与工作液链首行衔接)
      let tdTarget = null;
      if (isSolid) {
        const wc0 = (work[dg] || [])[0];
        const tgt = wc0 ? Number(wc0["母液浓度(mg/L)"]) : NaN;
        tdTarget = el("td"); tdTarget.rowSpan = grp.length; tdTarget.textContent = concFmt(tgt) ?? "";
      }
      grp.forEach(({ src, fd }, gi) => {
        const dgInp = el("input"); dgInp.type = "text"; dgInp.value = fd.dg; dgInp.placeholder = "中间液分组名";
        dgInp.onchange = () => {
          const old = fd.dg, next = dgInp.value;
          if (old && next && old !== next) {   // 改名迁移: 工作液链 + 中间液容量瓶 跟随新分组名, 不再孤立
            if (work[old] && !work[next]) { work[next] = work[old]; delete work[old]; }
            if (flasks[old] && !flasks[next]) { flasks[next] = flasks[old]; delete flasks[old]; }
          }
          fd.dg = next; re3();
        };
        const pv = el("input"); pv.type = "number"; pv.step = "any"; pv.placeholder = "移取体积(mL)"; pv.value = fd.pip_vol ?? "";
        pv.onchange = () => {
          if (pv.value === "") { fd.pip_vol = null; re3(); return; }
          const s = volStr(pv.value);
          if (s != null) { fd.pip_vol = s; pv.value = s; } else fd.pip_vol = parseFloat(pv.value);
          re3();
        };
        // 移液量器 → 按标称体积默认填充移取体积; 手改 pv 后可覆盖, 换量器再覆盖; re3 联动 Σ 笔记
        const pipSel = el("select"); const pe = el("option"); pe.value = ""; pe.textContent = "—"; pipSel.appendChild(pe);
        meta.pip_opts.forEach(o => { const op = el("option"); op.value = op.textContent = o; pipSel.appendChild(op); });
        pipSel.value = fd.pip_vessel || "";
        pipSel.onchange = () => {
          fd.pip_vessel = pipSel.value || null;
          if (pipSel.value) { const s = volStr(parseVesselNominal(pipSel.value)); if (s != null) fd.pip_vol = s; }
          re3();
        };
        syncPipOverflow(pv, fd.pip_vessel);   // 初渲: 量器量程/单标校验 (re3 后重渲会再跑)
        const tr = el("tr");
        const tdSrc = el("td"); tdSrc.textContent = src;
        const tdDg = el("td"); tdDg.appendChild(dgInp);
        // 固体: 母液浓度(逐物质) = m_std·纯度·1e6/储备液容量瓶
        let tdStock = null;
        if (isSolid) { tdStock = el("td"); tdStock.textContent = concFmt(solidStockConcMg(dgPrefix, src)) ?? ""; }
        const tdPv = el("td"); tdPv.appendChild(pipSel);
        const tdVol = el("td"); tdVol.appendChild(pv);
        // 删除按钮: 与工作液链一致 (row-del "−"); 仅剩一行时清空内容, 保留源可见
        const tdAct = el("td");
        const delBtn = el("button", "row-del"); delBtn.type = "button"; delBtn.textContent = "−";
        delBtn.title = "删除该行 (仅剩一行时清空内容)";
        delBtn.onclick = () => {
          const arr = feeds[src];
          if (arr.length <= 1) { arr[0].pip_vessel = null; arr[0].pip_vol = null; }
          else { const i = arr.indexOf(fd); if (i >= 0) arr.splice(i, 1); }
          re3();
        };
        tdAct.appendChild(delBtn);
        const cells = [tdSrc, tdDg];
        if (tdStock) cells.push(tdStock);
        cells.push(tdPv, tdVol);
        if (gi === 0) {   // 中间液分组(dg)名称一致 → 容量瓶/目标浓度合并为单一单元格 (rowspan 跨该 dg 全部行)
          const tdFl = el("td"); tdFl.rowSpan = grp.length;
          tdFl.appendChild(vesselSelect(meta, flasks[dg] || null, v => { flasks[dg] = v; re3(); }, "flask"));
          tdFl.appendChild(interVsumNote(dg, grp, flasks));   // Σ移取体积 vs 容量瓶 (sum>flask → 装不下)
          cells.push(tdFl);
          if (tdTarget) cells.push(tdTarget);
        }
        cells.push(tdAct);
        tr.append(...cells);
        tbody.appendChild(tr);
      });
    });
    tbl.appendChild(tbody); fold.appendChild(tbl);
    // 新增行: 与工作液链一致 (row-add "+ 新增行"); 源与 dg 延续最后一行 (无则首源 + 默认 dg)
    const addBtn = el("button", "row-add"); addBtn.type = "button"; addBtn.textContent = "+ 新增行";
    addBtn.onclick = () => {
      const last = ordered[ordered.length - 1];
      const src = last ? last.src : sources[0];
      const dg = (last && last.fd.dg) || `${dgPrefix}-中`;
      feeds[src].push({ dg, pip_vessel: null, pip_vol: null });
      re3();
    };
    fold.appendChild(addBtn);
  }
  // 工作液稀释链(每个中间液分组一条, 可多级); 容量瓶已在源表按中间液分组绑定
  // 工作液链按当前 sources 的 dg 渲染 (不扫全部 feeds → 改名/删行遗留的孤儿 feed 不再凭空多生一条链)
  const interDgs = [...new Set(sources.flatMap(src => feeds[src].map(fd => fd.dg)).filter(Boolean))];
  interDgs.forEach(dg => {
    const sub = el("div", "branch"); sub.style.marginTop = ".5rem";
    if (!work[dg]) work[dg] = [];
    const wrows = work[dg];
    if (!wrows.length) wrows.push({});   // 确保首行存在 (镜像 createGrid 空表补行, 供填默认)
    for (const r of wrows) if (!("flask_vessel" in r)) r.flask_vessel = WORK_FLASK_DEFAULT;   // 初始/加载缺省 → 默认容量瓶
    const wlab = el("label"); wlab.textContent = `中间液「${dg}」→ 工作液稀释链`; wlab.style.display = "block"; sub.appendChild(wlab);
    const gh = el("div"); gh.id = `grid-work-${gridIdPrefix}-${dg}`; sub.appendChild(gh);
    createGrid(gh, workChainCfg(meta, wrows, () => validateWorkGrid(gh, wrows)));
    validateWorkGrid(gh, wrows);   // 初渲: 移取量器/定容量器 校验
    fold.appendChild(sub);
  });
  parent.appendChild(fold);
}
// 中间液及工作液: 固体按分组名(每分组一块, 源=目标物); 液体按定容分组(跨分组合并, 共享 ding[D], 源=分组名)
function interWork(parent, meta) {
  const showSolid = S().scalars.mu_show_solid, showLiq = S().scalars.mu_show_liquid;
  const solidGroups = showSolid
    ? [...new Set(S().topo_rows.filter(r => r.类型 === "固体").map(r => (r.分组名 || "").trim()).filter(Boolean))]
    : [];
  const liqDings = showLiq
    ? [...new Set(S().topo_rows.filter(r => r.类型 === "液体").map(r => r.定容分组 || "定容组1"))]
    : [];
  if (!solidGroups.length && !liqDings.length) { const s = el("small"); s.className = "muted"; s.textContent = "(先在明细填分组)"; parent.appendChild(s); return; }
  solidGroups.forEach(gn => {
    const g = gp(gn); if (!g.inter) g.inter = { feeds: {}, flasks: {} }; if (!g.work) g.work = {};
    const sources = S().topo_rows.filter(r => r.类型 === "固体" && (r.分组名 || "").trim() === gn).map(r => (r.目标物 || "").trim()).filter(Boolean);
    renderPrepFold(parent, meta, `固体组「${gn}」中间液`, g.inter.feeds, g.inter.flasks, g.work, sources, gn, gn, true);
  });
  if (!S().ding) S().ding = {};
  liqDings.forEach(D => {
    const prep = S().ding[D] || (S().ding[D] = { feeds: {}, flasks: {}, work: {} });
    prep.feeds = prep.feeds || {}; prep.flasks = prep.flasks || {}; prep.work = prep.work || {};
    const groupsInD = [...new Set(S().topo_rows.filter(r => r.类型 === "液体" && (r.定容分组 || "定容组1") === D).map(r => (r.分组名 || "").trim()).filter(Boolean))];
    renderPrepFold(parent, meta, `液体组「${D}」中间液`, prep.feeds, prep.flasks, prep.work, groupsInD, D, `ding-${D}`);
  });
}
const WORK_FLASK_DEFAULT = "10 mL 容量瓶(A)(±0.02)";   // 定容量器列默认值 (合法选项, 见 _FLASK_OPTS)
// 首行母液浓度: 用户改非空 → 锁定用户值; 清空 → 解锁(回到中间液目标浓度均值默认)。仅首行受控。
function _lockMother(r, rows) {
  if (rows.indexOf(r) !== 0) return;
  const v = r["母液浓度(mg/L)"];
  r._motherLocked = (v !== null && v !== undefined && v !== "");
}
function workChainCfg(meta, rows, onChange) {
  const serial = !!S().scalars.mu_work_serial_dilute;   // 逐级稀释: 下行母液浓度 = 上行目标浓度 (闭包 per-chain rows)
  return {
    columns: [
      serial
        ? { key: "母液浓度(mg/L)", type: "text", label: "母液浓度(mg/L)", editable: r => rows.indexOf(r) === 0, computed: r => {
              const i = rows.indexOf(r);
              return i > 0 ? rows[i - 1]["目标浓度(mg/L)"] : r["母液浓度(mg/L)"];   // row0 默认中间液目标浓度均值(渲染期填入), 用户可改; i>0 取上行目标浓度
            }, onSet: r => { _lockMother(r, rows); const s = concStr(r["母液浓度(mg/L)"]); if (s != null) r["母液浓度(mg/L)"] = s; } }
        : { key: "母液浓度(mg/L)", type: "text", label: "母液浓度(mg/L)", onSet: r => { _lockMother(r, rows); const s = concStr(r["母液浓度(mg/L)"]); if (s != null) r["母液浓度(mg/L)"] = s; } },
      { key: "pip_vessel", type: "select", label: "移取量器", options: meta.pip_opts,
        onSet: r => { if (r.pip_vessel) { const s = volStr(parseVesselNominal(r.pip_vessel)); if (s != null) r.pip_vol = s; } } },   // 选量器 → 按标称体积自动填移取体积 (手改可覆盖)
      { key: "pip_vol", type: "number", label: "移取体积(mL)", step: "any",
        onSet: r => { const s = volStr(r.pip_vol); if (s != null) r.pip_vol = s; } },   // 移取体积 volStr 修约(<1mL 保留 3 位 μL 精度)
      { key: "flask_vessel", type: "select", label: "定容量器", options: meta.flask_opts, seed: WORK_FLASK_DEFAULT },
      { key: "目标浓度(mg/L)", computed: r => targetStr(r["母液浓度(mg/L)"], r.pip_vol, parseVesselNominal(r.flask_vessel)) },
    ],
    rows, dynamic: true, ctx: S(), onChange,
  };
}
function vesselSelect(meta, val, on, kindFilter) {
  const sel = el("select"); const e = el("option"); e.value = ""; e.textContent = "—"; sel.appendChild(e);
  const opts = kindFilter === "flask" ? meta.flask_opts : meta.pip_opts;
  opts.forEach(o => { const op = el("option"); op.value = op.textContent = o; sel.appendChild(op); });
  sel.value = val || ""; sel.onchange = () => { on(sel.value || null); }; return sel;
}
function targetStr(c, v, fnom) {
  if (c == null || v == null || !fnom) return null;
  const val = Number(c) * Number(v) / Number(fnom);
  // 目标浓度 < 0.001 mg/L 不修约，保留足够小数位显示
  if (Math.abs(val) < 0.001 && val !== 0) {
    const dp = Math.floor(-Math.log10(Math.abs(val))) + 1;
    return val.toFixed(dp);
  }
  return concStr(val);
}
// 移取体积校验 → 标红 + tooltip (非阻塞): 单标吸量管须=标称; 移液枪须在量程档[满量程×10%, 满量程]; 分度吸量管/量筒等 ≤ 量程; 传 flaskVesselStr 则校验 移取体积≤定容量瓶(单步, 工作液链用)
function syncPipOverflow(volInp, pipVesselStr, flaskVesselStr) {
  const v = parseFloat(volInp.value);
  let bad = false, msg = "";
  if (isFinite(v)) {
    const pnom = pipVesselStr ? parseVesselNominal(pipVesselStr) : null;
    if (pnom != null) {
      if (pipVesselStr.includes("单标吸量管")) {            // pip_s 单标线: 只能移取标称体积
        if (Math.abs(v - pnom) > 1e-9) { bad = true; msg = `单标吸量管须移取标称 ${pnom} mL`; }
      } else if (pipVesselStr.includes("移液枪")) {          // pip_p 量程档: 下限=满量程×10%, 上限=满量程
        const lo = pnom * 0.1;
        if (v < lo - 1e-9) { bad = true; msg = `低于 ${pipVesselStr} 量程下限 (${lo} mL)`; }
        else if (v > pnom + 1e-9) { bad = true; msg = `超出 ${pipVesselStr} 量程 (${pnom} mL)`; }
      } else if (v > pnom + 1e-9) { bad = true; msg = `超出 ${pipVesselStr} 量程 (${pnom} mL)`; }
    }
    if (!bad && flaskVesselStr) {                           // 单步定容: 移取体积 ≤ 定容量瓶
      const fnom = parseVesselNominal(flaskVesselStr);
      if (fnom != null && v > fnom + 1e-9) { bad = true; msg = `超过定容量瓶 ${fnom} mL`; }
    }
  }
  volInp.classList.toggle("pip-overflow", bad);
  volInp.title = msg;
}
// 工作液稀释链逐行校验: 移取体积 vs 移取量器(单标=标称/分度≤量程) + vs 该行定容量器(单步≤瓶); 按 data-key 找 pip_vol 输入框 (列序无关)
function validateWorkGrid(container, rows) {
  container.querySelectorAll("tbody tr").forEach((tr, ri) => {
    const r = rows[ri]; if (!r) return;
    const volInp = tr.querySelector('[data-key="pip_vol"]');
    if (volInp && volInp.tagName === "INPUT") syncPipOverflow(volInp, r.pip_vessel, r.flask_vessel);
  });
}
// 中间液容量瓶 Σ校验: 同分组(dg)各源移取体积之和 vs 容量瓶规格 → ok/warn/muted 笔记 (Σ>容量瓶 物理上装不下)
function interVsumNote(dg, grp, flasks) {
  const sum = grp.reduce((s, o) => s + (Number(o.fd.pip_vol) || 0), 0);
  const fStr = flasks[dg];
  const fnom = fStr ? parseVesselNominal(fStr) : null;
  const note = el("div"); note.style.cssText = "font-size:.72rem;line-height:1.25;margin-top:.3rem;";
  if (sum <= 0) { note.className = "muted"; note.textContent = "填移取体积后比对容量瓶"; return note; }
  if (fnom == null) { note.className = "muted"; note.textContent = `Σ移取 ${sum.toFixed(2)} mL`; return note; }
  const diff = sum - fnom;
  if (diff > 1e-9) { note.className = "warn"; note.textContent = `Σ移取 ${sum.toFixed(2)} > 容量瓶 ${fnom} ⚠ 超出 ${diff.toFixed(2)} mL`; }
  else { note.className = "ok"; note.textContent = `Σ移取 ${sum.toFixed(2)} ≤ 容量瓶 ${fnom} ✓`; }
  return note;
}

// ---- ④ 曲线拟合 (批量 + 逐物 曲线方法/内标物) ----
function renderT4(meta) {
  const c = document.getElementById("t4"); c.innerHTML = "";
  const card = el("div", "card"); card.append(cardTitle("曲线拟合 urel(Q)"));
  const g1 = el("div", "grid-5");
  bindSelect(g1, "批量修改定量方法", "mu_curve_method", MCM, { on: () => { /* 联动各物 curve_meta */ syncCurveBatch(); renderT4(meta); } });
  bindInput(g1, "曲线点数 (每物)", "mu_curve_npoints", { type: "number", attrs: { min: 3, step: 1 } });
  bindSelect(g1, "包含原点(0,0)参与拟合", "mu_curve_include_origin", [{ value: "否", label: "否" }, { value: "是", label: "是" }]);
  bindSelect(g1, "强制过原点(0,0)", "mu_curve_force_origin", [{ value: "否", label: "否" }, { value: "是", label: "是" }]);
  bindInput(g1, "每点标液进样次数", "mu_curve_inj", { type: "number", attrs: { min: 1, step: 1 } });
  card.appendChild(g1);
  c.appendChild(card);
  const names = analyteNames();
  if (!names.length) {
    const tc = el("div", "card"); tc.append(cardTitle("各目标物曲线方法"));
    const s = el("small"); s.className = "muted"; s.textContent = "(先在 ③ 填目标物)"; tc.appendChild(s);
    c.appendChild(tc); return;
  }
  const tc = el("details", "card");
  tc.open = S().curve_open !== false;
  tc.addEventListener("toggle", () => { S().curve_open = tc.open; });
  const tsum = el("summary"); tsum.textContent = "各目标物曲线方法"; tc.append(tsum);
  const note = el("small"); note.className = "muted";
  note.textContent = "勾选目标物 → 批量填充只作用于勾选项(未勾选则填全部); 从 Excel 复制列 → 点起始单元格 → Ctrl+V 粘贴(空白跳过)。";
  tc.appendChild(note);
  // 各目标物表 (目标物只读源自 ③; 定量方法/内标物可编辑 + 粘贴; 复选框用于批量定向)
  const rows = names.map((nm, i) => {
    const cm = S().curve_meta[nm] || (S().curve_meta[nm] = { method: S().scalars.mu_curve_method, is_name: "" });
    return { "序号": i + 1, sel: false, "目标物": nm, "定量方法": cm.method || "外标法", "内标物": cm.is_name || "" };
  });
  // 内标物 列批量填充 (仅作用于勾选行; 未勾选 → 全部)
  const batch = el("div", "row-inline"); batch.style.margin = ".5rem 0";
  const isBatchInp = el("input"); isBatchInp.placeholder = "批量内标物 (作用于勾选项)";
  const isBatchBtn = el("button", "row-add"); isBatchBtn.type = "button"; isBatchBtn.textContent = "填充勾选";
  isBatchBtn.onclick = () => {
    const v = isBatchInp.value.trim();
    if (!v) return;
    const list = rows.filter(r => r.sel); const targets = list.length ? list : rows;
    targets.forEach(r => { const cm = S().curve_meta[r["目标物"]] || (S().curve_meta[r["目标物"]] = { method: "外标法", is_name: "" }); cm.is_name = v; });
    renderT4(meta);
  };
  batch.append(isBatchInp, isBatchBtn); tc.appendChild(batch);
  const gh = el("div"); gh.id = "grid-curve"; tc.appendChild(gh);
  createGrid(gh, {
    columns: [
      { key: "sel", label: "选", type: "check", seed: false },
      { key: "序号", label: "序号", computed: r => r["序号"] },
      { key: "目标物", label: "目标物", computed: r => r["目标物"] },
      { key: "定量方法", label: "定量方法", type: "select", options: ["外标法", "内标法"] },
      { key: "内标物", label: "内标物 (内标法填)", type: "text" },
    ],
    rows, dynamic: false, ctx: S(),
    onChange: (rs) => rs.forEach(r => {
      const cm = S().curve_meta[r["目标物"]] || (S().curve_meta[r["目标物"]] = { method: "外标法", is_name: "" });
      cm.method = r["定量方法"] || "外标法"; cm.is_name = r["内标物"] || "";
    }),
  });
  c.appendChild(tc);
}
function analyteNames() {
  // parity engine_multi.build_params_multi._show: 未勾选类型(如未使用的固体行)整流程剔除
  const sh_s = S().scalars.mu_show_solid !== false, sh_l = S().scalars.mu_show_liquid !== false;
  const out = [];
  for (const r of S().topo_rows) {
    if (r.类型 === "固体" && !sh_s) continue;
    if (r.类型 === "液体" && !sh_l) continue;
    const n = (r.目标物 || "").trim(); if (n && !out.includes(n)) out.push(n);
  }
  return out;
}
function syncCurveBatch() {
  const m = S().scalars.mu_curve_method;
  analyteNames().forEach(nm => { (S().curve_meta[nm] || (S().curve_meta[nm] = { method: m, is_name: "" })).method = m; });
}

// ---- ⑤ 精密度 & 回收率 (2 input; 表在 Excel) ----
function renderT5(meta) {
  const c = document.getElementById("t5"); c.innerHTML = "";
  const infl = el("div", "card");
  bindInput(infl, "重复性影响量(、分隔)", "mu_influences");
  const _il = infl.querySelector("label"); if (_il) { _il.style.fontWeight = "700"; _il.style.color = "var(--ink)"; }
  c.appendChild(infl);
  const card = el("div", "card"); card.append(cardTitle("精密度 & 回收率 (数据走 Excel)"));
  const g = el("div", "grid-2");
  bindInput(g, "测定次数 (每物加标平行样)", "mu_spike_nrep", { type: "number", attrs: { min: 2, step: 1 } });
  bindInput(g, "每次测定进样次数", "mu_fr_inj", { type: "number", attrs: { min: 1, step: 1 } });
  card.appendChild(g);
  const note = el("small"); note.className = "muted";
  note.textContent = "⑥ 加标数据走 Excel「精密度&回收率」表(每物多组平行样)。下载模板→填→上传,系统按 R=C/C₀、w=C·V/m 自动算。";
  card.appendChild(note);
  c.appendChild(card);
}

// ---- Excel 模板下载/上传 ----
function excelMenu() {
  const btn = document.getElementById("btn-excel");
  const existing = document.getElementById("excel-menu");
  if (existing) { existing.remove(); return; }  // 再次点击 → 关闭
  const menu = el("div", "excel-menu"); menu.id = "excel-menu";
  const dl = el("button", "dp-act"); dl.type = "button"; dl.textContent = "⬇ 下载模板";
  dl.onclick = () => { menu.remove(); if (!analyteNames().length) { alert("先在 ③ 填目标物, 再下载 Excel 模板"); return; } downloadTemplate(); };
  const up = el("button", "dp-act"); up.type = "button"; up.textContent = "⬆ 上传模板";
  up.onclick = () => { menu.remove(); uploadTemplate(); };
  menu.append(dl, up); document.body.appendChild(menu);
  const r = btn.getBoundingClientRect(); menu.style.left = r.left + "px"; menu.style.top = (r.bottom + 4) + "px";
  setTimeout(() => {  // 点外部关闭
    const close = (e) => { if (!menu.contains(e.target) && e.target !== btn) { menu.remove(); document.removeEventListener("mousedown", close); } };
    document.addEventListener("mousedown", close);
  }, 0);
}
async function downloadTemplate() {
  try {
    // 未勾选的标准品类型 (mu_show_solid/liquid=false) 不进模板 (parity build_params_multi._show)
    const sh_s = S().scalars.mu_show_solid !== false, sh_l = S().scalars.mu_show_liquid !== false;
    const topo_rows = S().topo_rows.filter(r => (r.类型 === "固体" && sh_s) || (r.类型 === "液体" && sh_l));
    const blob = await templateMultiDownload({
      topo_rows, curve_meta: S().curve_meta,
      n_points: Number(S().scalars.mu_curve_npoints) || 3, n_reps: Number(S().scalars.mu_spike_nrep) || 2,
      n_inj_point: Number(S().scalars.mu_curve_inj) || 1, n_inj_meas: Number(S().scalars.mu_fr_inj) || 1,
    });
    const _parts = [S().scalars.mu_meta_ref, S().scalars.mu_title].map(x => (x || "").trim()).filter(Boolean);
    const url = URL.createObjectURL(blob); const a = el("a"); a.href = url; a.download = (_parts.join("_") || "不确定度评估") + ".xlsx"; a.click(); URL.revokeObjectURL(url);
  } catch (e) { alert("下载失败: " + e.message); }
}
function uploadTemplate() {
  const inp = el("input"); inp.type = "file"; inp.accept = ".xlsx";
  inp.onchange = async () => {
    const f = inp.files[0]; if (!f) return;
    try { const r = await templateMultiUpload(f); S().meas = r.meas; alert(`已解析测量数据: ${Object.keys(r.meas || {}).length} 种目标物`); }
    catch (e) { alert("解析失败: " + e.message); }
  };
  inp.click();
}

// ---- calc / report / 下载 ----
function collectState() {
  return { scalars: S().scalars, topo_rows: S().topo_rows, grp_params: S().grp_params, ding: S().ding, meas: S().meas, curve_meta: S().curve_meta, mu_rows: S().mu_rows };
}
function header() { const s = S().scalars; return { Reference: s.mu_meta_ref, Date: s.mu_meta_date, "Author(s)": s.mu_meta_author }; }

function wireCalcReport() {
  const out = document.getElementById("calc-out");
  document.getElementById("btn-calc-test").textContent = "生成报告";
  document.getElementById("btn-calc-test").onclick = async () => {
    const conflict = groupnameConflict();
    if (conflict) { out.textContent = "❌ " + conflict; return; }
    out.textContent = "计算中…";
    try {
      const body = { state: collectState(), header: header() };
      const r = await reportMulti(body);
      out.textContent = `已评估 ${r.analytes.length} 种目标物 (${r.groups.length} 组) — 见下载`;
      enableDownloads(body);
    } catch (e) { out.textContent = "❌ " + e.message; }
  };
}
function enableDownloads(body) {
  document.querySelectorAll(".dl").forEach(b => b.disabled = false);
  document.getElementById("dl-md").onclick = async () => {
    const r = await reportMulti(body);
    showPreview(r.md);
  };
  document.getElementById("dl-docx").onclick = () => {
    const parts = [S().scalars.mu_meta_ref, S().scalars.mu_title].map(x => (x || "").trim()).filter(Boolean);
    downloadBlob("/api/export/multi/docx", body, (parts.join("_") || "不确定度评估") + ".docx");
  };
}

// 草稿保存 (暴露给工具条)
window.__saveDraft = async (name) => { S().currentDraft = name; await draftsMultiSave(name, toMulti(S())); };
window.__newDraft = () => { S().scalars = { ...scalarDefaultsMulti(meta().baseline_params) }; S().topo_rows = [{ 分组名: "纯品-1", 类型: "固体", 目标物: "" }, { 分组名: "液体-1", 类型: "液体", 目标物: "", "Urel%": null, "C_cert": null, "U_abs": null, "定容分组": "定容组1" }]; S().grp_params = {}; S().ding = {}; S().meas = null; S().curve_meta = {}; S().mu_rows = { blend: [], reag: [] }; location.hash = ""; location.reload(); };
