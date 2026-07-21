// 量器下拉选项构造 (数据来自 /api/meta/constants; 勿在前端硬编码允差)。
import { parseVesselNominal } from './util.js';

// 量器类型: value=kind键, label=中文
export function kindOptions(meta) {
  return Object.entries(meta.kind_labels).map(([k, v]) => ({ value: k, label: v }));
}

// 量器规格: value=体积字符串, label="v mL (±tol)"; 末尾「自定义」
export function volOptions(meta, kind) {
  const t = meta.glass_tolerance;
  const vols = meta.volumes[kind];
  return [
    ...((vols || []).map(v => ({ value: String(v), label: `${v} mL (±${t[`${kind}@${v}`]})` }))),
    { value: "自定义", label: "自定义" },
  ];
}

export { parseVesselNominal };
