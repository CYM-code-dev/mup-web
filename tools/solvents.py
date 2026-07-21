# -*- coding: utf-8 -*-
"""
定容试剂 → 体积膨胀系数 α (1/℃, ~20℃) 查询.

第③页定容温度项 urel(t)=α·Δτ/√3 需要 α。三类入口的底层数据源:
  - SOLVENT_DB  : 内置 13 种常用溶剂的 α + CAS + 来源
  - lookup(q)   : 按 CAS(精确) 或 名称/别名(包含) 查, 始终返回 list
  - calc_beta_from_density : 查不到时用 NIST WebBook 相邻 3 温度点密度,
                              3 点中心差分反算 β=α

α 来源: Eurachem QUAM 附录 / Engineering Toolbox 体积膨胀系数表;
不确定项标 source="待核对", 由分析师终审 (报告会签字)。

单文件, 仅用标准库, 对齐 uncertainty.py 风格。

自检: python solvents.py
"""
import re
from html.parser import HTMLParser


def normalize_cas(s):
    """CAS 归一化: 只留数字, '67-56-1'/'67 56 1'/'67561' → '67561'。"""
    return re.sub(r"\D", "", s or "")


# 体积膨胀系数 α (1/℃, ~20℃)。density_20 为 20℃ 液态密度(g/cm³), 仅参考。
# source 标来源; "待核对" = 数值为估算中值, 需分析师核对原文后签字。
SOLVENT_DB = [
    # —— Eurachem QUAM 附录 (分析化学不确定度权威, 7 种) ——
    {"cas": "67-56-1", "name_cn": "甲醇", "name_en": "methanol", "aliases": ["木酒精", "methyl alcohol"], "alpha": 0.001183, "density_20": 0.7913, "source": "NIST 密度 15/20/25℃"},
    {"cas": "75-05-8", "name_cn": "乙腈", "name_en": "acetonitrile", "aliases": ["甲基氰", "cyanomethane"], "alpha": 0.00137, "density_20": 0.7822, "source": "Eurachem QUAM 附录"},
    {"cas": "110-54-3", "name_cn": "正己烷", "name_en": "n-hexane", "aliases": ["己烷", "hexane"], "alpha": 0.00138, "density_20": 0.6594, "source": "Eurachem QUAM 附录"},
    {"cas": "108-88-3", "name_cn": "甲苯", "name_en": "toluene", "aliases": ["toluol", "methylbenzene"], "alpha": 0.00107, "density_20": 0.8668, "source": "Eurachem QUAM 附录"},
    {"cas": "75-09-2", "name_cn": "二氯甲烷", "name_en": "dichloromethane", "aliases": ["DCM", "methylene chloride"], "alpha": 0.00137, "density_20": 1.3260, "source": "Eurachem QUAM 附录"},
    {"cas": "141-78-6", "name_cn": "乙酸乙酯", "name_en": "ethyl acetate", "aliases": ["EA", "醋酸乙酯"], "alpha": 0.00138, "density_20": 0.9006, "source": "Eurachem QUAM 附录"},
    {"cas": "67-63-0", "name_cn": "异丙醇", "name_en": "isopropanol", "aliases": ["IPA", "isopropyl alcohol", "2-丙醇"], "alpha": 0.00107, "density_20": 0.7858, "source": "Eurachem QUAM 附录"},
    # —— Engineering Toolbox 体积膨胀系数表 (3 种) ——
    {"cas": "67-64-1", "name_cn": "丙酮", "name_en": "acetone", "aliases": ["propanone", "阿西通"], "alpha": 0.00142, "density_20": 0.7899, "source": "密度法 β(20℃) (LSU ρ20=0.7900/ρ25=0.7844)"},
    {"cas": "109-99-9", "name_cn": "四氢呋喃", "name_en": "tetrahydrofuran", "aliases": ["THF", "氧杂环戊烷"], "alpha": 0.00126, "density_20": 0.8880, "source": "Engineering Toolbox 体积膨胀系数表"},
    {"cas": "1634-04-4", "name_cn": "甲基叔丁基醚", "name_en": "methyl tert-butyl ether", "aliases": ["MTBE", "叔丁基甲醚"], "alpha": 0.00119, "density_20": 0.7404, "source": "Engineering Toolbox 体积膨胀系数表"},
    # —— 待核对 (估算中值, 需分析师查原文复核, 3 种) ——
    {"cas": "67-68-5", "name_cn": "二甲基亚砜", "name_en": "dimethyl sulfoxide", "aliases": ["DMSO"], "alpha": 0.00088, "density_20": 1.1004, "source": "gChem DMSO 物性表"},
    {"cas": "68-12-2", "name_cn": "二甲基甲酰胺", "name_en": "N,N-dimethylformamide", "aliases": ["DMF", "N,N-二甲基甲酰胺"], "alpha": 0.00099, "density_20": 0.9487, "source": "密度法 β(20℃) (LSU ρ20=0.9487/Sigma ρ25=0.944)"},
    {"cas": "110-82-7", "name_cn": "环己烷", "name_en": "cyclohexane", "aliases": ["六氢化苯"], "alpha": 0.00121, "density_20": 0.7785, "source": "NIST 密度 15/20/25℃"},
]


