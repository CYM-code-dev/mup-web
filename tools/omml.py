# -*- coding: utf-8 -*-
"""原生 Word 方程 (OMML) 生成器.

让不确定度公式以真正的下标/上标/分式/根号渲染, 且可在 Word 中直接编辑
(与范本 4.1~4.4 那些方程同种, 非图片)。给配置驱动的多方法报告生成用。

基本构件 (均返回 OMML XML 串):
  r(t)          数学文本
  sub(b,s)      下标 b_s        (如 V_容, u_rel)
  sup(b,s)      上标 b^s        (如 (Δτ)^2)
  frac(n,d)     分式 n/d
  rad(e)        平方根 √e
  eq(*items)    组装行内方程 m:oMath
  urel(arg)     u_rel(arg)      相对不确定度记号
  add_eq(p,xml) 把方程追加到段落
"""
from docx.oxml import parse_xml

_M = 'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"'


def r(t):
    return f'<m:r><m:t xml:space="preserve">{t}</m:t></m:r>'


def _x(v):
    """str -> r(v); 否则原样(已是 OMML XML). 让 sub/sup 可直接传 "2" 这类裸串.
    含 '<' 的 str 视为已是 OMML 片段, 不再包一层 r() (否则 m:r/m:t 双重嵌套)."""
    return r(v) if isinstance(v, str) and "<" not in v else v


def sub(base, s):
    base, s = _x(base), _x(s)
    return f'<m:sSub><m:e>{base}</m:e><m:sub>{s}</m:sub></m:sSub>'


def sup(base, s):
    base, s = _x(base), _x(s)
    return f'<m:sSup><m:e>{base}</m:e><m:sup>{s}</m:sup></m:sSup>'


def frac(num, den):
    return f'<m:f><m:num>{_x(num)}</m:num><m:den>{_x(den)}</m:den></m:f>'


def rad(e):
    return f'<m:rad><m:radPr><m:degHide m:val="1"/></m:radPr><m:deg/><m:e>{_x(e)}</m:e></m:rad>'


def eq(*items):
    return f'<m:oMath {_M}>' + ''.join(items) + '</m:oMath>'


def urel(arg):
    """u_rel(arg): u 带下标 rel, 括号内为参数(arg 可为 r('f') 或 sub(r('V'),r('容')) 等)."""
    return sub(r('u'), r('rel')) + r('(') + arg + r(')')


def add_eq(paragraph, omml_xml):
    paragraph._p.append(parse_xml(omml_xml))


def _local(tag):
    return tag.rsplit('}', 1)[-1]


def rebuild(paragraph, label, omml_xml):
    """清空段落的 run/方程, 重写为 [标签文本] + [原生方程]. 保留段落样式."""
    for child in list(paragraph._p):
        if _local(child.tag) in ('r', 'oMath', 'oMathPara'):
            paragraph._p.remove(child)
    if label:
        paragraph.add_run(label)
    add_eq(paragraph, omml_xml)


# ---- LaTeX (math 子集) → OMML ----------------------------------------------
# 解析 gen_report 产出的 $$...$$ 公式, 复用上面的 r/sub/sup/frac/rad 构件,
# 让 .docx 里出现可编辑的原生公式 (非文本/非图片)。
_SYM2 = {"cdot": "·", "times": "×", "pm": "±", "div": "÷", "cdot": "·",
         "alpha": "α", "beta": "β", "Delta": "Δ", "delta": "δ", "mu": "μ",
         "sigma": "σ", "Sigma": "∑", "tau": "τ", "rho": "ρ", "pi": "π",
         "le": "≤", "ge": "≥", "approx": "≈", "to": "→", "sum": "∑", "infty": "∞"}


class _LP:
    def __init__(self, s):
        self.s, self.i, self.n = s, 0, len(s)

    def peek(self):
        return self.s[self.i] if self.i < self.n else ""

    def ws(self):
        while self.i < self.n and self.s[self.i] == " ":
            self.i += 1


def _grp(p):
    """一个公式参数: {组} 或 单原子 → OMML xml 串 (拼接, 不包 oMath)."""
    p.ws()
    if p.peek() == "{":
        p.i += 1
        items = _seq(p, "}")
        p.i += 1  # 跳 }
        return "".join(items)
    return _atom(p)


def _atom(p):
    p.ws()
    c = p.peek()
    if c == "":
        return ""
    if c == "\\":
        return _cmd(p)
    if c == "{":
        p.i += 1
        items = _seq(p, "}")
        p.i += 1
        return "".join(items)
    if c == "}":
        return ""
    p.i += 1
    return r(c)


def _mathgr(p):
    r"""\mathrm{X} 组内容 → 直立(plain style)数学 run (单位 g/mg/L 等)。
    仅取纯文本, 不支持组内嵌套命令 (本工具 \mathrm 只包单位)。"""
    p.ws()
    if p.peek() != "{":
        return ""
    p.i += 1
    t = ""
    while p.i < p.n and p.s[p.i] != "}":
        t += p.s[p.i]
        p.i += 1
    if p.peek() == "}":
        p.i += 1
    return ('<m:r><m:rPr><m:sty m:val="p"/></m:rPr>'
            f'<m:t xml:space="preserve">{t}</m:t></m:r>')


def _cmd(p):
    p.i += 1  # 跳 \
    name = ""
    while p.i < p.n and p.s[p.i].isalpha():
        name += p.s[p.i]
        p.i += 1
    if name == "mathrm":            # \mathrm{...} → 直立文本 (单位 g/mg/L)
        return _mathgr(p)
    if name in ("frac", "dfrac", "tfrac"):
        return frac(_grp(p), _grp(p))
    if name == "sqrt":
        deg = None
        if p.peek() == "[":  # \sqrt[n]{x}
            p.i += 1
            d = _seq(p, "]")
            p.i += 1
            deg = "".join(d)
        e = _grp(p)
        if deg:
            return f'<m:rad><m:deg>{deg}</m:deg><m:e>{e}</m:e></m:rad>'
        return rad(e)
    if name == "bar":
        ch = _grp(p)
        # 取纯文本字符加组合上划线 (够用于 x̄ 这类均值记号)
        import re as _re
        t = _re.sub(r"<[^>]+>", "", ch)
        return r(t + "̅")
    if name in _SYM2:
        return r(_SYM2[name])
    if name in ("left", "right"):
        return _atom(p)
    if name == "" and p.peek() in (",", ";", ":"):   # \, \; \: LaTeX 间距
        p.i += 1
        return r(" ")
    if name == "" and p.peek() == "!":               # \! 负细距
        p.i += 1
        return ""
    return r(name)


def _seq(p, stop):
    out = []
    while p.i < p.n:
        c = p.peek()
        if c == stop or c == "}":
            break
        if c == " ":
            p.i += 1
            continue
        a = _atom(p)
        while p.peek() == "^" or p.peek() == "_":
            op = p.s[p.i]
            p.i += 1
            a = sup(a, _grp(p)) if op == "^" else sub(a, _grp(p))
        if a:
            out.append(a)
    return out


def from_latex(s):
    """LaTeX(math 子集) → m:oMath xml 串 (可直接 add_eq)."""
    p = _LP(s)
    return eq(*_seq(p, None))

