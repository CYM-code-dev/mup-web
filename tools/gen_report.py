# -*- coding: utf-8 -*-
"""
不确定度报告生成器 (路径A: Markdown 草稿)

输入: 一份方法参数 (dict, 同 uncertainty.py 的结构) + 引擎算出的结果.
输出: 按范本 MUP-CG-248 结构的 Markdown 草稿 (6 章节 + 7 表), 数值已填好,
      公式以文本占位. 分析师复制到 Word 套范本样式, 或后续再做原生 docx.

用法:
  python gen_report.py            # 跑 MUP-CG-248 范例, 输出到 stdout
  python gen_report.py > out.md   # 存盘
或在 Python 里: from gen_report import render; print(render(method, result))
"""
import math
import sys
from decimal import Decimal, ROUND_CEILING

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
from uncertainty import mup_cg248, recovery, GLASS_TOLERANCE, _GRADUATED, round_sf, fmt_result, vessel_tol  # noqa: E402


def _f(x, nd=4):
    """相对不确定度类小数保留 nd 位有效(保留末尾0), 大数适当截断."""
    if x is None or x == 0:
        return "0"
    if abs(x) >= 1:
        return f"{x:#.4g}"
    return f"{x:#.{nd}g}"


def _ceil_dp(x, dp):
    """x 向上修约到 dp 位小数 (ROUND_CEILING; 不确定度只进不舍)."""
    if x is None or x == 0 or not math.isfinite(x):
        return 0.0 if x == 0 else x
    q = Decimal(1).scaleb(-dp)
    return float(Decimal(str(x)).quantize(q, rounding=ROUND_CEILING))


def _round_pair(X, U, method):
    """最终结果行 (X±U) 的显示串: w 按 round_mode/nd 修约;
    U 向上修约(ROUND_CEILING)至与 w 同小数位. 返回 (w_disp, U_disp)."""
    mode = method.get("round_mode", "有效数字")
    nd = method.get("round_nd", 3)
    w_disp = fmt_result(X, mode, nd)
    dp = len(w_disp.split(".", 1)[1]) if "." in w_disp else 0
    U_disp = fmt_result(_ceil_dp(U, dp), "小数位数", dp)
    return w_disp, U_disp


_SUP = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")


def _sci_t(x):
    """正文文本科学计数: 1.19e-3 → '1.19×10⁻³'; ≥0.01 原样 (4.2 温度系数用)。"""
    if x == 0 or abs(x) >= 0.01:
        return f"{x:g}"
    e = int(math.floor(math.log10(abs(x))))
    sign = "⁻" if e < 0 else ""
    return f"{x/10**e:g}×10{sign}{str(abs(e)).translate(_SUP)}"


def _sci_l(x):
    """LaTeX 科学计数: 1.19e-3 → '1.19\\times10^{-3}' (4.2 温度式代入用)。"""
    if x == 0 or abs(x) >= 0.01:
        return f"{x:g}"
    e = int(math.floor(math.log10(abs(x))))
    return f"{x/10**e:g}\\times10^{{{e}}}"


# 量器类型代码 → 中文名 (4.2 定容描述用)
KIND_CN = {"flask": "容量瓶", "pip_s": "单标线吸量管", "pip_g": "分度吸量管", "cylinder": "量筒", "pip_p": "移液枪"}

# 4.3.2 稀释流程表量器名 (模板/分析师口径): 单标/刻度移液管, 容量瓶, 量筒
_FLOW_VESSEL = {"flask": "容量瓶", "pip_s": "单标移液管", "pip_g": "刻度移液管", "cylinder": "量筒", "pip_p": "移液枪"}


def _work_flow_rows(method):
    """4.3.2 稀释流程表 markdown 行 (表头+分隔+数据), 模板表1。
    浓度沿稀释链按首次出现顺序标 C(N)..C1 (N=去重后浓度数; 最高浓=C(N), 末级=C1)。
    method['work_chain']: [{母液,体积,pip_kind,pip_vol,flask_vol,目标}, ...]
    (app._dilution_chain 产出, 描述性不进计算)。空 → []。"""
    wc = method.get("work_chain") or []
    if not wc:
        return []
    seen = {}
    for row in wc:
        for key in ("母液", "目标"):
            c = (row.get(key) or "").strip()
            if c and c not in seen:
                seen[c] = len(seen)
    N = len(seen)

    def _lab(c):
        c = (c or "").strip()
        return f"C{N - seen[c]}({c})" if c in seen else c

    out = ["| 母液浓度（mg/L） | 移取体积（mL） | 移取量器 | 定容量器 | 目标浓度（mg/L） |",
           "|---|---|---|---|---|"]
    for row in wc:
        v = row.get("体积")
        v_l = f"{v:.2f}" if isinstance(v, (int, float)) else ""
        pk, pv = row.get("pip_kind"), row.get("pip_vol")
        pip_l = f"{pv:g}ml{_FLOW_VESSEL[pk]}" if (pk in _FLOW_VESSEL and pv) else ""
        fv = row.get("flask_vol")
        fl_l = f"{fv:g}ml容量瓶" if fv else ""
        out.append(f"| {_lab(row.get('母液'))} | {v_l} | {pip_l} | {fl_l} | {_lab(row.get('目标'))} |")
    return out


def _work_flow_rows_multi(grp, unit):
    """多目标物 4.3.2 稀释流程表: 中间液(混合定容, inter.feeds) + 工作液(串行, work) 完整链。
    grp: 标准品分组 (inter={feeds,flasks}, work={dg:[step]}); unit: 源单元(液体=ding_group/固体=目标物名)。
    母液/目标浓度 <0.10 留3位 / ≥0.10 留2位; 量器串去等级允差后缀 (A)(±…)。
    中间液浓度=工作液首步母液(工作液自中间液起稀释), 储备液(其母液)由此反推。无中间液移取/空 → []。"""
    inter = grp.get("inter") or {}
    feeds = inter.get("feeds") or {}
    flasks = inter.get("flasks") or {}
    work = grp.get("work") or {}

    def _strip(s):
        return str(s or "").split("(")[0].strip()       # ponytail: 去量器等级/允差后缀 (A)(±…)

    def _nominal(s):
        try:
            return float(str(s).split(" mL")[0])        # ponytail: 量器串恒为 "N mL …" (app._vsl_label)
        except (ValueError, IndexError):
            return None

    def _conc(x):
        try:
            v = float(x)
        except (TypeError, ValueError):
            return str(x) if x not in (None, "") else ""
        return f"{v:.3f}" if abs(v) < 0.1 else f"{v:.2f}"   # <0.10 留3位 / ≥0.10 留2位

    def _dilute(a, b, c):
        try:
            return float(a) * float(b) / float(c)       # a·b/c
        except (TypeError, ValueError, ZeroDivisionError):
            return None

    def _vol(pv):
        return f"{pv:.2f}" if isinstance(pv, (int, float)) and pv else ""

    rows = []
    fd = feeds.get(unit)
    dg = fd.get("dg") if fd else None
    wchain = work.get(dg) or [] if dg is not None else []
    # 中间液 (混合定容): 源单元移取 → 所在 dg 容量瓶定容
    if fd and fd.get("pip_vol") and float(fd["pip_vol"]) > 0:
        pv = float(fd["pip_vol"])
        fv_str = flasks.get(dg)
        fv = _nominal(fv_str)
        inter_c = wchain[0].get("母液浓度(mg/L)") if wchain else None
        stock_c = _dilute(inter_c, fv, pv) if (inter_c is not None and fv) else None
        rows.append(f"| {_conc(stock_c)} | {_vol(pv)} | {_strip(fd.get('pip_vessel'))} | "
                    f"{_strip(fv_str)} | {_conc(inter_c)} |")
    # 工作液 (串行稀释): 目标 = 母液×移取/定容
    for s in wchain:
        fv = _nominal(s.get("flask_vessel"))
        tgt = _dilute(s.get("母液浓度(mg/L)"), s.get("pip_vol"), fv)
        rows.append(f"| {_conc(s.get('母液浓度(mg/L)'))} | {_vol(s.get('pip_vol'))} | "
                    f"{_strip(s.get('pip_vessel'))} | {_strip(s.get('flask_vessel'))} | {_conc(tgt)} |")
    if not rows:
        return []
    return ["| 母液浓度（mg/L） | 移取体积<br>（mL） | 移取量器 | 定容量器 | 目标浓度（mg/L） |",
            "|---|---|---|---|---|"] + rows


def _curve_word(method):
    return "内标法面积比最小二乘(y=A分析物/A内标)" if method.get("curve_method") == "内标法" \
        else "外标法最小二乘(y=峰面积)"


def _stock_word(r):
    """储备液来源措辞。r: 引擎结果 dict (含 stock_source/stock_detail)。"""
    src = r.get("stock_source", "solid")
    if src == "liquid_dilute":
        return "高浓液标(证书浓度+移取浓标+定容[定容试剂])"
    return "含纯度/称量/定容"


def _group_header(g):
    """§5 标准品分组标题行: solid 注明共用称量/容量瓶; liquid 注明共用移液/定容。"""
    nm = g.get("name", "")
    n = len(g.get("analytes", []))
    if g.get("kind") == "liquid":
        pk = KIND_CN.get(g.get("pip_kind", ""), g.get("pip_kind", ""))
        cert = "绝对浓度 C±U" if g.get("cert_mode") == "absolute" else "证书 Urel"
        return (f"### 标准品分组：{nm}（液体标液，{n} 种目标物共用 "
                f"{g.get('pip_vol', '?')}mL{pk}→{g.get('flask_vol', '?')}mL容量瓶；"
                f"{cert}按目标物分别取值）\n")
    kind_cn = "混标" if n > 1 else "纯品"
    return (f"### 标准品分组：{nm}（固体{kind_cn}，{n} 种目标物共用同一称量 "
            f"m_std={g.get('m_std_g', '?')}g、{g.get('flask_volume_mL', '?')}mL容量瓶；"
            f"各目标物纯度分别评定）\n")


def _sample_effective_alpha(method, r):
    """样液定容(4.2)的有效膨胀系数α, 供储备液定容(4.3.1.3)引用去重比对.
    single→r['alpha']; mixed→makeup_detail.blend_alpha; multi→None(无单一α, 不引用)."""
    mm = method.get("makeup_mode", "single")
    if mm == "mixed":
        return (r.get("makeup_detail") or {}).get("blend_alpha")
    if mm == "multi":
        return None
    return r.get("alpha", 1.19e-3)


