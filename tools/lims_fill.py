# -*- coding: utf-8 -*-
"""工作液溯源链 → mup 表单字段的【纯提取】（无 Streamlit / 无 app.py 依赖，可单测）。

输入: tools.lims_trace.trace_working_solution() 返回的溯源链 matched（top→bottom: A..B..C..D；
A 型标准品不入链，B 称量型为链顶并止步）。
输出: 结构化字段（储备液 + 稀释链行），仅含数值/文本，**不含量器选项标签** ——
量器选择（查实验室库存规格 VOLUMES）与标签格式化（_vsl_label）留在 app.py（那里才有这些数据），
本模块只做「链 → 字段」映射与边界判定。

约定（与 mup 单目标物 tab ③ 标准溶液 对应）:
- 链顶 matched[0] = 储备液（B；缺 B 时为最高非 A 级，当储备液处理）。
- matched[1:] = 稀释链行（C、D…），每行: 从其父级（上一条）移取 received_quantity，
  定容到 constant_volume；母液浓度 = 该行 parent_concentration（= 上一条的浓度）。
"""
import re


def _f(s):
    """字符串→float；空/解析失败→None。链里 concentration/constant_volume/received_quantity/
    parent_concentration 已是 first-number 字符串（见 lims_trace._first_number），直接 float 即可。"""
    if s is None:
        return None
    m = re.match(r'^\s*([\d.]+)', str(s))
    return float(m.group(1)) if m else None


def extract_chain_fields(chain):
    """chain: list[dict]（trace_working_solution 返回，top→bottom）。返回 dict；链空抛 ValueError。

    返回键:
      stock_source: 'solid'(称量型) | 'liquid_dilute'(高浓液标)
      m_std: solid 的称取质量(g) | None
      c_cert: liquid 的证书浓度(取 stock.parent_concentration) | None
      stock_received_qty: liquid 的移取浓标体积(mL) | None
      stock_flask_vol: 储备液容量瓶规格(constant_volume) | None
      stock_medium: 储备液定容溶剂名
      stock_name/order/level/date/validity/controlled: 储备液描述（供 UI 参考）
      dilution_rows: [{mother_conc, pip_vol, flask_vol, name, order, level, date}, ...]
      multi_source: 是否检出多源（source_details）
      info_chain: [(level, order, name, concentration, date), ...] 全链摘要
      manual: 需手补的字段名列表（纯度/U·k 等，LIMS 不含）
    """
    if not chain:
        raise ValueError("溯源链为空")
    stock = chain[0]
    dilution = chain[1:]
    manual = []

    # stock_source 判定: 称量型(B + received_unit=='g', 或 _is_weighing_top) vs 高浓液标(mL)
    ru = (stock.get("received_unit") or "").strip()
    is_solid = (ru == "g") or bool(stock.get("_is_weighing_top"))
    stock_source = "solid" if is_solid else "liquid_dilute"

    m_std = c_cert = stock_received_qty = None
    if is_solid:
        m_std = _f(stock.get("received_quantity"))
        manual += ["标准品纯度 p", "纯度扩展不确定度 U(p)", "纯度包含因子 k"]
    else:
        c_cert = _f(stock.get("parent_concentration"))
        stock_received_qty = _f(stock.get("received_quantity"))
        manual += ["证书扩展不确定度 U", "证书包含因子 k"]

    dilution_rows = []
    multi_source = False
    for r in dilution:
        if r.get("source_details"):
            multi_source = True
        dilution_rows.append({
            "mother_conc": _f(r.get("parent_concentration")),
            "pip_vol": _f(r.get("received_quantity")),
            "flask_vol": _f(r.get("constant_volume")),
            "name": (r.get("solution_name") or "").strip(),
            "order": (r.get("configure_order") or "").strip(),
            "level": (r.get("level") or "").strip(),
            "date": (r.get("configure_date") or "").strip(),
        })

    return {
        "stock_source": stock_source,
        "m_std": m_std,
        "c_cert": c_cert,
        "stock_received_qty": stock_received_qty,
        "stock_flask_vol": _f(stock.get("constant_volume")),
        "stock_medium": (stock.get("medium") or "").strip(),
        "stock_name": (stock.get("solution_name") or "").strip(),
        "stock_order": (stock.get("configure_order") or "").strip(),
        "stock_level": (stock.get("level") or "").strip(),
        "stock_date": (stock.get("configure_date") or "").strip(),
        "stock_validity": (stock.get("validity_date") or "").strip(),
        "stock_controlled": (stock.get("controlled_no") or "").strip(),
        "dilution_rows": dilution_rows,
        "multi_source": multi_source,
        "info_chain": [((r.get("level") or ""), (r.get("configure_order") or ""),
                        (r.get("solution_name") or ""), (r.get("concentration") or ""),
                        (r.get("configure_date") or "")) for r in chain],
        "manual": manual,
    }


