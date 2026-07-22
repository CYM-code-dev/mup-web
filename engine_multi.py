# -*- coding: utf-8 -*-
"""
多目标物: 草稿形状 state (v4) → {method, groups, analytes, params_list, errors, warns}。

从 app.py multi_form (3189-3335) 的装配逻辑逐字抽出 (去 Streamlit / 去 pandas)。
复用 engine_single 的量器常量 / _uses_from_ops / _PIP_REV / _FLASK_REV / AI helper。
前端只发 v4 形状 state (scalars + topo_rows + grp_params + meas + curve_meta),
参数装配留在后端 → parity 由同一段 Python 保证。

state 形状 (= _mu_draft_payload app.py:1196):
  { scalars: {mu_* 方法级标量}, topo_rows: [{分组名,类型,目标物, ...逐物列}],
    grp_params: {gn: {kind, stock_alpha, m_std_g, flask_volume_mL, flasks{dg}, cert_mode, k_cert, inter, work}},
    meas: {名: {X,p,x_pred,points,replicates,recovery,curve_method,is_name,spike_*}} 或 {},
    curve_meta: {名: {method, is_name}} }
"""
import os
import sys
import math

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from uncertainty import (mup_cg248, BASELINE_PARAMS, UNIT_EXP, balance_mpe_g,  # noqa: E402
                         round_sf, round_dp, urel_stock_liquid, urel_mass,
                         urel_sample_volume)
from engine_single import (KIND_LABELS, VOLUMES, _PIP_REV, _FLASK_REV, _resolve_pip,  # noqa: E402
                           _uses_from_ops, _is_na, _vessels_of, _vessel_echo,
                           _ai_fill_solvent)
import solvents  # noqa: E402

DEF = BASELINE_PARAMS
_MISSING = object()

_KIND_FROM_CN = {"固体": "solid", "液体": "liquid"}


# ---- 逐字移植 app.py:169-197 ----
def _analyte_work_uses(group, a):
    """多目标物逐目标物装配稀释 uses 列表 (喂 dilution_budget)。opt-in: 本物无有效中间液移取 → [] → u_work=0。"""
    inter = group.get("inter") or {}
    feeds = inter.get("feeds") or {}
    if group.get("kind") == "liquid":
        _unit = (a.get("group") or "").strip()        # 中间液/工作液按定容分组共享 → feeds 改按分组名键
    else:
        _unit = a.get("name")
    fd = feeds.get(_unit)
    if not fd:
        return []
    _pv = fd.get("pip_vol")
    if not (_pv and float(_pv) > 0 and _resolve_pip(fd.get("pip_vessel"))[0] is not None):
        return []
    dg = fd.get("dg")
    ops = [("pip", fd["pip_vessel"], float(_pv))]
    fv = (inter.get("flasks") or {}).get(dg)
    if fv in _FLASK_REV:
        ops.append(("flask", fv, None))
    for step in (group.get("work") or {}).get(dg) or []:
        _sv = step.get("pip_vol")
        if _sv and float(_sv) > 0 and _resolve_pip(step.get("pip_vessel"))[0] is not None:
            ops.append(("pip", step["pip_vessel"], float(_sv)))
            if step.get("flask_vessel") in _FLASK_REV:
                ops.append(("flask", step["flask_vessel"], None))
    return _uses_from_ops(ops)


# ---- 逐字移植 app.py:1223-1237 ----
def _rows_to_groups(rows):
    """表格行 [{分组名,类型,目标物}] → 分组 [{name,kind,analytes:[名]}] (同分组名合并, 按首次出现排序)。"""
    order, members, kind = [], {}, {}
    for r in rows:
        gn = str(r.get("分组名", "")).strip()
        an = str(r.get("目标物", "")).strip()
        if not gn and not an:
            continue
        if gn not in members:
            members[gn] = []
            kind[gn] = _KIND_FROM_CN.get(str(r.get("类型", "固体")).strip() or "固体", "solid")
            order.append(gn)
        if an:
            members[gn].append(an)
    return [{"name": gn, "kind": kind[gn], "analytes": members[gn]} for gn in order]