def _stock_solid_detail(method, r, analyte, sec="4.3.1"):
    """4.3.1 储备液(纯品称量)明细 = √(纯度² + 称量² + 定容²), 返回行列表.
    定容再拆 容量瓶允差(三角√6) + 温度(均匀√3, α·Δτ/√3).
    定容试剂 α: 混合(method['stock_reagents']→体积加权 blend) / 单一(method['stock_alpha']) / 缺省方法级 α.
    数值由 method+r 重算 (与 4.1/4.2 同; 引擎 r['u_stock'] 供末式结果对账)."""
    g = lambda x: f"{x:g}"
    sq = math.sqrt
    env_temp = method.get("env_temp", 20.0)
    dtau = r.get("dtau", 5.0)
    p_purity = method["purity"]; U_p = method["U_purity"]; k_p = int(method["k_purity"])
    m_std = method["m_std"]
    d = method.get("stock_balance_tol", method["balance_tol"])           # 默认同样品天平 d
    bid = method.get("stock_balance_id", method.get("balance_id", ""))   # 默认同样品天平编号
    n_w = int(method.get("stock_n_weighings", 2))                        # 去皮+称量次数
    fv = int(method["stock_flask_volume"])
    tol_f = GLASS_TOLERANCE[("flask", fv)]
    reags = method.get("stock_reagents")
    if reags:
        alpha_s = sum(x["volume"] * x["alpha"] for x in reags) / sum(x["volume"] for x in reags)
        solvent = ""
    else:
        alpha_s = method.get("stock_alpha", r.get("alpha", 1.19e-3))
        solvent = method.get("stock_solvent", "")
    u_p = U_p / (k_p * p_purity)                     # 纯度
    u_sm_abs = sq(n_w) * d / sq(3)                   # 称量 绝对 (g), √n 去皮+称量
    u_sm = u_sm_abs / m_std                          # 称量 相对
    v_ml = tol_f / (sq(6) * fv)                      # 容量瓶允差 (三角 √6)
    v_t = alpha_s * dtau / sq(3)                     # 温度 (均匀 √3)
    u_sv = sq(v_ml ** 2 + v_t ** 2)                  # 定容 合成
    L = []
    A = L.append
    A(f"{analyte}是由纯品配置为储备液，因此其不确定度主要有三个来源：标准品纯度产生的不确定度"
      f" $u_{{rel}}(c_{{s,p}})$，标准品称量产生的不确定度 $u_{{rel}}(c_{{s,m}})$，"
      f"标准品定容体积产生的不确定度 $u_{{rel}}(c_{{s,V}})$。")
    A("$$ u_{rel}(C_{stock}) = \\sqrt{u_{rel}(c_{s,p})^{2} + u_{rel}(c_{s,m})^{2}"
      " + u_{rel}(c_{s,V})^{2}} $$")
    A(f"储备液的配置流程：称取{g(m_std)}g标准品于{fv}mL容量瓶中，"
      + (f"用{solvent}溶解定容。" if solvent else "溶解定容。"))
    # 4.3.1.1 纯度 (U/(k·p); 正文用%, 式中用存储小数)
    A(f"**{sec}.1 标准品纯度产生的不确定度 $u_{{rel}}(c_{{s,p}})$**")
    A(f"查标准品证书可得，{analyte}纯度p为{g(p_purity * 100)}%，扩展不确定度U={g(U_p * 100)}%、"
      f"k={k_p}，按均匀分布，则由纯度引入的不确定度为：")
    A("$$ u_{rel}(c_{s,p}) = \\frac{U}{k \\cdot p} = \\frac{" + g(U_p) + "}{"
      + str(k_p) + " \\times " + g(p_purity) + "} = " + _f(u_p) + " $$")
    # 4.3.1.2 称量 (√n_w·d/√3 绝对; /m 相对)
    A(f"**{sec}.2 标准品称量产生的不确定度 $u_{{rel}}(c_{{s,m}})$**")
    twice = "两次" if n_w == 2 else f"{n_w}次"
    bid_c = f"称量使用{bid}的电子分析天平，" if bid else "称量使用电子分析天平，"
    A(f"{bid_c}其示值允差为±{g(d * 1000)}mg，按均匀分布，k=√3，由于称量时有去皮和称量{twice}操作，"
      f"分量应计算{twice}，则标准品称量引入的不确定度：")
    A("$$ u(c_{s,m}) = \\frac{\\sqrt{" + str(n_w) + "} \\times " + g(d) + "\\,\\mathrm{g}}{\\sqrt{3}} = "
      + _f(u_sm_abs) + "\\,\\mathrm{g} $$")
    A("则标准品称量引入的相对标准不确定度为：")
    A("$$ u_{rel}(c_{s,m}) = \\frac{u(c_{s,m})}{m} = \\frac{" + _f(u_sm_abs) + "}{"
      + g(m_std) + "} = " + _f(u_sm) + " $$")
    # 4.3.1.3 定容 (允差 + 温度)
    A(f"**{sec}.3 标准品定容体积产生的不确定度 $u_{{rel}}(c_{{s,V}})$**")
    A("此相对标准不确定度的来源有两个：一是配制标准储备液使用的容量瓶允差引入的相对标准不确定度"
      " $u_{rel}(c_{s,V容})$，二是温度变化导致定容试剂体积膨胀引入的相对标准不确定度"
      " $u_{rel}(c_{s,Vt})$。")
    A("$$ u_{rel}(c_{s,V}) = \\sqrt{u_{rel}(c_{s,V容})^{2} + u_{rel}(c_{s,Vt})^{2}} $$")
    # 4.3.1.3.1 容量瓶允差
    A(f"**{sec}.3.1 容量瓶允差引入的相对不确定度 $u_{{rel}}(c_{{s,V容}})$**")
    A(f"根据JJG 196-2006《常用玻璃量器》规定，20℃时{fv}mL单标线容量瓶（A级，V={fv}mL）的允差"
      f"d=±{g(tol_f)}mL，按三角分布（k=√6），则{fv}mL容量瓶体积引入的相对不确定度为：")
    A("$$ u_{rel}(c_{s,V容}) = \\frac{d}{k \\cdot V} = \\frac{" + g(tol_f)
      + "}{\\sqrt{6} \\times " + g(fv) + "} = " + _f(v_ml) + " $$")
    # 4.3.1.3.2 温度 (α·Δτ/√3; V 抵消, 式中仍写 V 体现量纲)
    A(f"**{sec}.3.2 温度变化引入的相对不确定度 $u_{{rel}}(c_{{s,Vt}})$**")
    _sa = _sample_effective_alpha(method, r)
    if _sa is not None and math.isclose(_sa, alpha_s, rel_tol=1e-9):
        # 温度项与样液定容(4.2.2)一致: 只引用 + 取值, 不重复 α·Δτ/√3 推导
        A(f"假定实验室的温度变化在（{env_temp:g}±{dtau:g}）℃（∆τ={dtau:g}），温度变化为均匀分布。"
          f"本步定容试剂与样液定容一致，温度变化引入的相对不确定度的评定详见 4.2.2（样液定容温度项），"
          f"$u_{{rel}}(c_{{s,Vt}})={_f(v_t)}$。")
    else:
        if reags:
            _alab = lambda x: x.get("name") or f"{x['volume']:g}mL试剂"
            _alpha_list = "、".join(f"{_alab(x)} α={_sci_t(x['alpha'])}/℃" for x in reags)
            blend_terms = " + ".join(f"{g(x['volume'])}\\times{_sci_l(x['alpha'])}" for x in reags)
            A(f"假定实验室的温度变化在（{env_temp:g}±{dtau:g}）℃（∆τ={dtau:g}），温度变化为均匀分布。"
              f"各试剂的体积膨胀系数：{_alpha_list}。混合试剂由各试剂按体积混合，其膨胀系数 α 为各试剂 αi 按体积加权：")
            A("$$ \\alpha = \\frac{" + blend_terms + "}{" + g(sum(x["volume"] for x in reags))
              + "} = " + _sci_l(alpha_s) + "/℃ $$")
            A("按均匀分布，k=√3，则温度变化引入的相对不确定度为：")
        else:
            sol_w = solvent if solvent else "定容试剂"
            A(f"假定实验室的温度变化在（{env_temp:g}±{dtau:g}）℃（∆τ={dtau:g}），温度变化为均匀分布。"
              f"{sol_w}膨胀系数α为{_sci_t(alpha_s)}/℃，按均匀分布，k=√3，则温度变化引入的相对不确定度为：")
        A("$$ u_{rel}(c_{s,Vt}) = \\frac{\\alpha \\cdot \\Delta\\tau \\cdot V}{\\sqrt{3} \\cdot V}"
          " = \\frac{" + _sci_l(alpha_s) + " \\times " + g(dtau) + " \\times " + g(fv)
          + "}{\\sqrt{3} \\times " + g(fv) + "} = " + _f(v_t) + " $$")
    A("则标准品配制储备液定容体积产生的不确定度：")
    A("$$ u_{rel}(c_{s,V}) = \\sqrt{u_{rel}(c_{s,V容})^{2} + u_{rel}(c_{s,Vt})^{2}}"
      " = \\sqrt{" + _f(v_ml) + "^{2} + " + _f(v_t) + "^{2}} = " + _f(u_sv) + " $$")
    A("故配制标准储备液引入的相对不确定度：")
    A("$$ u_{rel}(C_{stock}) = \\sqrt{u_{rel}(c_{s,p})^{2} + u_{rel}(c_{s,m})^{2}"
      " + u_{rel}(c_{s,V})^{2}} = \\sqrt{" + _f(u_p) + "^{2} + " + _f(u_sm) + "^{2} + "
      + _f(u_sv) + "^{2}} = " + _f(r["u_stock"]) + " $$")
    return L


