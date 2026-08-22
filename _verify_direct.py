# -*- coding: utf-8 -*-
"""_verify_direct: 多目标物·液体标准品「直接稀释到工作液各点位」自检。

变体A(储备液行留空): u_stock = 证书浓度单项; 变体B(填移液+定容): u_stock = 证书+移取+定容三项。
点位 = work 链各行 (母液=储备液/标品, feeds 不参与); 报告 render_multi 含直接稀释叙事/流程表;
旧形状(无 direct 键)回归不变。
run: .venv/Scripts/python _verify_direct.py
"""
import math

import engine_multi
from engine_multi import build_params_multi
from uncertainty import mup_cg248, dilution_budget
from gen_report import render_multi

FLASK10 = "10 mL 容量瓶(A)(±0.02)"


def _state(stock_prep, absolute=False):
    """最小液体组 multi state: 1 组 2 目标物, ding[定容组1] 直接稀释, work 链 5 个点位。"""
    fl = {"pip_vessel": None, "pip_kind": None, "pip_nominal": None,
          "pip_vol": None, "flask_vol": None}
    if stock_prep:   # 变体B: 先配储备液 (5 mL 单标吸量管 → 10 mL 容量瓶)
        fl.update(pip_vessel="5 mL 单标吸量管(A)(±0.015)", pip_vol="5.00",
                  flask_vessel=FLASK10, flask_vol=10)
    rows = []
    for nm in ("A", "B"):
        r = {"分组名": "液1", "类型": "液体", "目标物": nm, "定容分组": "定容组1"}
        if absolute:
            r.update({"C_cert": 100, "U_abs": 2})
        else:
            r.update({"Urel%": 2})
        rows.append(r)
    pts = [("1 mL 单标吸量管(A)(±0.007)", "1.00"), ("2 mL 单标吸量管(A)(±0.01)", "2.00"),
           ("5 mL 单标吸量管(A)(±0.015)", "5.00"), ("5 mL 单标吸量管(A)(±0.015)", "5.00"),
           ("10 mL 单标吸量管(A)(±0.02)", "10.00")]
    wrows = [{"母液浓度(mg/L)": 100, "pip_vessel": v, "pip_vol": p, "flask_vessel": FLASK10}
             for v, p in pts]
    meas = {nm: {"X": 4.0, "p": 5, "x_pred": 4.0,
                 "points": [[1, 10], [2, 21], [4, 39], [8, 81], [10, 100]],
                 "replicates": [3.9, 4.0, 4.1], "recovery": [0.98, 1.0, 1.02],
                 "curve_method": "外标法"} for nm in ("A", "B")}
    return {
        "scalars": {"mu_show_liquid": True, "mu_show_solid": False,
                    "mu_m_sample_raw": "1.0", "mu_vessel_kind": "flask",
                    "mu_vessel_vol_sel": 10, "mu_curve_method": "外标法",
                    "mu_liq_stock_alpha": 0.00119, "mu_work_same_solvent": True},
        "topo_rows": rows,
        "grp_params": {"液1": {"kind": "liquid", "cert_mode": "absolute" if absolute else "relative",
                               "k_cert": 2, "flasks": {"定容组1": fl}}},
        "ding": {"定容组1": {"direct": True, "feeds": {}, "flasks": {},
                             "work": {"点位": wrows}}},
        "meas": meas, "curve_meta": {},
    }


def _run(state):
    out = build_params_multi(state)
    assert not out["errors"], out["errors"]
    res = [mup_cg248(p) for p in out["params_list"]]
    return out, res


# ---- 变体A: 储备液行留空 → u_stock = 证书浓度单项 ----
out, res = _run(_state(False))
u_cert_rel = 2.0 / (2 * 100.0)                      # Urel=2%, k=2 → 2/(k·100)
assert math.isclose(res[0]["u_stock"], u_cert_rel, rel_tol=1e-12), res[0]["u_stock"]
wd = res[0]["work_detail"]
assert len(wd) == 5, len(wd)                        # 同器合并: 4 档移液 (5mL×2) + 容量瓶×5
assert sum(d["n"] for d in wd if d.get("role") == "makeup") == 5
assert sum(d["n"] for d in wd if d.get("role") != "makeup") == 5
# u_work 与逐点位 uses 手算一致 (dilution_budget 同源对账)
ops = []
for r in out["groups"][0]["inter"]["work"]["点位"]:
    ops.append(("pip", r["pip_vessel"], float(r["pip_vol"])))
    ops.append(("flask", FLASK10, None))
u_w_manual, _ = dilution_budget(engine_multi._uses_from_ops(ops), alpha=0.00119)
assert math.isclose(res[0]["u_work"], u_w_manual, rel_tol=1e-12), (res[0]["u_work"], u_w_manual)
md = render_multi(out["method"], out["groups"], out["analytes"], res)
assert "直接由买来的高浓液标准品移取定容制得" in md
assert "直接稀释制得（非逐级）" in md
assert "工作液直接稀释过程中使用了" in md
assert "母液浓度（mg/L）" in md                       # 流程表头
print("变体A (标品直用): u_stock=%.6g (纯证书)  u_work=%.6g (10 量器项)  OK" % (res[0]["u_stock"], res[0]["u_work"]))

# ---- 变体B: 储备液行填 移液+定容 → u_stock = 证书+移取浓标+定容 三项 ----
out_b, res_b = _run(_state(True, absolute=True))
sd = dict(res_b[0]["stock_detail"])
assert set(sd) == {"证书浓度", "移取浓标", "定容"}, set(sd)
three = math.sqrt(sum(v ** 2 for v in sd.values()))
assert math.isclose(res_b[0]["u_stock"], three, rel_tol=1e-9)
md_b = render_multi(out_b["method"], out_b["groups"], out_b["analytes"], res_b)
assert "储备液由高浓液标准确移取后定容制得" in md_b      # 报告侧 3 来源叙事 (UI 只写 pip_vessel → 串名判型)
assert "A（50.00）" in md_b                           # 母液 = C_cert 100 × 5/10
print("变体B (先配储备液): u_stock=%.6g (证书+移取+定容)  流程表母液 A（50.00） OK" % res_b[0]["u_stock"])

# ---- 回归: 无 direct 键的旧形状 → 不走直接稀释叙事 ----
st_old = _state(False)
del st_old["ding"]["定容组1"]["direct"]
out_o, res_o = _run(st_old)
md_o = render_multi(out_o["method"], out_o["groups"], out_o["analytes"], res_o)
assert "直接稀释制得" not in md_o
print("回归 (无 direct 键): 直接稀释叙事不出现 OK")

print("ALL OK")