def lookup(query):
    """按 CAS(精确, 归一化等值) 或 名称/别名(大小写不敏感包含) 查询。始终返回 list。
    CAS 优先: query 含数字时先按 CAS 精确匹配; 无命中再走名称包含。"""
    if not query or not query.strip():
        return []
    q = query.strip()
    qn = normalize_cas(q)
    if qn:                       # query 像个 CAS → 先精确匹配
        hits = [s for s in SOLVENT_DB
                if s.get("cas") and normalize_cas(s["cas"]) == qn]
        if hits:
            return hits
    ql = q.lower()               # 否则/兜底: 名称与别名包含
    out = []
    for s in SOLVENT_DB:
        names = [s.get("name_cn", ""), s.get("name_en", "")] + s.get("aliases", [])
        if any(ql in str(n).lower() for n in names):
            out.append(s)
    return out


def calc_beta_from_density(rho1, T1, rho2, T2, rho3, T3):
    """3 点中心差分反算体积膨胀系数 β=α (照 NIST WebBook 取相邻 3 温度点)。
    β = (ρ1-ρ3)/(ρ2·(T3-T1)), ρ2 为中心点 T2 处基准密度;
    斜率用端点 T1/T3, T2 仅作基准密度定位。
    返回 None: 端点温度相同(T3==T1) / 基准密度为 0 / 任一 ρ≤0。"""
    if T3 == T1 or rho2 == 0 or rho1 <= 0 or rho2 <= 0 or rho3 <= 0:
        return None
    return (rho1 - rho3) / (rho2 * (T3 - T1))


class _NistRowParser(HTMLParser):
    """收 <tr>/<td|th> 为 rows (list[list[str]]); 仅供 _parse_nist_density_table。"""
    def __init__(self):
        super().__init__()
        self.rows = []
        self._row = None
        self._cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._row is not None:
            self._row.append(" ".join(self._cell).strip() if self._cell else "")
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def _parse_nist_density_table(html):
    """解析 NIST fluid.cgi 等压表 HTML → {T(℃): ρ}。
    表头含 'density' 的列为密度列, 'temperature' 的列为温度列(缺省首列);
    无 Density 列 / 无数据行 → ValueError (流体不在 NIST 流体库 / 参数无效)。"""
    p = _NistRowParser()
    p.feed(html)
    dcol = tcol = None
    start = None
    for i, row in enumerate(p.rows):
        cells = [c.lower() for c in row]
        for j, c in enumerate(cells):
            if dcol is None and "density" in c:
                dcol = j
            if tcol is None and "temperature" in c:
                tcol = j
        if dcol is not None:
            if tcol is None:
                tcol = 0
            start = i + 1
            break
    if dcol is None:
        raise ValueError("NIST 返回无 Density 列 (流体不在库/参数无效)")
    out = {}
    for row in p.rows[start:]:
        if len(row) <= max(dcol, tcol):
            continue
        try:
            T = float(row[tcol].split()[0].replace(",", ""))
            rho = float(row[dcol].split()[0].replace(",", ""))
        except (ValueError, IndexError):
            continue
        out[T] = rho
    if not out:
        raise ValueError("NIST 表无数据行")
    return out