def _stock_liquid_dilute_detail(method, r, analyte, sec="4.3.1"):
    """4.3.1 储备液(高浓液标·移取+定容)明细 = √(证书浓度² + 移取浓标² + 定容²), 返回行列表.
    与纯品称量对称(纯度→证书浓度, 称量→移取浓标, 定容同)。移取浓标=吸量管允差+温度(浓标α, 不含容量瓶);
    定容=容量瓶允差(√6)+定容试剂温度(单一α/混合blend α)。证书浓度按 cert_mode 分相对/绝对式。
    数值由 method+r 重算, r['u_stock'] 供末式对账。"""
    g = lambda x: f"{x:g}"
    sq = math.sqrt
    env_temp = method.get("env_temp", 20.0)
    dtau = r.get("dtau", 5.0)
    alpha_conc = method.get("alpha", 1.19e-3)            # 浓标膨胀 α (移取浓标温度项, 与引擎同源)
    kc = int(method["k_cert"])
    cert_mode = method.get("cert_mode", "relative")
    Urel = method.get("Urel_cert", 0.0)
    pk = method["pip_kind"]
    pv = float(method["pip_vol"])                          # 实际移取体积 (允差项除数)
    pnom = method.get("pip_nominal", pv)                   # 量器规格 (查允差; 满刻度时=pv); pip_p=校准点(可为分数 mL)
    if pk != "pip_p":
        pnom = int(pnom)
    fv = int(method["stock_flask_volume"])
    tol_p = vessel_tol(pk, pv, pnom)                       # 移取浓标吸量管允差 (pip_p=PIPETTE_TOL[校准点]·pv)
    k_pip = sq(3) if pk in _GRADUATED else sq(6)            # 分度吸量管/量筒 √3 / 单标吸量管 √6
    ksym_p = "\\sqrt{3}" if pk in _GRADUATED else "\\sqrt{6}"
    dist_p = "均匀分布（k=√3）" if pk in _GRADUATED else "三角分布（k=√6）"
    tol_f = GLASS_TOLERANCE[("flask", fv)]
    reags = method.get("stock_reagents")
    if reags:
        alpha_s = sum(x["volume"] * x["alpha"] for x in reags) / sum(x["volume"] for x in reags)
        solvent = ""
    else:
        alpha_s = method.get("stock_alpha", alpha_conc)
        solvent = method.get("stock_solvent", "")
    if cert_mode == "absolute":
        C_cert = method["C_cert"]; U_abs = method["U_abs"]
        u_cert = U_abs / (kc * C_cert)                      # 证书浓度 (绝对式: U/(k·C))
    else:
        u_cert = Urel / (kc * 100.0)                        # 证书浓度 (相对式: Urel/(k·100))
    p_ml = tol_p / (k_pip * pv)                           # 移取浓标 允差
    p_t = alpha_conc * dtau / sq(3)                       # 移取浓标 温度 (浓标α)
    u_pip = sq(p_ml ** 2 + p_t ** 2)                      # 移取浓标 合成
    v_ml = tol_f / (sq(6) * fv)                           # 定容 容量瓶允差
    v_t = alpha_s * dtau / sq(3)                          # 定容 温度 (定容试剂α)
    u_sv = sq(v_ml ** 2 + v_t ** 2)                       # 定容 合成
    L = []
    A = L.append
    A(f"{analyte}储备液由高浓液标准确移取后定容制得，因此其不确定度主要有三个来源：标准品证书浓度"
      f"产生的不确定度 $u_{{rel}}(c_{{s,c}})$，移取浓标体积产生的不确定度 $u_{{rel}}(c_{{s,p}})$，"
      f"定容体积产生的不确定度 $u_{{rel}}(c_{{s,V}})$。")
    A("$$ u_{rel}(C_{stock}) = \\sqrt{u_{rel}(c_{s,c})^{2} + u_{rel}(c_{s,p})^{2}"
      " + u_{rel}(c_{s,V})^{2}} $$")
    A(f"储备液的配置流程：准确用{g(pnom)}mL{KIND_CN[pk]}移取{g(pv)}mL浓标于{fv}mL容量瓶中，"
      + (f"用{solvent}定容。" if solvent else "定容。"))
    # 4.3.1.1 证书浓度
    A(f"**{sec}.1 标准品证书浓度产生的不确定度 $u_{{rel}}(c_{{s,c}})$**")
    if cert_mode == "absolute":
        A(f"标准品证书给出标称浓度 $c_{{cert}}$={g(C_cert)}mg/L，扩展不确定度 $U$={g(U_abs)}mg/L"
          f"（包含因子 k={kc}），换算为相对标准不确定度：")
        A("$$ u_{rel}(c_{s,c}) = \\frac{U}{k \\cdot c_{cert}} = \\frac{" + g(U_abs)
          + "}{" + str(kc) + " \\times " + g(C_cert) + "} = " + _f(u_cert) + " $$")
    else:
        A(f"标准品证书给出相对扩展不确定度 $U_{{rel}}$={g(Urel)}%（包含因子 k={kc}），"
          f"换算为相对标准不确定度：")
        A("$$ u_{rel}(c_{s,c}) = \\frac{U_{rel}}{k \\times 100} = \\frac{" + g(Urel)
          + "}{" + str(kc) + " \\times 100} = " + _f(u_cert) + " $$")
    # 4.3.1.2 移取浓标 (吸量管允差 + 温度; 仅吸量管, 不含容量瓶)
    A(f"**{sec}.2 移取浓标体积产生的不确定度 $u_{{rel}}(c_{{s,p}})$**")
    A("此相对标准不确定度的来源有两个：一是移取浓标所用吸量管允差引入的相对标准不确定度"
      " $u_{rel}(c_{s,p,容})$，二是温度变化引入的相对标准不确定度 $u_{rel}(c_{s,p,\\tau})$。")
    A("$$ u_{rel}(c_{s,p}) = \\sqrt{u_{rel}(c_{s,p,容})^{2} + u_{rel}(c_{s,p,\\tau})^{2}} $$")
    _partial = "" if pnom == pv else f"（量器规格{g(pnom)}mL，实际移取{g(pv)}mL）"
    A(f"根据JJG 196-2006《常用玻璃量器》规定，20℃时{g(pnom)}mL{KIND_CN[pk]}（A级）的允差"
      f"d=±{g(tol_p)}mL，按{dist_p}，则移取浓标体积引入的相对不确定度{_partial}为：")
    A("$$ u_{rel}(c_{s,p,容}) = \\frac{d}{k \\cdot V} = \\frac{" + g(tol_p) + "}{" + ksym_p
      + " \\times " + g(pv) + "} = " + _f(p_ml) + " $$")
    A(f"假定实验室的温度变化在（{env_temp:g}±{dtau:g}）℃（∆τ={dtau:g}），温度变化为均匀分布。"
      f"浓标溶液的体积膨胀系数α为{_sci_t(alpha_conc)}/℃，按均匀分布，k=√3，则温度变化引入的相对不确定度为：")
    A("$$ u_{rel}(c_{s,p,\\tau}) = \\frac{\\alpha \\cdot \\Delta\\tau \\cdot V}{\\sqrt{3} \\cdot V}"
      " = \\frac{" + _sci_l(alpha_conc) + " \\times " + g(dtau) + " \\times " + g(pv)
      + "}{\\sqrt{3} \\times " + g(pv) + "} = " + _f(p_t) + " $$")
    A("则移取浓标体积产生的不确定度：")
    A("$$ u_{rel}(c_{s,p}) = \\sqrt{u_{rel}(c_{s,p,容})^{2} + u_{rel}(c_{s,p,\\tau})^{2}}"
      " = \\sqrt{" + _f(p_ml) + "^{2} + " + _f(p_t) + "^{2}} = " + _f(u_pip) + " $$")
    # 4.3.1.3 定容 (容量瓶允差 + 定容试剂温度) — 复用纯品称量 4.3.1.3 写法
    A(f"**{sec}.3 定容体积产生的不确定度 $u_{{rel}}(c_{{s,V}})$**")
    A("此相对标准不确定度的来源有两个：一是配制标准储备液使用的容量瓶允差引入的相对标准不确定度"
      " $u_{rel}(c_{s,V容})$，二是温度变化导致定容试剂体积膨胀引入的相对标准不确定度"
      " $u_{rel}(c_{s,Vt})$。")
    A("$$ u_{rel}(c_{s,V}) = \\sqrt{u_{rel}(c_{s,V容})^{2} + u_{rel}(c_{s,Vt})^{2}} $$")
    A(f"**{sec}.3.1 容量瓶允差引入的相对不确定度 $u_{{rel}}(c_{{s,V容}})$**")
    A(f"根据JJG 196-2006《常用玻璃量器》规定，20℃时{fv}mL单标线容量瓶（A级，V={fv}mL）的允差"
      f"d=±{g(tol_f)}mL，按三角分布（k=√6），则{fv}mL容量瓶体积引入的相对不确定度为：")
    A("$$ u_{rel}(c_{s,V容}) = \\frac{d}{k \\cdot V} = \\frac{" + g(tol_f)
      + "}{\\sqrt{6} \\times " + g(fv) + "} = " + _f(v_ml) + " $$")
    A(f"**{sec}.3.2 温度变化引入的相对不确定度 $u_{{rel}}(c_{{s,Vt}})$**")
    _sa = _sample_effective_alpha(method, r)
    if _sa is not None and math.isclose(_sa, alpha_s, rel_tol=1e-9):
        # 温度项与样液定容(4.2.2)一致: 只引用 + 取值, 不重复 α·Δτ/√3 推导
        A(f"假定实验室的温度变化在（{env_temp:g}±{dtau:g}）℃（∆τ={dtau:g}），温度变化为均匀分布。"
          f"本步定容试剂与样液定容一致，温度变化引入的相对不确定度的评定详见 4.2.2（样液定容温度项），"
          f"$u_{{rel}}(c_{{s,Vt}})={_f(v_t)}$。")
    else:
        if reags:
            _alab = lambda x: x.get("name") or f"{x['volume']:g}mL试剂"
            _alpha_list = "、".join(f"{_alab(x)} α={_sci_t(x['alpha'])}/℃" for x in reags)
            blend_terms = " + ".join(f"{g(x['volume'])}\\times{_sci_l(x['alpha'])}" for x in reags)
            A(f"假定实验室的温度变化在（{env_temp:g}±{dtau:g}）℃（∆τ={dtau:g}），温度变化为均匀分布。"
              f"各试剂的体积膨胀系数：{_alpha_list}。混合试剂由各试剂按体积混合，其膨胀系数 α 为各试剂 αi 按体积加权：")
            A("$$ \\alpha = \\frac{" + blend_terms + "}{" + g(sum(x["volume"] for x in reags))
              + "} = " + _sci_l(alpha_s) + "/℃ $$")
            A("按均匀分布，k=√3，则温度变化引入的相对不确定度为：")
        else:
            sol_w = solvent if solvent else "定容试剂"
            A(f"假定实验室的温度变化在（{env_temp:g}±{dtau:g}）℃（∆τ={dtau:g}），温度变化为均匀分布。"
              f"{sol_w}膨胀系数α为{_sci_t(alpha_s)}/℃，按均匀分布，k=√3，则温度变化引入的相对不确定度为：")
        A("$$ u_{rel}(c_{s,Vt}) = \\frac{\\alpha \\cdot \\Delta\\tau \\cdot V}{\\sqrt{3} \\cdot V}"
          " = \\frac{" + _sci_l(alpha_s) + " \\times " + g(dtau) + " \\times " + g(fv)
          + "}{\\sqrt{3} \\times " + g(fv) + "} = " + _f(v_t) + " $$")
    A("则定容体积产生的不确定度：")
    A("$$ u_{rel}(c_{s,V}) = \\sqrt{u_{rel}(c_{s,V容})^{2} + u_{rel}(c_{s,Vt})^{2}}"
      " = \\sqrt{" + _f(v_ml) + "^{2} + " + _f(v_t) + "^{2}} = " + _f(u_sv) + " $$")
    A("故配制标准储备液引入的相对不确定度：")
    A("$$ u_{rel}(C_{stock}) = \\sqrt{u_{rel}(c_{s,c})^{2} + u_{rel}(c_{s,p})^{2}"
      " + u_{rel}(c_{s,V})^{2}} = \\sqrt{" + _f(u_cert) + "^{2} + " + _f(u_pip) + "^{2} + "
      + _f(u_sv) + "^{2}} = " + _f(r["u_stock"]) + " $$")
    return L


# 结果单位相对基准 (C·V/m ⇒ mg/kg) 的换算因子 = 10 的幂 (仅 display 层; 引擎无量纲不依赖)
_UNIT_EXP = {"mg/kg": 0, "µg/kg": 3, "g/kg": -3, "%": -4}


def _model_latex(unit):
    """测量模型 LaTeX: 基准 w=C·V/m; 非基准单位附 ×10^n 换算因子 (g/kg→×10⁻³ 等)。"""
    base = r"w = \frac{C \cdot V}{m}"
    e = _UNIT_EXP.get(unit, 0)
    return base if e == 0 else base + rf" \times 10^{{{e}}}"


def _prep_influences(prep_flow):
    """4.5 重复性影响量列表: 从前处理流程文本按关键词识别 + 通用项, 「、」分隔。
    空流程 → 范本默认(水浴法, MUP-CG-248); 否则 水浴/超声/振摇 命中即加, 末尾恒加 制样均匀性·进样误差。"""
    pf = prep_flow or ""
    if not pf.strip():
        return "水浴温度、恒温时间、制样的均匀性、进样误差"
    items = []
    if "水浴" in pf:
        items += ["水浴温度", "恒温时间"]
    if "超声" in pf:
        items += ["超声时间"]
    if any(k in pf for k in ("振摇", "振荡", "摇床")):
        items += ["振摇时间"]
    items += ["制样的均匀性", "进样误差"]
    return "、".join(items)


def _influences_text(method):
    """4.5 影响量串: 优先用 AI 识别的 method['influences'](list 或「、」串), 空则按关键词兜底。
    baseline/旧草稿无该键 → 走 _prep_influences → 输出与改动前完全一致。"""
    raw = method.get("influences") if isinstance(method, dict) else None
    infs = []
    if isinstance(raw, list):
        infs = [str(s).strip() for s in raw if str(s).strip()]
    elif raw:
        infs = [s.strip() for s in str(raw).replace("，", "、").replace(",", "、").split("、") if s.strip()]
    return "、".join(infs) if infs else _prep_influences(method.get("prep_flow", "") if isinstance(method, dict) else "")


def _sec4_1_weighing(method, r):
    """4.1 样品称量导致的相对不确定度 (方法级共享)。render/render_multi 共用, 返回行列表。"""
    g = lambda x: f"{x:g}"
    sq = math.sqrt
    n_w = int(method.get("n_weighings", 2))
    d = method["balance_tol"]; m_s = method["m_sample"]
    bid = method.get("balance_id", "")
    u_m_abs = sq(n_w) * d / sq(3)                       # u(m) 绝对 (g)
    m_d = f"{m_s:.2f}"                                  # 称样量显示 (2位小数, 对齐模板 "1.00g")
    L = []; A = L.append
    A("**4.1 样品称量导致的相对不确定度 $u_{rel}(m)$**")
    bid_c = f"称量使用{bid}的电子分析天平，" if bid else "称量使用电子分析天平，"
    A(f"本实验称样量为{m_d}g，{bid_c}其示值允差为±{g(d * 1000)}mg，"
      f"按均匀分布，k=√3，由于称量时有去皮和称量两次操作，分量应计算两次，"
      f"则样品称量引入的标准不确定度为：")
    A("$$ u(m) = \\frac{\\sqrt{" + str(n_w) + "} \\times " + g(d)
      + "\\,\\mathrm{g}}{\\sqrt{3}} = " + _f(u_m_abs) + "\\,\\mathrm{g} $$")
    A("则样品称量引入的相对标准不确定度为：")
    A("$$ u_{rel}(m) = \\frac{u(m)}{m} = \\frac{" + _f(u_m_abs)
      + "}{" + m_d + "} = " + _f(r["u_m"]) + " $$")
    return L


