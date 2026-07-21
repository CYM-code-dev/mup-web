// 工具: 四舍六入五成双 (BigInt 精确移植 uncertainty._round_decimal) + 量器串解析。

// "1.23e-4" → "0.000123"; 无指数原样返回。
function expandExp(s) {
  if (!/e/i.test(s)) return s;
  const m = s.split(/[eE]/)[0];
  let exp = parseInt(s.split(/[eE]/)[1], 10);
  let neg = m[0] === '-';
  let mm = neg ? m.slice(1) : m;
  const [ip, fp = ""] = mm.split(".");
  let digits = ip + fp;
  let point = ip.length + exp;
  if (point <= 0) digits = "0." + "0".repeat(-point) + digits;
  else if (point >= digits.length) digits = digits + "0".repeat(point - digits.length);
  else digits = digits.slice(0, point) + "." + digits.slice(point);
  return (neg ? "-" : "") + digits;
}

// 四舍六入五成双, 保留到 10^q 位。value=int(numStr)/10^scale; 取整 int(numStr)/10^(scale+q)。
function roundQ(x, q) {
  if (x == null || !isFinite(x)) return x;
  if (x === 0) return 0.0;
  const s = expandExp(String(x));
  const neg = s[0] === "-";
  const ss = s.replace(/^[+-]/, "");
  const [ip, fp = ""] = ss.split(".");
  const numStr = (ip + fp).replace(/^0+(?=\d)/, "") || "0";
  const scale = fp.length;
  const k = scale + q;
  let N = BigInt(numStr);
  let rounded;
  if (k <= 0) {
    rounded = N * (10n ** BigInt(-k));
  } else {
    const den = 10n ** BigInt(k);
    let qi = N / den, r = N % den;
    const twice = 2n * r;
    if (twice > den) qi += 1n;
    else if (twice === den && qi % 2n === 1n) qi += 1n;   // 半 → 偶
    rounded = qi;
  }
  if (neg) rounded = -rounded;
  const v = Number(rounded) * Math.pow(10, q);
  return parseFloat(v.toPrecision(15));   // 清浮点尾噪声: 111*0.1 → 11.100000000000001 修为 11.1
}

// 最高位阶 (10^n), 从字符串取避免 log10 噪声。
function _adjusted(s) {
  const [ip, fp = ""] = s.split(".");
  if (ip[0] !== "0") return ip.length - 1;        // "12.3"→1, "123"→2
  let i = 0;
  while (i < fp.length && fp[i] === "0") i++;      // "0.005"→i=2→-3
  return -(i + 1);
}

export function round_dp(x, n) { return roundQ(x, -n); }
export function round_sf(x, n) {
  if (x == null || !isFinite(x) || x === 0) return x === 0 ? 0.0 : x;
  const s = expandExp(String(Math.abs(x))).replace(/^[+-]/, "");
  return roundQ(x, _adjusted(s) - (n - 1));
}

// 浓度量级显示: <0.10→3 位小数 / ≥0.10→2 位小数 (single_form _c0_dp)
export function roundC(v) { return v == null || !isFinite(v) ? v : round_dp(v, Math.abs(v) < 0.1 ? 3 : 2); }
// 浓度显示串(带尾零): <0.10→3 位小数 / ≥0.10→2 位小数 — 母液/目标浓度列 onSet 与 targetStr 共用
export function concStr(v) { const n = Number(v); return isFinite(n) ? n.toFixed(Math.abs(n) < 0.1 ? 3 : 2) : null; }
// 移取体积显示串: ≥0.01→2 位小数 (<0.01 返回 null, 保留原精度) — 量器联动/手输/onSet 共用
export function volStr(v) { const n = Number(v); return isFinite(n) && n >= 0.01 ? round_dp(n, 2).toFixed(2) : null; }

// 有效数字显示串: n 位有效数字 (银行家修约 round_sf + 补尾零, 展开科学计数)
function sfStr(v, n) {
  if (v == null || !isFinite(v)) return v;
  if (v === 0) return "0";
  if (!(n >= 1)) return String(round_sf(v, n));          // 位数未设/0 → 不补尾零
  return expandExp(round_sf(v, n).toPrecision(n));
}
// 结果修约显示串 (保留尾零): 小数位数→toFixed(nd); 有效数字→n 位有效数字
export function resultStr(v, mode, nd) {
  if (v == null || (typeof v === "number" && !isFinite(v))) return v;
  const n = Number(nd);
  return mode === "有效数字" ? sfStr(v, n) : round_dp(v, n).toFixed(n);
}

// "10 mL 容量瓶(A)(±0.020)" → 10 ; 解析失败 → null
export function parseVesselNominal(label) {
  if (!label) return null;
  const m = String(label).match(/^([\d.]+)/);
  return m ? parseFloat(m[1]) : null;
}

export function today() {
  const d = new Date();
  return `${d.getFullYear()}/${String(d.getMonth() + 1).padStart(2, "0")}/${String(d.getDate()).padStart(2, "0")}`;
}
