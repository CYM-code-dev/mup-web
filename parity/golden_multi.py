# -*- coding: utf-8 -*-
"""golden_multi: AppTest 跑 mup/app.py 多目标物 + 注入草稿 → 取 render_multi md。
有 meas 时注入 mu_excel_load (Streamlit 用作来源, 对齐 multi_form 的 cached 分支)。
run: E:\\AI\\mup\\.venv\\Scripts\\python.exe golden_multi.py [草稿名]"""
import json
import os
import sys

MUP = r"E:\AI\mup"
HERE = os.path.dirname(os.path.abspath(__file__))
NAME = sys.argv[1] if len(sys.argv) > 1 else "parity_demo"
os.chdir(MUP)
sys.path.insert(0, MUP)
import pandas as pd  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

DRAFT = os.path.join(HERE, "..", "drafts", "multi", f"{NAME}.json")
d = json.load(open(DRAFT, encoding="utf-8"))

at = AppTest.from_file(os.path.join(MUP, "app.py"), default_timeout=60)
for k, v in d.get("scalars", {}).items():
    if v is not None:
        at.session_state[k] = v
at.session_state["mu_topo_rows"] = d["topo_rows"]
at.session_state["mu_grp_params"] = d["grp_params"]
at.session_state["mu_curve_meta"] = d["curve_meta"]
at.session_state["current_mu_draft"] = NAME
if d.get("meas"):                                   # 有测量数据 → Streamlit 用作 Excel 来源
    at.session_state["mu_excel_load"] = d["meas"]
at.run()

mr = next((r for r in at.radio if "多目标物" in (r.options or [])), None)
if mr is None:
    print("NO 模式 radio; exc:", [e.value for e in at.exception])
    sys.exit(2)
mr.set_value("多目标物").run()

excs = [str(e.value) for e in at.exception]
succ = [s.value for s in at.success]
print(f"=== golden_multi ({NAME}) ===")
print("success:", succ)
print("exceptions:", excs)
mds = [m.value for m in at.markdown]
golden_md = max(mds, key=len) if mds else ""
print("md blocks:", len(mds), " longest:", len(golden_md), " chars")
out = os.path.join(HERE, f"golden_multi_{NAME}_md.txt")
with open(out, "w", encoding="utf-8") as f:
    f.write(golden_md)
print("wrote", os.path.basename(out))
