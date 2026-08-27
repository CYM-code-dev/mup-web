# -*- coding: utf-8 -*-
"""
不确定度评估计算引擎 (Eurachem/GUM 自下而上, 相对不确定度 RSS 合成)

照搬 MUP-CG-248 范本及其配套《副本MUP的测定-正己烷.xlsx》Sheet1 的公式, 并按
GUM/Eurachem 与实验室确认的口径修正:
  - 标准差用样本标准差 (÷(n-1), 贝塞尔, STDEV.S), 而非范本原来的 STDEV.P(÷n).
  - 回收率分量直接评定并计入合成, 不再做 t 检验 (按实验室决定删除 t 检验内容).
  - 占比用方差贡献 u_i²/Σu_i² (GUM 口径), 非线性比.

单文件, 仅用标准库. 不引第三方.

自检: python uncertainty.py
  内置 MUP-CG-248 基线参数, 校验各分量与合成. m/V/C_stock/C/Q 仍对账范本显示值
  (≤0.5%); f/R/合成/U 为按修正口径重算的值.
"""
import math
from decimal import Decimal, ROUND_HALF_EVEN

SQRT2 = math.sqrt(2.0)
SQRT3 = math.sqrt(3.0)
SQRT6 = math.sqrt(6.0)

# 结果单位相对 mg/kg 的换算因子 (display 层用; 引擎数学无量纲, 不依赖)。
# 1% (m/m) = 10000 mg/kg, 故 mg/kg→% 为 ×1e-4。
UNIT_OPTIONS = ("mg/kg", "µg/kg", "g/kg", "µg/g", "%")

# 结果值换算: mg/kg → unit 为 ×10**exp (1 mg/kg = 1e3 µg/kg = 1e-3 g/kg = 1e-4 %)。
# w = C·V/m (C mg/L, V mL, m g) 天然得 mg/kg; 选其他单位时乘 10**exp。
# µg/g ≡ mg/kg (exp 0): 数值与 mg/kg 相同, 仅报告显示单位不同 (与样液 ng/mL 配对)。
UNIT_EXP = {"mg/kg": 0, "µg/kg": 3, "g/kg": -3, "µg/g": 0, "%": -4}

# 样液浓度(⑤/⑥ 实测加标C)的可选单位: 引擎在装配层统一换算为 mg/L 再参与曲线/回收率计算,
# 测定值按 10**(UNIT_EXP[unit] + CIN_UNIT_EXP[cin]) 折算 (ng/mL+µg/g → ×10⁻³)。
# 与证书侧 CONC_UNIT_* 刻意分开 (语义不同, 值恰好部分重合)。
CIN_UNIT_OPTIONS = ("mg/L", "ng/mL")
CIN_UNIT_EXP = {"mg/L": 0, "ng/mL": -3}

# 标准品证书浓度的可选单位 (高浓液标): 内部统一换算为 mg/L 再参与计算/报告。
# µg/mL ≡ mg/L (exp 0); mg/mL、g/L = 1e3 mg/L (exp 3); µg/L、ng/mL = 1e-3 mg/L (exp -3)。
CONC_UNIT_OPTIONS = ("mg/L", "µg/mL", "mg/mL", "µg/L", "g/L", "ng/mL")
CONC_UNIT_EXP = {"mg/L": 0, "µg/mL": 0, "mg/mL": 3, "µg/L": -3, "g/L": 3, "ng/mL": -3}

# 玻璃量器 A 级允差 (mL), 取自 JJG 196-2006《常用玻璃量器》全系列 A 级标称容量.
# pip_g 取完全流出式 A 级标称总容量; 不完全流出式/吹出式(含 0.1~0.5mL 小规格)需另查规程表.
GLASS_TOLERANCE = {
    # 单标线容量瓶 (volumetric flask, 量入 A级) — JJG 196-2006 表6
    ("flask", 1): 0.010, ("flask", 2): 0.015, ("flask", 5): 0.020,
    ("flask", 10): 0.020, ("flask", 25): 0.030, ("flask", 50): 0.05,
    ("flask", 100): 0.10, ("flask", 200): 0.15, ("flask", 250): 0.15,
    ("flask", 500): 0.25, ("flask", 1000): 0.40, ("flask", 2000): 0.60,
    # 单标线吸量管 (single-mark pipette, 量出 A级) — JJG 196-2006 表4
    ("pip_s", 1): 0.007, ("pip_s", 2): 0.010, ("pip_s", 3): 0.015,
    ("pip_s", 5): 0.015, ("pip_s", 10): 0.020, ("pip_s", 15): 0.025,
    ("pip_s", 20): 0.030, ("pip_s", 25): 0.030, ("pip_s", 50): 0.05,
    ("pip_s", 100): 0.08,
    # 分度吸量管 (graduated pipette, 流出式 A级) — JJG 196-2006 表5
    ("pip_g", 1): 0.008, ("pip_g", 2): 0.012, ("pip_g", 5): 0.025,
    ("pip_g", 10): 0.05, ("pip_g", 20): 0.10, ("pip_g", 25): 0.10, ("pip_g", 50): 0.10,
    # 量筒 (measuring cylinder, 量出式) — JJG 196-2006; 取值核对自 RF24-03 设备一览表校准证书(量出式)
    ("cylinder", 10): 0.20, ("cylinder", 50): 0.50, ("cylinder", 100): 1.0,
    ("cylinder", 250): 2.0, ("cylinder", 500): 5.0, ("cylinder", 1000): 10.0,
}

