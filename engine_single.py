# -*- coding: utf-8 -*-
"""
单目标物: 草稿形状 state → mup_cg248 入参 params。

从 app.py single_form (1443-2034) 逐字抽出的纯函数版 (去 Streamlit / 去 pandas)。
前端只发草稿形状的原始 widget 值 (scalars + rows + editors), 参数装配留在后端 →
parity 由"同一段 Python 代码"结构性保证, 前端无需复刻易错的派生逻辑。

state 形状 (= 草稿 payload):
  { scalars: {<widget 键>: 值}, rows: {reag:[{s,k,v,vi,a}], blend:[{s,vi,a}], stock_blend:[{s,vi,a}]},
    editors: {work_df:[...], points_df:[...], spike_df:[...]} }
"""
import os
import sys
import math
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from uncertainty import (mup_cg248, GLASS_TOLERANCE, BASELINE_PARAMS, UNIT_EXP,  # noqa: E402
                         CONC_UNIT_EXP, balance_mpe_g, round_sf, round_dp)
import solvents  # noqa: E402

DEF = BASELINE_PARAMS
_MISSING = object()

# ---- 量器常量 (与 app.py:36-81 一致; 前端 /api/meta 也用) ----
KIND_LABELS = {"flask": "容量瓶(A)", "pip_s": "单标吸量管(A)", "pip_g": "分度吸量管(A)", "cylinder": "量筒（流出式）"}
VOLUMES = {
    "flask":    [1, 2, 5, 10, 25, 50, 100, 250, 500, 1000],
    "pip_s":    [1, 2, 5, 10, 25, 50],
    "pip_g":    [1, 2, 5, 10, 20],
    "cylinder": [10, 50, 100, 250, 500, 1000],
}
_USE_GRP = {"pip_s": 0, "pip_g": 1, "flask": 2}
_C_COL, _M_COL, _R_COL, _W_COL = "实测加标 C (mg/L)", "称样量 m (g)", "回收率 R", "测定值 w"


def _is_na(v):
    return v is None or v == "" or (isinstance(v, float) and v != v)


def _vol_label(kind, v):
    return f"{v} mL (±{GLASS_TOLERANCE[(kind, v)]:g})"


def _vsl_label(kind, v):
    return f"{v:g} mL {KIND_LABELS[kind]}(±{GLASS_TOLERANCE[(kind, v)]:g})"


def _vessel_opts(kinds):
    opts, rev = [], {}
    for k in kinds:
        for v in VOLUMES[k]:
            s = _vsl_label(k, v)
            opts.append(s)
            rev[s] = (k, v)
    return opts, rev


_PIP_OPTS, _PIP_REV = _vessel_opts(("pip_s", "pip_g"))
_FLASK_OPTS, _FLASK_REV = _vessel_opts(("flask",))


# ---- 稀释链 helper (逐字移植 app.py:129-235) ----
def _uses_from_ops(ops):
    agg = {}
    for role, label, vol in ops:
        if role == "flask":
            if label and label in _FLASK_REV:
                k, nom = _FLASK_REV[label]
                key = (k, nom, float(nom))
            else:
                continue
        else:
            if label and not _is_na(vol) and label in _PIP_REV:
                k, nom = _PIP_REV[label]
                key = (k, nom, float(vol))
            else:
                continue
        agg[key] = agg.get(key, 0) + 1
    uses = [(k, vused, n, GLASS_TOLERANCE[(k, nom)], nom) for (k, nom, vused), n in agg.items()]
    uses.sort(key=lambda u: (_USE_GRP[u[0]], u[4], u[1]))
    return uses


def _dilution_to_uses(rows):
    if not rows:
        return []
    ops = []
    for r in rows:
        ops.append(("pip", r.get("移取量器"), r.get("移取体积(mL)")))
        ops.append(("flask", r.get("定容量器"), None))
    return _uses_from_ops(ops)


def _dilution_chain(rows):
    out = []
    if not rows:
        return out
    for r in rows:
        mc, pv = r.get("母液浓度(mg/L)"), r.get("移取体积(mL)")
        pk, fk, tg = r.get("移取量器"), r.get("定容量器"), r.get("目标浓度(mg/L)")
        if _is_na(mc) and _is_na(pv) and _is_na(tg):
            continue
        pip = _PIP_REV[pk] if (pk and pk in _PIP_REV) else (None, None)
        fl = _FLASK_REV[fk][1] if (fk and fk in _FLASK_REV) else None
        out.append({"母液": "" if _is_na(mc) else str(mc),
                    "体积": None if _is_na(pv) else float(pv),
                    "pip_kind": pip[0], "pip_vol": pip[1], "flask_vol": fl,
                    "目标": "" if _is_na(tg) else str(tg)})
    return out


def _spike_pairs(rows):
    if not rows:
        return []
    out = []
    for r in rows:
        c, m = r.get(_C_COL), r.get(_M_COL)
        out.append((None if _is_na(c) else float(c), None if _is_na(m) else float(m)))
    return out


