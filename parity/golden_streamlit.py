# -*- coding: utf-8 -*-
"""golden: 用 Streamlit AppTest 无头跑 mup/app.py + 注入 111 草稿 → 点生成报告 → 取真实结果。
run: E:\\AI\\mup\\.venv\\Scripts\\python.exe E:\\AI\\mup-web\\parity\\golden_streamlit.py"""
import json
import os
import sys

MUP = r"E:\AI\mup"
os.chdir(MUP)
sys.path.insert(0, MUP)
import pandas as pd  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

d = json.load(open(os.path.join(MUP, "drafts", "111.json"), encoding="utf-8"))
at = AppTest.from_file(os.path.join(MUP, "app.py"), default_timeout=60)
# 预置 session_state (对齐 _load_draft: 标量 + 3 个 editor holder)
for k, v in d.get("scalars", {}).items():
    if v is not None:
        at.session_state[k] = v
ed = d.get("editors", {})
at.session_state["work_df_df"] = pd.DataFrame(ed.get("work_df", []))
at.session_state["points_df_df"] = pd.DataFrame(ed.get("points_df", []))
at.session_state["spike_ed_df"] = pd.DataFrame(ed.get("spike_df", []))
at.session_state["current_draft"] = "111"
at.run()

btn = next((b for b in at.button if b.label == "生成报告"), None)
if btn is None:
    print("NO 生成报告 button; errors:", [e.value for e in at.exception])
    sys.exit(2)
btn.click().run()

print("=== Streamlit AppTest golden (draft 111) ===")
for m in at.metric:
    print(f"metric: {m.label} = {m.value}")
for s in at.success:
    print("success:", s.value)
for e in at.exception:
    print("EXC:", e.value)