# ---- 逐字移植 app.py:2069-2087 ----
def _compute_group_stock_solid(group, members, method):
    """固体分组: 各目标物按自身纯度+称样量+自身储备液容量瓶 合成 u_stock → a['_u_stock_inj']
    (容量瓶逐物取自身行; 缺失回退组级 flask_volume_mL。物理上各目标物各自定容一瓶。)"""
    bal = group.get("balance_tol_g")
    bal = method["balance_tol"] if bal in (None, "") else float(bal)
    alpha = method.get("alpha", 1.19e-3)
    dtau = method.get("dtau", 5.0)
    sa = group.get("stock_alpha")
    stock_alpha = float(sa) if sa not in (None, "") else alpha
    _g_flask = group.get("flask_volume_mL")   # 组级回退 (旧草稿/未逐行设置)
    _g_mstd = group.get("m_std_g")
    for a in members:
        _fv = a.get("stock_flask")
        _fnom = (_FLASK_REV.get(_fv, (None, None))[1] if _fv else None) or _g_flask
        urel_v = urel_sample_volume("flask", _fnom, stock_alpha, dtau) if _fnom else 0.0
        _m = a.get("m_std_g")
        _m = _g_mstd if _m in (None, "") else _m
        urel_m = urel_mass(bal, _m, group.get("n_weighings", 2))
        urel_p = a["U_purity"] / (a["k_purity"] * a["purity"])
        a["_u_stock_inj"] = (math.sqrt(urel_p ** 2 + urel_m ** 2 + urel_v ** 2),
                             [("纯度", urel_p), ("称量", urel_m), ("定容", urel_v)])


# ---- 逐字移植 app.py:2090-2143 ----
def _build_params(method, group, a):
    """合并方法级共享 + 分组共享 + 单目标物参数 → mup_cg248 入参。"""
    p = {
        "balance_tol": method["balance_tol"], "m_sample": method["m_sample"],
        "n_weighings": method["n_weighings"],
        "vessel_kind": method["vessel_kind"], "vessel_volume": method["vessel_volume"],
        "alpha": method.get("alpha", 1.19e-3),
        "dtau": method.get("dtau", 5.0),
        "points": a["points"], "p": a["p"], "x_pred": a["x_pred"],
        "include_origin": method.get("include_origin", False),
        "force_origin": method.get("force_origin", False),
        "replicates": a["replicates"], "recovery": a["recovery"], "X": a["X"],
        "stock_source": "liquid_dilute" if group["kind"] == "liquid" else "solid",
    }
    _mm = method.get("makeup_mode", "single")
    if _mm in ("mixed", "multi"):                       # 样液定容混合/多次: 喂 reagents 给 mup_cg248
        p["makeup_mode"] = _mm
        p["reagents"] = method.get("reagents") or []     # single 不加键 → 与旧版逐字一致 (parity)
        if _mm == "mixed" and method.get("vessel_tol") is not None:
            p["vessel_tol"] = method["vessel_tol"]
    if group["kind"] == "solid":
        p["u_stock"], p["stock_detail"] = a["_u_stock_inj"]
    else:
        cm = group.get("cert_mode", "relative")
        kc = a.get("k_cert") or group.get("k_cert")
        dg = a.get("ding_group") or "1"
        fl = group.get("flasks", {}).get(dg, {})
        _pk, _pnom = _resolve_pip(fl.get("pip_vessel"))   # 量器名→类型 (UI 只写 pip_vessel; 镜像 engine_single:228)
        _pv = fl.get("pip_vol")
        _pk2 = _pk or fl.get("pip_kind")
        pip = (_pk2, _pv) if _pk2 and isinstance(_pv, (int, float)) and _pv > 0 else None
        p["u_stock"], p["stock_detail"] = urel_stock_liquid(
            (a.get("Urel_cert") or 0.0) if cm == "relative" else 0.0,
            kc, pip=pip, flask=fl.get("flask_vol"),
            alpha=method.get("alpha", 1.19e-3), dtau=method.get("dtau", 5.0),
            flask_alpha=group.get("stock_alpha"),
            cert_mode=cm,
            C_cert=a.get("C_cert") or group.get("C_cert"),
            U_abs=a.get("U_abs") or group.get("U_abs"),
            pip_nominal=_pnom or fl.get("pip_nominal"))
    _inter = group.get("inter")
    if _inter and _inter.get("feeds"):
        _uses_a = _analyte_work_uses(group, a)
        if _uses_a:
            p["work_uses"] = _uses_a
            wa = group.get("stock_alpha") if group.get("work_same_solvent", True) else group.get("work_alpha")
            if wa not in (None, ""):
                p["work_alpha"] = float(wa)
        else:
            p["u_work"] = 0.0
    elif group.get("work_uses"):
        p["work_uses"] = group["work_uses"]
        wa = group.get("stock_alpha") if group.get("work_same_solvent", True) else group.get("work_alpha")
        if wa not in (None, ""):
            p["work_alpha"] = float(wa)
    else:
        p["u_work"] = group.get("u_work", 0.0)
    return p