def _f(v):
    """JSON 值 → float; None/缺 → nan (对齐 pandas float(NaN))。"""
    return float(v) if not _is_na(v) else float("nan")


def _instrument_fa(instrument):
    """仪器名 → 方法名(法): 去括号注记, 去末尾 仪/计, 加 法。高效液相色谱仪→高效液相色谱法。"""
    if not instrument:
        return None
    s = str(instrument).strip()
    for lpar, rpar in (("（", "）"), ("(", ")")):   # 去 (HPLC-PDA) 等注记
        i = s.find(lpar)
        if i >= 0:
            j = s.find(rpar, i)
            s = (s[:i] + (s[j + 1:] if j > i else "")).strip()
    if s.endswith("仪") or s.endswith("计"):
        s = s[:-1]
    return (s + "法") if s else None


def _ensure_instr_in_title(title, instrument):
    """报告标题须含仪器(法): 已含则原样; 缺则把 仪器法 插到首个「测定」前; 无「测定」不插。"""
    if not title or not instrument:
        return title
    fa = _instrument_fa(instrument)
    if not fa:
        return title
    core = fa[:-1] if fa.endswith("法") else fa          # 仪器核心 (高效液相色谱), 匹配 仪/法 任一形态
    if core and core in title:
        return title
    if "测定" in title:
        return title.replace("测定", fa + "测定", 1)
    return title


