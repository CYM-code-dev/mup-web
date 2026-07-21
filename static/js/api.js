// 每个后端端点一个 fetch 封装。Phase 0 仅 meta/calc-single; 后续阶段补齐。
const BASE = '/api';
const get = (url, opts) => fetch(url, opts).then(async r => {
  if (!r.ok) {
    let detail = `HTTP ${r.status}`;
    try { const j = await r.json(); detail = typeof j.detail === 'string' ? j.detail : (j.detail ? JSON.stringify(j.detail) : detail); } catch {}
    throw new Error(detail);
  }
  return r.json();
});
const post = (url, body) => get(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });

export const getConstants = () => get(`${BASE}/meta/constants`);
export const calcSingle   = p => post(`${BASE}/calc/single`, p);
export const reportSingle = body => post(`${BASE}/report/single`, body);
export const draftsList   = () => get(`${BASE}/drafts/single`);
export const draftsLoad   = name => get(`${BASE}/drafts/single/${encodeURIComponent(name)}`);
export const draftsSave   = (name, body) => post(`${BASE}/drafts/single/${encodeURIComponent(name)}`, body);
export const draftsDelete = name => get(`${BASE}/drafts/single/${encodeURIComponent(name)}`, { method: 'DELETE' });
export const aiParse = prep_flow => post(`${BASE}/ai/parse-prep-flow`, { prep_flow });
export const aiParseMethod = std_no => post(`${BASE}/ai/parse-method`, { std_no });
export const aiConfigStatus = () => get(`${BASE}/ai/config-status`);
export const solvAlpha = body => post(`${BASE}/solvents/alpha-by-cas`, body);
export const limsTrace = code => post(`${BASE}/lims/trace`, { code });

// ---- 多目标物 ----
export const calcMulti   = p => post(`${BASE}/calc/multi`, p);
export const reportMulti = body => post(`${BASE}/report/multi`, body);
export const draftsMultiList = () => get(`${BASE}/drafts/multi`);
export const draftsMultiLoad = name => get(`${BASE}/drafts/multi/${encodeURIComponent(name)}`);
export const draftsMultiSave = (name, body) => post(`${BASE}/drafts/multi/${encodeURIComponent(name)}`, body);
export const draftsMultiDelete = name => get(`${BASE}/drafts/multi/${encodeURIComponent(name)}`, { method: 'DELETE' });
export const aiParseMulti = prep_flow => post(`${BASE}/ai/parse-prep-flow-multi`, { prep_flow });
export async function templateMultiDownload(body) {
  const res = await fetch(`${BASE}/template/multi/download`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.blob();
}
export async function templateMultiUpload(file) {
  const fd = new FormData(); fd.append("file", file);
  const res = await fetch(`${BASE}/template/multi/upload`, { method: "POST", body: fd });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}
