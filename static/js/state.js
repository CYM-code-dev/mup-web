// 中央状态 + 极简 pub/sub。路径用点号 (scalars.m_sample_raw / editors.work_df)。
const S = {
  mode: "single", meta: {},
  scalars: {}, rows: { reag: [], blend: [], stock_blend: [] },
  mu_rows: { blend: [], reag: [] },
  editors: { work_df: [], points_df: [], spike_df: [] },
  groups: {}, mu: {}, currentDraft: null,
};
const subs = new Map();

export function state() { return S; }

export function get(p) {
  return p.split(".").reduce((o, k) => (o == null ? o : o[k]), S);
}

export function set(p, v) {
  const ks = p.split(".");
  let o = S;
  for (let i = 0; i < ks.length - 1; i++) { if (o[ks[i]] == null) o[ks[i]] = {}; o = o[ks[i]]; }
  o[ks[ks.length - 1]] = v;
  subs.get(p)?.forEach(f => f(get(p)));
}

export function on(paths, fn) {
  paths.forEach(p => { if (!subs.has(p)) subs.set(p, new Set()); subs.get(p).add(fn); });
}