# ---- 主: state → params ----
def build_params_single(state):
    scalars = state.get("scalars", {}) or {}
    rows = state.get("rows", {}) or {}
    editors = state.get("editors", {}) or {}

    def S(k):  # widget 值: 有且非 None/非空串 用之, 否则 DEF 默认 (前端输入框空串=未填)
        v = scalars.get(k, _MISSING)
        if v is _MISSING or v is None or v == "":
            return DEF.get(k)
        return v

    title, basis, instrument = S("title"), S("basis"), S("instrument")
    title = _ensure_instr_in_title(title, instrument)   # 报告标题须含仪器(法): AI/草稿漏了则补
    analyte, matrix, std_name = S("analyte"), S("matrix"), S("std_name")
    unit = S("unit")
    round_mode = S("round_mode")
    round_nd = int(S("round_nd"))
    env_temp, dtau, prep_flow = S("env_temp"), S("dtau"), S("prep_flow")
    influences = scalars.get("influences")
    balance_id = S("balance_id")
    try:
        m_sample = float(S("m_sample_raw"))
    except (TypeError, ValueError):
        m_sample = float("nan")
    n_weighings = int(S("n_weighings"))
    _d_mg = scalars.get("balance_tol_mg")
    if _is_na(_d_mg):
        _d_mg = balance_mpe_g(m_sample) * 1000          # I级 MPE 按称样量动态取 (single_form:1531)
    balance_tol = float(_d_mg) / 1000.0
    curve_method = S("curve_method")
    makeup_mode = S("makeup_mode")
    include_origin = bool(scalars.get("curve_include_origin", False))
    force_origin = bool(scalars.get("curve_force_origin", False))
    stock_source = S("stock_source")
    spike_std_conc = S("spike_std_conc")
    spike_add_vol = S("spike_add_vol")
    spike_add_mass = S("spike_add_mass")
    spike_vol = S("spike_vol")
    spike_theor = S("spike_theor")
    exp = UNIT_EXP[unit]

    # ② 定容 (single/mixed/multi)
    if makeup_mode == "mixed":
        vessel_kind = S("blend_vk")
        vessel_tol = None
        bvv = S("blend_vv")
        if bvv == "自定义":
            vessel_volume = float(S("blend_vv_custom"))
            vessel_tol = float(S("blend_vv_tol_custom"))
        else:
            vessel_volume = int(bvv)
        reagents = [{"volume": float(r.get("vi")), "alpha": float(r.get("a")),
                     "name": "" if r.get("s") == "自定义" else r.get("s")}
                    for r in rows.get("blend", [])]
        vessel_used_volume = float(_bvu) if isinstance(_bvu := scalars.get("blend_vuse"), (int, float)) else vessel_volume  # 使用规格 (满刻度=规格)
        makeup_solvent = "、".join(r["name"] for r in reagents if r.get("name")) or "混合试剂"
        alpha = None
    elif makeup_mode == "multi":
        reagents = []
        for r in rows.get("reag", []):
            vv = r.get("v")
            reagents.append({"kind": r.get("k"), "nominal": int(vv),
                             "volume": float(r.get("vi", vv)), "alpha": float(r.get("a")),
                             "name": "" if r.get("s") == "自定义" else r.get("s")})
        vessel_kind = vessel_volume = vessel_used_volume = None
        makeup_solvent = "、".join(r["name"] for r in reagents if r.get("name"))
        alpha = None
    else:  # single
        reagents = None
        vessel_kind = S("vessel_kind")
        vvs = S("vessel_vol_sel")
        vessel_tol = None
        if vvs == "自定义":
            vessel_volume = float(S("vessel_vol_custom"))
            vessel_tol = float(S("vessel_tol_custom"))
        else:
            vessel_volume = int(vvs)
        vessel_used_volume = (float(scalars.get("vuv") if not _is_na(scalars.get("vuv")) else vessel_volume)
                              if vessel_kind in ("pip_g", "cylinder") else vessel_volume)
        makeup_solvent = S("makeup_solvent_val")
        alpha = float(S("alpha_val"))

    # ③ 储备液
    stock_extra = {}
    if stock_source == "solid":
        _smg = scalars.get("stock_balance_tol_mg")
        if _is_na(_smg):
            _smg = float(_d_mg)                          # 默认同样品天平 I级 d (single_form:1652)
        _snw = scalars.get("stock_n_weighings")
        stock_extra.update(purity=S("purity"), U_purity=S("U_purity"),
                           k_purity=int(S("k_purity")), m_std=S("m_std"),
                           stock_balance_id=S("stock_balance_id"),
                           stock_balance_tol=float(_smg) / 1000.0,
                           stock_n_weighings=int(_snw) if not _is_na(_snw) else n_weighings)
    else:
        cert_mode = S("cert_mode")
        stock_extra.update(cert_mode=cert_mode, k_cert=int(S("k_cert")))
        _pk, _pnom = _PIP_REV.get(S("pip_vessel"), (None, None)) or ("pip_s", 5)
        _pva = scalars.get("pip_vol_actual")
        if _is_na(_pva):
            _pva = float(_pnom)                          # 默认置满刻度 (single_form:1696)
        stock_extra.update(pip_kind=_pk, pip_nominal=_pnom, pip_vol=float(_pva))
        _cert_unit = S("C_cert_unit") or "mg/L"
        _cexp = CONC_UNIT_EXP.get(_cert_unit, 0)
        _ccert_raw = S("C_cert")
        # 证书浓度统一换算为 mg/L (两模式都采集: 相对式供母液浓度自动填; 绝对式进 U/(k·C))
        stock_extra["C_cert"] = (float(_ccert_raw) * (10.0 ** _cexp)) if not _is_na(_ccert_raw) else None
        if cert_mode == "relative":
            stock_extra["Urel_cert"] = S("Urel_cert")
        else:
            stock_extra["U_abs"] = float(S("U_abs")) * (10.0 ** _cexp)   # U_abs 同单位 → mg/L
    stock_makeup_mode = S("stock_makeup_mode")
    stock_extra["stock_flask_volume"] = int(S("stock_flask_s"))
    if stock_makeup_mode == "mixed":
        stock_reagents = [{"volume": float(r.get("vi")), "alpha": float(r.get("a")),
                           "name": "" if r.get("s") == "自定义" else r.get("s")}
                          for r in rows.get("stock_blend", [])]
    else:
        stock_reagents = None
        stock_alpha = float(S("stock_alpha"))
        stock_solvent = S("stock_solvent")

    # ③ 中间液/工作液
    dil_df = editors.get("work_df") or []
    work_uses = _dilution_to_uses(dil_df)
    if stock_makeup_mode == "mixed":
        _vtot = sum(r["volume"] for r in stock_reagents) if stock_reagents else 0
        _stock_alpha = (sum(r["volume"] * r["alpha"] for r in stock_reagents) / _vtot) if _vtot else 0.0
    else:
        _stock_alpha = float(S("stock_alpha"))
    work_alpha = _stock_alpha if scalars.get("work_same_solvent", True) else float(S("work_alpha"))

    # ④ 曲线点
    points, analyte_areas, is_areas, is_missing = [], [], [], 0
    for r in (editors.get("points_df") or []):
        x = r.get("浓度mg/L")
        if _is_na(x):
            continue
        x = float(x)
        a = _f(r.get("分析物峰面积"))
        if curve_method == "内标法":
            isa = r.get("内标峰面积")
            if _is_na(isa):
                is_missing += 1
                continue
            isa = float(isa)
            analyte_areas.append(a)
            is_areas.append(isa)
            points.append((x, a / isa))
        else:
            analyte_areas.append(a)
            points.append((x, a))

    # ⑤ 加标 → p/x_pred/replicates/recovery/X
    spike_rows = _spike_pairs(editors.get("spike_df") or [])
    _rnd = round_sf if round_mode == "有效数字" else round_dp
    nd = int(round_nd)
    c_vals = [c for c, _ in spike_rows if c is not None]
    p_curve = len(c_vals) if c_vals else DEF["p"]
    x_pred = sum(c_vals) / len(c_vals) if c_vals else DEF["x_pred"]
    pairs = [(c, m) for c, m in spike_rows if c is not None and m is not None and m > 0]
    if pairs:
        replicates = [_rnd(c * spike_vol / m * 10 ** exp, nd) for c, m in pairs]
        recovery = [round_sf(c / spike_theor, 3) if spike_theor else float("nan") for c, _ in pairs]
        X = _rnd(sum(c * spike_vol / m for c, m in pairs) / len(pairs) * 10 ** exp, nd)
    else:
        replicates, recovery, X = [], [], DEF["X"]

    # ---- 组装 params (app.py:1973-2034 逐字) ----
    params = {
        "title": title, "basis": basis, "instrument": instrument,
        "analyte": analyte, "matrix": matrix,
        "balance_tol": balance_tol, "m_sample": m_sample, "n_weighings": int(n_weighings),
        "balance_id": balance_id, "dtau": dtau, "env_temp": env_temp, "std_name": std_name,
        "prep_flow": prep_flow, "influences": influences,
        "points": points, "p": int(p_curve), "x_pred": x_pred,
        "include_origin": include_origin, "force_origin": force_origin,
        "analyte_areas": analyte_areas, "is_areas": is_areas,
        "replicates": replicates, "recovery": recovery, "X": X,
        "curve_method": curve_method, "unit": unit, "stock_source": stock_source,
        "spike_std_conc": spike_std_conc, "spike_add_vol": spike_add_vol, "spike_add_mass": spike_add_mass,
    }
    if makeup_mode == "mixed":
        params.update(makeup_mode="mixed", vessel_kind=vessel_kind,
                      vessel_volume=int(vessel_volume) if vessel_tol is None else vessel_volume,
                      vessel_used_volume=vessel_used_volume,
                      reagents=reagents)
        if vessel_tol is not None:
            params["vessel_tol"] = vessel_tol
    elif makeup_mode == "multi":
        params.update(makeup_mode="multi", reagents=reagents)
    else:
        params.update(vessel_kind=vessel_kind,
                      vessel_volume=int(vessel_volume) if vessel_tol is None else vessel_volume,
                      vessel_used_volume=vessel_used_volume,
                      makeup_solvent=makeup_solvent, alpha=alpha)
        if vessel_tol is not None:
            params["vessel_tol"] = vessel_tol
    if stock_source == "solid":
        params.update(purity=stock_extra["purity"], U_purity=stock_extra["U_purity"],
                      k_purity=int(stock_extra["k_purity"]), m_std=stock_extra["m_std"],
                      stock_balance_id=stock_extra["stock_balance_id"],
                      stock_balance_tol=stock_extra["stock_balance_tol"],
                      stock_n_weighings=stock_extra["stock_n_weighings"])
    else:
        params.update(cert_mode=stock_extra["cert_mode"], k_cert=int(stock_extra["k_cert"]),
                      pip_kind=stock_extra["pip_kind"], pip_vol=stock_extra["pip_vol"],
                      pip_nominal=stock_extra["pip_nominal"])
        params["C_cert"] = stock_extra["C_cert"]   # mg/L, 两模式都供母液浓度自动填
        if stock_extra["cert_mode"] == "relative":
            params["Urel_cert"] = stock_extra["Urel_cert"]
        else:
            params["U_abs"] = stock_extra["U_abs"]
    params["stock_flask_volume"] = int(stock_extra["stock_flask_volume"])
    if stock_makeup_mode == "mixed":
        params["stock_reagents"] = stock_reagents
    else:
        params["stock_alpha"] = stock_alpha
        params["stock_solvent"] = stock_solvent
    params["work_uses"] = work_uses if work_uses else None
    params["work_chain"] = _dilution_chain(dil_df)
    params["work_alpha"] = work_alpha
    if not work_uses:
        params["u_work"] = DEF["u_work"]

    # ---- 校验 (app.py:2036-2048) ----
    errors = []
    if len(points) < 3:
        errors.append(f"曲线点至少 3 个 (现 {len(points)})")
    if curve_method == "内标法" and is_missing:
        errors.append(f"内标法: {is_missing} 个曲线点缺内标峰面积")
    if len(replicates) < 2:
        errors.append(f"完整加标行至少 2 行 (现 {len(replicates)})")
    if not spike_theor or spike_theor <= 0:
        errors.append("理论加标必须 > 0")
    if not spike_vol or spike_vol <= 0:
        errors.append("定容体积必须 > 0")
    if _is_na(m_sample) or m_sample <= 0:
        errors.append("称样量必须 > 0")
    if stock_source == "solid" and (stock_extra["m_std"] <= 0 or stock_extra["purity"] <= 0):
        errors.append("标品称量/纯度必须 > 0")
    if stock_source != "solid" and (stock_extra.get("C_cert") or 0) <= 0:
        errors.append("证书浓度必须 > 0")
    return {"params": params, "errors": errors}


