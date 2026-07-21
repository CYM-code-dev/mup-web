// 量器下拉选项构造 (数据来自 /api/meta/constants; 勿在前端硬编码允差)。
import { parseVesselNominal } from './util.js';

// 量器类型: value=kind键, label=中文
// pip_p (移液枪) 仅作「移取量器」(走 meta.pip_opts), 不进定容/混合量器类型 → 此处排除。
export function kindOptions(meta) {
  return Object.entries(meta.kind_labels)
    .filter(([k]) => k !== 'pip_p')
    .map(([k, v]) => ({ value: k, label: v }));
}

// 量器规格: value=体积字符串, label="v mL (±tol)"; 末尾「自定义」
// pip_p (移液枪) 允差为体积百分比, label 显示 ±%; 其余 glass 仍显示 ±mL (查 glass_tolerance)。
export function volOptions(meta, kind) {
  const vols = meta.volumes[kind] || [];
  if (kind === 'pip_p') {
    const t = meta.pipette_tol || {};
    return [
      ...vols.map(v => ({ value: String(v), label: `${v} mL (±${(t[`pip_p@${v}`] * 100)}%)` })),
      { value: "自定义", label: "自定义" },
    ];
  }
  const t = meta.glass_tolerance;
  return [
    ...(vols.map(v => ({ value: String(v), label: `${v} mL (±${t[`${kind}@${v}`]})` }))),
    { value: "自定义", label: "自定义" },
  ];
}

export { parseVesselNominal };