def _sec4_2_volume(method, r):
    """4.2 样液体积导致的相对不确定度 (方法级共享, makeup_mode 三分支)。render/render_multi 共用。"""
    g = lambda x: f"{x:g}"
    sq = math.sqrt
    env_temp = method.get("env_temp", 20.0)
    dtau = r.get("dtau", 5.0)
    L = []; A = L.append
    # 允差按量器类型分流: 容量瓶/单标线→三角√6, 分度吸量管→均匀√3
    mm = method.get("makeup_mode", "single")
    if mm == "mixed":
        # 混合试剂: 单一量器(种类+规格V) + 混合溶剂; blend α=Σ(Vi·αi)/ΣVi; 套单器皿公式
        md = r["makeup_detail"]; per = md["per"]
        V = md["V"]; blend_alpha = md["blend_alpha"]
        vk = method["vessel_kind"]; vv = method["vessel_volume"]
        tol = vessel_tol(vk, vv)
        kind_cn = KIND_CN.get(vk, vk)
        is_grad = (vk in _GRADUATED)
        k_ml = sq(3) if is_grad else sq(6)
        dist = "均匀分布(√3)" if is_grad else "三角分布(√6)"
        sqrtk = "\\sqrt{3}" if is_grad else "\\sqrt{6}"
        v_ml = tol / (k_ml * V); v_t = blend_alpha * dtau / sq(3)
        parts = " + ".join(f"{p['volume']:g}mL{p.get('name', '')}" for p in per)
        A("**4.2 样液体积导致的相对不确定度 $u_{rel}(V)$**")
        A(f"根据1.5中的样品前处理流程，样品的定容方式为加入混合试剂（{parts}）定容，"
          f"因此定容使用的量器为{kind_cn}({V:g}mL)。需考虑{kind_cn}的允差和温度变化"
          f"导致定容试剂体积膨胀产生的不确定度。")
        A(f"**4.2.1 {kind_cn}允差引入的相对不确定度 $u_{{rel}}(V_容)$**")
        A(f"根据JJG 196-2006《常用玻璃量器》规定，20℃时{V:g}mL{kind_cn}（A级）的允差"
          f"d=±{g(tol)}mL(按规格{V:g}mL查表)，按{dist}，则{kind_cn}体积引入的相对不确定度为：")
        A("$$ u_{rel}(V_容) = \\frac{d}{k \\cdot V} = \\frac{" + g(tol) + "}{"
          + sqrtk + " \\times " + g(V) + "} = " + _f(v_ml) + " $$")
        A("**4.2.2 温度变化引入的相对不确定度 $u_{rel}(V_τ)$**")
        blend_terms = " + ".join(f"{g(p['volume'])}\\times{_sci_l(p['alpha'])}" for p in per)
        _alab = lambda i, p: p.get("name") or f"{p['volume']:g}mL试剂"
        _alpha_list = "、".join(f"{_alab(i, p)} α={_sci_t(p['alpha'])}/℃" for i, p in enumerate(per))
        A(f"假定实验室的温度变化在（{env_temp:g}±{dtau:g}）℃（∆τ={dtau:g}），温度变化为均匀分布。"
          f"各试剂的体积膨胀系数：{_alpha_list}。"
          f"混合试剂由各试剂按体积混合，其膨胀系数 α 为各试剂 αi 按体积加权：")
        A("$$ \\alpha = \\frac{" + blend_terms + "}{" + g(sum(p["volume"] for p in per))
          + "} = " + _sci_l(blend_alpha) + "/℃ $$")
        A("按均匀分布，k=√3，则温度变化引入的相对不确定度为：")
        A("$$ u_{rel}(V_\\tau) = \\frac{\\alpha \\cdot \\Delta\\tau}{\\sqrt{3}}"
          " = \\frac{" + _sci_l(blend_alpha) + " \\times " + g(dtau) + "}{\\sqrt{3}} = "
          + _f(v_t) + " $$")
        A("所以样液体积引入的相对不确定度")
        A("$$ u_{rel}(V) = \\sqrt{u_{rel}(V_容)^{2} + u_{rel}(V_\\tau)^{2}}"
          " = \\sqrt{" + _f(v_ml) + "^{2} + " + _f(v_t) + "^{2}} = "
          + _f(r["u_v"]) + " $$")
    elif mm == "multi":
        # 多次定容: N 器皿分次加入同一瓶, V=ΣVi, 允差RSS(不同器皿), 温度RSS(分时独立)
        md = r["makeup_detail"]; per = md["per"]
        V = md["V"]; u_tol = md["u_tol"]; u_temp = md["u_temp"]; u_V = md["u_V"]
        reags = method.get("reagents", [])
        ksym = lambda p: "\\sqrt{3}" if p["kind"] in _GRADUATED else "\\sqrt{6}"
        parts = " + ".join(f"{p['volume']:g}mL{reags[i].get('name', '')}" for i, p in enumerate(per))
        A("**4.2 样液体积导致的相对不确定度 $u_{rel}(V)$**")
        A(f"根据1.5中的样品前处理流程，样品的定容方式为分次加入不同试剂（{parts}）定容，"
          f"定容体积 V=ΣVi={V:g}mL。需考虑各量器允差和温度变化导致试剂体积膨胀产生的不确定度。")
        A("**4.2.1 各量器允差引入的不确定度 $u(V_容)$**")
        def _vlab(p):
            nm = p.get("nominal", p["volume"]); kc = KIND_CN.get(p["kind"], p["kind"])
            return f"{nm:g}mL{kc}" if nm == p["volume"] else f"{nm:g}mL规格{kc}(实际移取{p['volume']:g}mL)"
        A("本次定容各次使用的量器及允差（均按A级查表）："
          + "、".join(f"{_vlab(p)}（允差 ±{g(p['tol'])}mL）" for p in per) + "。")
        _has_cyl = any(p["kind"] == "cylinder" for p in per)
        A("根据JJG 196-2006《常用玻璃量器》规定，各量器的允差按三角分布(√6)"
          f"（{'分度吸量管/量筒' if _has_cyl else '分度吸量管'}按均匀分布(√3)），不同量器互相独立，按方和根合成：")
        tol_sq = " + ".join(f"\\left(\\frac{{{g(p['tol'])}}}{{{ksym(p)}}}\\right)^{{2}}" for p in per)
        A("$$ u(V_容) = \\sqrt{" + tol_sq + "} = " + _f(u_tol) + "\\,\\mathrm{mL} $$")
        def _alab(i, p):
            nm = reags[i].get("name") if i < len(reags) else ""
            return nm or f"{p['volume']:g}mL{KIND_CN.get(p['kind'], p['kind'])}"
        _alpha_list = "、".join(f"{_alab(i, p)} α={_sci_t(p['alpha'])}/℃" for i, p in enumerate(per))
        A("**4.2.2 温度变化引入的不确定度 $u(V_τ)$**")
        A(f"假定实验室的温度变化在（{env_temp:g}±{dtau:g}）℃（∆τ={dtau:g}），温度变化为均匀分布，k=√3。"
          f"各试剂的体积膨胀系数：{_alpha_list}。各试剂温度引入的体积不确定度按 Vi·αi·∆τ/√3 计算"
          "（Vi 为各试剂体积），由于各试剂分次加入、温差独立，温度项按方和根合成：")
        term = lambda p: ("\\frac{" + g(p["volume"]) + "\\times" + _sci_l(p["alpha"])
                          + "\\times" + g(dtau) + "}{\\sqrt{3}}")
        A("$$ u(V_\\tau) = \\sqrt{" + " + ".join(f"\\left({term(p)}\\right)^{{2}}" for p in per)
          + "} = " + _f(u_temp) + "\\,\\mathrm{mL} $$")
        A("所以样液体积引入的相对不确定度")
        A("$$ u(V) = \\sqrt{u(V_容)^{2} + u(V_\\tau)^{2}} = \\sqrt{" + _f(u_tol)
          + "^{2} + " + _f(u_temp) + "^{2}} = " + _f(u_V) + "\\,\\mathrm{mL} $$")
        A("$$ u_{rel}(V) = \\frac{u(V)}{V} = \\frac{" + _f(u_V) + "}{" + g(V)
          + "} = " + _f(r["u_v"]) + " $$")
    else:
        vk = method["vessel_kind"]; vv = method["vessel_volume"]
        v_used = method.get("vessel_used_volume", vv)   # 实际定容体积 (满刻度默认=规格)
        tol = method.get("vessel_tol")
        if tol is None:
            tol = vessel_tol(vk, vv)              # 允差按量器规格查 JJG 196 (无手填允差时查表)
        alpha = r.get("alpha", 1.19e-3)
        solvent = method.get("makeup_solvent", "")
        kind_cn = KIND_CN.get(vk, vk)
        is_grad = (vk in _GRADUATED)
        k_ml = sq(3) if is_grad else sq(6)
        dist = "均匀分布(√3)" if is_grad else "三角分布(√6)"
        sqrtk = "\\sqrt{3}" if is_grad else "\\sqrt{6}"
        v_ml = tol / (k_ml * v_used); v_t = alpha * dtau / sq(3)
        spec = f"{g(vv)}mL" if v_used == vv else f"{g(vv)}mL规格/实际定容{v_used:g}mL"
        A("**4.2 样液体积导致的相对不确定度 $u_{rel}(V)$**")
        if solvent:
            A(f"根据1.5中的样品前处理流程，样品的定容方式为加入{v_used:g}mL{solvent}定容，"
              f"因此定容使用的量器为{kind_cn}({spec})。需考虑{kind_cn}的允差和温度变化"
              f"导致定容试剂体积膨胀产生的不确定度。")
        else:
            A(f"根据1.5中的样品前处理流程，定容使用的量器为{kind_cn}({spec})。"
              f"需考虑{kind_cn}的允差和温度变化导致定容试剂体积膨胀产生的不确定度。")
        A(f"**4.2.1 {kind_cn}允差引入的相对不确定度 $u_{{rel}}(V_容)$**")
        A(f"根据JJG 196-2006《常用玻璃量器》规定，20℃时{spec}{kind_cn}（A级）的允差"
          f"d=±{g(tol)}mL(按规格{g(vv)}mL查表)，按{dist}，则{kind_cn}体积引入的相对不确定度为：")
        A("$$ u_{rel}(V_容) = \\frac{d}{k \\cdot V} = \\frac{" + g(tol) + "}{"
          + sqrtk + " \\times " + g(v_used) + "} = " + _f(v_ml) + " $$")
        A("**4.2.2 温度变化引入的相对不确定度 $u_{rel}(V_τ)$**")
        solvent_w = solvent if solvent else "定容试剂"
        A(f"假定实验室的温度变化在（{env_temp:g}±{dtau:g}）℃（∆τ={dtau:g}），温度变化为均匀分布。"
          f"{solvent_w}膨胀系数α为{_sci_t(alpha)}/℃，按均匀分布，k=√3，"
          f"则温度变化引入的相对不确定度为：")
        A("$$ u_{rel}(V_\\tau) = \\frac{\\alpha \\cdot \\Delta\\tau \\cdot V}{k \\cdot V}"
          " = \\frac{" + _sci_l(alpha) + " \\times " + g(dtau) + " \\times " + g(v_used)
          + "}{\\sqrt{3} \\times " + g(v_used) + "} = " + _f(v_t) + " $$")
        A("所以样液体积引入的相对不确定度")
        A("$$ u_{rel}(V) = \\sqrt{u_{rel}(V_容)^{2} + u_{rel}(V_\\tau)^{2}}"
          " = \\sqrt{" + _f(v_ml) + "^{2} + " + _f(v_t) + "^{2}} = "
          + _f(r["u_v"]) + " $$")
    return L


def _sec1_overview(method, r, analyte_label, std_label=None):
    """§1 概述 (方法级共享)。analyte_label: 单目标物=目标物名, 多目标物='多种目标物'。
    std_label=None → method['std_name'] or analyte_label (单目标物行为); std_label='' → 略过标准品行。"""
    basis = method.get("basis", "（测量依据/标准号）")
    instrument = method.get("instrument", "（仪器）")
    matrix = method.get("matrix", "（基质）")
    env_temp = method.get("env_temp", 20.0)
    dtau = r.get("dtau", 5.0)
    L = []; A = L.append
    A("## 1 概述\n")
    A("### 1.1 测量依据")
    A(f"{basis}，采用 {instrument} 测定 {matrix} 中 {analyte_label} 的含量。")
    A("### 1.2 测量环境")
    A(f"温度：({env_temp:g}±{dtau:g})℃，湿度：≤75%RH。")
    A("### 1.3 测量设备与试剂")
    A(f"仪器：{instrument}")
    _std = (method.get("std_name") or analyte_label) if std_label is None else std_label
    if _std:
        A(f"标准品：{_std}")
    if method.get("makeup_solvent"):
        A(f"试剂：{method['makeup_solvent']}")
    A("### 1.4 测量对象")
    A(f"{matrix}中 {analyte_label} 的含量。")
    if method.get("prep_flow"):
        A("### 1.5 测定程序")
        A(method["prep_flow"])
    A("")
    return L


def _sec2_model(method, r, analyte_label):
    """§2 测量模型 (方法级共享)。"""
    matrix = method.get("matrix", "（基质）")
    unit = method.get("unit", "mg/kg")
    L = []; A = L.append
    A("## 2 测量模型\n")
    A(f"$$ {_model_latex(unit)} $$")
    A(f"式中：w—{matrix}中{analyte_label}含量({unit})；")
    A("　　　C—样液浓度(mg/L)；")
    A("　　　V—定容体积(mL)；")
    A("　　　m—称样量(g)。")
    A("从测量模型可看出，各影响参数相互独立，且由于数学模型是积和商的模型，合成标准不确定度可用相对标准不确定度进行合成。")
    A("")
    return L


def _sec3_sources():
    """§3 不确定度来源分析 (方法级共享, 含因果图占位)。"""
    L = []; A = L.append
    A("## 3 不确定度来源分析\n")
    A("!cause_effect!")  # 因果分析图 (复用模板 image3)
    for _k, _desc in [("m", "样品称量产生的相对不确定度"),
                      ("V", "样品定容产生的相对不确定度"),
                      ("C", "配制标准溶液的相对标准不确定度"),
                      ("Q", "曲线拟合产生的相对不确定度"),
                      ("f", "样品测量精密度产生的不确定度"),
                      ("R", "样品测量正确度（回收率）产生的不确定度")]:
        A(f"$u_{{rel}}({_k})$-------------{_desc}；")
    A("")
    return L


