# -*- coding: utf-8 -*-
"""
不确定度报告 .docx 生成器

基于实验室模板骨架 (_uncertainty_template.docx, 已剥离正文/图片, 仅留样式与页面
设置) 生成 Word: 套用模板的 Heading 1/2/3 + Normal(12pt) + Table Grid, A4 页边距,
使输出与范本格式一致。分析师核对数值后可直接用。

可选传入 prep_flow (前处理流程文本): 在「测量模型」前插入 1.5 测定程序流程图
(原生表格框 + ↓ 箭头, 可编辑, 无图片依赖)。
"""
import io
import os
import re

from docx.oxml.ns import qn
from docx.oxml import parse_xml
from omml import from_latex, add_eq

_TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_uncertainty_template.docx")
_CAUSE_EFFECT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_cause_effect.jpeg")


def _add_opara(doc, omml_xml):
    """把 <m:oMath> 包成 <m:oMathPara> (居中, 显示样式), 放进一个新段落 (w:p > m:oMathPara).
    oMathPara 必须是 w:p 的子节点 (直接挂 body 会被 Word 拒绝)."""
    xml = ('<m:oMathPara xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">'
           '<m:oMathParaPr><m:jc m:val="center"/></m:oMathParaPr>'
           + omml_xml + '</m:oMathPara>')
    p = doc.add_paragraph()
    p._p.append(parse_xml(xml))


def _set_font(run, cn="宋体", en="Times New Roman"):
    """显式设置 run 中英文字体 (匹配范本: 正文中文宋体, ASCII 宋体)。"""
    run.font.name = en
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = rPr.makeelement(qn("w:rFonts"), {})
        rPr.insert(0, rFonts)
    rFonts.set(qn("w:ascii"), en)
    rFonts.set(qn("w:hAnsi"), en)
    rFonts.set(qn("w:eastAsia"), cn)


def _add_image(doc, path, width_in=5.5):
    """居中插入图片 (第3节因果图等)。"""
    from docx.shared import Inches
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(path, width=Inches(width_in))


def _add_inline(paragraph, text):
    """段内渲染: $..$→内联 OMML 公式, √N→原生根号, **粗体**→加粗, <br>→换行; 统一宋体。
    √N 单独走 OMML 根号, 避免宋体 U+221A 显示成勾号。"""
    for pi, part in enumerate(text.split("<br>")):
        if pi > 0:
            paragraph.add_run().add_break()      # <br> → 段内换行 (表头两行等)
        for seg in re.split(r"(\$[^$]+\$|√\d*)", part):
            if not seg:
                continue
            if seg.startswith("$") and seg.endswith("$") and len(seg) > 2:
                latex = seg[1:-1]
                try:
                    add_eq(paragraph, from_latex(latex))
                except Exception:
                    _set_font(paragraph.add_run(_pretty_formula(latex)))
                continue
            if seg.startswith("√"):
                n = seg[1:]
                try:
                    add_eq(paragraph, from_latex("\\sqrt{%s}" % n))
                except Exception:
                    _set_font(paragraph.add_run(seg))
                continue
            for i, s in enumerate(seg.split("**")):
                if s == "":
                    continue
                run = paragraph.add_run(s)
                run.bold = bool(i % 2)
                _set_font(run)


def _add_flowchart_img(doc, prep_flow):
    """1.5 测定程序: PIL 生成纵向流程图 PNG (仿模板方框+箭头) 嵌入。
    替代旧 native-table 版, 视觉与模板图片流程图一致, 且反映实际 prep_flow。"""
    import tempfile
    from flowchart import make as fc_make
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    tmp.close()
    try:
        if fc_make(prep_flow, tmp.name):
            _add_image(doc, tmp.name, width_in=5.4)
    finally:
        try:
            os.remove(tmp.name)
        except OSError:
            pass