# 分度量器: 允差按均匀 √3 (全程读数缺中心化依据); 容量瓶/单标线 → 三角 √6
# pip_p (可调移液枪): 容量允许误差为体积百分比, 按均匀 √3 计入 (JJG 646-2006)
_GRADUATED = {"pip_g", "cylinder", "pip_p"}

# 可调移液枪 (移液器): 按市售量程档组织 (实验室实有 4 档), 允差为体积百分比 (相对移取体积),
# 取自 JJG 646-2006 (可调移液器按标称容量=满量程规定允差). 仅计容量误差项 (不计测量重复性).
# PIPETTE_RANGES: (下限_μL, 满量程_μL, 标称容量_mL=满量程); 下限=满量程×10% (有效量程惯例).
# 允差按满量程取 (挂在 nominal 上); PIPETTE_TOL 保留全量校准点供老 method 兼容查表.
PIPETTE_RANGES = [(2, 20, 0.02), (5, 50, 0.05), (20, 200, 0.2), (100, 1000, 1.0)]
PIPETTE_TOL = {
    0.002: 0.12, 0.004: 0.10, 0.005: 0.08, 0.01: 0.08, 0.02: 0.04,
    0.025: 0.04, 0.05: 0.03, 0.1: 0.02, 0.2: 0.015, 0.5: 0.01, 1.0: 0.01,
}


def pipette_cal_point(vol):
    """≥vol 的最小移液枪档满量程 nominal (mL); 无 (vol 超最大档 1.0) → None。

    nominal=档标称容量, vessel_tol 据此查 PIPETTE_TOL 得允差百分比 (按满量程)。
    """
    cand = [nom for (_lo, _hi, nom) in PIPETTE_RANGES if nom >= vol]
    return min(cand) if cand else None


def vessel_tol(kind, volume, nominal=None):
    """量器允差 (绝对 mL): glass 查 GLASS_TOLERANCE; pip_p (移液枪) = PIPETTE_TOL[校准点]·volume.

    pip_p 的允差是体积百分比, 故绝对允差随实际移取体积变化; nominal=校准点 (≥volume).
    """
    if kind == "pip_p":
        cp = nominal if nominal is not None else pipette_cal_point(volume)
        return PIPETTE_TOL[cp] * volume
    return GLASS_TOLERANCE[(kind, nominal if nominal is not None else volume)]

# I 级电子天平最大允许误差 (JJG 1036, 检定分度值 e=1mg), 按载荷(称样量) m 分档:
#   0≤m≤50g → ±0.5mg;  50g<m≤200g → ±1.0mg;  m>200g → ±1.5mg
def balance_mpe_g(m):
    """I 级天平按载荷 m (称样量, g) 的最大允许误差, 返回 g。前端据此随称样量自动取允差。"""
    mg = 0.5 if m <= 50 else (1.0 if m <= 200 else 1.5)
    return mg / 1000.0

# t 分布双侧 0.05 临界值已不再使用 (回收率 t 检验按实验室决定删除).


# ---- 分量公式 ------------------------------------------------------------

def urel_mass(balance_tol, m_sample, n_weighings=2):
    """样品称量相对不确定度.
    天平示值允差均匀分布 (√3), 去皮+称量 n 次 RSS.
    范本: d=0.0005g, m=1.00, n=2 -> √2·d/√3/m = 0.0004082.
    (注: 范本写成 '2×', 实为 √2×, 数值 0.0004082 对应 √2.)
    """
    return math.sqrt(n_weighings) * balance_tol / SQRT3 / m_sample


def urel_glassware(kind, volume, alpha=1.19e-3, dtau=5.0, tol=None, nominal=None):
    """单个玻璃量器一次使用的相对不确定度.
    允差分布按量器类型分流 (JJF 1059.1-2012 B类):
      flask/pip_s (容量瓶/单标线吸量管) -> 三角 √6: A级逐只按标称容积校准、
        检定超差剔除, 误差集中于中心.
      pip_g/cylinder (分度吸量管/量筒) -> 均匀 √3: 全程允差缺中心化依据, 取保守.
    nominal=量器标称规格(查允差), volume=实际移取/定容体积 V(进温度项与 V 分母);
      缺省 nominal=volume(满刻度). 部分移取(如 50mL量筒取40mL)时 nominal≠volume.
    温度膨胀始终均匀 √3: urel(t)=α·Δτ/√3 (与 V 无关). RSS 合成.
    """
    if not isinstance(volume, (int, float)) or not volume:
        return 0.0, 0.0, 0.0
    if tol is None:
        tol = GLASS_TOLERANCE[(kind, nominal if nominal is not None else volume)]
    k_ml = SQRT3 if kind in _GRADUATED else SQRT6
    urel_ml = tol / (k_ml * volume)
    urel_t = alpha * dtau / SQRT3
    return math.sqrt(urel_ml ** 2 + urel_t ** 2), urel_ml, urel_t


def urel_sample_volume(kind, volume, alpha=1.19e-3, dtau=5.0, tol=None, nominal=None):
    """样液定容相对不确定度 (4.2): 单个量器允差 + 温度.
    范本: 5mL 单标移液管 -> 0.003647.
    nominal=量器标称规格(查允差), 缺省=volume(满刻度); 部分移取(如量筒取部分)时传入.
    """
    urel, _, _ = urel_glassware(kind, volume, alpha, dtau, tol, nominal)
    return urel