# ---- 逐字移植 app.py:3173-3186 ----
def _derive_spike_rw(spike_C, spike_m, V, exp, c0, round_mode="有效数字", nd=3):
    """加标原始 C(mg/L)/m(g) + 方法定容 V + 单位 exp + 理论加标 C₀ → (测定值列表, 回收率列表)。"""
    if not c0 or not V or exp is None:
        return [], []
    rnd = round_sf if round_mode == "有效数字" else round_dp
    det, rec = [], []
    for c, m in zip(spike_C, spike_m):
        if c is None or not m or m <= 0:
            continue
        det.append(rnd(c * V / m * 10 ** exp, nd))
        rec.append(round_sf(c / c0, 3))
    return det, rec


# ---- 逐字移植 app.py:517-534 ----
def _map_vessel(kind, vol, allow_custom):
    """AI 解析出的定容 (kind, vol) → (sel_value, custom_vol, msg)。"""
    if kind is None:
        return None, None, "定容器具未识别, 定容块未填。"
    if kind not in KIND_LABELS:
        return None, None, f"量器类型「{kind}」不在库(flask/pip_s/pip_g), 定容未填。"
    std = VOLUMES[kind]
    if vol is None:
        return None, None, f"量器类型={KIND_LABELS[kind]}已识别, 规格待手填。"
    if any(abs(v - vol) < 1e-6 for v in std):
        return int(round(vol)), None, f"量器={KIND_LABELS[kind]}, 规格={vol:g} mL。"
    if allow_custom:
        return "自定义", float(vol), f"量器={KIND_LABELS[kind]}, 规格={vol:g} mL(非标, 已转自定义, 请补允差)。"
    nearest = min(std, key=lambda v: abs(v - vol))
    return nearest, None, f"库内无 {vol:g} mL, 已就近取 {nearest:g} mL({KIND_LABELS[kind]}), 请核对。"