def _set_header_field(doc, label, value):
    """改页眉表格某字段值 (按中间列标签定位: 'Reference'/'Date'/'Author(s)' 等)。
    清原 run 重写, 保留宋体, 字号 8pt。"""
    from docx.shared import Pt
    if value is None:
        return
    for s in doc.sections:
        for t in s.header.tables:
            for row in t.rows:
                cells = row.cells
                if len(cells) >= 3 and cells[1].text.strip() == label:
                    p = cells[2].paragraphs[0]
                    for r in list(p.runs):
                        r._element.getparent().remove(r._element)
                    run = p.add_run(str(value))
                    _set_font(run)
                    run.font.size = Pt(8)


def _add_page_footer(doc):
    """页脚右下角页码 (右对齐)。单域 PAGE + 数字图片开关 \\# "- 0 -" → "- n -";
    短横线属于域格式, 不用游离 dash 文本 (避免重复)."""
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    for s in doc.sections:
        footer = s.footer
        footer.is_linked_to_previous = False
        p = footer.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        for r in list(p._p.findall(qn("w:r"))):
            p._p.remove(r)

        def _fld(kind):
            r = OxmlElement("w:r")
            fc = OxmlElement("w:fldChar"); fc.set(qn("w:fldCharType"), kind); r.append(fc)
            return r

        def _instr(t):
            r = OxmlElement("w:r")
            it = OxmlElement("w:instrText"); it.set(qn("xml:space"), "preserve"); it.text = t; r.append(it)
            return r

        def _txt(t):
            r = OxmlElement("w:r")
            tt = OxmlElement("w:t"); tt.set(qn("xml:space"), "preserve"); tt.text = t; r.append(tt)
            return r

        # 单域: PAGE 用图片开关 "- 0 -" → "- 1 -"; 缓存结果 "- 1 -" 供未更新时显示
        for el in (_fld("begin"), _instr(' PAGE \\# "- 0 -" '),
                   _fld("separate"), _txt("- 1 -"), _fld("end")):
            p._p.append(el)


def _pretty_formula(s):
    """把 $$...$$ 里的 LaTeX 展平成可读文本 (不引公式库; 分析师在 Word 里再排)。"""
    s = s.strip().strip("$").strip()
    s = s.replace("\\dfrac", "").replace("\\frac", "").replace("\\cdot", "·")
    s = s.replace("\\sqrt", "√").replace("\\times", "×").replace("\\pm", "±")
    s = s.replace("}{", ")/(").replace("_{rel}", "(rel)").replace("_{rel}", "(rel)")
    s = s.replace("^{2}", "²").replace("^{3}", "³").replace("^2", "²").replace("^3", "³")
    s = s.replace("{", "(").replace("}", ")")
    return s


def _fmt_table_cells(t):
    """表格所有单元格: 去 Normal 带来的首行缩进(2字符≈1.13cm 的"空格")+ 段间距,
    单倍行距, 水平+垂直居中。(字号不动, 由调用方按需另设。)"""
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt
    from docx.oxml import OxmlElement
    for row in t.rows:
        for ci, cell in enumerate(row.cells):
            tcPr = cell._tc.get_or_add_tcPr()
            va = tcPr.find(qn('w:vAlign'))
            if va is None:
                va = OxmlElement('w:vAlign'); tcPr.append(va)
            va.set(qn('w:val'), 'center')          # 垂直居中
            if ci > 0 and tcPr.find(qn('w:noWrap')) is None:
                tcPr.append(OxmlElement('w:noWrap'))   # 数据列不换行; 首列(项目/化合物/目标物/分量来源)允许换行
            for p in cell.paragraphs:
                pf = p.paragraph_format
                pf.first_line_indent = Pt(0)       # 写 <w:ind w:firstLine="0">
                ind = p._p.get_or_add_pPr().find(qn('w:ind'))
                if ind is not None:
                    ind.set(qn('w:firstLineChars'), '0')   # 关键: 清字符缩进(Normal firstLineChars=200=2字符, 否则 Word 仍缩进 2 "空格")
                pf.left_indent = Pt(0)
                pf.space_before = Pt(0); pf.space_after = Pt(0)
                pf.line_spacing = 1.0              # 1.5→单倍
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER   # 水平居中