def _blend_alpha(reagents):
    """混合试剂体积加权膨胀系数 blend α = Σ(Vi·αi)/ΣVi.
    单器皿一次性加入各试剂, 共同经历同一 Δτ → 温度贡献线性体现在合成 α 里 (见 mup_cg248 混合分支).
    样液定容(4.2)与储备液定容(4.3.1)共用."""
    return sum(r["volume"] * r["alpha"] for r in reagents) / sum(r["volume"] for r in reagents)


def urel_makeup_additive(reagents, dtau=5.0):
    """多次定容相对不确定度 (4.2 多次定容): N 个器皿分次加入同一瓶.
    V = ΣVi. 每试剂 i 自带器器(kind, volume): 允差(绝对 tol_i/k_i) + 温度(绝对 Vi·αi·Δτ/√3).
      允差项: 不同器皿独立 -> RSS (同管复用应改代数和, CNAS-GL016 §4.5; 此处默认不同器皿).
      温度项: 分次加入、温差独立 -> RSS.
    返回 (urel = u(V)/V, detail{V, u_tol, u_temp, u_V, per[每试剂明细]}).
    """
    V = sum(r["volume"] for r in reagents)
    u_tol2 = 0.0
    temp_terms = []
    per = []
    for r in reagents:
        kind, vol = r["kind"], r["volume"]
        alpha = r.get("alpha", 1.19e-3)
        nominal = r.get("nominal", vol)          # 量器标称规格(查允差); 缺省=vol(满刻度)
        tol = r.get("tol", GLASS_TOLERANCE[(kind, nominal)])
        k = SQRT3 if kind in _GRADUATED else SQRT6
        u_tol_i = tol / k                  # 绝对 (mL)
        u_temp_i = vol * alpha * dtau / SQRT3   # 绝对 (mL)
        u_tol2 += u_tol_i ** 2
        temp_terms.append(u_temp_i)
        per.append(dict(kind=kind, volume=vol, nominal=nominal, alpha=alpha, tol=tol, k=k,
                        u_tol=u_tol_i, u_temp=u_temp_i))
    u_tol = math.sqrt(u_tol2)              # RSS (不同器皿)
    u_temp = math.sqrt(sum(t * t for t in temp_terms))   # 独立 -> RSS
    u_V = math.sqrt(u_tol ** 2 + u_temp ** 2)
    return u_V / V, dict(V=V, u_tol=u_tol, u_temp=u_temp, u_V=u_V, per=per)


def urel_stock(purity, U_purity, k_purity, m_std, balance_tol,
               flask_volume, alpha=1.19e-3, dtau=5.0, reagents=None, n_weighings=2):
    """标准储备液相对不确定度 (4.3.1, Case A 纯品称量) = √(纯度² + 称量² + 定容²).
    纯度: U/(k·p); 称量: √n·d/√3/m (n=去皮+称量次数, 默认2); 定容: 容量瓶允差+温度.
    定容试剂: reagents=None→单一溶剂(用 alpha); reagents=[{volume,alpha},...]→混合试剂(blend α).
    范本(单一) -> 0.03704.
    """
    urel_p = U_purity / (k_purity * purity)
    urel_m = math.sqrt(n_weighings) * balance_tol / SQRT3 / m_std
    blend = _blend_alpha(reagents) if reagents else alpha
    urel_v = urel_sample_volume("flask", flask_volume, blend, dtau)
    return math.sqrt(urel_p ** 2 + urel_m ** 2 + urel_v ** 2), urel_p, urel_m, urel_v


def urel_stock_liquid(Urel_cert, k_cert, pip=None, flask=None,
                      alpha=1.19e-3, dtau=5.0, reagents=None, flask_alpha=None,
                      cert_mode="relative", C_cert=None, U_abs=None, pip_nominal=None):
    """购入液标(高浓液标)作储备液相对不确定度 (4.3.1, Case B 移取+定容) = √(证书浓度² + 移取浓标² + 定容²).
    证书浓度项 urel 按证书形式:
      relative(默认): urel = Urel_cert/(k·100)。Urel_cert=相对扩展不确定度(%, 如 2 表 2%)。 (例: 2%/2/100=0.01)
      absolute:       urel = U_abs/(k·C_cert)。C_cert=标称浓度(mg/L), U_abs=扩展不确定度(同单位)。 (例: 5.1/2/100=0.0255)
    pip=(kind, actual_volume): 移取浓标的吸量管; 允差项允差按 pip_nominal(量器规格)查表, 除以 actual_volume.
      pip_nominal 缺省=pip[1](满刻度); 分度吸量管只移取部分体积时 actual<nominal。温度用浓标膨胀 alpha。移取浓标不含容量瓶.
    flask=体积: 定容容量瓶(允差+温度); 定容温度用定容试剂 α —
      reagents=[{volume,alpha},...]→混合 blend α; 否则 flask_alpha(单一溶剂); 都缺省回落 alpha.
    返回 (urel, [(来源, urel),...]).
    """
    if cert_mode == "absolute":
        urel_conc = U_abs / (k_cert * C_cert)
    else:
        urel_conc = Urel_cert / (k_cert * 100.0)
    detail = [("证书浓度", urel_conc)]
    terms = [urel_conc]
    if pip is not None:
        nominal = pip_nominal if pip_nominal is not None else pip[1]
        tol = vessel_tol(pip[0], pip[1], nominal)
        u_pip, _, _ = urel_glassware(pip[0], pip[1], alpha, dtau, tol=tol)
        terms.append(u_pip)
        detail.append(("移取浓标", u_pip))
    if flask is not None:
        fa = _blend_alpha(reagents) if reagents else (flask_alpha if flask_alpha is not None else alpha)
        u_fl = urel_sample_volume("flask", flask, fa, dtau)
        terms.append(u_fl)
        detail.append(("定容", u_fl))
    return math.sqrt(sum(t * t for t in terms)), detail


