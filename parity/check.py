# -*- coding: utf-8 -*-
"""
parity 自检 (无框架, 可跑 main)。先起服务: python server.py, 再跑:
  .venv/Scripts/python parity/check.py

两条检查:
  1. engine  — POST /api/calc/engine(BASELINE_PARAMS) 深等于直调 mup_cg248  (验 HTTP+引擎)
  2. build   — POST /api/calc/single(draft 111 的 state) 的 U/X/urel_w == 真 Streamlit golden
               (golden 由 parity/golden_streamlit.py 用 AppTest 跑 mup/app.py 取得, 已逐位对齐)
"""
import json
import os
import sys
import urllib.request
from decimal import Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))

from uncertainty import mup_cg248, BASELINE_PARAMS  # noqa: E402

BASE = "http://127.0.0.1:8000"

# draft 111 的真 Streamlit golden (AppTest 跑 mup/app.py 取得, 2026-07-17)
GOLDEN_111 = {"U": 1.516963648543781, "X": 16.1, "urel_w": 0.04711067231502425}


def _default(o):
    if isinstance(o, Decimal):
        return float(o)
    if isinstance(o, (set, tuple)):
        return list(o)
    raise TypeError(f"not JSON: {type(o)}")


def _norm(obj):
    return json.loads(json.dumps(obj, default=_default))


def _post(path, body):
    req = urllib.request.Request(f"{BASE}{path}", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req))


def check_engine():
    ref = _norm(mup_cg248(BASELINE_PARAMS))
    cand = _post("/api/calc/engine", BASELINE_PARAMS)
    ok = ref == cand
    print(f"[{'OK' if ok else 'FAIL'}] engine: U={cand.get('U')} X={cand.get('X')}")
    return ok


def check_build():
    with open(os.path.join(HERE, "..", "drafts", "111.json"), encoding="utf-8") as f:
        state = json.load(f)
    r = _post("/api/calc/single", state)["result"]
    ok = (abs(r["U"] - GOLDEN_111["U"]) < 1e-12 and r["X"] == GOLDEN_111["X"]
          and abs(r["urel_w"] - GOLDEN_111["urel_w"]) < 1e-15)
    print(f"[{'OK' if ok else 'FAIL'}] build(111): U={r['U']} X={r['X']} urel_w={r['urel_w']}  "
          f"(golden U={GOLDEN_111['U']})")
    return ok


def check_multi(name="mixed_solid_liq"):
    """多目标物: engine_multi 装配草稿 → 逐物 mup_cg248 → render_multi md
    逐字等于 golden_multi_{name}_md.txt。mixed_solid_liq 为固+液混合回归门
    (golden 由本仓 build_params_multi+mup_cg248+render_multi 快照, 2026-07-20)。"""
    sys.path.insert(0, os.path.join(HERE, ".."))
    from engine_multi import build_params_multi  # noqa: E402
    from gen_report import render_multi  # noqa: E402
    with open(os.path.join(HERE, "..", "drafts", "multi", f"{name}.json"), encoding="utf-8") as f:
        state = json.load(f)
    out = build_params_multi(state)
    if out["errors"]:
        print(f"[FAIL] multi({name}): 装配报错 {out['errors'][:3]}")
        return False
    results = [mup_cg248(p) for p in out["params_list"]]
    md = render_multi(out["method"], out["groups"], out["analytes"], results)
    with open(os.path.join(HERE, f"golden_multi_{name}_md.txt"), encoding="utf-8") as f:
        golden = f.read()
    ok = md.strip() == golden.strip()
    print(f"[{'OK' if ok else 'FAIL'}] multi({name}): md {len(md)} chars vs golden {len(golden)}  "
          f"({len(out['analytes'])} 物 {len(out['groups'])} 组)")
    if not ok:
        for i, (a, b) in enumerate(zip(md, golden)):
            if a != b:
                lo = max(0, i - 30)
                print(f"  首差 @ {i}: cand={md[lo:i+30]!r}\n         golden={golden[lo:i+30]!r}")
                break
        if len(md) != len(golden):
            print(f"  长度差: cand={len(md)} golden={len(golden)}")
    return ok


if __name__ == "__main__":
    only = sys.argv[1] if len(sys.argv) > 1 else None
    if only == "multi":
        sys.exit(0 if check_multi(sys.argv[2] if len(sys.argv) > 2 else "mixed_solid_liq") else 1)
    ok = check_engine() and check_build() and check_multi()
    sys.exit(0 if ok else 1)