def _compact_table(t, first_cm=None):
    """宽表: 固定列宽(首列加宽放化合物名) + 8pt 字号; 首列默认2.6cm, first_cm 覆盖
    (多目标物4.4 拟合表6列长名多→4.8cm)。其余列按内容加权填满 A4 纵向 usable=14.66cm。"""
    from docx.shared import Pt, Cm
    from docx.oxml import OxmlElement
    cols = len(t.columns)
    tblPr = t._tbl.tblPr
    layout = tblPr.find(qn('w:tblLayout'))
    if layout is None:
        layout = OxmlElement('w:tblLayout'); tblPr.append(layout)
    layout.set(qn('w:type'), 'fixed')        # 固定列宽, honour gridCol (首列加宽才生效)
    mar = tblPr.find(qn('w:tblCellMar'))
    if mar is None:
        mar = OxmlElement('w:tblCellMar'); tblPr.append(mar)
    for side in ('top', 'left', 'bottom', 'right'):
        e = mar.find(qn('w:' + side))
        if e is None:
            e = OxmlElement('w:' + side); mar.append(e)
        e.set(qn('w:w'), '20'); e.set(qn('w:type'), 'dxa')
    # 首列固定宽 (分析物名); 其余列按内容加权 (CJK=2 / ASCII=1, 取列内最大) 分配剩余宽度,
    # 使长数值列(如 u_rel=0.007604)得到足够宽度不再换行, 短列(回收率%)不浪费空间。
    first_w = Cm(first_cm) if first_cm else Cm(2.6)
    usable = Cm(14.66)
    def _wt(s):
        return sum(2 if ord(c) > 0x2e80 else 1 for c in (s or ""))
    dw = [max(4, max((_wt(t.cell(r, c).text) for r in range(len(t.rows))), default=1))
          for c in range(1, cols)]   # 权重下限 4: 同类短值列(如 16.0→"16")不致过窄, 保持齐整
    sw = sum(dw) or 1
    widths = [first_w] + [int(round((usable - first_w) * w / sw)) for w in dw]
    for i, col in enumerate(t.columns):
        col.width = widths[i]
        for cell in col.cells:          # tcW 与 gridCol 同步, 固定布局下更稳
            cell.width = widths[i]
    for row in t.rows:
        for cell in row.cells:
            for p in cell.paragraphs:
                for run in p.runs:
                    run.font.size = Pt(8)


def _rebalance_vessel_table(t):
    """4.3.2 量器明细表: 量器列("10mL单标移液管")加宽、使用规格V/mL列(数据仅"10.00")收窄。
    _compact_table 已设固定布局; 此处把约 0.8cm 从次列挪到首列, 其余列不变, 次列留 ≥1.1cm 容下"10.00"。"""
    from docx.shared import Cm
    cols = t.columns
    w0, w1 = cols[0].width, cols[1].width
    if w0 is None or w1 is None:
        return
    delta = min(Cm(0.8), max(w1 - Cm(1.1), Cm(0)))   # 次列保留 ≥1.1cm, 数据"10.00"不换行
    for w, idx in ((w0 + delta, 0), (w1 - delta, 1)):
        cols[idx].width = w
        for cell in cols[idx].cells:
            cell.width = w


def _size_flow_table(t):
    """4.3.2 稀释流程表(5列): 固定布局 + 紧凑边距, 移取体积列("8.00"+换行表头)收窄、量器列加宽。
    列序 [母液浓度, 移取体积, 移取量器, 定容量器, 目标浓度]; 宽度和≈A4 usable 14.6cm。"""
    from docx.shared import Cm
    from docx.oxml import OxmlElement
    if len(t.columns) != 5:
        return
    tblPr = t._tbl.tblPr
    layout = tblPr.find(qn('w:tblLayout'))
    if layout is None:
        layout = OxmlElement('w:tblLayout'); tblPr.append(layout)
    layout.set(qn('w:type'), 'fixed')
    mar = tblPr.find(qn('w:tblCellMar'))
    if mar is None:
        mar = OxmlElement('w:tblCellMar'); tblPr.append(mar)
    for side in ('left', 'right'):
        e = mar.find(qn('w:' + side))
        if e is None:
            e = OxmlElement('w:' + side); mar.append(e)
        e.set(qn('w:w'), '20'); e.set(qn('w:type'), 'dxa')   # 紧凑左右边距, 量器长串不溢出
    widths = [Cm(3.0), Cm(1.8), Cm(3.4), Cm(3.4), Cm(3.0)]   # 移取体积(1)窄
    for i, col in enumerate(t.columns):
        col.width = widths[i]
        for cell in col.cells:
            cell.width = widths[i]


