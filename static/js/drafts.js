// 草稿 v1 (单目标物) 双向序列化 + 标量默认值 (来自 baseline_params, 对齐 single_form value=)。
import { today, round_dp, round_sf } from './util.js';

// I级天平 MPE (JJG1036, e=1mg) 按称样量取 → mg
function balanceMPEmg(m) { return m <= 50 ? 0.5 : m <= 200 ? 1.0 : 1.5; }

// 全部 widget 键的默认值 (B = meta.baseline_params)
export function scalarDefaults(B) {
  const pipVesselDefault = "5 mL 单标吸量管(A)(±0.007)";
  return {
    meta_ref: "MUP-CG-", meta_date: today(), meta_author: "",
    title: "", basis: "", instrument: "", method_std_no: "",
    analyte: "", matrix: "", std_name: "",
    unit: "", round_mode: "", round_nd: "",
    env_temp: B.env_temp ?? 20.0, dtau: B.dtau, prep_flow: B.prep_flow ?? "", influences: "",
    balance_id: "",
    m_sample_raw: "", n_weighings: B.n_weighings, balance_tol_mg: "",
    makeup_mode: "single",
    vessel_kind: "", vessel_vol_sel: "", vessel_vol_custom: "", vessel_tol_custom: "", vuv: "",
    solvent_preset: "自定义", makeup_solvent_val: B.makeup_solvent ?? "", alpha_val: "",
    blend_vk: "", blend_vv: "", blend_vuse: null, blend_n: 2, n_reag: 2,
    stock_source: B.stock_source ?? "solid",
    purity: "", U_purity: "", k_purity: B.k_purity, m_std: "",
    stock_balance_id: "", stock_balance_tol_mg: balanceMPEmg(B.m_sample), stock_n_weighings: B.n_weighings,
    stock_flask_s: 10,
    cert_mode: "relative", k_cert: 2, Urel_cert: "", C_cert: 100.0, C_cert_unit: "mg/L", U_abs: 5.1,
    pip_vessel: pipVesselDefault, pip_vol_actual: "",
    stock_makeup_mode: "single", stock_solvent_preset: "自定义", stock_solvent: B.stock_solvent ?? "", stock_alpha: "", stbl_n: 2,
    work_same_solvent: true, work_makeup_mode: "single", work_alpha: "", work_serial_dilute: true, wbl_n: 2,
    spike_std_conc: "", spike_add_vol: "", spike_vol: "",
    spike_theor: "",
    spike_add_mass: "",
    curve_method: B.curve_method, curve_include_origin: false, curve_force_origin: false, curve_link_chain: true,
  };
}
// editors 种子 (空表单): 新建草稿时曲线点/加标表各默认一行空行，由用户填写
export function editorSeeds(B, meta) {
  return { work_df: [{}], points_df: [{}], spike_df: [{}] };
}

// 载入草稿 payload → S (defaults 补缺)
export function applySingle(payload, S) {
  const d = payload || {};
  S.scalars = { ...S.scalars, ...(d.scalars || {}) };
  S.rows = {
    reag: (d.rows && d.rows.reag) || [],
    blend: (d.rows && d.rows.blend) || [],
    stock_blend: (d.rows && d.rows.stock_blend) || [],
    work_blend: (d.rows && d.rows.work_blend) || [],
  };
  if ((S.rows.stock_blend || []).some(r => r.s)) S.scalars.stock_blend_custom = true;   // 已有储备液混合试剂 → 锁定, 不被样液跟随覆盖
  S.editors = {
    work_df: (d.editors && d.editors.work_df) || S.editors.work_df || [],
    points_df: (d.editors && d.editors.points_df) || S.editors.points_df || [],
    spike_df: (d.editors && d.editors.spike_df) || S.editors.spike_df || [],
  };
  S.currentDraft = d._name || null;
}

// S → 草稿 payload (v1)
export function toSingle(S) {
  return {
    _draft_version: 1, _saved_at: new Date().toISOString().slice(0, 19).replace("T", "T"),
    makeup_mode: S.scalars.makeup_mode,
    scalars: { ...S.scalars },
    rows: { reag: S.rows.reag, blend: S.rows.blend, stock_blend: S.rows.stock_blend, work_blend: S.rows.work_blend },
    editors: { work_df: S.editors.work_df, points_df: S.editors.points_df, spike_df: S.editors.spike_df },
  };
}