# ---- 自检: 两段假溯源链(称量型 B / 证书液型 B), 验证字段提取正确 ----
def _selfcheck():
    # 链1: 称量型储备液 B(g) → C → D
    chain_solid = [
        {"level": "B", "configure_order": "B-3408", "solution_name": "AZO储备液",
         "concentration": "1090.02(mg/L)", "constant_volume": "10.00", "medium": "正己烷",
         "received_quantity": "0.1100", "received_unit": "g", "_is_weighing_top": True,
         "parent_concentration": "", "configure_date": "2026-01-10",
         "validity_date": "2027-01-10", "controlled_no": "CK-CG-001"},
        {"level": "C", "configure_order": "C-201", "solution_name": "AZO应用液",
         "concentration": "109.00(mg/L)", "constant_volume": "10.00", "medium": "正己烷",
         "received_quantity": "1.00", "received_unit": "mL", "_is_weighing_top": False,
         "parent_concentration": "1090.02(mg/L)", "configure_date": "2026-02-01"},
        {"level": "D", "configure_order": "D-9203", "solution_name": "AZO工作液",
         "concentration": "10.90(mg/L)", "constant_volume": "10.00", "medium": "正己烷",
         "received_quantity": "1.00", "received_unit": "mL", "_is_weighing_top": False,
         "parent_concentration": "109.00(mg/L)", "configure_date": "2026-03-01"},
    ]
    f = extract_chain_fields(chain_solid)
    assert f["stock_source"] == "solid", f
    assert f["m_std"] == 0.11, f["m_std"]
    assert f["stock_flask_vol"] == 10.0, f
    assert f["stock_medium"] == "正己烷", f
    assert len(f["dilution_rows"]) == 2, f
    assert f["dilution_rows"][0]["mother_conc"] == 1090.02, f   # C 行母液 = B 浓度
    assert f["dilution_rows"][0]["pip_vol"] == 1.0, f
    assert f["dilution_rows"][1]["mother_conc"] == 109.0, f     # D 行母液 = C 浓度
    assert "标准品纯度 p" in f["manual"], f

    # 链2: 证书液型储备液 B(mL, 由证书浓标稀释) → D
    chain_liquid = [
        {"level": "B", "configure_order": "B-5001", "solution_name": "PAE储备液",
         "concentration": "1000.00(mg/L)", "constant_volume": "10.00", "medium": "甲醇",
         "received_quantity": "1.00", "received_unit": "mL", "_is_weighing_top": False,
         "parent_concentration": "10000.00(mg/L)", "configure_date": "2026-01-15",
         "controlled_no": "CK-CG-200"},
        {"level": "D", "configure_order": "D-9300", "solution_name": "PAE工作液",
         "concentration": "100.00(mg/L)", "constant_volume": "10.00", "medium": "甲醇",
         "received_quantity": "1.00", "received_unit": "mL", "_is_weighing_top": False,
         "parent_concentration": "1000.00(mg/L)", "configure_date": "2026-02-15"},
    ]
    g = extract_chain_fields(chain_liquid)
    assert g["stock_source"] == "liquid_dilute", g
    assert g["c_cert"] == 10000.0, g
    assert g["stock_received_qty"] == 1.0, g
    assert len(g["dilution_rows"]) == 1, g
    assert g["dilution_rows"][0]["mother_conc"] == 1000.0, g
    assert "证书扩展不确定度 U" in g["manual"], g

    print("lims_fill self-check OK")


if __name__ == "__main__":
    _selfcheck()