def dilution_budget(uses, alpha=1.19e-3, dtau=5.0):
    """标准工作液多级稀释相对不确定度 (4.3.2) = √Σ(nᵢ·urel(Vᵢ)²).
    uses 每项可为:
      (kind, volume, n)                 — tol/nominal 按 (kind,volume) 查表 (满刻度, 向后兼容)
      (kind, volume, n, tol)            — tol 独立指定
      (kind, volume, n, tol, nominal)   — 再带标称规格 (非满刻度刻度管: volume=实际移取体积, nominal=管规格)
    volume 恒为分母里的体积; 刻度吸量管非满刻度时 tol 按标称规格查、volume 填实际移取体积.
    每级移取(吸量管)+定容(容量瓶)各算一次. 返回 (urel, 明细[dict]).
    """
    total = 0.0
    detail = []
    for use in uses:
        kind, volume, n = use[0], use[1], use[2]
        tol = use[3] if len(use) > 3 and use[3] is not None else vessel_tol(kind, volume)
        nominal = use[4] if len(use) > 4 and use[4] is not None else volume
        role = use[5] if len(use) > 5 else None           # "makeup"=定容 / "pip"=移取 (报告角色判定用)
        urel, urel_ml, urel_t = urel_glassware(kind, volume, alpha, dtau, tol=tol)
        total += n * urel ** 2
        detail.append({"kind": kind, "nominal": nominal, "v_used": volume, "n": n,
                       "tol": tol, "k": SQRT3 if kind in _GRADUATED else SQRT6,
                       "role": role,
                       "urel_ml": urel_ml, "urel_t": urel_t, "urel": urel})
    return math.sqrt(total), detail


def least_squares(points):
    """最小二乘 y = b0 + b1·x. points: [(x,y),...].
    返回 b0, b1, s(残差标准差, ÷(n-2)), x̄, Sxx=Σ(xi-x̄)².
    """
    n = len(points)
    sx = sum(p[0] for p in points)
    sy = sum(p[1] for p in points)
    sxx = sum(p[0] ** 2 for p in points)
    sxy = sum(p[0] * p[1] for p in points)
    xbar = sx / n
    Sxx = sum((p[0] - xbar) ** 2 for p in points)
    b1 = (n * sxy - sx * sy) / (n * sxx - sx * sx)
    b0 = (sy - b1 * sx) / n
    resid_ss = sum((p[1] - (b0 + b1 * p[0])) ** 2 for p in points)
    s = math.sqrt(resid_ss / (n - 2))
    return b0, b1, s, xbar, Sxx


def least_squares_origin(points):
    """过原点回归 y = b1·x (无截距, 强制过原点). points: [(x,y),...].
    返回 b1, s(残差标准差, ÷(n-1)), Sxx=Σ(xi)²."""
    n = len(points)
    sxx = sum(p[0] ** 2 for p in points)
    sxy = sum(p[0] * p[1] for p in points)
    b1 = sxy / sxx
    rss = sum((p[1] - b1 * p[0]) ** 2 for p in points)
    s = math.sqrt(rss / (n - 1))
    return b1, s, sxx


def urel_calibration(points, p, x_pred, include_origin=False, force_origin=False):
    """曲线拟合相对不确定度 (4.4).
    标准(含截距): u(x_pred) = (s/b1)·√(1/p + 1/n + (x_pred-x̄)²/Sxx); 范本 -> 0.003694.
    强制过原点(无截距 y=b1·x): u(x_pred) = (s/b1)·√(1/p + x_pred²/Σx²); s÷(n-1), 无 1/n 项
      (无截距→截距方差不存在; Δ法反推 Var(x̂0)=(σ²/b1²)(1/p + x0²/Σx²))。
    include_origin: 含截距时把原点(0,0)并入拟合(n+1); force_origin 时无效(线已锚于原点)。"""
    if force_origin:
        pts = list(points)
        b1, s, Sxx = least_squares_origin(pts)
        n = len(pts)
        b0, xbar = 0.0, 0.0
        u = (s / b1) * math.sqrt(1.0 / p + x_pred ** 2 / Sxx)
    else:
        pts = ([(0.0, 0.0)] + list(points)) if include_origin else list(points)
        b0, b1, s, xbar, Sxx = least_squares(pts)
        n = len(pts)
        u = (s / b1) * math.sqrt(1.0 / p + 1.0 / n + (x_pred - xbar) ** 2 / Sxx)
    return u / x_pred, dict(b0=b0, b1=b1, s=s, xbar=xbar, Sxx=Sxx, u=u)


def std(values, ddof=1):
    n = len(values)
    mean = sum(values) / n
    return math.sqrt(sum((v - mean) ** 2 for v in values) / (n - ddof)), mean