# ==== AI 自动填充 (移植 app.py _ai_apply_single + helpers; 去 st.*, 写 sc/rows) ====
def _vessel_echo(kind, sel, custom_vol=None, actual=None):
    lab = KIND_LABELS.get(kind, kind or "量器")
    if sel == "自定义" or sel is None:
        return f"自定义{custom_vol:g}mL{lab}" if custom_vol else f"自定义{lab}"
    if actual is not None and actual != sel:
        return f"{sel:g}mL{lab}(实际{actual:g}mL)"
    return f"{sel:g}mL{lab}"


def _pick_vessel(kind, vol, allow_custom):   # app.py:537-576 逐字
    if kind is None:
        return None, None, None, None, "定容器具未识别, 定容块未填。"
    if kind in ("pip_s", "pip_g", "cylinder"):
        if vol is None:
            return "pip_s", None, None, None, "移取量器已识别, 体积待手填。"
        lab_ps, lab_pg, lab_cyl = VOLUMES["pip_s"], VOLUMES["pip_g"], VOLUMES["cylinder"]
        if any(abs(v - vol) < 1e-6 for v in lab_ps):
            v = int(round(vol)); return "pip_s", v, None, float(v), f"量器=单标吸量管, 规格={v:g} mL。"
        cand = [v for v in lab_pg if v >= vol]
        if cand:
            nom = min(cand); return "pip_g", nom, None, float(vol), f"量器=分度吸量管, 规格={nom:g} mL(移取{vol:g}mL)。"
        cand = [v for v in lab_cyl if v >= vol]
        if cand:
            nom = min(cand); return "cylinder", nom, None, float(vol), f"量器=量筒, 规格={nom:g} mL(移取{vol:g}mL)。"
        if allow_custom:
            return "pip_s", "自定义", float(vol), float(vol), f"库存无≥{vol:g}mL 移取量器, 已转自定义, 请补允差。"
        near = min(lab_ps, key=lambda v: abs(v - vol))
        return "pip_s", near, None, float(vol), f"库存无≥{vol:g}mL 移取量器, 就近取 {near:g}mL单标, 请核对。"
    if kind == "flask":
        if vol is None:
            return "flask", None, None, None, "量器=容量瓶, 规格待手填。"
        lab_fl = VOLUMES["flask"]
        if any(abs(v - vol) < 1e-6 for v in lab_fl):
            v = int(round(vol)); return "flask", v, None, float(v), f"量器=容量瓶, 规格={v:g} mL。"
        if allow_custom:
            return "flask", "自定义", float(vol), float(vol), f"容量瓶无 {vol:g}mL 规格, 已转自定义, 请补允差。"
        near = min(lab_fl, key=lambda v: abs(v - vol))
        return "flask", near, None, float(near), f"库内无 {vol:g}mL 容量瓶, 就近取 {near:g}mL, 请核对。"
    return None, None, None, None, f"量器类型「{kind}」不在库, 定容未填。"