def render(method, r):
    """method: 描述方法的 dict; r: 引擎结果 dict (mup_cg248(...) 返回值)."""
    title = method.get("title", "（方法名称）")
    instrument = method.get("instrument", "（仪器）")
    analyte = method.get("analyte", "（目标物）")
    matrix = method.get("matrix", "（基质）")
    X = r["X"]
    U = r["U"]
    comps = r["components"]
    share = r["share"]
    rec = r["recovery"]
    fit = r["fit"]
    unit = method.get("unit", "mg/kg")

    # 占比按 *方差贡献* (正确 GUM 口径). 注: 范本表7用的是线性占比(非标准).
    g = lambda x: f"{x:g}"
    sq = math.sqrt
    lines = []
    A = lines.append
    _ntab = [0]
    def _tab():
        _ntab[0] += 1
        return _ntab[0]                       # 表序号: 按实际出现的表顺序 1,2,3...
    A(f"# {title}\n")
    lines.extend(_sec1_overview(method, r, analyte))
    lines.extend(_sec2_model(method, r, analyte))
    lines.extend(_sec3_sources())
    # ---- 4 分量评定 ----
    A("## 4 标准不确定度分量的评定\n")
    lines.extend(_sec4_1_weighing(method, r))
    lines.extend(_sec4_2_volume(method, r))
    # 4.3 标液
    A("**4.3 标准溶液配置的相对不确定度 $u_{rel}(C)$**")
    A("标准溶液的相对不确定度由标准储备液 $u_{rel}(C_{stock})$（见4.3.1）"
      "和工作液 $u_{rel}(C_{work})$（见4.3.2）引入的相对不确定度合成：")
    A("$$ u_{rel}(C) = \\sqrt{u_{rel}(C_{stock})^{2} + u_{rel}(C_{work})^{2}} $$")
    # 4.3.1 储备液
    A("**4.3.1 配制标准储备液引入的相对不确定度 $u_{rel}(C_{stock})$**")
    if r.get("stock_source", "solid") == "solid":
        lines.extend(_stock_solid_detail(method, r, analyte))
    elif r.get("stock_source") == "liquid_dilute":
        lines.extend(_stock_liquid_dilute_detail(method, r, analyte))
    else:   # 兜底: 合成值 + 来源措辞
        A(f"{analyte}储备液由高浓液标配置，$u_{{rel}}(C_{{stock}})={_f(r['u_stock'])}$"
          f"（{_stock_word(r)}）。")
    # 4.3.2 中间液及工作液稀释: 稀释流程表(描述性, 模板表1) → 量器明细表 + 合成式; 空(直填) → 单行合成值
    A("**4.3.2 中间液及工作液稀释引入的相对不确定度 $u_{rel}(C_{work})$**")
    if method.get("work_chain"):
        A("中间液及工作液由标准储备液经多级稀释制得，各级稀释的母液浓度、移取体积与量器、定容量器及目标浓度见下表：")
        nt_flow = _tab()
        A("")
        A(f"表{nt_flow} 中间液及工作液稀释流程\n")
        for _ln in _work_flow_rows(method):
            A(_ln)
        A("")
    wd = r.get("work_detail") or []
    if wd:
        A("每一稀释级的移取(吸量管)与定容(容量瓶)各引入体积不确定度，"
          "同器同体积多次使用者按使用次数 n 合成。考虑量器允差与温度变化(均匀分布√3)，"
          "各量器一次使用的相对不确定度如下表：")
        nt = _tab()
        A("")
        A(f"表{nt} 中间液及工作液稀释量器相对不确定度明细\n")
        A("| 量器 | 使用规格V/mL | 次数n | 允差d/mL | 包含因子k | $u_{rel}(V_容)$ | $u_{rel}(V_τ)$ | $u_{rel}(V)$ |")
        A("|---|---|---|---|---|---|---|---|")
        for d in wd:
            ksym = "\\sqrt{3}" if d["kind"] in _GRADUATED else "\\sqrt{6}"
            A(f"| {d['nominal']:g}mL{KIND_CN.get(d['kind'], d['kind'])} | {d['v_used']:.2f} | {d['n']} | "
              f"{d['tol']:g} | ${ksym}$ | {_f(d['urel_ml'])} | {_f(d['urel_t'])} | {_f(d['urel'])} |")
        A("")
        A("其中允差按量器类型取分布（容量瓶/单标线吸量管三角分布√6，分度吸量管均匀分布√3）；"
          f"温度项 $u_{{rel}}(V_\\tau)=\\alpha\\cdot\\Delta\\tau/\\sqrt{{3}}$，"
          f"中间液及工作液定容试剂膨胀系数 $\\alpha={_sci_l(r.get('work_alpha', r.get('alpha', 1.19e-3)))}$/℃；"
          "分度吸量管非满刻度使用时，允差按标称规格查表、体积按实际移取量计入；"
          "移液枪允差为移取体积的百分比、按≥V 的校准点取值，按均匀分布√3计入。"
          "单器一次使用 $u_{rel}(V)=\\sqrt{u_{rel}(V_容)^{2}+u_{rel}(V_\\tau)^{2}}$，"
          "多级稀释按方和根合成：")
        A("$$ u_{rel}(C_{work}) = \\sqrt{\\sum n_i \\cdot u_{rel}(V_i)^{2}} = " + _f(r["u_work"]) + " $$")
    else:
        A(f"$u_{{rel}}(C_{{work}})={_f(r['u_work'])}$（分析师给定/范本实测值）。")
    # 标液合成结论 (4.3.1 储备液 + 4.3.2 工作液 → u_rel(C))
    A("故标准溶液配置引入的相对不确定度：")
    A("$$ u_{rel}(C) = \\sqrt{u_{rel}(C_{stock})^{2} + u_{rel}(C_{work})^{2}}"
      " = \\sqrt{" + _f(r["u_stock"]) + "^{2} + " + _f(r["u_work"]) + "^{2}} = "
      + _f(r["u_c"]) + " $$")
    # 4.4 曲线 (对齐 Word 范本: 表标曲数据 + 方法学叙述 + u(Q)/u_rel(Q) 式 + 式中 + 拟合结果表)
    pts = method.get("points", [])
    n_pt = len(pts)
    include_origin = method.get("include_origin", False)
    force_origin = method.get("force_origin", False)
    # 含原点(0,0) → 拟合点数 n+1; 强制过原点 → 原点为锚不另加点, n=n_pt; 二者互斥(force 优先)
    n_fit = (n_pt + 1) if (include_origin and not force_origin) else n_pt
    origin_clause = "，并包含原点(0,0)共同拟合" if (include_origin and not force_origin) else ""
    force_clause = "，并强制过原点(0,0)（无截距）" if force_origin else ""
    is_is = method.get("curve_method") == "内标法"
    method_word = "内标法" if is_is else "外标法"
    x_word = "目标物与内标物浓度之比（浓度比）" if is_is else "目标物浓度（mg/L）"
    y_word = "分析物与内标峰面积之比（响应比）" if is_is else "峰面积"
    # 内标法: 叙述按浓度比模型, 但各点 c_IS 恒定→浓度比∝目标物浓度, 仍以 mg/L 代入, u_rel(Q) 等价
    is_clause = ("因各浓度点内标物浓度 c_IS 恒定，浓度比与目标物浓度成正比，"
                 "故以目标物浓度（mg/L）参与计算，u_rel(Q) 结果等价。") if is_is else ""
    p_meas = method.get("p", 1)
    A("**4.4 曲线拟合导致的相对不确定度 $u_{rel}(Q)$**")
    # 表: 目标物理论浓度与峰面积 (内标法: 目标物峰面积 + 内标峰面积 两行; 外标法: 峰面积 一行)
    if pts:
        nt = _tab()
        A("")
        A(f"表{nt} 目标物理论浓度与峰面积\n")
        A("| 项目 | 浓度 | " + " | ".join(f"X{i+1}" for i in range(n_pt)) + " |")
        A("|---|" + "---|" * (n_pt + 1))
        A(f"| {analyte} | X (mg/L) | " + " | ".join(g(x) for x, _ in pts) + " |")
        if is_is:
            a_areas = method.get("analyte_areas") or [yy for _, yy in pts]
            i_areas = method.get("is_areas") or []
            A(f"| {analyte} | 目标物峰面积 | " + " | ".join(g(v) for v in a_areas) + " |")
            A(f"| {analyte} | 内标峰面积 | " + " | ".join(g(v) for v in i_areas) + " |")
        else:
            A(f"| {analyte} | 峰面积 | " + " | ".join(g(y) for _, y in pts) + " |")
        A("")
    eq_str = "y = ax" if force_origin else "y = ax + b"
    A(f"本方法采用{method_word}定量，最小二乘法拟合出的标准曲线线性方程为 {eq_str}，"
      f"其中 x 为{x_word}，y 为{y_word}。{is_clause}拟合时选用 {n_pt} 个浓度点{origin_clause}{force_clause}"
      f"（n = {n_fit}），样品溶液平行测定 {p_meas} 次（p = {p_meas}），由标准曲线线性回归方程求得的样液平均质量浓度 "
      f"C₀ = {g(method['x_pred'])} mg/L。")
    # 式中各分量独占一行并对齐 (仿「2 测量模型」式中): 首行"式中："+变量, 续行3个全角空格
    # 缩进使变量字母与首行对齐 (每行各为独立段→同享 Normal 首行缩进2字符; 3全角空格 == "式中：" 3字宽)。
    # 行尾两空格=Markdown硬换行 (st.markdown预览换行; docx按行分段, 尾空格被 strip)。
    if force_origin:
        A("标准曲线各浓度点浓度的平方和 Sxx 与回归残差标准差 s 分别为：")
        A("$$ S_{xx} = \\sum_{i=1}^{n} x_i^{2} = " + g(fit["Sxx"]) + " $$")
        A("$$ s = \\sqrt{\\frac{\\sum_{i=1}^{n}(y_i-ax_i)^{2}}{n-1}} = "
          + format(fit["s"], ".4g") + " $$")
        A("则由最小二乘法拟合标准工作曲线所引入的标准不确定度为：")
        A("$$ u(Q) = \\frac{s}{a}\\sqrt{\\frac{1}{p}+\\frac{C_0^{2}}{S_{xx}}} = "
          + _f(fit["u"]) + " $$")
        A("")
        A("$$ u_{rel}(Q) = \\frac{u(Q)}{C_0} = " + _f(r["u_q"]) + " $$")
        A("  \n".join([
            "式中：a——标准曲线斜率；",
            "　　　s——回归残差标准差（自由度 n−1，过原点仅估斜率一个参数）；",
            "　　　n——标准曲线浓度点数；",
            "　　　p——样品溶液平行测定次数；",
            "　　　C₀——由标准曲线求得的样液平均质量浓度（mg/L）；",
            "　　　Sxx——各浓度点浓度的平方和（过原点回归，非离差平方和）。",
        ]))
    else:
        A("标准曲线各浓度点浓度的离差平方和 Sxx 与回归残差标准差 s 分别为：")
        A("$$ S_{xx} = \\sum_{i=1}^{n}(x_i-\\bar{x})^{2} = " + g(fit["Sxx"]) + " $$")
        A("$$ s = \\sqrt{\\frac{\\sum_{i=1}^{n}(y_i-(b+ax_i))^{2}}{n-2}} = "
          + format(fit["s"], ".4g") + " $$")
        A("则由最小二乘法拟合标准工作曲线所引入的标准不确定度为：")
        A("$$ u(Q) = \\frac{s}{a}\\sqrt{\\frac{1}{p}+\\frac{1}{n}+\\frac{(C_0-\\bar{x})^{2}}{S_{xx}}} = "
          + _f(fit["u"]) + " $$")
        A("")
        A("$$ u_{rel}(Q) = \\frac{u(Q)}{C_0} = " + _f(r["u_q"]) + " $$")
        A("  \n".join([
            "式中：a——标准曲线斜率；",
            "　　　b——截距；",
            "　　　s——回归残差标准差（自由度 n−2）；",
            "　　　n——标准曲线浓度点数；",
            "　　　p——样品溶液平行测定次数；",
            "　　　C₀——由标准曲线求得的样液平均质量浓度（mg/L）；",
            "　　　x̄——标准曲线各浓度点浓度的平均值；",
            "　　　Sxx——各浓度点浓度的离差平方和。",
        ]))
    # 表: 拟合曲线求引入的相对不确定度
    nt = _tab()
    A("")
    A(f"表{nt} 拟合曲线求引入的相对不确定度\n")
    A("| 目标物 | C₀ (mg/L) | x̄ | a (斜率) | b (截距) | u(Q) | u_rel(Q) |")
    A("|---|" + "---|" * 6)
    _xbar_cell = "—" if force_origin else f"{fit['xbar']:.4g}"
    _b_cell = "0" if force_origin else g(fit["b0"])
    A("| " + analyte + " | " + g(method["x_pred"]) + " | " + _xbar_cell
      + " | " + g(fit["b1"]) + " | " + _b_cell + " | "
      + _f(fit["u"]) + " | " + _f(r["u_q"]) + " |")
    # 4.5 重复性 (对齐 Word 范本: 影响量叙述(随前处理流程自动识别) + 重复性表(逐次测定值) + s/u/u_rel 文本式)
    rep = r["rep"]
    rep_vals = method.get("replicates_data") or []      # 逐次测定值 X 列表 (mg/kg); 无则只出汇总式
    n_rep = int(method.get("replicates", 0)) or len(rep_vals)
    A("**4.5 重复性测量引入的不确定度 $u_{rel}(f)$**")
    nt_rep = _tab() if rep_vals else None
    _rep_tail = f"测定结果见表{nt_rep}。" if nt_rep else "测定结果见下式。"
    A(f"{_influences_text(method)}等影响量对不确定度的影响是随机的，"
      f"且这些影响量很难一一加以评估，因此采用对{matrix}样品重复性测定{n_rep}次，"
      f"来替代这些影响量和操作过程带来的不确定度总和，{_rep_tail}")
    _wrm = method.get("round_mode", "有效数字")
    _wnd = int(method.get("round_nd", 3))
    if rep_vals:
        A(f"表{nt_rep} 试样重复性测定参数  (目标物测量结果 X，{unit})\n")
        A("| 化合物 | " + " | ".join(str(i + 1) for i in range(n_rep)) + " | x̄ | s | u | u_rel(f) |")
        A("|---|" + "---|" * (n_rep + 4))
        A("| " + analyte + " | " + " | ".join(fmt_result(v, _wrm, _wnd) for v in rep_vals)
          + f" | {fmt_result(rep['mean'], _wrm, _wnd)} | {rep['s']:#.4g} | {rep['u']:#.4g} | {_f(r['u_f'])} |")
    A("重复性标准偏差：$s=\\sqrt{\\frac{\\sum(x_i-\\bar{x})^2}{n-1}}=" + format(rep['s'], '#.4g') + "$")
    A("重复性标准不确定度：$u=\\frac{s}{\\sqrt{n}}=" + format(rep['u'], '#.4g') + "$")
    A("重复性相对不确定度：$u_{rel}(f)=\\frac{u}{\\bar{x}}=" + _f(r['u_f']) + "$")
    # 4.6 回收率 (对齐 Word 范本: 平行加标叙述 + 回收率表(逐次回收率%) + s/u/u_rel 文本式)
    rec = r["recovery"]
    rec_vals = method.get("recovery", []) or []        # 回收率分数列表; 无则只出汇总式
    n_rec = len(rec_vals)
    A("**4.6 样品加标回收率引入的不确定度 $u_{rel}(R)$**")
    c_std, v_add, w_add = (method.get("spike_std_conc"), method.get("spike_add_vol"), method.get("spike_add_mass"))
    # 加标体积 ≥1000 μL(超 3 位)时, Word 导出按 mL 显示
    if v_add and v_add >= 1000:
        _vol = f"{v_add / 1000:.2f}mL"
    elif v_add:
        _vol = f"{g(v_add)}μL"
    else:
        _vol = ""
    spike_clause = (f"均添加{g(c_std)}mg/L的标准溶液{_vol}，使加入的目标物含量为{fmt_result(w_add, _wrm, _wnd)}mg/kg，"
                    if all(v for v in (c_std, v_add, w_add)) else "")
    nt_rec = _tab() if rec_vals else None
    _rec_tail = f"结果见表{nt_rec}。" if nt_rec else "结果见下式。"
    A(f"对{matrix}样品做{n_rec}个平行加标（n={n_rec}），{spike_clause}经样品前处理，"
      f"测定目标物的加标回收率，{_rec_tail}")
    if rec_vals:
        A(f"表{nt_rec} 样品加标回收率检测结果  (回收率 R，%)\n")
        A("| 化合物 | " + " | ".join(str(i + 1) for i in range(n_rec)) + " | R̄ | s | u | u_rel(R) |")
        A("|---|" + "---|" * (n_rec + 4))
        A("| " + analyte + " | " + " | ".join(fmt_result(v * 100, "有效数字", 3) for v in rec_vals)
          + f" | {fmt_result(rec['mean'] * 100, '有效数字', 3)} | {rec['s'] * 100:#.4g} | {rec['u'] * 100:#.4g} | {_f(rec['urel'])} |")
    A("回收率标准偏差：$s=\\sqrt{\\frac{\\sum(R_i-\\bar{R})^2}{n-1}}=" + format(rec['s'] * 100, '#.4g') + "$（%）")
    A("回收率标准不确定度：$u=\\frac{s}{\\sqrt{n}}=" + format(rec['u'] * 100, '#.4g') + "$（%）")
    A("回收率相对不确定度：$u_{rel}(R)=\\frac{u}{\\bar{R}}=" + _f(rec['urel']) + "$")
    A("")
    # ---- 5 合成 (表先行 → 合成式 → 扩展式 → 计算结果) ----
    name_cn = {"m": "样品称量", "V": "样液定容", "C": "标液配制",
               "Q": "曲线拟合", "f": "重复性", "R": "回收率"}
    nt = _tab()
    w_disp, U_disp = _round_pair(X, U, method)           # U 向上修约至与 w 同小数位
    urel_pct = U / X * 100 if X else 0                    # U/w% (公式带数值代入显示原始 U)
    A("## 5 合成标准不确定度与扩展不确定度\n")
    A(f"表{nt} 不确定度分量汇总（方差贡献占比）\n")
    A("| 分量来源 | $u_{rel}$ | 方差贡献 % |")
    A("|---|---|---|")
    for k, v in comps.items():
        A(f"| {name_cn.get(k,k)} $u_{{rel}}({k})$ | {_f(v)} | {share[k]:.2f} |")
    A("")
    A("测量模型为积和商形式，各影响量相互独立，合成相对标准不确定度按各分量方差和的平方根合成：")
    A("$$ u_{rel}(W) = \\sqrt{u_{rel}(m)^{2}+u_{rel}(V)^{2}+u_{rel}(C)^{2}"
      "+u_{rel}(Q)^{2}+u_{rel}(f)^{2}+u_{rel}(R)^{2}} = "
      + _f(r["urel_w"]) + " $$")
    A(f"取包含因子 k=2（置信概率约 95%，按正态分布），扩展不确定度为：")
    A(f"$$ U = k \\cdot u_{{rel}}(W) \\cdot w = 2 \\times {_f(r['urel_w'])} \\times {w_disp} = {_f(U)}\\ {unit} $$")
    A("相对扩展不确定度为：")
    A(f"$$ U/w = {_f(U)}/{w_disp} = {urel_pct:#.3g}% $$")
    A(f"**计算结果**：{analyte} w = ({w_disp} ± {U_disp}) {unit}，k=2。")
    A("")
    # ---- 6 结论 (主要来源 + 可忽略分量) ----
    ranked = sorted(comps, key=lambda k: comps[k] ** 2, reverse=True)
    A("## 6 结论\n")
    # 主要来源取方差贡献前两位; 最小分量贡献<5% 才称"可忽略不计", 否则归为"其余较小"
    top = ranked[:2]
    _negl = (f"，而{name_cn[ranked[-1]]}产生的不确定度可忽略不计"
             if share[ranked[-1]] < 5.0 else "，其余各分量贡献相对较小")
    A(f"由此可见，采用{instrument}测定{matrix}中{analyte}含量的能力时，"
      f"其测量不确定度主要来源于{name_cn[top[0]]}和{name_cn[top[1]]}的测定{_negl}。")
    return "\n".join(lines)