def _round_decimal(x, n, kind, rounding=ROUND_HALF_EVEN):
    """四舍六入五成双 (GB/T 8170, Decimal ROUND_HALF_EVEN)。
    kind='sig' → n 位有效数字; kind='dp' → n 位小数。
    x 为 None/0/非有限时原样返回(0 返回 0.0)。用 Decimal(str(x)) 规避 float 尾数噪声,
    保证“5”这类边界按 half-even 取舍。
    """
    if x is None or x == 0 or not math.isfinite(x):
        return 0.0 if x == 0 else x
    d = Decimal(str(x))
    q = Decimal(1).scaleb(d.adjusted() - (n - 1)) if kind == "sig" else Decimal(1).scaleb(-n)
    return float(d.quantize(q, rounding=rounding))


def round_sf(x, n):
    """保留 n 位有效数字 (四舍六入五成双)。"""
    return _round_decimal(x, n, "sig")


def round_dp(x, n):
    """保留 n 位小数 (四舍六入五成双)。"""
    return _round_decimal(x, n, "dp")


def fmt_result(x, mode, nd):
    """按修约方式格式化为显示字符串 (保留有效尾零, 不走科学计数)。
    mode='小数位数' → n 位小数; '有效数字' → n 位有效数字。x 应已按同方式修约。
    例: 16.0 + 小数位数1 → '16.0' (避免 :g 把尾零吃掉显示成 '16')。"""
    if x is None:
        return ""
    if not math.isfinite(x):
        return str(x)
    d = Decimal(str(x))
    q = Decimal(1).scaleb(-nd) if mode == "小数位数" else Decimal(1).scaleb(d.adjusted() - (nd - 1))
    return str(d.quantize(q, rounding=ROUND_HALF_EVEN))


def urel_replicate(values, ddof=1):
    """重复性相对不确定度 (4.5): s/√n/均值.
    默认样本标准差 (÷(n-1), 贝塞尔, STDEV.S).
    """
    s, mean = std(values, ddof)
    u = s / math.sqrt(len(values))
    return u / mean, dict(s=s, mean=mean, u=u)


def recovery(values, ddof=1):
    """回收率相对不确定度 (4.6): u(R)=s/√n, urel=u/R̄.
    默认样本标准差 (÷(n-1), 贝塞尔). values 为回收率(分数, 如 0.793).
    按实验室决定, 不再做 t 检验, 回收率分量直接计入合成.
    """
    s, mean = std(values, ddof)
    n = len(values)
    u = s / math.sqrt(n)
    urel = u / mean
    return dict(mean=mean, s=s, u=u, urel=urel)


def combine(components):
    """相对不确定度 RSS 合成. components: {name: urel}. 返回 urel 与占比%."""
    urel_w = math.sqrt(sum(v ** 2 for v in components.values()))
    share = {k: (v ** 2 / urel_w ** 2 * 100 if urel_w else 0.0)
             for k, v in components.items()}
    return urel_w, share


# ---- MUP-CG-248 基线 + 自检 ----------------------------------------------

# 范本 6 点外标曲线 (浓度 mg/L, 峰面积)
MUP_POINTS = [(0.49, 4184), (0.98, 10549), (1.96, 24701),
              (3.92, 50588), (7.85, 106136), (9.81, 133613)]
# 7 次重复性测定值 (mg/kg)
MUP_REPLICATES = [17.7, 16.5, 16.5, 15.6, 15.2, 16.1, 14.9]
# 7 次回收率 (分数)
MUP_RECOVERY = [0.793, 0.794, 0.774, 0.817, 0.781, 0.769, 0.788]
# 7 次加标实验原始数据: 实测加标 C (样液浓度 mg/L) 与 称样量 m (g)。理论加标 C₀=4.36, 定容 V=5。
# 由它们派生: 测定值 w=C·V/m == MUP_REPLICATES; 回收率 R=C/C₀ (3位有效数字) == MUP_RECOVERY。
MUP_SPIKE_C = [3.458, 3.464, 3.373, 3.561, 3.406, 3.353, 3.437]
MUP_SPIKE_M = [0.9787, 1.0474, 1.023, 1.1441, 1.1222, 1.0388, 1.1503]