def _vessels_of(r):   # app.py:724-735
    vs = r.get("vessels")
    if vs:
        return vs
    k, v, s = r.get("vessel_kind"), r.get("vessel_volume"), r.get("makeup_solvent")
    if k is None and v is None and s is None:
        return []
    return [{"solvent": s, "volume": v, "kind": k, "cas": None, "alpha": None}]


def _solvent_hits(name, cas=None):   # app.py:579-585
    hits = solvents.lookup(name) if name else []
    if not hits and cas:
        hits = solvents.lookup(cas)
    return hits


def _ai_resolve_alpha(name, cas=None, alpha_ai=None):   # app.py:588-607
    def _ok(x):
        return x is not None and math.isfinite(x) and 1e-5 < x < 5e-3
    if cas:
        try:
            pts = solvents.fetch_nist_density(cas, 15, 35, 5, p=1.0, timeout=12)
            rows = [(T, pts[T]) for T in (15, 20, 25) if T in pts]
            if len(rows) == 3:
                (T1, r1), (_T2, r2), (T3, r3) = rows
                b = solvents.calc_beta_from_density(r1, T1, r2, 20, r3, T3)
                if _ok(b):
                    return float(b), f"NIST 密度法(CAS {cas}, ρ {r1:.4g}/{r2:.4g}/{r3:.4g})"
        except Exception:
            pass
    if _ok(alpha_ai):
        return float(alpha_ai), "AI 查询估值(待核对)"
    return None, None


def _ai_fill_solvent(name, filled, notes, cas, alpha_ai, sc):   # app.py:610-632, 写 sc
    hits = _solvent_hits(name, cas)
    if hits:
        h = hits[0]
        sc["solvent_preset"] = h["name_cn"]; sc["makeup_solvent_val"] = h["name_cn"]; sc["alpha_val"] = h["alpha"]
        filled.append(f"定容试剂={h['name_cn']}(α={h['alpha']:g})")
        if len(hits) > 1:
            notes.append(f"溶剂库匹配到多个, 已取「{h['name_cn']}」, 请核对。")
    else:
        sc["solvent_preset"] = "自定义"; sc["makeup_solvent_val"] = name
        a, src = _ai_resolve_alpha(name, cas, alpha_ai)
        if a is not None:
            sc["alpha_val"] = a; filled.append(f"定容试剂={name}(α={a:g})")
            notes.append(f"「{name}」不在溶剂库, α 已按{src}填, 请核对。")
        else:
            filled.append(f"定容试剂={name}(α 待填)")
            notes.append(f"定容试剂「{name}」不在溶剂库, α 待手填(可用底部密度法)。")