# ---- 多目标物合并报告 -------------------------------------------------------

_NAME_CN = {"m": "样品称量", "V": "样液定容", "C": "标液配制",
            "Q": "曲线拟合", "f": "重复性", "R": "回收率"}


def _stock_method_for_analyte(method, grp, a):
    """多目标物: 为目标物 a (所属分组 grp) 合并出 _stock_solid_detail / _stock_liquid_dilute_detail
    所读的 method 视图 (方法级 + 分组共享 + 目标物级)。键名与 app._build_params /
    _compute_group_stock_solid 同源, 保证 helper 重算的分量与引擎 r['stock_detail'] 一致;
    helper 末式仍用传入的 r['u_stock'] 收口。液体移液/定容取 flasks[ding_group]
    (app 迁移后结构), 兼容扁平键 (legacy/demo 未迁移)。"""
    m = dict(method)
    if grp.get("kind") == "liquid":
        dg = a.get("ding_group") or "1"
        fl = (grp.get("flasks") or {}).get(dg) or \
            {k: grp.get(k) for k in ("pip_kind", "pip_vol", "pip_nominal", "flask_vol")}
        m.update({
            "k_cert": a.get("k_cert") or grp.get("k_cert"),
            "cert_mode": grp.get("cert_mode", "relative"),
            "Urel_cert": a.get("Urel_cert", 0.0),
            "C_cert": a.get("C_cert") or grp.get("C_cert"),
            "U_abs": a.get("U_abs") or grp.get("U_abs"),
            "pip_kind": fl.get("pip_kind"),
            "pip_vol": fl.get("pip_vol"),
            "pip_nominal": fl.get("pip_nominal"),
            "stock_flask_volume": fl.get("flask_vol"),
        })
    else:   # solid
        bal = grp.get("balance_tol_g")
        bal = method["balance_tol"] if bal in (None, "") else float(bal)
        _gm = grp.get("m_std_g")
        _m = a.get("m_std_g")
        _m = _gm if _m in (None, "") else _m
        m.update({
            "purity": a["purity"], "U_purity": a["U_purity"], "k_purity": a["k_purity"],
            "m_std": _m,
            "stock_balance_tol": bal,
            "stock_balance_id": method.get("stock_balance_id", method.get("balance_id", "")),
            "stock_n_weighings": grp.get("n_weighings", 2),
            "stock_flask_volume": int(grp["flask_volume_mL"]),
        })
    sa = grp.get("stock_alpha")
    if sa not in (None, ""):
        m["stock_alpha"] = float(sa)
    return m