# ---- method 组装: 从 scalars(mu_* 键) → method dict (对齐 _method_inputs_multi 3154-3168) ----
def _method_from_scalars(scalars, mu_rows=None):
    sc = scalars or {}
    mu_rows = mu_rows or {}

    def S(k, d=None):
        v = sc.get(k, _MISSING)
        return d if (v is _MISSING or v is None or v == "") else v

    try:
        m_sample = float(S("mu_m_sample_raw"))
    except (TypeError, ValueError):
        m_sample = float("nan")
    _d_mg = sc.get("mu_balance_tol_mg")
    if _is_na(_d_mg):
        _d_mg = balance_mpe_g(m_sample) * 1000          # I级 MPE 按称样量动态取
    balance_tol = float(_d_mg) / 1000.0

    # ② 样液定容 (single/mixed/multi) — 对齐 engine_single _method_inputs(161-205)
    makeup_mode = S("mu_makeup_mode", "single")
    vessel_tol = None
    if makeup_mode == "mixed":
        vessel_kind = S("mu_blend_vk", "flask")
        bvv = S("mu_blend_vv", 10)
        if bvv == "自定义":
            vessel_volume = float(S("mu_blend_vv_custom"))
            vessel_tol = float(S("mu_blend_vv_tol_custom"))
        else:
            vessel_volume = int(bvv)
        reagents = [{"volume": float(r.get("vi")), "alpha": float(r.get("a")),
                     "name": "" if r.get("s") == "自定义" else r.get("s")}
                    for r in mu_rows.get("blend", [])
                    if r.get("vi") not in (None, "") and r.get("a") not in (None, "")]
        vessel_used_volume = float(_bvu) if isinstance(_bvu := S("mu_blend_vuse", None), (int, float)) else vessel_volume  # 使用规格 (满刻度=规格)
        makeup_solvent = "、".join(r["name"] for r in reagents if r.get("name")) or "混合试剂"
        alpha = DEF["alpha"]
    elif makeup_mode == "multi":
        reagents = []
        for r in mu_rows.get("reag", []):
            vv = r.get("v")
            if r.get("vi") in (None, "") or r.get("a") in (None, ""):
                continue
            reagents.append({"kind": r.get("k"), "nominal": int(vv) if vv not in (None, "") else None,
                             "volume": float(r.get("vi")), "alpha": float(r.get("a")),
                             "name": "" if r.get("s") == "自定义" else r.get("s")})
        vessel_kind = None
        vessel_volume = sum(r["volume"] for r in reagents) or None     # ΣVi: 供加标 C₀
        vessel_used_volume = vessel_volume
        makeup_solvent = "、".join(r["name"] for r in reagents if r.get("name")) or "多次定容"
        alpha = DEF["alpha"]
    else:  # single (与旧版逐字一致 → parity_demo 不变)
        reagents = None
        vessel_kind = S("mu_vessel_kind")
        vvs = S("mu_vessel_vol_sel")
        vessel_volume = int(vvs) if vvs not in (None, _MISSING) else None
        vessel_used_volume = vessel_volume
        makeup_solvent = S("makeup_solvent_val", "")
        alpha = float(S("alpha_val", DEF["alpha"]))

    return {
        "title": S("mu_title", DEF["title"]), "basis": S("mu_basis", DEF["basis"]),
        "instrument": S("mu_instrument", DEF["instrument"]),
        "matrix": S("mu_matrix", DEF["matrix"]), "analyte": S("mu_analyte", ""),
        "curve_method": S("mu_curve_method", "外标法"),
        "include_origin": S("mu_curve_include_origin") == "是",
        "force_origin": S("mu_curve_force_origin") == "是",
        "unit": S("mu_unit", "mg/kg"),
        "round_mode": S("mu_round_mode", "有效数字"), "round_nd": int(S("mu_round_nd", DEF["round_nd"])),
        "balance_id": S("mu_balance_id", ""), "balance_tol": balance_tol,
        "m_sample": m_sample, "n_weighings": int(S("mu_n_weighings", DEF["n_weighings"])),
        "makeup_mode": makeup_mode,
        "vessel_kind": vessel_kind, "vessel_volume": vessel_volume,
        "vessel_used_volume": vessel_used_volume, "vessel_tol": vessel_tol,
        "reagents": reagents,
        "makeup_solvent": makeup_solvent, "alpha": alpha,
        "dtau": S("mu_dtau", DEF["dtau"]), "env_temp": S("mu_env_temp", DEF.get("env_temp", 20.0)),
        "prep_flow": S("mu_prep_flow", ""), "influences": sc.get("mu_influences"),
    }


def _fnum(v):
    """scalar → float; None/NaN/空串/非数 → None (回填 gp 前的安全转换)。"""
    if v is None or v == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