// ---- 多目标物 (v4; 对齐 _mu_draft_payload app.py:1196) ----
// mu_ 前缀方法级标量 + topo_rows(分组拓扑宽表) + grp_params(组级共享) + meas(Excel) + curve_meta
export function scalarDefaultsMulti(B) {
  const d = balanceMPEmg(B.m_sample);
  return {
    mu_meta_ref: "MUP-CG-", mu_meta_date: today(), mu_meta_author: "",
    mu_title: "", mu_basis: "", mu_instrument: "", method_std_no: "",
    mu_matrix: "", mu_analyte: "",
    mu_curve_method: "外标法", mu_curve_npoints: 5, mu_curve_inj: 1, mu_spike_nrep: 7, mu_fr_inj: 1,
    mu_unit: "", mu_round_mode: "", mu_round_nd: "",
    mu_dtau: B.dtau, mu_env_temp: B.env_temp ?? 20.0, mu_prep_flow: B.prep_flow ?? "", mu_influences: "",
    mu_balance_id: "",
    mu_m_sample_raw: "", mu_n_weighings: B.n_weighings, mu_balance_tol_mg: "",
    mu_vessel_kind: "", mu_vessel_vol_sel: "",
    mu_makeup_mode: "single", mu_blend_vk: "", mu_blend_vv: "", mu_blend_vuse: null, mu_blend_n: 2, mu_n_reag: 2,
    solvent_preset: "自定义", makeup_solvent_val: B.makeup_solvent ?? "", alpha_val: "",
    mu_show_solid: false, mu_show_liquid: false,
    mu_solid_bal_mg: d, mu_solid_balance_id: "",
    mu_stock_makeup_mode: "single", mu_stock_solvent_preset: "自定义", mu_stock_solvent: B.makeup_solvent ?? "",
    mu_stock_alpha: "", mu_stock_reagents: [], mu_stock_blend_n: 2,
    mu_liq_stock_makeup_mode: "single", mu_liq_stock_solvent_preset: "自定义", mu_liq_stock_solvent: B.makeup_solvent ?? "",
    mu_liq_stock_alpha: "", mu_liq_stock_reagents: [], mu_liq_stock_blend_n: 2,
    mu_work_serial_dilute: true, mu_work_same_solvent: true,
    mu_work_solvent_preset: "自定义", mu_work_solvent: B.makeup_solvent ?? "", mu_work_alpha: "", mu_work_makeup_mode: "single", mu_work_blend_n: 2,
  };
}

export function applyMulti(payload, S) {
  const d = payload || {};
  S.scalars = { ...scalarDefaultsMulti(S.meta?.baseline_params || {}), ...(d.scalars || {}) };
  S.topo_rows = d.topo_rows || [{ 分组名: "纯品-1", 类型: "固体", 目标物: "" }];
  S.grp_params = d.grp_params || {};
  S.meas = d.meas ?? null;
  S.curve_meta = d.curve_meta || {};
  S.mu_rows = d.mu_rows || { blend: [], reag: [] };
  for (const pfx of ["mu_stock", "mu_liq_stock"]) {
    if ((S.mu_rows[pfx + "_blend"] || []).some(r => r.s)) S.scalars[pfx + "_blend_custom"] = true;   // 已有储备液混合试剂 → 锁定, 不被样液跟随覆盖
  }
  // 中间液/工作液按「定容分组」跨组共享 (ding[D]); 旧草稿无 ding → 从 grp_params[gn].inter/work 迁出
  S.ding = d.ding || {};
  if (!d.ding) {
    const seen = {};
    for (const r of (S.topo_rows || [])) {
      if (r.类型 !== "液体") continue;
      const gn = (r.分组名 || "").trim();
      if (!gn || seen[gn]) continue;
      seen[gn] = true;
      const D = (r.定容分组 ?? "1").toString().trim() || "1";
      const g = S.grp_params[gn] || {};
      if (!g.inter && !g.work) continue;
      S.ding[D] = S.ding[D] || { feeds: {}, flasks: {}, work: {} };
      if (g.inter) {
        const fd = g.inter.feeds?.[D] || Object.values(g.inter.feeds || {})[0];
        if (fd) S.ding[D].feeds[gn] = fd;                // 源键 D → gn (按分组名)
        Object.assign(S.ding[D].flasks, g.inter.flasks || {});
      }
      if (g.work) Object.assign(S.ding[D].work, g.work);
      delete g.inter; delete g.work;
    }
  }
  S.currentDraft = d._name || null;
}

export function toMulti(S) {
  return {
    _draft_version: 4, mode: "multi",
    _saved_at: new Date().toISOString().slice(0, 19),
    scalars: { ...S.scalars }, topo_rows: S.topo_rows,
    grp_params: S.grp_params, ding: S.ding, meas: S.meas, curve_meta: S.curve_meta, mu_rows: S.mu_rows,
  };
}