def render_multi(method, groups, analytes, results):
    """多目标物报告: 章节结构与单目标物 render() 一致 (1-6 节), 各目标物差异用表格 (每物一行)。
    1/2/3/4.1/4.2 复用单目标物共享节 helper; 4.3 按分组 (储备液表 + 工作液量器明细表);
    4.4 曲线 / 4.5 重复性 / 4.6 回收率 / 5 合成 用各目标物汇总表; 6 结论。
    method: 方法级 dict; groups: 标准品分组; analytes: 各目标物参数; results: mup_cg248 结果列表 (一一对应)。"""
    title = method.get("title", "（方法名称）")
    matrix = method.get("matrix", "（基质）")
    r0 = results[0]
    unit = method.get("unit", "mg/kg")
    g = lambda x: f"{x:g}"
    _LABEL = method.get("analyte") or "多种目标物"
    lines = []
    A = lines.append
    _ntab = [0]
    def _tab():
        _ntab[0] += 1
        return _ntab[0]

    A(f"# {title}\n")
    lines.extend(_sec1_overview(method, r0, _LABEL, std_label=""))
    lines.extend(_sec2_model(method, r0, _LABEL))
    lines.extend(_sec3_sources())
    # ---- 4 分量评定 ----
    A("## 4 标准不确定度分量的评定\n")
    lines.extend(_sec4_1_weighing(method, r0))
    lines.extend(_sec4_2_volume(method, r0))
    # 4.3 标液 (合成 intro + 按分组: 4.3.x 储备液表 + 工作液量器明细表)
    A("**4.3 标准溶液配置的相对不确定度 $u_{rel}(C)$**")
    A("标准溶液的相对不确定度由标准储备液 $u_{rel}(C_{stock})$（见4.3.1）"
      "和工作液 $u_{rel}(C_{work})$（见4.3.2）引入的相对不确定度合成：")
    A("$$ u_{rel}(C) = \\sqrt{u_{rel}(C_{stock})^{2} + u_{rel}(C_{work})^{2}} $$")
    _n43 = [1]   # 4.3 子节连续编号: 每分组 储备液(N)/工作液(N+1) 顺延, 对齐单目标物 4.3.1储备/4.3.2工作
    for gi, grp in enumerate(groups):
        idxs = [i for i, a in enumerate(analytes) if a.get("group") == grp["name"]]
        if not idxs:
            continue
        _ns = _n43[0]; _n43[0] += 1   # 本分组 储备液 子节号
        kind = grp.get("kind", "solid")
        src_labels = ("纯度", "称量", "定容") if kind == "solid" else ("证书浓度", "移取浓标", "定容")
        vary = "纯度" if kind == "solid" else "证书浓度"
        # 4.3.{_ns} 储备液: 代表目标物逐分量叙述 (4.3.{_ns}.1/.2/.3/.3.1/.3.2, 复用单目标物 helper)
        #     + 各目标物逐物取值表 (纯度/证书浓度等差异项 + u_stock)。
        A(f"**4.3.{_ns} 「{grp['name']}」配制标准储备液引入的相对不确定度 $u_{{rel}}(C_{{stock}})$**")
        _ri = idxs[0]
        _mr = _stock_method_for_analyte(method, grp, analytes[_ri])
        if kind == "solid":
            lines.extend(_stock_solid_detail(_mr, results[_ri], analytes[_ri].get("name", ""), sec=f"4.3.{_ns}"))
        else:
            # 液体混标储备液为分组共享(同一标液), 叙述用分组(标液)名而非首目标物名
            lines.extend(_stock_liquid_dilute_detail(_mr, results[_ri], grp["name"], sec=f"4.3.{_ns}"))
        # 储备液逐物取值表: 各物全同(液体混标共享标液/证书一致)→ 一行汇总, 略去无差异逐物表
        _srows = []
        for i in idxs:
            sd = results[i].get("stock_detail") or []
            _vals = tuple(sd[j][1] if j < len(sd) else None for j in range(3))
            _srows.append((_vals, results[i].get("u_stock")))
        if len(set(_srows)) <= 1:
            A(f"本分组各目标物标准储备液配制一致，$u_{{rel}}(C_{{stock}})$ 均为 {_f(results[idxs[0]].get('u_stock'))}。")
        else:
            A(f"本分组各目标物按自身{vary}等分别取值，储备液相对不确定度见下表：")
            nt = _tab()
            A(f"表{nt} 「{grp['name']}」储备液相对不确定度\n")
            A(f"| 目标物 | $u_{{rel}}$({src_labels[0]}) | $u_{{rel}}$({src_labels[1]}) | $u_{{rel}}$({src_labels[2]}) | $u_{{rel}}(C_{{stock}})$ |")
            A("|---|---|---|---|---|")
            for i, (_vals, _ustock) in zip(idxs, _srows):
                cells = " | ".join(_f(v) if v is not None else "—" for v in _vals)
                A(f"| {analytes[i].get('name', '')} | {cells} | {_f(_ustock)} |")
            A("")
        # 4.3.x.2 中间液及工作液稀释 (稀释流程表 + 量器明细表 + 合成式)
        # u_work 逐目标物: 各物 u_work 全同(无中间液混合/legacy 单链)→ 沿用旧文(保 baseline); 否则出逐物表。
        _uws = [results[i].get("u_work") for i in idxs]
        _same = len(set(_uws)) <= 1
        rg = next((results[i] for i in idxs if results[i].get("work_detail")), results[idxs[0]])
        wd = rg.get("work_detail") or []
        _nw = _n43[0]; _n43[0] += 1   # 本分组 工作液 子节号
        A(f"**4.3.{_nw} 「{grp['name']}」中间液及工作液稀释引入的相对不确定度 $u_{{rel}}(C_{{work}})$**")
        # 稀释流程表 (描述性): 中间液(混合定容)+工作液(串行) 完整链, 置量器明细表前
        _a0 = analytes[idxs[0]]
        _unit = _a0.get("group") if kind == "liquid" else _a0.get("name")
        _flow = _work_flow_rows_multi(grp, _unit)
        if _flow:
            A("中间液及工作液由标准储备液经多级稀释制得，各级稀释的母液浓度、移取体积与量器、定容量器及目标浓度见下表：")
            nt = _tab()
            A(f"表{nt} 「{grp['name']}」中间液及工作液稀释流程\n")
            for _ln in _flow:
                A(_ln)
            A("")
        if wd:
            A("每一稀释级的移取(吸量管)与定容(容量瓶)各引入体积不确定度，"
              "同器同体积多次使用者按使用次数 n 合成。考虑量器允差与温度变化(均匀分布√3)，"
              "各量器一次使用的相对不确定度如下表：")
            nt = _tab()
            A(f"表{nt} 「{grp['name']}」中间液及工作液稀释量器相对不确定度明细\n")
            A("| 量器 | 使用规格V/mL | 次数n | 允差d/mL | 包含因子k | $u_{rel}(V_容)$ | $u_{rel}(V_τ)$ | $u_{rel}(V)$ |")
            A("|---|---|---|---|---|---|---|---|")
            for d in wd:
                ksym = "\\sqrt{3}" if d["kind"] in _GRADUATED else "\\sqrt{6}"
                A(f"| {d['nominal']:g}mL{KIND_CN.get(d['kind'], d['kind'])} | {d['v_used']:.2f} | {d['n']} | "
                  f"{d['tol']:g} | ${ksym}$ | {_f(d['urel_ml'])} | {_f(d['urel_t'])} | {_f(d['urel'])} |")
            A("")
            A("其中允差按量器类型取分布（容量瓶/单标线吸量管三角分布√6，分度吸量管均匀分布√3）；"
              f"温度项 $u_{{rel}}(V_\\tau)=\\alpha\\cdot\\Delta\\tau/\\sqrt{{3}}$，"
              f"工作液定容试剂膨胀系数 $\\alpha={_sci_l(rg.get('work_alpha', rg.get('alpha', 1.19e-3)))}$/℃；"
              "分度吸量管非满刻度使用时，允差按标称规格查表、体积按实际移取量计入；"
              "移液枪允差为移取体积的百分比、按≥V 的校准点取值，按均匀分布√3计入。"
              "单器一次使用 $u_{rel}(V)=\\sqrt{u_{rel}(V_容)^{2}+u_{rel}(V_\\tau)^{2}}$，"
              "多级稀释按方和根合成：")
            if _same:
                A(f"$$ u_{{rel}}(C_{{work}}) = \\sqrt{{\\sum n_i \\cdot u_{{rel}}(V_i)^{{2}}}} = {_f(rg['u_work'])} $$")
            else:
                A("$$ u_{rel}(C_{work}) = \\sqrt{\\sum n_i \\cdot u_{rel}(V_i)^{2}} $$")
                A("中间液各目标物移取体积不同，$u_{rel}(C_{work})$ 逐目标物取值：")
                nt = _tab()
                A(f"表{nt} 「{grp['name']}」各目标物工作液相对不确定度\n")
                A("| 目标物 | $u_{rel}(C_{work})$ |")
                A("|---|---|")
                for i in idxs:
                    A(f"| {analytes[i].get('name', '')} | {_f(results[i].get('u_work'))} |")
                A("")
        else:
            A(f"$u_{{rel}}(C_{{work}})={_f(rg['u_work'])}$（分析师给定/范本实测值）。")
        # u_rel(C) 全组同值(液标组: 共享证书+共享稀释链) → 直接出最终结果; 否则仍见第5节汇总表
        # (u_work 值上方 4.3.x.2 已给, 此处不重复)
        _ucs = [results[i].get("u_c") for i in idxs]
        _tail = (f"={_f(_ucs[0])}$。" if len(set(_ucs)) <= 1
                 else "$ 见第5节汇总表。")
        A("各目标物 $u_{rel}(C)=\\sqrt{u_{rel}(C_{stock})^{2}+u_{rel}(C_{work})^{2}}" + _tail)
        A("")
    # 4.4 曲线拟合 (方案B: 标曲表先行 → 方法学叙述+式中写一次 → 汇总表; 无逐物带数字行, 汇总表无定量方法列)
    A("**4.4 曲线拟合导致的相对不确定度 $u_{rel}(Q)$**")
    cm_set = {a.get("curve_method", "外标法") for a in analytes}
    has_is = "内标法" in cm_set
    method_word = ("外标法/内标法" if len(cm_set) > 1
                   else ("内标法" if cm_set == {"内标法"} else "外标法"))
    y_word = ("峰面积（内标法目标物为分析物与内标峰面积之比，即响应比）" if has_is else "峰面积")
    force_origin = method.get("force_origin", False)
    eq_str = "y = ax" if force_origin else "y = ax + b"
    # n/p 叙述值 (方法学写一次; 各物通常同设计→取首物; 含原点(非强制)→拟合点数 n_pt+1)
    include_origin = method.get("include_origin", False)
    _first = next((a for a in analytes if a.get("points")), None)
    n_pt = len(_first["points"]) if _first else 0
    n_fit = (n_pt + 1) if (include_origin and not force_origin) else n_pt
    p_meas = next((a.get("p") for a in analytes if a.get("p")), 1)
    # 各目标物标曲数据合并成一张表 (列数=最大点数; 不足补空; 首列物名由 _merge_first_col_repeats 跨2行合并)
    # 放方法学叙述前, 对齐单目标物范本 (表先行)
    _rows44 = [(a, r, a.get("points") or []) for a, r in zip(analytes, results)
               if r.get("fit") is not None and (a.get("points") or [])]
    if _rows44:
        _max_pt = max(len(p) for _, _, p in _rows44)
        nt = _tab()
        A(f"表{nt} 各目标物理论浓度与峰面积\n")
        A("| 项目 | 浓度 | " + " | ".join(f"X{i+1}" for i in range(_max_pt)) + " |")
        A("|---|" + "---|" * (_max_pt + 1))
        # 浓度: <0.10→3位小数, ≥0.10→2位小数; 峰面积/响应比: 不修约 (整数去.0, 小数原样)
        _xfmt = lambda v: f"{v:.3f}" if v < 0.10 else f"{v:.2f}"
        _yfmt = lambda v: str(int(v)) if float(v).is_integer() else str(v)
        for a, r, pts in _rows44:
            nm = a.get("name", "")
            ylab = "响应比" if a.get("curve_method") == "内标法" else "峰面积"
            A(f"| {nm} | X (mg/L) | " + " | ".join(_xfmt(x) for x, _ in pts) + " |")
            A(f"| {nm} | {ylab} | " + " | ".join(_yfmt(y) for _, y in pts) + " |")
        A("")
    # 方法学叙述 (写一次): 定义 x/y + 线性方程; Sxx/s/u(Q)/u_rel(Q) 各独占一显示行 (对齐单目标物范本,
    # 多目标物无逐物数值, 仅符号式)
    A(f"本方法采用{method_word}定量，最小二乘法拟合出的标准曲线线性方程为 {eq_str}，"
      f"其中 x 为目标物浓度（mg/L），y 为{y_word}"
      + ("，x̄ 为标准曲线各浓度点浓度的平均值" if not force_origin else "")
      + "。"
      + ("并强制过原点（无截距）。" if force_origin else "")
      + ("各浓度点均包含原点(0,0)共同拟合。" if method.get("include_origin") and not force_origin else "")
      + (f"拟合时选用 {n_pt} 个浓度点（n = {n_fit}），样品溶液平行测定 {p_meas} 次（p = {p_meas}）。" if n_pt else ""))
    if force_origin:
        A("标准曲线各浓度点浓度的平方和 Sxx 与回归残差标准差 s 分别为：")
        A("$$ S_{xx} = \\sum_{i=1}^{n} x_i^{2} $$")
        A("$$ s = \\sqrt{\\frac{\\sum_{i=1}^{n}(y_i-ax_i)^{2}}{n-1}} $$")
    else:
        A("标准曲线各浓度点浓度的离差平方和 Sxx 与回归残差标准差 s 分别为：")
        A("$$ S_{xx} = \\sum_{i=1}^{n}(x_i-\\bar{x})^{2} $$")
        A("$$ s = \\sqrt{\\frac{\\sum_{i=1}^{n}(y_i-(b+ax_i))^{2}}{n-2}} $$")
    A("则由最小二乘法拟合标准工作曲线所引入的标准不确定度为：")
    if force_origin:
        A("$$ u(Q) = \\frac{s}{a}\\sqrt{\\frac{1}{p}+\\frac{C_0^{2}}{S_{xx}}} $$")
    else:
        A("$$ u(Q) = \\frac{s}{a}\\sqrt{\\frac{1}{p}+\\frac{1}{n}+\\frac{(C_0-\\bar{x})^{2}}{S_{xx}}} $$")
    A("$$ u_{rel}(Q) = \\frac{u(Q)}{C_0} $$")
    # 式中 (写一次, 对齐单目标物范本「式中」段)
    if force_origin:
        A("  \n".join([
            "式中：a——标准曲线斜率；",
            "　　　s——回归残差标准差（自由度 n−1，过原点仅估斜率一个参数）；",
            "　　　n——标准曲线浓度点数；",
            "　　　p——样品溶液平行测定次数；",
            "　　　C₀——由标准曲线求得的样液平均质量浓度（mg/L）；",
            "　　　Sxx——各浓度点浓度的平方和（过原点回归，非离差平方和）。",
        ]))
    else:
        A("  \n".join([
            "式中：a——标准曲线斜率；",
            "　　　b——截距；",
            "　　　s——回归残差标准差（自由度 n−2）；",
            "　　　n——标准曲线浓度点数；",
            "　　　p——样品溶液平行测定次数；",
            "　　　C₀——由标准曲线求得的样液平均质量浓度（mg/L）；",
            "　　　x̄——标准曲线各浓度点浓度的平均值；",
            "　　　Sxx——各浓度点浓度的离差平方和。",
        ]))
    # 汇总表 (各目标物 C₀/a/b/u(Q)/u_rel(Q) 一表比对; 无定量方法列, 无 x̄ 列)
    # 格式: C₀ 小数2位(对齐Excel加标C列); a/b 统一科学计数法 .3e=4位有效数字(斜率跨3e3~2e7, 避免
    # _f 的 #.4g 在大小数间自动切科学/常规致混排, 如 5.816e+04 旁出现 -4805.)
    if any(rr.get("fit") is not None for rr in results):
        nt = _tab()
        A(f"表{nt} 各目标物曲线拟合相对不确定度\n")
        A("| 目标物 | C₀ (mg/L) | a (斜率) | b (截距) | u(Q) | $u_{rel}(Q)$ |")
        A("|---|---|---|---|---|---|")
        for a, r in zip(analytes, results):
            fit = r.get("fit")
            if fit is not None:
                _b = "0" if force_origin else f"{fit['b0']:.3e}"
                _c0 = f"{a.get('x_pred'):.2f}" if a.get("x_pred") is not None else "—"
                A(f"| {a.get('name', '')} | {_c0} | "
                  f"{fit['b1']:.3e} | {_b} | {_f(fit['u'])} | {_f(r.get('u_q'))} |")
            else:
                A(f"| {a.get('name', '')} | — | — | — | — | — |")
        A("")
    else:
        A("（未提供曲线数据，暂不评定。）")
    A("")
    # 4.5 重复性 (对齐单目标物: 影响量叙述(含n) + 逐次测定值表(1..n) + s/u/u_rel 文本式)
    A("**4.5 重复性测量引入的不确定度 $u_{rel}(f)$**")
    _has_rep = any(rr.get("rep") is not None for rr in results)
    _nt_rep = _tab() if _has_rep else None
    _rep_tail = f"，测定结果见表{_nt_rep}。" if _nt_rep else "。"
    # 同一批进样 → 各目标物重复性测定次数 n 统一, 写入叙述; 表逐次测定值列(1..n)
    _n_rep = next((len(a.get("replicates") or []) for a, rr in zip(analytes, results)
                   if rr.get("rep") is not None), 0)
    _n_clause = f"{_n_rep}次" if _n_rep else ""
    A(f"{_influences_text(method)}等影响量对不确定度的影响是随机的，"
      f"且这些影响量很难一一加以评估，因此采用对{matrix}样品重复性测定{_n_clause}，"
      f"来替代这些影响量和操作过程带来的不确定度总和{_rep_tail}")
    if _has_rep:
        _rmode = method.get("round_mode", "有效数字")
        _rnd = int(method.get("round_nd", 3))
        A(f"表{_nt_rep} 各目标物重复性测定相对不确定度  (测定结果 X，{unit})\n")
        A("| 目标物 | " + " | ".join(str(i + 1) for i in range(_n_rep))
          + " | x̄ | s | u | $u_{rel}(f)$ |")
        A("|---|" + "---|" * (_n_rep + 4))
        for a, r in zip(analytes, results):
            rep = r.get("rep")
            if rep is not None:
                _vals = " | ".join(fmt_result(v, _rmode, _rnd) for v in (a.get("replicates") or []))
                A(f"| {a.get('name', '')} | {_vals} | "
                  f"{fmt_result(rep['mean'], _rmode, _rnd)} | {rep['s']:#.4g} | {rep['u']:#.4g} | {_f(r.get('u_f'))} |")
            else:
                A(f"| {a.get('name', '')} | " + " | ".join("—" for _ in range(_n_rep))
                  + " | — | — | — | — |")
        A("")
        A("重复性标准偏差：$s=\\sqrt{\\frac{\\sum(x_i-\\bar{x})^2}{n-1}}$")
        A("重复性标准不确定度：$u=\\frac{s}{\\sqrt{n}}$")
        A("重复性相对不确定度：$u_{rel}(f)=\\frac{u}{\\bar{x}}$")
    else:
        A("（未提供重复性数据，暂不评定。）")
    A("")
    # 4.6 回收率 (对齐单目标物/Word 范本: 平行加标叙述 + 逐次回收率表(1..n列,每物一行) + 逐物 s/u/u_rel 带值式)
    A("**4.6 样品加标回收率引入的不确定度 $u_{rel}(R)$**")
    _has_rec = any(rr.get("recovery") is not None for rr in results)
    _nt_rec = _tab() if _has_rec else None
    _rec_tail = f"，结果见表{_nt_rec}。" if _nt_rec else "。"
    # 同一批加标 → 各目标物平行加标次数 n 统一; 表逐次回收率列(1..n)
    _n_rec = next((len(a.get("recovery") or []) for a, rr in zip(analytes, results)
                   if rr.get("recovery") is not None), 0)
    # 4.6 段落: 取首个有加标目标物的 标液浓度/加标体积/加入含量 (同一批加标各物一致), 对齐单目标物
    _sa = next((a for a in analytes if a.get("spike_std_conc")), None)
    c_std = _sa.get("spike_std_conc") if _sa else None
    v_add = _sa.get("spike_add_vol") if _sa else None
    w_add = _sa.get("spike_add_mass") if _sa else None
    if v_add and v_add >= 1000:
        _vol = f"{v_add / 1000:.2f}mL"
    elif v_add:
        _vol = f"{g(v_add)}μL"
    else:
        _vol = ""
    _wrm = method.get("round_mode", "有效数字")
    _wnd = int(method.get("round_nd", 3))
    _spike_clause = (f"均添加{g(c_std)}mg/L的标准溶液{_vol}，使加入的目标物含量为{fmt_result(w_add, _wrm, _wnd)}mg/kg，"
                     if all(v for v in (c_std, v_add, w_add)) else "")
    _n_clause = f"{_n_rec}个平行加标（n={_n_rec}）" if (_has_rec and _n_rec) else "平行加标"
    A(f"对{matrix}样品做{_n_clause}，{_spike_clause}经样品前处理，"
      f"测定各目标物的加标回收率{_rec_tail}")
    if _has_rec:
        A(f"表{_nt_rec} 各目标物加标回收率检测结果  (回收率 R，%)\n")
        A("| 目标物 | " + " | ".join(str(i + 1) for i in range(_n_rec))
          + " | R̄ | s | u | $u_{rel}(R)$ |")
        A("|---|" + "---|" * (_n_rec + 4))
        for a, r in zip(analytes, results):
            rec = r.get("recovery")
            if rec is not None:
                _vals = " | ".join(fmt_result(v * 100, "有效数字", 3) for v in (a.get("recovery") or []))
                A(f"| {a.get('name', '')} | {_vals} | "
                  f"{fmt_result(rec['mean'] * 100, '有效数字', 3)} | {rec['s'] * 100:#.4g} | {rec['u'] * 100:#.4g} | {_f(rec['urel'])} |")
            else:
                A(f"| {a.get('name', '')} | " + " | ".join("—" for _ in range(_n_rec))
                  + " | — | — | — | — |")
        A("")
        A("回收率标准偏差：$s=\\sqrt{\\frac{\\sum(R_i-\\bar{R})^2}{n-1}}$（%）")
        A("回收率标准不确定度：$u=\\frac{s}{\\sqrt{n}}$（%）")
        A("回收率相对不确定度：$u_{rel}(R)=\\frac{u}{\\bar{R}}$")
    else:
        A("（未提供回收率数据，暂不评定。）")
    A("")
    # 5 合成 (各目标物分量汇总表 + 合成式/扩展式写一次 + 结果行)
    A("## 5 合成标准不确定度与扩展不确定度\n")
    A("测量模型为积和商形式，各影响量相互独立，合成相对标准不确定度按各分量方差和的平方根合成：")
    A("$$ u_{rel}(W) = \\sqrt{u_{rel}(m)^{2}+u_{rel}(V)^{2}+u_{rel}(C)^{2}"
      "+u_{rel}(Q)^{2}+u_{rel}(f)^{2}+u_{rel}(R)^{2}} $$")
    # 样品称量、样液体积为方法级共享项, 各目标物相同, 不再单列为表列:
    _c0 = results[0]["components"] if results else {}
    A("取包含因子 k=2（置信概率约 95%，按正态分布），扩展不确定度 $U = k \\cdot u_{rel}(W) \\cdot w$。"
      f"样品称量、样液体积为方法共享项，各目标物相同："
      f"$u_{{rel}}(m)={_f(_c0.get('m'))}$、$u_{{rel}}(V)={_f(_c0.get('V'))}$。"
      f"各目标物分量贡献与结果见下表 (单位 {unit})：")
    nt = _tab()
    A(f"表{nt} 各目标物不确定度分量汇总与扩展不确定度\n")
    A("| 目标物 | $u_{rel}(C)$ | $u_{rel}(Q)$ | $u_{rel}(f)$ | $u_{rel}(R)$ | $u_{rel}(W)$ | w | U (k=2) | U/w (%) | 主导 |")
    A("|---|---|---|---|---|---|---|---|---|---|")
    for a, r in zip(analytes, results):
        comps = r["components"]
        cells = [_f(comps[k]) if k in comps else "—" for k in ("C", "Q", "f", "R")]
        dom = max(comps, key=lambda k: comps[k]) if comps else "—"
        x_str = _f(r["X"], 4) if r.get("X") is not None else "—"
        u_str = _f(r["U"], 4) if r.get("U") is not None else "—"
        urel_pct = f"{r['U'] / r['X'] * 100:#.3g}" if (r.get("U") and r.get("X")) else "—"
        A(f"| {a.get('name', '')} | " + " | ".join(cells) +
          f" | {_f(r['urel_w'])} | {x_str} | {u_str} | {urel_pct} | {dom} |")
    A("")
    for a, r in zip(analytes, results):
        if r.get("U") is not None:
            w_disp, U_disp = _round_pair(r["X"], r["U"], method)
            A(f"**{a.get('name', '')}**：w = ({w_disp} ± {U_disp}) {unit}，k=2。")
        else:
            A(f"**{a.get('name', '')}**：仅前处理侧 $u_{{rel}}(W)={_f(r['urel_w'])}$；测量数据待补，暂无最终结果。")
    A("")
    # 6 结论 (对齐全范例结构: 概述(依据+仪器) → 结果表示(k=2) → 主要来源(逐物值)/其次/其他较小)
    basis = method.get("basis", "（测量依据/标准号）")
    instrument = method.get("instrument", "（仪器）")
    A("## 6 结论\n")
    _grp = method.get("analyte") or ""
    _concl = [f"依据{basis}，采用{instrument}，对{matrix}中 {len(analytes)} 种{_grp}目标物进行测量不确定度评定。",
              f"取包含因子 k=2（约 95% 置信概率），结果以 (w±U) {unit} 给出，扩展不确定度见第5节汇总表。"]
    _done = [r for r in results if r.get("U") is not None]
    if _done:
        # 按平均方差贡献排序分量: 最大/其次/其他较小 (对齐全范例结论)
        _keys = sorted(set().union(*(r["share"] for r in _done)))
        _mean = {k: sum(r["share"].get(k, 0.0) for r in _done) / len(_done) for k in _keys}
        _ranked = sorted(_keys, key=lambda k: _mean[k], reverse=True)
        _top1, _top2 = _ranked[0], _ranked[1]
        # 主导分量逐物 urel: ≤5 种逐物列出(其中A为x，B为y), 否则给范围
        _pairs = [(a.get("name", ""), r["components"][_top1])
                  for a, r in zip(analytes, results)
                  if r.get("U") is not None and _top1 in r["components"]]
        _vals1 = sorted(v for _, v in _pairs)
        if len(_pairs) <= 5:
            _main_vals = "，其中" + "，".join(f"{nm}为{_f(v)}" for nm, v in _pairs)
        else:
            _main_vals = f"（各目标物为 {_f(_vals1[0])}~{_f(_vals1[-1])}）"
        # 次要分量平均相对不确定度(%)
        _top2_vals = [r["components"][_top2] for r in _done if _top2 in r["components"]]
        _top2_pct = (sum(_top2_vals) / len(_top2_vals) * 100) if _top2_vals else 0.0
        _concl.append(f"通过对影响测量不确定度的主要来源及因素分析可知：最大的影响因素是"
                      f"{_NAME_CN[_top1]}引入的相对标准不确定度{_main_vals}；其次为{_NAME_CN[_top2]}"
                      f"（约{_top2_pct:.1f}%）；其他影响因素引起的不确定度较小。")
    if len(_done) < len(results):
        _concl.append("**部分目标物尚未提供测量数据(曲线/重复性/回收率)，仅给出前处理侧相对不确定度；"
                      "测量数据补齐后再给出最终扩展不确定度。**")
    A("".join(_concl))
    return "\n".join(lines)


# 范例方法描述 (MUP-CG-248)
MUP_METHOD = {
    "title": "ISO 17234-2:2011 液相法测定皮革中4-氨基偶氮苯含量的不确定度评估",
    "basis": "ISO 17234-2:2011《皮革中4-氨基偶氮苯的含量测定》",
    "instrument": "高效液相色谱仪(HPLC-PDA)",
    "analyte": "4-氨基偶氮苯",
    "matrix": "皮革",
    "replicates": 7,
}


if __name__ == "__main__":
    result = mup_cg248()
    print(render(MUP_METHOD, result))