def _ai_fill_blend(vessels, vkind, vvol, filled, notes, sc, blend):   # app.py:671-705
    sc["makeup_mode"] = "mixed"
    kind = vkind if vkind in KIND_LABELS else "flask"
    sc["blend_vk"] = kind
    vol = vvol if vvol else sum(c["volume"] for c in vessels if c["volume"])
    if vol is not None:
        std = VOLUMES[kind]
        bsel = next((v for v in std if abs(v - vol) < 1e-6), min(std, key=lambda v: abs(v - vol)))
        if abs(bsel - vol) >= 1e-6:
            notes.append(f"单器皿 {vol:g}mL 非标, 已就近取 {bsel:g}mL({KIND_LABELS[kind]}), 请核对。")
        sc["blend_vv"] = bsel
    sc["blend_n"] = len(vessels)
    for c in vessels:
        vi = c["volume"]; name = c["solvent"]; row = {"s": "自定义", "vi": float(vi) if vi else 0.0, "a": None}
        hits = _solvent_hits(name, c.get("cas"))
        if hits:
            h = hits[0]; row["s"] = h["name_cn"]; row["a"] = h["alpha"]
            filled.append(f"组分={h['name_cn']}" + (f" {vi:g}mL" if vi else ""))
            if len(hits) > 1:
                notes.append(f"组分「{h['name_cn']}」溶剂库匹配多个, 已取, 请核对。")
        else:
            a, src = _ai_resolve_alpha(name, c.get("cas"), c.get("alpha"))
            if a is not None:
                row["a"] = a; notes.append(f"组分「{name or '?'}」不在库, α 按{src}填, 请核对。")
            else:
                notes.append(f"组分「{name or '?'}」不在库, α 待手填。")
        blend.append(row)
    filled.append(f"混合试剂(单器皿 {vol:g}mL)" if vol else "混合试剂")


def _ai_fill_multi_reagents(vessels, filled, notes, sc, reag):   # app.py:635-668
    sc["makeup_mode"] = "multi"; sc["n_reag"] = len(vessels)
    for vs in vessels:
        vol = vs["volume"]
        vk, sel, _c, actual, vmsg = _pick_vessel(vs["kind"], vol, allow_custom=False)
        row = {"s": "自定义", "k": None, "v": None, "vi": None, "a": None}
        if sel is None:
            notes.append(f"试剂体积未识别, 请手填。" if vol is None else vmsg)
        else:
            row["k"] = vk; row["v"] = sel; row["vi"] = actual; notes.append(vmsg)
        name = vs["solvent"]; hits = _solvent_hits(name, vs.get("cas"))
        if hits:
            h = hits[0]; row["s"] = h["name_cn"]; row["a"] = h["alpha"]
            filled.append(f"试剂={h['name_cn']}" + (f" {vol:g}mL" if vol else ""))
            if len(hits) > 1:
                notes.append(f"试剂「{h['name_cn']}」溶剂库匹配多个, 已取, 请核对。")
        else:
            a, src = _ai_resolve_alpha(name, vs.get("cas"), vs.get("alpha"))
            if a is not None:
                row["a"] = a; notes.append(f"试剂「{name or '?'}」不在库, α 按{src}填, 请核对。")
            else:
                notes.append(f"试剂「{name or '?'}」不在库, α 待手填。")
        reag.append(row)
    vtot = sum(vs["volume"] for vs in vessels if vs["volume"])
    filled.append(f"多次定容(V=ΣVi={vtot:g}mL)")