def _set_table_font(t, pt):
    """表格所有单元格文本 run 字号设为 pt (小五=9 等); 不影响 OMML 公式 (m:r 非 w:r)。"""
    from docx.shared import Pt
    for row in t.rows:
        for cell in row.cells:
            for p in cell.paragraphs:
                for run in p.runs:
                    run.font.size = Pt(pt)


def _set_cell_size(cell, pt):
    """单元格内 w:r(文本) 与 m:r(OMML 公式) run 字号统设为 pt。表头 $u_rel(.)$ 是 m:r,
    需在其内注入 w:rPr 的 w:sz/w:szCs (Word 数学 run 靠此定字号)。"""
    from docx.shared import Pt
    from docx.oxml import OxmlElement
    hp = str(int(round(pt * 2)))
    for p in cell.paragraphs:
        for run in p.runs:                        # 普通文本 run (u_rel 数值)
            run.font.size = Pt(pt)
    for mr in cell._tc.findall('.//' + qn('m:r')):   # 公式 run (表头)
        rpr = mr.find(qn('w:rPr'))
        if rpr is None:
            rpr = OxmlElement('w:rPr')
            mt = mr.find(qn('m:t'))
            (mt.addprevious(rpr) if mt is not None else mr.append(rpr))
        for tag in ('w:sz', 'w:szCs'):
            e = rpr.find(qn(tag))
            if e is None:
                e = OxmlElement(tag); rpr.append(e)
            e.set(qn('w:val'), hp)


def _shrink_urel_cols(t, pt):
    """各目标物汇总表 u_rel(C/Q/f/R/W) 列缩字号 (表头公式+数值), 余列不动。
    列布局 [目标物][u_rel 分量列…][u_rel(W)][w][U][U%][主导] → u_rel 列=第1列..倒数第5列。"""
    if not t.rows:
        return
    hi = len(t.rows[0].cells) - 5
    for row in t.rows:
        for ci in range(1, hi + 1):
            if ci < len(row.cells):
                _set_cell_size(row.cells[ci], pt)


def _vmerge(t, r1, r2, col=0):
    """纵向合并 t.cell(r1..r2, col): 首格 vMerge=restart 保留文字, 续格 vMerge=continue
    (Word/WPS 只显示首格文字)。"""
    from docx.oxml import OxmlElement
    for r in range(r1, r2 + 1):
        tcPr = t.cell(r, col)._tc.get_or_add_tcPr()
        for old in tcPr.findall(qn("w:vMerge")):
            tcPr.remove(old)
        vm = OxmlElement("w:vMerge")
        if r == r1:
            vm.set(qn("w:val"), "restart")
        tcPr.append(vm)


def _merge_first_col_repeats(t):
    """首列连续相同值纵向合并 (如标曲表分析物名跨"浓度/峰面积"两行)。表头(row 0)不参与。"""
    n = len(t.rows)
    i = 1
    while i < n:
        val = t.cell(i, 0).text.strip()
        j = i + 1
        while j < n and val and t.cell(j, 0).text.strip() == val:
            j += 1
        if j > i + 1:
            _vmerge(t, i, j - 1)
        i = j


def _merge_blank_trailing(t):
    """纵向合并「有值后接连续空格」的单元格 (Markdown 合并约定: 首格填值, 续格留空)。
    稀释流程表固体逐物质多行: 定容量器/目标浓度 首行有值、其余物质行留空 → 合并。表头(row 0)不参与。"""
    n = len(t.rows)
    ncols = len(t.columns)
    for col in range(ncols):
        i = 1
        while i < n:
            if t.cell(i, col).text.strip():
                j = i + 1
                while j < n and not t.cell(j, col).text.strip():
                    j += 1
                if j > i + 1:
                    _vmerge(t, i, j - 1, col)
                i = j
            else:
                i += 1