# ---- 主: state → {method, groups, analytes, params_list, errors, warns} ----
def build_params_multi(state):
    scalars = state.get("scalars", {}) or {}
    topo_rows = state.get("topo_rows") or []
    # ④ 复选框过滤 (parity app.py:_mu_visible_rows 1240): 未勾选的标准品类型 = 该方法不用 → 全流程剔除
    _show = {"固体": scalars.get("mu_show_solid", True), "液体": scalars.get("mu_show_liquid", True)}
    topo_rows = [r for r in topo_rows if _show.get(r.get("类型") or "固体", True)]
    mu_grp_params = state.get("grp_params", {}) or {}
    meas = state.get("meas") or {}
    curve_meta = state.get("curve_meta", {}) or {}
    mu_rows = state.get("mu_rows") or {}
    method = _method_from_scalars(scalars, mu_rows)

    # groups: _rows_to_groups + 合并 grp_params (组级共享)
    groups = []
    for g in _rows_to_groups(topo_rows):
        gp = dict(g)
        gp.update(mu_grp_params.get(g["name"], {}))
        groups.append(gp)
    g_by_name = {g["name"]: g for g in groups}

    # ③ 全方法统一的标品称量天平 d(固体) + 储备液定容试剂 α(固/液) → 回填各组 gp。
    # parity app.py:_wide_table 表上方(mu_solid_bal_mg) / _mu_stock_reagent_block(stock_alpha)。
    # 前端写 mu_ scalar; 此处落各组 gp, 供 _compute_group_stock_solid(balance_tol_g/stock_alpha)
    # 与 _build_params 液体 flask_alpha/work_alpha(均 stock_alpha)读取。
    _solid_bal = _fnum(scalars.get("mu_solid_bal_mg"))
    _sa_solid = _fnum(scalars.get("mu_stock_alpha"))
    _sa_liq = _fnum(scalars.get("mu_liq_stock_alpha"))
    _work_same = scalars.get("mu_work_same_solvent", True)
    _wa_custom = _fnum(scalars.get("mu_work_alpha"))
    for g in groups:
        if g["kind"] == "solid":
            if _solid_bal is not None:
                g["balance_tol_g"] = _solid_bal / 1000.0
            if _sa_solid is not None:
                g["stock_alpha"] = _sa_solid
        elif _sa_liq is not None:
            g["stock_alpha"] = _sa_liq
        g["work_same_solvent"] = _work_same
        if not _work_same and _wa_custom is not None:
            g["work_alpha"] = _wa_custom

    # 中间液/工作液按「定容分组」跨组共享: 液体组 inter/work 覆盖为共享袋 ding[D]
    # (储备液 stock flasks[D] 仍按组; 仅中间液/工作液按 D 共享)
    mu_ding = state.get("ding", {}) or {}
    if not mu_ding:   # 旧草稿无 ding → 从 grp_params[gn].inter/work 迁出 (与前端 applyMulti 同构; 供 __main__/parity 直读草稿)
        _seen = set()
        for r in topo_rows:
            if (r.get("类型") or "固体") != "液体":
                continue
            _gn = (r.get("分组名") or "").strip()
            if not _gn or _gn in _seen:
                continue
            _seen.add(_gn)
            _gp = mu_grp_params.get(_gn, {}) or {}
            if not _gp.get("inter") and not _gp.get("work"):
                continue
            _D = str(r.get("定容分组") or "").strip() or "定容组1"
            mu_ding[_D] = mu_ding.get(_D) or {"feeds": {}, "flasks": {}, "work": {}}
            _inter = _gp.get("inter") or {}
            _fds = _inter.get("feeds") or {}
            _fd = _fds.get(_D) or next(iter(_fds.values()), None)
            if _fd:
                mu_ding[_D]["feeds"][_gn] = _fd
            if _inter.get("flasks"):
                mu_ding[_D]["flasks"].update(_inter["flasks"])
            if _gp.get("work"):
                mu_ding[_D]["work"].update(_gp["work"])
    _liq_dg = {}
    for r in topo_rows:
        if (r.get("类型") or "固体") != "液体":
            continue
        _gn = (r.get("分组名") or "").strip()
        if _gn and _gn not in _liq_dg:
            _liq_dg[_gn] = str(r.get("定容分组") or "").strip() or "定容组1"
    for g in groups:
        if g["kind"] != "liquid":
            continue
        _prep = mu_ding.get(_liq_dg.get(g["name"], "1")) or {}
        g["inter"] = _prep
        g["work"] = _prep.get("work", {})

    # analytes: topo 行 → 逐物 dict (纯度/证书列映射)
    _TOPO_KEYMAP = {"纯度p": "purity", "U_purity": "U_purity", "k_purity": "k_purity",
                    "m_std(g)": "m_std_g",
                    "Urel%": "Urel_cert", "C_cert": "C_cert", "U_abs": "U_abs", "k_cert": "k_cert",
                    "定容分组": "ding_group",
                    "储备液容量瓶(mL)": "stock_flask"}
    analytes = []
    for r in topo_rows:
        nm = (r.get("目标物") or "").strip()
        if not nm:
            continue
        a = {"name": nm, "group": (r.get("分组名") or "").strip()}
        for tk, ek in _TOPO_KEYMAP.items():
            if r.get(tk) is not None:
                a[ek] = r[tk]
        analytes.append(a)

    errors, warns = [], []
    # 分组名跨类型撞名 (根因防护): _rows_to_groups 按名合并 + kind 取首个 → 同名固/液被合成一组、错类型处理
    _seen_kind = {}
    for r in topo_rows:
        gn = (r.get("分组名") or "").strip()
        if not gn:
            continue
        k = _KIND_FROM_CN.get((r.get("类型") or "固体").strip() or "固体", "solid")
        if gn in _seen_kind and _seen_kind[gn] != k:
            errors.append(f"分组名「{gn}」同时含固体与液体: 模型要求每分组名单一类型, 请拆分")
        else:
            _seen_kind[gn] = k
    # 混合法 stock_alpha 只填一个 → 未填的那个静默回退样液 α (固/液溶剂可能不同)
    if any((r.get("类型") or "固体") == "固体" for r in topo_rows) and \
       any((r.get("类型") or "固体") == "液体" for r in topo_rows):
        if _sa_solid is None and _sa_liq is not None:
            warns.append("固体储备液 α(mu_stock_alpha) 未填, 按样液 α 计算; 固/液溶剂不同时请在③区分别填写")
        elif _sa_liq is None and _sa_solid is not None:
            warns.append("液体储备液 α(mu_liq_stock_alpha) 未填, 按样液 α 计算; 固/液溶剂不同时请在③区分别填写")
    has_source = bool(meas)                                  # meas 非空 = 有来源(草稿/上传); {} = 无 → 降级
    default_cm = scalars.get("mu_curve_method", "外标法")
    _V = method.get("vessel_volume")
    _exp = UNIT_EXP.get(method.get("unit", "mg/kg"))
    _rm = method.get("round_mode", "有效数字")
    _nd = int(method.get("round_nd", 3))
    for a in analytes:
        m = meas.get(a["name"])
        if m:
            for k in ("X", "p", "x_pred", "points", "replicates", "recovery"):
                a[k] = m[k]
            a["curve_method"] = m.get("curve_method", "外标法")
            a["is_name"] = m.get("is_name", "")
            if m.get("spike_C"):                             # ⑥ 新格式: 原始 加标C/m → 派生 测定值/回收率
                a["p"] = len(m["spike_C"])
                a["x_pred"] = sum(m["spike_C"]) / len(m["spike_C"])
                a["X"] = None
                c_std, v_add = m.get("spike_std_conc"), m.get("spike_add_vol")
                a["spike_std_conc"], a["spike_add_vol"] = c_std, v_add
                if c_std and v_add and _V and _exp is not None:
                    c0 = c_std * v_add * 1e-3 / _V
                    a["replicates"], a["recovery"] = _derive_spike_rw(
                        m["spike_C"], m["spike_m"], _V, _exp, c0, _rm, _nd)
                    _ms = method.get("m_sample")
                    if _ms and not _is_na(_ms) and _ms > 0:
                        _rnd_fn = round_sf if _rm == "有效数字" else round_dp
                        a["spike_add_mass"] = _rnd_fn(c_std * v_add * 1e-3 / _ms * 10 ** _exp, _nd)
                else:
                    errors.append(f"{a['name']}: ⑥新格式需 各物标液浓度/加标体积 + ③定容V 才能算 测定值/回收率")
        elif has_source:
            errors.append(f"{a['name']}: 上传 Excel 缺该目标物测量数据")
        else:                                                # 无任何来源 → 测量数据留空(引擎降级)
            pm = curve_meta.get(a["name"], {})
            a["curve_method"] = pm.get("method") or default_cm
            a["is_name"] = pm.get("is_name", "")
            a.update({"X": None, "p": None, "x_pred": None,
                      "points": [], "replicates": [], "recovery": []})
    extra = sorted(set(meas) - {a["name"] for a in analytes})
    if extra:
        warns.append(f"Excel 有而页面无的目标物(忽略): {', '.join(extra)}")

    if not analytes:
        errors.append("目标物表为空 (④ 表未填目标物)")
    for a in analytes:
        g = g_by_name.get(a["group"])
        if not g:
            errors.append(f"{a['name']}: 分组「{a['group']}」不存在")
            continue
        if g["kind"] == "solid":
            for req in ("purity", "U_purity", "k_purity"):
                if not a.get(req):
                    errors.append(f"{a['name']}(solid): 缺 {req} (④ 表纯度列)")
            if not a.get("m_std_g"):
                errors.append(f"{a['name']}(solid): 缺 称样量 m_std (④ 表 m_std(g) 列)")
            if not a.get("stock_flask") and not g.get("flask_volume_mL"):
                errors.append(f"{a['name']}(solid): 缺 储备液容量瓶 (④ 表容量瓶列 或 该组折叠)")
        else:
            cm = g.get("cert_mode", "relative")
            _dg = a.get("ding_group") or "定容组1"
            if _dg not in g.get("flasks", {}):
                errors.append(f"{a['name']}(liquid): 定容分组「{_dg}」缺储备液参数(④储备液标签页该组折叠)")
            elif cm == "relative":
                if not a.get("Urel_cert") or not g.get("k_cert"):
                    errors.append(f"{a['name']}(liquid/relative): 缺 Urel%(表) 或 k_cert(该组折叠)")
            elif not a.get("C_cert") or not a.get("U_abs") or not g.get("k_cert"):
                errors.append(f"{a['name']}(liquid/absolute): 缺 C_cert/U_abs(表) 或 k_cert(该组折叠)")
        _inter = g.get("inter") or {}
        _unit = a["group"] if g["kind"] == "liquid" else a["name"]
        _fd = (_inter.get("feeds") or {}).get(_unit)
        if _fd and float(_fd.get("pip_vol") or 0) > 0 and _fd.get("dg") not in (_inter.get("flasks") or {}):
            errors.append(f"{a['name']}: 中间液分组「{_fd.get('dg')}」缺容量瓶(中间液标签页该分组下拉)")
    if _is_na(method.get("m_sample")) or method.get("m_sample") <= 0:
        errors.append("称样量必须 > 0")
    _mm = method.get("makeup_mode", "single")
    if _mm == "multi":
        if not method.get("reagents"):
            errors.append("多次定容: 样液定容试剂表为空 (② 表)")
    else:
        if not method.get("vessel_kind") or method.get("vessel_kind") not in KIND_LABELS:
            errors.append(f"量器类型非法 ({method.get('vessel_kind')})")
        if _mm == "mixed" and not method.get("reagents"):
            errors.append("混合试剂: 样液定容溶剂表为空 (② 表)")
    if errors:
        return {"method": method, "groups": groups, "analytes": analytes,
                "params_list": [], "errors": errors, "warns": warns}

    # 固体分组预算 u_stock: 称量/纯度各物独立, 定容(容量瓶)逐物取自身行 (物理上各自定容一瓶)
    for g in groups:
        if g["kind"] == "solid":
            _compute_group_stock_solid(g, [a for a in analytes if a["group"] == g["name"]], method)
    params_list = [_build_params(method, g_by_name[a["group"]], a) for a in analytes]
    return {"method": method, "groups": groups, "analytes": analytes,
            "params_list": params_list, "errors": [], "warns": warns}


