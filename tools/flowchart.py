# -*- coding: utf-8 -*-
"""前处理流程文本 → 纵向流程图 PNG (仿模板: 白底黑框方框 + ↓ 箭头, 宋体).

供 gen_docx 在 1.5 测定程序处嵌入。输入 prep_flow 文本, 输出 PNG。
matplotlib 未装, 用 PIL (已装) + Windows 宋体绘制。
"""
import os
import re

from PIL import Image, ImageDraw, ImageFont

_FONTS = [r"C:\Windows\Fonts\simsun.ttc", r"C:\Windows\Fonts\msyh.ttc",
          r"C:\Windows\Fonts\simhei.ttf"]


def _load_font(size):
    for p in _FONTS:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def _steps(text):
    """前处理流程文本 → 有序步骤 (按 →/➜/；/序号/。 切, 去前缀)。"""
    if not text or not text.strip():
        return []
    s = re.sub(r"^\s*\d+\s*[.、)]\s*", "", text.strip())
    parts = [p.strip() for p in re.split(r"[→➜➝；;]|->", s) if p.strip()]
    parts = [re.sub(r"^[①②③④⑤⑥⑦⑧⑨⑩]\s*", "", p) for p in parts]
    if len(parts) == 1 and "。" in parts[0]:
        parts = [p.strip() for p in parts[0].split("。") if p.strip()]
    return parts


def _wrap(text, font, max_w, draw):
    """中文按字符断行到 max_w 像素宽。"""
    lines, cur = [], ""
    for ch in text:
        if draw.textlength(cur + ch, font=font) <= max_w:
            cur += ch
        else:
            if cur:
                lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return lines or [""]


def make(text, out_path, box_w=380, p_w=520, r_w=300, pad=22, varrow=60, varrow2=30, hgap=180, margin=40, max_pt=12, embed_in=5.4):
    """生成分支流程图 PNG (用户订正):
    左[前处理](宽框 p_w) ‖ 右[标准溶液配制]→[曲线拟合](窄框 r_w) 两支,
    前处理+曲线拟合 同汇入 [结果](box_w); [结果]居中在左右分支之间, 两路对称拐入。
    p_w=前处理框宽(宽), r_w=标液/曲线框宽(窄), varrow=标液→曲线间距, varrow2=曲线→结果间距。
    字号由 max_pt(默认小四=12pt) × embed_in 反算, 保证图中最大字号不超过 max_pt。"""
    steps = _steps(text)
    if not steps:
        return False
    inner_w = box_w - pad * 2
    p_inner_w = p_w - pad * 2
    r_inner_w = r_w - pad * 2
    dummy = Image.new("RGB", (10, 10))
    dd = ImageDraw.Draw(dummy)

    # 反算字号使 doc 中 ≤ max_pt(小四=12pt): 图宽 W=p_w+hgap+r_w+2·margin, doc_pt = font_px·72·embed_in/W
    font_size = int(max_pt * (p_w + hgap + r_w + 2 * margin) / (72 * embed_in))

    def meas(s, fsize, iw):
        f = _load_font(fsize)
        lh = fsize + 14
        ln = _wrap(s, f, iw, dd)
        return ln, lh * len(ln) + pad * 2, f, lh

    prep = "；".join(steps)
    s_ln, s_h, s_font, s_lh = meas("标准溶液配制", font_size, r_inner_w)
    q_ln, q_h, q_font, q_lh = meas("曲线拟合", font_size, r_inner_w)
    r_ln, r_h, r_font, r_lh = meas("结果", font_size, inner_w)
    right_h = s_h + varrow + q_h                     # 右列总高 = 前处理目标高
    chosen = None
    for fs in range(font_size, 12, -2):              # 缩字号直到前处理高 ≤ 右列高
        chosen = meas(prep, fs, p_inner_w)
        if chosen[1] <= right_h:
            break
    p_ln, p_h, p_font, p_lh = chosen

    cL = margin + p_w // 2                          # 前处理 中心 (左, 宽框 p_w)
    cS = cL + p_w // 2 + hgap + r_w // 2            # 右轴 中心 (标液/曲线, 窄框 r_w)
    cR = (cL + cS) // 2                              # 结果 中心 (左右分支中间)
    W = cS + r_w // 2 + margin
    top = 30
    yS = top
    yQ = yS + s_h + varrow
    yP = max(top, top + (right_h - p_h) // 2)        # 前处理 垂直居中对齐右列
    yR = top + right_h + varrow2                       # 曲线→结果 间距 (独立, 较标液→曲线短)
    H = yR + r_h + margin

    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)
    bw = 2

    def draw_box(x, y, ln, h, f, lh, center=False, w=box_w):
        draw.rectangle([x, y, x + w, y + h], outline="black", width=bw)
        ty = y + (h - lh * len(ln)) // 2 if center else y + pad
        for l in ln:
            tx = x + (w - draw.textlength(l, font=f)) // 2 if center else x + pad
            draw.text((tx, ty), l, fill="black", font=f)
            ty += lh

    def arrow_down(x, y1, y2):
        draw.line([x, y1, x, y2 - 18], fill="black", width=bw)
        draw.polygon([(x, y2), (x - 14, y2 - 22), (x + 14, y2 - 22)], fill="black")

    def arrow_right(x1, x2, y):
        draw.line([x1, y, x2 - 18, y], fill="black", width=bw)
        draw.polygon([(x2, y), (x2 - 22, y - 14), (x2 - 22, y + 14)], fill="black")

    def arrow_left(x1, x2, y):
        draw.line([x1, y, x2 + 18, y], fill="black", width=bw)
        draw.polygon([(x2, y), (x2 + 22, y - 14), (x2 + 22, y + 14)], fill="black")

    draw_box(cL - p_w // 2, yP, p_ln, p_h, p_font, p_lh, center=False, w=p_w)  # 前处理 (左, 宽框, 左对齐)
    draw_box(cS - r_w // 2, yS, s_ln, s_h, s_font, s_lh, center=True, w=r_w)    # 标准溶液配制 (窄框, 居中)
    draw_box(cS - r_w // 2, yQ, q_ln, q_h, q_font, q_lh, center=True, w=r_w)    # 曲线拟合 (窄框, 居中)
    draw_box(cR - box_w // 2, yR, r_ln, r_h, r_font, r_lh, center=True)   # 结果 (居中, 左右分支中间)

    arrow_down(cS, yS + s_h, yQ)                     # 标液 → 曲线
    y_bus = yR + r_h // 2
    draw.line([cS, yQ + q_h, cS, y_bus], fill="black", width=bw)  # 曲线 → (下行+左拐) → 结果右侧
    arrow_left(cS, cR + box_w // 2, y_bus)
    draw.line([cL, yP + p_h, cL, y_bus], fill="black", width=bw)  # 前处理 → (下行+右拐) → 结果左侧
    arrow_right(cL, cR - box_w // 2, y_bus)

    img.save(out_path, dpi=(192, 192))
    return True


if __name__ == "__main__":
    import sys
    ok = make(sys.argv[1] if len(sys.argv) > 1
              else "称取1.00g样品→加入5mL含内标的叔丁基甲醚→超声提取30min→定容至5mL→HPLC-PDA进样分析",
              "_flowchart_preview.png")
    print("OK" if ok else "no steps", "-> _flowchart_preview.png")