def _keep_table_on_one_page(t):
    """整表尽量不跨页: 每行 cantSplit(行内不裂) + 非末行单元格段落 keepNext(行间不分页)。
    表本身小于一页时, Word 会把整表推到下一页而非拆开。"""
    from docx.oxml import OxmlElement
    nrows = len(t.rows)
    for ri, row in enumerate(t.rows):
        trPr = row._tr.get_or_add_trPr()
        if trPr.find(qn("w:cantSplit")) is None:
            trPr.append(OxmlElement("w:cantSplit"))
        if ri >= nrows - 1:
            continue                        # 末行不需 keepNext
        for cell in row.cells:
            for p in cell.paragraphs:
                pPr = p._p.get_or_add_pPr()
                if pPr.find(qn("w:keepNext")) is None:
                    pPr.append(OxmlElement("w:keepNext"))


def _allow_table_split(t):
    """多目标物: 表允许跨页 — 每行 cantSplit(单行不裂, 行间可分页, 不加 keepNext) +
    首行 tblHeader(表头跨页重复)。与 _keep_table_on_one_page 互斥(后者整表绑一页)。"""
    from docx.oxml import OxmlElement
    for row in t.rows:
        trPr = row._tr.get_or_add_trPr()
        if trPr.find(qn("w:cantSplit")) is None:
            trPr.append(OxmlElement("w:cantSplit"))
    hdr = t.rows[0]._tr.get_or_add_trPr()
    if hdr.find(qn("w:tblHeader")) is None:
        hdr.append(OxmlElement("w:tblHeader"))