# MUP-CG-248 基线参数 (范本实测值). mup_cg248(p=None) 默认用它, 前端传 p 覆盖.
BASELINE_PARAMS = {
    "title": "ISO 17234-2:2011 高效液相色谱法测定染色皮革中4-氨基偶氮苯含量的不确定度评估",
    "basis": "ISO 17234-2:2011《皮革中4-氨基偶氮苯的含量测定》",
    "instrument": "高效液相色谱仪(HPLC-PDA)",
    "analyte": "4-氨基偶氮苯",
    "matrix": "皮革",
    "curve_method": "外标法",     # 外标法 / 内标法 (内标法 y=面积比)
    "unit": "mg/kg",              # X/重复性值与报告共用单位 (数据单位即报告单位)
    "stock_source": "solid",      # solid(纯品称量) / liquid_dilute(购入液标移取+定容)
    # 4.1 样品称量
    "balance_id": "CK-SB295-CG",   # 天平设备编号 (仅报告溯源, 不进计算)
    "balance_tol": 0.0005, "m_sample": 1.00, "n_weighings": 2,
    # 4.2 样液定容
    "vessel_kind": "pip_s", "vessel_volume": 5,
    "makeup_solvent": "",          # 定容试剂(溶剂名, 仅报告溯源, 不进计算)
    "alpha": 1.19e-3,              # 溶剂体积膨胀系数 (1/℃), 决定温度项; 按定容试剂选
    "env_temp": 20.0,             # 测量环境基准温度 (℃, 范本 20), 报告「1.2 测量环境」与 4.2 温度变化式
    "dtau": 5.0,                   # 实验室温差 Δτ (℃, 范本 20±5 取 5), 均匀分布 √3
    # 4.3.1 储备液
    "purity": 0.982, "U_purity": 0.005, "k_purity": 2,
    "m_std": 0.0111, "stock_flask_volume": 10,
    # 4.3.2 工作液: 基线用范本实测值; 前端传 work_uses 则自动算 (见 dilution_budget).
    "u_work": 0.01495,
    # 4.4 曲线
    "points": MUP_POINTS, "p": 7, "x_pred": 16.1,
    # 4.5 重复性 / 4.6 回收率
    "replicates": MUP_REPLICATES, "recovery": MUP_RECOVERY,
    # 结果取值 (默认重复性均值; 基线显式给 16.1)
    "X": 16.1,
    # 加标实验原始数据 (single_form ⑥ 精密度·回收率 tab 录入; 派生上方 replicates/recovery)。
    # 理论加标 C₀ 与 定容体积 V 为固定值; 每行 实测加标 C / 称样量 m 可变。
    # w=C·V/m → 测定值(mg/kg); R=C/C₀ → 回收率(3位有效数字)。
    "spike_theor": 4.36, "spike_vol": 5,
    # 加标信息 (报告 4.6 叙述用, 不参与计算): 标液浓度 / 加标体积 / 加入目标物含量
    "spike_std_conc": 1090.02, "spike_add_vol": 20, "spike_add_mass": 21.8,
    "spike_C": list(MUP_SPIKE_C), "spike_m": list(MUP_SPIKE_M),
    # 结果值 X 的修约: 方式(有效数字/小数位数) + 位数; 取舍=四舍六入五成双。
    "round_mode": "有效数字", "round_nd": 3,
}


def mup_cg248(p=None):
    """跑测量模型 w=C·V/m 的不确定度评估, 返回完整结果 dict.
    p: 参数 dict (结构见 BASELINE_PARAMS). None 时用基线 (MUP-CG-248).
    工作液稀释: p 含 'work_uses' ([(kind, volume, n_uses),...]) 时用 dilution_budget
    自动算; 否则用 p['u_work'] 直填.
    口径: 贝塞尔标准差(÷n-1); 回收率不做 t 检验, 直接计入合成 (6 分量全在)."""
    if p is None:
        p = BASELINE_PARAMS
    alpha = p.get("alpha", 1.19e-3)            # 溶剂膨胀系数 (方法级, 所有玻璃量器共用)
    dtau = p.get("dtau", 5.0)                  # 温差 Δτ (方法级)
    u_m = urel_mass(p["balance_tol"], p["m_sample"], p.get("n_weighings", 2))
    # 定容: 允差按量器规格 vessel_volume 查 JJG 196, 代入 V 用实际定容体积 (默认=规格).
    makeup_mode = p.get("makeup_mode", "single")
    makeup_detail = None
    if makeup_mode == "mixed":
        # 混合试剂: 单一量器(种类+规格V) + 混合溶剂; blend α=Σ(Vi·αi)/ΣVi (体积加权);
        #   套单器皿公式: 允差 d/(k·V), 温度 blend_α·Δτ/√3 (同器皿共同温差→线性, 体现在 blend α 里)
        reags = p["reagents"]
        blend_alpha = _blend_alpha(reags)
        V = p["vessel_volume"]
        tol_v = p.get("vessel_tol")
        if tol_v is None:
            tol_v = GLASS_TOLERANCE[(p["vessel_kind"], V)]
        u_v = urel_sample_volume(p["vessel_kind"], V, blend_alpha, dtau, tol=tol_v)
        makeup_detail = {"V": V, "blend_alpha": blend_alpha, "per": reags, "u_v": u_v}
    elif makeup_mode == "multi":
        # 多次定容: N 个器皿分次加入同一瓶, V=ΣVi, 允差RSS, 温度RSS(分时独立)
        u_v, makeup_detail = urel_makeup_additive(p["reagents"], dtau)
    else:
        v_used = p.get("vessel_used_volume", p["vessel_volume"])
        tol_v = p.get("vessel_tol")
        if tol_v is None:
            tol_v = GLASS_TOLERANCE[(p["vessel_kind"], p["vessel_volume"])]
        u_v = urel_sample_volume(p["vessel_kind"], v_used, alpha, dtau, tol=tol_v)
    src = p.get("stock_source", "solid")
    if "u_stock" in p:                       # 预算好直接注入 (共享液标场景)
        u_stock = p["u_stock"]
        stock_detail = p.get("stock_detail", [])
    elif src == "liquid_dilute":
        pip = (p["pip_kind"], p["pip_vol"])
        flask = p["stock_flask_volume"]
        u_stock, stock_detail = urel_stock_liquid(p.get("Urel_cert", 0.0), p["k_cert"],
                                                   pip=pip, flask=flask, alpha=alpha, dtau=dtau,
                                                   reagents=p.get("stock_reagents"),
                                                   flask_alpha=p.get("stock_alpha"),
                                                   cert_mode=p.get("cert_mode", "relative"),
                                                   C_cert=p.get("C_cert"), U_abs=p.get("U_abs"),
                                                   pip_nominal=p.get("pip_nominal"))
    else:                                    # Case A 纯品称量
        u_stock, u_p, u_wm, u_vl = urel_stock(p["purity"], p["U_purity"], p["k_purity"],
                                              p["m_std"], p.get("stock_balance_tol", p["balance_tol"]),
                                              p["stock_flask_volume"],
                                              alpha=p.get("stock_alpha", alpha), dtau=dtau,
                                              reagents=p.get("stock_reagents"),
                                              n_weighings=p.get("stock_n_weighings", 2))
        stock_detail = [("纯度", u_p), ("称量", u_wm), ("定容", u_vl)]
    if p.get("work_uses"):
        u_work, work_detail = dilution_budget(p["work_uses"], alpha=p.get("work_alpha", alpha), dtau=dtau)
    else:
        u_work, work_detail = p["u_work"], []
    u_c = math.sqrt(u_stock ** 2 + u_work ** 2)
    # ponytail: 测量数据(曲线/重复/回收)缺失时优雅降级 — 跳过对应分量, 仅算前处理侧 m/V/C;
    #          全数据路径(≥3 点曲线 + ≥2 次重复/回收)与原基线完全一致, 不改任何已标定值。
    pts = p.get("points") or []
    reps = p.get("replicates") or []
    recs = p.get("recovery") or []
    if len(pts) >= 3 and p.get("p") and p.get("x_pred"):
        u_q, fit = urel_calibration(pts, p["p"], p["x_pred"], p.get("include_origin", False),
                                    p.get("force_origin", False))
    else:
        u_q, fit = None, None
    if len(reps) >= 2:
        u_f, rep = urel_replicate(reps)
    else:
        u_f, rep = None, None
    if len(recs) >= 2:
        rec = recovery(recs)
    else:
        rec = None

    comps = {"m": u_m, "V": u_v, "C": u_c}
    if u_q is not None:
        comps["Q"] = u_q
    if u_f is not None:
        comps["f"] = u_f
    if rec is not None:
        comps["R"] = rec["urel"]
    urel_w, share = combine(comps)
    X = p.get("X")
    if X is None and rep is not None:
        X = rep["mean"]                  # 未指定时取重复性均值
    U = (2 * urel_w * X) if X is not None else None
    return dict(components=comps, urel_w=urel_w, share=share, U=U, X=X,
                u_m=u_m, u_v=u_v, u_stock=u_stock, u_work=u_work, u_c=u_c,
                u_q=u_q, fit=fit, u_f=u_f, rep=rep, recovery=rec,
                work_detail=work_detail, work_alpha=p.get("work_alpha", alpha),
                stock_source=src, stock_detail=stock_detail,
                alpha=alpha, dtau=dtau, makeup_mode=makeup_mode, makeup_detail=makeup_detail)