# ==== AI 自动填充 (移植 app.py _ai_apply_multi 795-843; 去 st.*, 写 mu_ 标量) ====
def apply_ai_multi(prep_flow_text):
    """多物质: AI 解析前处理流程 → 回填 mu_* 称样量/称量次数/定容 + 影响量。
    单溶剂→单一溶剂定容(单器皿); 多溶剂→多次定容(mu_rows.reag, 各试剂独立量器/α)。"""
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

    sc, filled, notes = {}, [], []
    if r["m_sample"] is not None and math.isfinite(r["m_sample"]):
        sc["mu_m_sample_raw"] = f"{r['m_sample']:g}"
        sc["mu_balance_tol_mg"] = None                          # 让前端 d 随新 m 重取
        filled.append(f"称样量 m={r['m_sample']:g} g")
    if r["n_weighings"]:
        sc["mu_n_weighings"] = int(r["n_weighings"])
    info = ""
    if r.get("influences"):
        info = "、".join(r["influences"])
        sc["mu_influences"] = info
    vessels = _vessels_of(r)
    mu_rows = None
    if vessels:
        if len(vessels) == 1:
            vs = vessels[0]
            sel, custom, msg = _map_vessel(vs["kind"], vs["volume"], allow_custom=False)
            notes.append(msg)
            if sel is not None:
                sc["mu_vessel_kind"] = vs["kind"]
                sc["mu_vessel_vol_sel"] = sel
                filled.append("定容量器=" + _vessel_echo(vs["kind"], sel, custom))
            if vs["solvent"]:
                _ai_fill_solvent(vs["solvent"], filled, notes, vs.get("cas"), vs.get("alpha"), sc)
                # _ai_fill_solvent 写单模式键 (solvent_preset/makeup_solvent_val/alpha_val) — 多模式同键复用
        else:                                                   # 多溶剂 → 多次定容 (分次加入不同试剂)
            sc["mu_makeup_mode"] = "multi"
            reag = []
            for v in vessels:
                _a = v.get("alpha")
                if _a is None and v.get("solvent"):          # 库内查 α
                    hits = solvents.lookup(v["solvent"])
                    _a = hits[0]["alpha"] if hits else None
                if _a is None:
                    _a = 0.00119
                    notes.append(f"试剂「{v.get('solvent')}」α 未识别, 已填默认 {_a:g}, 请核对。")
                vk = v.get("kind") if v.get("kind") in KIND_LABELS else "pip_s"
                vol = v.get("volume")
                reag.append({"s": v.get("solvent") or "自定义", "k": vk,
                             "v": int(round(vol)) if vol else 5,
                             "vi": vol if vol is not None else 5, "a": _a})
            mu_rows = {"blend": [], "reag": reag}
            vsum = sum(v["volume"] for v in vessels if v["volume"]) or None
            names = "、".join(v["solvent"] for v in vessels if v["solvent"]) or None
            filled.append(f"多次定容(ΣVi={vsum:g}mL): {names or '多试剂'}")
            notes.append("多溶剂已按「多次定容」填入样液定容试剂表, 请核对各量器/α。")
    if r["note"]:
        notes.append(f"AI 依据: {r['note']}")
    out = {"scalars": sc, "filled": filled, "notes": notes, "info": info}
    if mu_rows is not None:
        out["mu_rows"] = mu_rows
    return out


if __name__ == "__main__":
    import json
    import glob
    cand = sorted(glob.glob(os.path.join(ROOT, "drafts", "multi", "*.json")))
    if not cand:
        print("(无 drafts/multi/*.json)")
        raise SystemExit(0)
    from uncertainty import mup_cg248
    for fp in cand:
        with open(fp, encoding="utf-8") as f:
            st = json.load(f)
        out = build_params_multi(st)
        print(f"\n=== {os.path.basename(fp)}: 目标物 {len(out['analytes'])}  分组 {len(out['groups'])} ===")
        if out["errors"]:
            for e in out["errors"][:6]:
                print("  ERR:", e)
            continue
        for a, p in zip(out["analytes"], out["params_list"]):
            res = mup_cg248(p)
            print(f"  {a['name']:>12}  U={res.get('U')!r}  X={res.get('X')!r}  urel_w={res.get('urel_w')!r}")