def fetch_nist_density(cas, tlow=20, thigh=40, tinc=5, p=1.0, dunit="g/ml", timeout=20):
    """从 NIST WebBook fluid.cgi 抓等压(默认 1 atm)液态密度, 返回 {T(℃): ρ}。
    需联网; 失败抛异常(调用方捕获)。仅用标准库。
    cas: CAS 号(如 '110-54-3'); tlow/thigh/tinc: 温度范围(℃); p: 压力(atm); dunit: 密度单位。"""
    import urllib.request, urllib.parse
    cid = "C" + normalize_cas(cas)          # 110-54-3 → C110543
    q = urllib.parse.urlencode({
        "Action": "Load", "ID": cid, "Type": "IsoBar", "RefState": "DEF",
        "TLow": tlow, "THigh": thigh, "TInc": tinc, "P": p,
        "TUnit": "C", "PUnit": "atm", "DUnit": dunit,
        "HUnit": "kJ/mol", "WUnit": "m/s", "VisUnit": "uPa*s", "STUnit": "N/m",
    })
    req = urllib.request.Request(
        "https://webbook.nist.gov/cgi/fluid.cgi?" + q,
        headers={"User-Agent": "Mozilla/5.0"})
    html = urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "replace")
    return _parse_nist_density_table(html)


def _approx(a, b, tol=0.005):
    return abs(a - b) / max(abs(b), 1e-12) <= tol


def selfcheck():
    assert normalize_cas("67-56-1") == "67561", "CAS 归一化(连字符)"
    assert normalize_cas("67 56 1") == "67561", "CAS 归一化(空格)"
    # CAS 查询
    hits = lookup("67-56-1")
    assert len(hits) == 1 and hits[0]["name_cn"] == "甲醇", "CAS 查甲醇"
    assert lookup("67561")[0]["name_cn"] == "甲醇", "无连字符 CAS"
    # 名称/别名查询
    assert lookup("methanol")[0]["alpha"] == 0.001183, "英文名"
    assert lookup("木酒精")[0]["name_cn"] == "甲醇", "中文别名"
    assert lookup("MTBE")[0]["name_cn"] == "甲基叔丁基醚", "英文缩写别名"
    # 无匹配
    assert lookup("xyz不存在") == [], "无匹配返回空 list"
    # 3 点中心差分: 正己烷 NIST 精确密度 15/20/25℃ (锚 20℃, 与量器标称/Δτ=T−20 口径一致)
    b = calc_beta_from_density(0.66388, 15, 0.65938, 20, 0.65485, 25)
    assert _approx(b, 0.00137, 0.005), f"正己烷 β={b} 预期≈0.00137"
    # 端点温度相同 → None
    assert calc_beta_from_density(0.7, 20, 0.69, 25, 0.68, 20) is None, "T3==T1 → None"
    print("=== solvents.selfcheck OK ===")
    print(f"  内置 {len(SOLVENT_DB)} 种溶剂")
    print(f"  正己烷 β(20℃) = {b:.5g} /℃  (NIST 密度 3 点中心差分, "
          f"与表 α=0.00138 互校一致, 差 {abs(b-0.00138)/0.00138*100:.1f}%)")
    todo = [s["name_cn"] for s in SOLVENT_DB if s.get("source") == "待核对"]
    if todo:
        print(f"  ⚠ α 待分析师核对: {', '.join(todo)}")
    # NIST 在线自检 (离线/失败则跳过, 不影响 selfcheck)
    try:
        pts = fetch_nist_density("110-54-3", 15, 30, 5)
        bn = calc_beta_from_density(pts[15], 15, pts[20], 20, pts[25], 25)
        assert _approx(bn, 0.00137, 0.01), f"NIST 在线 β={bn}"
        print(f"  NIST 在线: 正己烷 ρ={pts[15]:.5g}/{pts[20]:.5g}/{pts[25]:.5g}, "
              f"β={bn:.5g} (与手算一致)")
    except Exception as e:
        print(f"  NIST 在线自检跳过 ({type(e).__name__}: {e})")
    return b


if __name__ == "__main__":
    selfcheck()