def _approx(a, b, tol=0.005):
    return abs(a - b) / max(abs(b), 1e-12) <= tol


def selfcheck():
    r = mup_cg248()
    assert (balance_mpe_g(1.0) == 0.0005 and balance_mpe_g(50) == 0.0005
            and balance_mpe_g(50.1) == 0.001 and balance_mpe_g(201) == 0.0015), "balance_mpe_g"
    # m/V/C_stock/C/Q 对账范本显示值 (≤0.5%, 与标准差口径无关).
    # f/R/合成/U 为按修正口径(贝塞尔÷n-1 + 计入回收率 + 无t检验)重算的预期值.
    checks = [
        ("urel(m)", r["u_m"], 0.0004082, 0.005),
        ("urel(V)", r["u_v"], 0.003647, 0.005),
        ("urel(C_stock)", r["u_stock"], 0.03704, 0.005),
        ("urel(C) 含称量项", r["u_c"], 0.03994, 0.005),
        ("urel(Q)", r["u_q"], 0.003694, 0.005),
        ("urel(f) 贝塞尔", r["u_f"], 0.02226, 0.005),
        ("urel(R) 贝塞尔", r["recovery"]["urel"], 0.007602, 0.005),
        ("合成 urel(W)", r["urel_w"], 0.04664, 0.01),
        ("扩展 U (mg/kg)", r["U"], 1.50, 0.02),
    ]
    print("=== MUP-CG-248 自检 (修正口径: 贝塞尔÷(n-1) + 计入回收率 + 无t检验) ===")
    allok = True
    for name, got, exp, tol in checks:
        ok = _approx(got, exp, tol)
        allok &= ok
        print(f"  {'OK ' if ok else 'FAIL'} {name}: 引擎={got:.5g}  预期={exp:.5g}")
    rec = r["recovery"]
    print(f"  --  回收率 R̄={rec['mean']:.4f}  s={rec['s']:.4g}  u={rec['u']:.4g}  "
          f"urel={rec['urel']:.5g} (计入合成, 无t检验)")
    # 混合试剂(单一量器+blend α): 10mL 单标吸量管 + THF 5mL(α=0.00126)+正己烷 5mL(α=0.00138)
    _mp = dict(BASELINE_PARAMS); _mp["makeup_mode"] = "mixed"
    _mp["vessel_kind"] = "pip_s"; _mp["vessel_volume"] = 10
    _mp["reagents"] = [{"volume": 5, "alpha": 0.00126, "name": "THF"},
                       {"volume": 5, "alpha": 0.00138, "name": "正己烷"}]
    _mr = mup_cg248(_mp)
    ok_mix = _approx(_mr["u_v"], 0.003897, 0.01)
    # 多次定容(N 器皿, 允差RSS+温度RSS): THF 5mL(pip_s) + 正己烷 10mL(pip_s), V=15
    _mp2 = dict(BASELINE_PARAMS); _mp2["makeup_mode"] = "multi"
    _mp2["reagents"] = [{"kind": "pip_s", "volume": 5, "alpha": 0.00126},
                        {"kind": "pip_s", "volume": 10, "alpha": 0.00138}]
    _mr2 = mup_cg248(_mp2)
    ok_mul = _approx(_mr2["u_v"], 0.002998, 0.01)
    allok &= ok_mix and ok_mul
    print(f"  {'OK ' if ok_mix else 'FAIL'} urel(V) 混合试剂(单器皿+blend α): {_mr['u_v']:.5g}  预期≈0.003897")
    print(f"  {'OK ' if ok_mul else 'FAIL'} urel(V) 多次定容(N器皿,RSS):    {_mr2['u_v']:.5g}  预期≈0.002998")
    # 量筒部分移取: 50mL量筒(标称 tol=0.50, 分度→√3)实际移取40mL(乙酸乙酯 α=0.00149)。
    #   urel_ml=0.50/(√3·40)=0.007217, urel_t=0.00149·5/√3=0.004301 → urel≈0.008401。
    _mp3 = dict(BASELINE_PARAMS); _mp3["makeup_mode"] = "single"
    _mp3["vessel_kind"] = "cylinder"; _mp3["vessel_volume"] = 50
    _mp3["vessel_used_volume"] = 40; _mp3["alpha"] = 0.00149
    _mr3 = mup_cg248(_mp3)
    ok_cyl = _approx(_mr3["u_v"], 0.008401, 0.01)
    allok &= ok_cyl
    print(f"  {'OK ' if ok_cyl else 'FAIL'} urel(V) 量筒部分移取(50mL筒取40mL): {_mr3['u_v']:.5g}  预期≈0.008401")
    # 工作液稀释 (4.3.2): 刻度管非满刻度 (tol 按标称规格查, V 用实际移取体积) + 同器聚合 n
    # pip_g 1mL 规格放出 0.9mL、10mL 规格放出 8mL; 5mL 单标×4、10mL 容量瓶×7。预期 u_work≈0.01495。
    _wu = [("pip_s", 1, 1, 0.007, 1), ("pip_g", 0.9, 1, 0.008, 1),
           ("pip_s", 5, 4, 0.015, 5), ("pip_g", 8, 1, 0.05, 10),
           ("flask", 10, 7, 0.020, 10)]
    _uw, _wd = dilution_budget(_wu)
    ok_w = _approx(_uw, 0.01495, 0.005)
    allok &= ok_w
    print(f"  {'OK ' if ok_w else 'FAIL'} urel(C_work) 稀释(含非满刻度刻度管): {_uw:.5g}  预期≈0.01495")
    # 修约 (四舍六入五成双) + 加标→测定值/回收率 派生校验
    assert round_sf(0.79266, 3) == 0.793, "round_sf"
    assert round_dp(0.125, 2) == 0.12, "half-even 0.125→0.12 (前位2偶, 舍)"
    assert round_dp(0.375, 2) == 0.38, "half-even 0.375→0.38 (前位7奇, 进)"
    assert round_dp(2.5, 0) == 2 and round_dp(3.5, 0) == 4, "half-even 2.5→2, 3.5→4"
    assert fmt_result(16.0, "小数位数", 1) == "16.0", "fmt 16.0 不丢尾零"
    assert fmt_result(16.0, "有效数字", 3) == "16.0", "fmt 有效数字保尾零"
    assert fmt_result(0.793, "有效数字", 3) == "0.793", "fmt 回收率 3 位有效数字"
    th, vol = BASELINE_PARAMS["spike_theor"], BASELINE_PARAMS["spike_vol"]
    R = [round_sf(c / th, 3) for c in MUP_SPIKE_C]
    w = [c * vol / m for c, m in zip(MUP_SPIKE_C, MUP_SPIKE_M)]
    assert R == MUP_RECOVERY, f"加标派生回收率不一致: {R}"
    assert round_sf(sum(w) / len(w), 3) == 16.1, f"加标派生结果 X 不一致: {sum(w)/len(w)}"
    # 单位换算恒等式: µg/g≡mg/kg; ng/mL→µg/kg 与 mg/L→mg/kg 数值路径相同 (ng/g ≡ µg/kg)
    assert UNIT_EXP["µg/g"] == 0 and CIN_UNIT_EXP["ng/mL"] == -3, "单位换算指数"
    assert UNIT_EXP["µg/kg"] + CIN_UNIT_EXP["ng/mL"] == 0, "ng/mL+µg/kg 合成指数应为0"
    assert UNIT_EXP["µg/g"] + CIN_UNIT_EXP["ng/mL"] == -3, "ng/mL+µg/g 合成指数应为-3"
    assert set(CIN_UNIT_OPTIONS) == set(CIN_UNIT_EXP), "样液单位表 options/exp 不一致"
    assert "µg/g" in UNIT_OPTIONS and all(u in UNIT_EXP for u in UNIT_OPTIONS), "结果单位表不一致"
    ok_round = True
    allok &= ok_round
    print(f"  {'OK ' if ok_round else 'FAIL'} 修约四舍六入五成双 + 加标派生(R==MUP_RECOVERY, X==16.1)")
    if not allok:
        raise SystemExit("自检未通过, 引擎有误, 停止.")
    print("\n自检全部通过. 当前口径: 标准差÷(n-1), 回收率计入, 方差占比.")
    return r


if __name__ == "__main__":
    selfcheck()