def apply_ai_single(prep_flow_text):   # app.py:_ai_apply_single 708-792, 去 st.*
    from ai_fill import parse_prep_flow, load_config
    try:
        cfg = load_config()
    except Exception as e:
        return {"error": f"ai_config.toml 解析失败: {e}"}
    if not cfg or not all(str(cfg.get(k, "")).strip() for k in ("ai_base_url", "ai_model", "ai_api_key")):
        return {"error": "未配置 AI: ai_config.toml 填 ai_base_url/ai_model/ai_api_key"}
    try:
        r = parse_prep_flow(prep_flow_text, base_url=cfg["ai_base_url"],
                            model=cfg["ai_model"], api_key=cfg["ai_api_key"])
    except Exception as e:
        return {"error": f"AI 解析失败: {e}"}

    sc, reag, blend, filled, notes = {}, [], [], [], []
    if r["m_sample"] is not None and math.isfinite(r["m_sample"]):
        sc["m_sample_raw"] = f"{r['m_sample']:g}"; filled.append(f"称样量 m={r['m_sample']:g} g")
        sc["balance_tol_mg"] = None   # 让前端 d 随新 m 重取
    if r["n_weighings"]:
        sc["n_weighings"] = int(r["n_weighings"])
    info = ""
    if r.get("influences"):
        info = "、".join(r["influences"]); sc["influences"] = info
    vessels = _vessels_of(r); mode = r.get("mode")
    if vessels:
        if mode is None:
            mode = "single" if len(vessels) == 1 else ("mixed" if r.get("vessel_kind") else "multi")
        if mode == "multi":
            _ai_fill_multi_reagents(vessels, filled, notes, sc, reag)
        elif mode == "mixed":
            _ai_fill_blend(vessels, r.get("vessel_kind"), r.get("vessel_volume"), filled, notes, sc, blend)
        else:
            vs = vessels[0]
            vkind, sel, custom_vol, actual, msg = _pick_vessel(vs["kind"], vs["volume"], allow_custom=True)
            notes.append(msg)
            if sel is not None:
                sc["makeup_mode"] = "single"; sc["vessel_kind"] = vkind; sc["vessel_vol_sel"] = sel
                if custom_vol is not None:
                    sc["vessel_vol_custom"] = custom_vol
                if vkind in ("pip_g", "cylinder") and actual is not None:
                    sc["vuv"] = actual
                filled.append("定容量器=" + _vessel_echo(vkind, sel, custom_vol, actual))
            if vs["solvent"]:
                sc["makeup_mode"] = "single"
                _ai_fill_solvent(vs["solvent"], filled, notes, vs.get("cas"), vs.get("alpha"), sc)
    if r["note"]:
        notes.append(f"AI 依据: {r['note']}")
    return {"scalars": sc, "rows": {"reag": reag, "blend": blend}, "filled": filled, "notes": notes, "info": info}


def apply_ai_method(std_no):
    """按检测标准编号 AI 回填方法信息。返回:
    scalars=标准级字段(title/basis/instrument/analyte/matrix/std_name);
    methods=[{name,unit,round_mode,round_nd,prep_flow}](round_nd 为标准原值, 前端按所选方法 +1);
    target_mode: single/multi/None。前端按 target_mode 映射 single/mu_ 键, 并按所选方法填单位/修约/前处理。"""
    from ai_fill import parse_method_info, load_config
    if not str(std_no or "").strip():
        return {"error": "请先填写检测标准编号"}
    try:
        cfg = load_config()
    except Exception as e:
        return {"error": f"ai_config.toml 解析失败: {e}"}
    if not cfg or not all(str(cfg.get(k, "")).strip() for k in ("ai_base_url", "ai_model", "ai_api_key")):
        return {"error": "未配置 AI: ai_config.toml 填 ai_base_url/ai_model/ai_api_key"}
    try:
        r = parse_method_info(std_no, base_url=cfg["ai_base_url"],
                              model=cfg["ai_model"], api_key=cfg["ai_api_key"])
    except Exception as e:
        return {"error": f"AI 解析失败: {e}"}

    sc, filled, notes = {}, [], []
    for key, label in (("title", "报告标题"), ("basis", "测量依据/标准号"), ("instrument", "仪器"),
                       ("analyte", "目标物"), ("matrix", "基质"), ("std_name", "标准品")):
        v = r.get(key)
        if v:
            sc[key] = v
            filled.append(label)
    methods = r.get("methods") or []
    if methods:                                  # 首个方法的单位/修约/前处理计入 filled 提示
        m0 = methods[0]
        if m0.get("unit"): filled.append("单位")
        if m0.get("round_mode"): filled.append("修约方式/位数")
        if m0.get("prep_flow"): filled.append("前处理流程")
        if len(methods) > 1:
            filled.append(f"{len(methods)}个方法(可切换)")
    if r.get("note"):
        notes.append(f"AI 依据: {r['note']}")
    return {"scalars": sc, "methods": methods, "filled": filled, "notes": notes, "target_mode": r.get("target_mode")}


# ==== LIMS 工作液溯源 (移植 app.py _apply_trace_single + helpers; session 模块级缓存) ====
_LIMS_SESS = {"res": None, "ts": 0}
_LIMS_SESS_TTL = 3600


def _lims_session_cached():
    now = time.time()
    if _LIMS_SESS["res"] and now - _LIMS_SESS["ts"] < _LIMS_SESS_TTL:
        return _LIMS_SESS["res"], None
    try:
        from lims_auto_login import auto_login
        from lims_config import get_credentials
    except Exception as e:
        return None, f"缺少 LIMS 依赖(requests/Pillow/ddddocr): {e}"
    creds = get_credentials()
    if not creds:
        return None, "未配置 LIMS: lims_config.toml 填 [lims] base_url/username/password"
    base_url, user, pwd = creds
    try:
        res = auto_login(user, pwd, base_url=base_url)
    except Exception as e:
        return None, f"LIMS 登录异常: {e}"
    if not res:
        return None, "LIMS 登录失败(验证码/账密), 请稍后重试。"
    _LIMS_SESS["res"] = res
    _LIMS_SESS["ts"] = now
    return res, None