def md_to_docx(md_text, prep_flow=None, header=None, multi=False):
    """Markdown (render 子集) → 基于模板的 docx bytes。
    prep_flow: 1.5 测定程序前处理文本 → PIL 流程图 PNG 嵌入 (替代正文文本, 仿模板)。
    header: 页眉字段 {"Reference":..,"Date":..,"Author(s)":..}。
    multi: 多目标物报告 → 表格允许跨页(行间可分页)+表头跨页重复(tblHeader)+全表字号小五(9pt);
           单目标物(False) → 整表尽量不跨页, 字号按表型(宽表8pt/工作液表9pt)。"""
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    doc = Document(_TEMPLATE)
    prev_15 = False  # 上一行是 '### 1.5 测定程序' → 下一行 prep_flow 文本用流程图替代
    cur_caption = ""  # 最近一个「表N ...」标题, 用于按表名定字号 (4.3.2 两表 → 小五)
    lines = md_text.split("\n")
    i = 0
    while i < len(lines):
        raw = lines[i].strip(" \t")  # 只剥 ASCII 空白; 保留全角空格 U+3000
        s = raw
        if s.startswith("# "):
            doc.add_heading(s[2:], level=1)
            prev_15 = False
        elif s.startswith("### "):
            doc.add_heading(s[4:], level=3)
            prev_15 = s[4:].strip().startswith("1.5")
        elif s.startswith("## "):
            doc.add_heading(s[3:], level=2)
            prev_15 = False
        elif s.startswith("|"):
            tbl = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                row = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(set(c) <= set("-: ") for c in row):  # 跳过分隔行
                    tbl.append(row)
                i += 1
            if tbl:
                cols = len(tbl[0])
                t = doc.add_table(rows=len(tbl), cols=cols)
                t.style = "Table Grid"
                for r, row in enumerate(tbl):
                    for c in range(cols):
                        cell = t.cell(r, c)
                        _add_inline(cell.paragraphs[0], row[c] if c < len(row) else "")
                _fmt_table_cells(t)            # 所有表格: 居中 + 删首行缩进"空格" + 不换行
                if cols >= 7:
                    _compact_table(t)          # 宽表再: 固定列宽(首列加宽) + 8pt
                    if "量器相对不确定度明细" in cur_caption:
                        _rebalance_vessel_table(t)   # 量器明细表: 量器列加宽、使用规格列收窄
                if multi and "曲线拟合相对不确定度" in cur_caption:
                    _compact_table(t, 4.8)     # 多目标物4.4 6列拟合表: 目标物列加宽4.8cm(长名如3,3'-二甲氧基联苯胺不换行), C₀/u(Q)/u_rel(Q) 按内容收窄
                if multi and "稀释流程" in cur_caption:   # 稀释流程表: 移取体积列收窄、量器列宽
                    _size_flow_table(t)
                    _merge_blank_trailing(t)     # 定容量器/目标浓度 空白续格纵向合并 (固体逐物质多行)
                if multi:                       # 多目标物: 表允许跨页 + 表头跨页重复 + 全表小五
                    _allow_table_split(t)
                    _set_table_font(t, 9)
                else:
                    _keep_table_on_one_page(t) # 整表不跨页 (cantSplit + keepNext), 在合并前
                    if "工作液稀释" in cur_caption:   # 4.3.2 两表 (稀释流程+量器明细) → 小五(9pt)
                        _set_table_font(t, 9)
                if "不确定度分量汇总与扩展不确定度" in cur_caption:
                    _shrink_urel_cols(t, 8)   # u_rel(C/Q/f/R/W) 列缩字号(表头公式+数值), 余列不变
                _merge_first_col_repeats(t)    # 首列连续相同值纵向合并 (标曲表分析物名)
            cur_caption = ""
            prev_15 = False
            continue
        elif s == "!cause_effect!":
            if os.path.exists(_CAUSE_EFFECT):
                _add_image(doc, _CAUSE_EFFECT)
            prev_15 = False
        elif s.startswith("$$"):
            if s.rstrip().endswith("$$"):      # 单行 $$..$$
                latex = s.strip().strip("$").strip()
            else:                               # 多行 $$ .. $$
                latex = s.strip().strip("$").strip()
                i += 1
                while i < len(lines) and "$$" not in lines[i]:
                    seg = lines[i].strip().strip("$").strip()
                    if seg:
                        latex += " " + seg
                    i += 1
            try:
                _add_opara(doc, from_latex(latex))   # 块级显示样式 OMML 公式
            except Exception:
                p = doc.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                _set_font(p.add_run(_pretty_formula(latex)))  # 解析失败兜底
            prev_15 = False
        elif s.startswith(">"):
            p = doc.add_paragraph()
            run = p.add_run(s.lstrip(">").strip())
            run.italic = True
            _set_font(run)
            prev_15 = False
        elif s == "---" or s == "":
            pass  # 空行不重置 prev_15
        else:
            if prev_15:  # 1.5 后的 prep_flow 文本 → 流程图替代 (匹配模板: 只留图)
                prev_15 = False
                if prep_flow and prep_flow.strip():
                    _add_flowchart_img(doc, prep_flow)
                else:
                    _add_inline(doc.add_paragraph(), s)
            else:
                p = doc.add_paragraph()
                if re.match(r"表\s*\d", s):     # 表标题 (表N ...) 居中, 对齐范本
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    p.paragraph_format.keep_with_next = True   # 表标题与表保持在同一页
                    cur_caption = s
                _add_inline(p, s)
        i += 1

    if header:
        for label, val in header.items():
            _set_header_field(doc, label, val)

    _add_page_footer(doc)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from uncertainty import mup_cg248, BASELINE_PARAMS
    from gen_report import render, MUP_METHOD
    m = {**BASELINE_PARAMS, **MUP_METHOD}
    m["prep_flow"] = "称取1.00g样品→加入5mL含内标的叔丁基甲醚→超声提取30min→取上清液过0.45μm滤膜→定容至5mL→HPLC-PDA进样分析"
    m["makeup_solvent"] = "叔丁基甲醚"
    md = render(m, mup_cg248(BASELINE_PARAMS))
    data = md_to_docx(md, prep_flow=m["prep_flow"],
                      header={"Reference": "MUP-CG- 248", "Date": "2026/07/07", "Author(s)": "张三"})
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "_smoke.docx")
    with open(out, "wb") as f:
        f.write(data)
    print(f"OK docx {len(data)} bytes -> {out}")