def _pick_pip(vol):   # app.py:879-891
    if vol is None:
        return None, None
    lab_ps, lab_pg = VOLUMES["pip_s"], VOLUMES["pip_g"]
    if any(abs(v - vol) < 1e-6 for v in lab_ps):
        return "pip_s", int(round(vol))
    cand = [v for v in lab_pg if v >= vol]
    if cand:
        return "pip_g", min(cand)
    return "pip_s", min(lab_ps, key=lambda v: abs(v - vol))


def _conc_text(v):
    return None if v is None else (f"{v:.3f}" if abs(v) < 0.1 else f"{v:.2f}")


def apply_trace_single(code):   # app.py:_apply_trace_single 899-1001, 去 st.*
    code = (code or "").strip()
    if not code:
        return {"error": "请输入工作液编号(如 D-9203)。"}
    system, err = _lims_session_cached()
    if err:
        return {"error": err}
    try:
        from lims_trace import trace_working_solution
        from lims_fill import extract_chain_fields
        chain = trace_working_solution(code, system)
        fields = extract_chain_fields(chain)
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        _LIMS_SESS["res"] = None   # 疑似会话过期, 清缓存
        return {"error": f"溯源失败: {e}"}

    sc, work, fb = {}, [], {"errors": [], "filled": [], "notes": [], "manual": [], "chain": ""}
    fb["manual"] = list(fields["manual"])
    if fields.get("multi_source"):
        fb["notes"].append("检出多源工作液，稀释链已填主源路径，请核对。")

    sc["stock_source"] = fields["stock_source"]
    fb["filled"].append(f"储备液={'纯品称量' if fields['stock_source'] == 'solid' else '高浓液标'}")
    if fields["stock_source"] == "solid":
        if fields["m_std"] is not None:
            sc["m_std"] = fields["m_std"]; fb["filled"].append(f"m_std={fields['m_std']:g} g")
    else:
        if fields["c_cert"] is not None:
            sc["C_cert"] = fields["c_cert"]; sc["C_cert_unit"] = "mg/L"
            fb["filled"].append(f"证书浓度={fields['c_cert']:g} mg/L")
        if fields["stock_received_qty"] is not None:
            sc["pip_vol_actual"] = fields["stock_received_qty"]
            _pk, _ps = _pick_pip(fields["stock_received_qty"])
            if _ps is not None:
                sc["pip_vessel"] = _vsl_label(_pk, _ps)
            fb["filled"].append(f"移取浓标={fields['stock_received_qty']:g} mL")
    if fields["stock_flask_vol"] is not None:
        _fk, _fs, _c, _a, _m = _pick_vessel("flask", fields["stock_flask_vol"], allow_custom=False)
        if _fs is not None:
            sc["stock_flask_s"] = _fs; fb["filled"].append(f"容量瓶={_fs:g} mL")
    med = fields["stock_medium"]
    if med:
        hits = solvents.lookup(med)
        if hits:
            h = hits[0]
            sc["stock_solvent_preset"] = h["name_cn"]; sc["stock_solvent"] = h["name_cn"]; sc["stock_alpha"] = h["alpha"]
            fb["filled"].append(f"定容试剂={h['name_cn']}(α={h['alpha']:g})")
        else:
            sc["stock_solvent_preset"] = "自定义"; sc["stock_solvent"] = med
            fb["notes"].append(f"储备液定容试剂「{med}」不在溶剂库, α 待手填。")
    sc["work_same_solvent"] = True

    for r in fields["dilution_rows"]:
        pk_lab = fk_lab = None
        if r["pip_vol"] is not None:
            _pk, _ps = _pick_pip(r["pip_vol"])
            if _ps is not None:
                pk_lab = _vsl_label(_pk, _ps)
        if r["flask_vol"] is not None:
            _fk, _fs, _c, _a, _m = _pick_vessel("flask", r["flask_vol"], allow_custom=False)
            if _fs is not None:
                fk_lab = _vsl_label("flask", _fs)
        work.append({"母液浓度(mg/L)": _conc_text(r["mother_conc"]), "移取体积(mL)": r["pip_vol"],
                     "移取量器": pk_lab, "定容量器": fk_lab, "目标浓度(mg/L)": None})
    if work:
        fb["filled"].append(f"稀释链 {len(work)} 步")
    fb["chain"] = " → ".join(f"{lv}({od})" for lv, od, _n, _c, _d in fields["info_chain"] if od)
    return {"scalars": sc, "work_df": work, "feedback": fb}


if __name__ == "__main__":
    import json
    with open(os.path.join(ROOT, "drafts", "111.json"), encoding="utf-8") as fp:
        st = json.load(fp)
    out = build_params_single(st)
    if out["errors"]:
        print("ERRORS:", out["errors"])
    res = mup_cg248(out["params"])
    print(f"U={res['U']}  X={res['X']}  urel_w={res['urel_w']}  recovery_mean={res['recovery']['mean']}")
    print("params keys:", sorted(out["params"].keys()))
