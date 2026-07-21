# -*- coding: utf-8 -*-
"""AI 解析「前处理流程」→ 称样量 + 样液定容信息。

走 OpenAI 兼容 /chat/completions(中转站/官方均可), 仅用标准库(urllib + tomllib)。
配置存仓库根 ai_config.toml(见 load_config)。网络/HTTP/鉴权/格式错误抛 RuntimeError,
交上层(app.py)用 st.error 兜底, 不让表单崩。
"""
import json
import re
import urllib.request
import urllib.error
from pathlib import Path

# 公司网络 SSL 拦截(自签 CA) → 让 Python 信任 Windows 证书库里的公司根证书。
# truststore 未装则回退 certifi(开发机够用)。
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

try:
    import tomllib  # py3.11+ 标准库
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore

CONFIG_PATH = Path(__file__).resolve().parent.parent / "ai_config.toml"

_SYSTEM_PROMPT = (
    "你是化学前处理流程解析助手。从用户给出的中文「样品前处理流程」文本中,"
    "只提取以下信息, 严格输出一个 JSON 对象(不要解释文字、不要 markdown 代码块):\n"
    "- m_sample: 样品称样量(单位 g, 数字)。取称量动词(称取/称样/称m/准确称取)后紧跟的数字。找不到用 null。\n"
    "- n_weighings: 称量次数(去皮+称量, 通常为 2)。文本未明说就给 2。\n"
    "- 定容/提取溶剂: 必选 mode(single/mixed/multi 之一, 无法判断用 null) + vessels 数组。\n"
    "    判定体积 volume_ml: 显式定容「定容至/定容到/定容于 X mL」「用 XmL 容量瓶定容」→ X"
    "(多级定容/二次定容取【最终进样前最后一级】); 提取法→分析物最终富集并直接进样的有机相体积。\n"
    "    切勿取: 水相试剂(NaOH/连二亚硫酸钠等)、已弃去溶剂(如超声后弃去的正己烷)、固体加入量(氯化钠等)、半途体积。\n"
    "    mode=\"single\" 单一溶剂: 只一种有机溶剂、一个量器。vessels=[{solvent,volume_ml,kind}]。\n"
    "       例「甲醇定容至10mL容量瓶」→ vessels=[{甲醇,10,flask}]。\n"
    "    mode=\"mixed\" 混合试剂: 多种溶剂【预混成一份溶液、按一个体积一次性加入/定容】"
    "(如「X:Y(V:V)溶液」「混合溶剂」), 共用一个量器。vessels 列各组分 {solvent,volume_ml}(各自的 Vi),"
    "另给 vessel_kind=该单一量器代号、vessel_volume_ml=该量器总体积(≈ΣVi)。\n"
    "       例「加入10mL丙酮:甲醇(1:1)溶液」→ vessel_kind=flask, vessel_volume_ml=10, vessels=[{丙酮,5},{甲醇,5}]。\n"
    "    mode=\"multi\" 多次定容: 多种溶剂【分次、各自按独立体积量取加入】(非预混), 每个独立量器。"
    "vessels 列各自 {solvent,volume_ml,kind}(不给 vessel_kind)。\n"
    "       例「加5mL四氢呋喃…再加10mL正己烷…过滤…上机」→ vessels=[{四氢呋喃,5,pip_s},{正己烷,10,pip_s}]。\n"
    "    都不符合 → mode=null, vessels=[]。\n"
    "    solvent: 该相有机溶剂中文常用名。kind: flask/pip_s/pip_g(未说量具: 容量瓶定容→flask; 按体积加入/量取→pip_s)。\n"
    "    cas/alpha(能确定就给, 即便是常见溶剂): cas=该溶剂 CAS 号(如水 7732-18-5, 二甲基甲酰胺/DMF 68-12-2; "
    "名字是缩写/别名/俗称时也填标准 CAS, 便于按 CAS 匹配溶剂库; 不确定用 null); "
    "alpha=该溶剂体积膨胀系数(1/℃, ~20℃; 水约 0.00021, 一般有机溶剂 0.001~0.0015; 不确定用 null)。\n"
    "- note: 一句话中文, 说明 mode 判定依据与取的相/体积(多溶剂说明为何是 mixed/multi)。\n"
    "- influences: 数组, 列出该前处理流程隐含的【随机影响量】短中文名(水浴温度/恒温时间/超声时间/振摇时间/萃取效率/衍生反应程度/离心/氮吹浓缩/加热回流/净化损失…, 按流程实有给), 末尾恒加「制样的均匀性」「进样误差」; 无特定项仍给末两项。\n\n"
    "输出格式严格为 JSON。示例:\n"
    "单溶剂: {\"m_sample\":1.0,\"n_weighings\":2,\"mode\":\"single\","
    "\"vessels\":[{\"solvent\":\"甲醇\",\"volume_ml\":10,\"kind\":\"flask\",\"cas\":\"67-56-1\",\"alpha\":0.00118}],\"note\":\"甲醇定容至10mL容量瓶\",\"influences\":[\"制样的均匀性\",\"进样误差\"]}\n"
    "混合试剂: {\"m_sample\":0.5,\"n_weighings\":2,\"mode\":\"mixed\",\"vessel_kind\":\"flask\",\"vessel_volume_ml\":10,"
    "\"vessels\":[{\"solvent\":\"丙酮\",\"volume_ml\":5},{\"solvent\":\"甲醇\",\"volume_ml\":5}],"
    "\"note\":\"丙酮:甲醇(1:1)预混液,一次性加入10mL\",\"influences\":[\"制样的均匀性\",\"进样误差\"]}\n"
    "多次定容: {\"m_sample\":0.05,\"n_weighings\":2,\"mode\":\"multi\","
    "\"vessels\":[{\"solvent\":\"四氢呋喃\",\"volume_ml\":5,\"kind\":\"pip_s\"},{\"solvent\":\"正己烷\",\"volume_ml\":10,\"kind\":\"pip_s\"}],"
    "\"note\":\"THF与正己烷分次加入,互溶且保留\",\"influences\":[\"制样的均匀性\",\"进样误差\"]}\n\n"
    "mode 必须是 single/mixed/multi/null 之一; kind 必须是 flask/pip_s/pip_g/null。只输出 JSON 本身。"
)

_METHOD_PROMPT = (
    "你是检测方法信息助手。用户给一个「检测标准编号」(如 GB/T 2912.1、ISO 14362-1:2017、"
    "GB 31604.8-2021、HJ 535), 你据此补全不确定度评估报告的方法信息。"
    "只输出一个 JSON 对象, 不要解释文字、不要 markdown 代码块。字段:\n"
    "- basis: 完整「测量依据/标准号」引用, 形如「编号《标准中文名称》」"
    "(如 GB/T 2912.1-2009《纺织品 甲醛的测定 第1部分:游离和水解》)。编号沿用用户给的, 可补年份/分部号, 不要换成别的号。\n"
    "- title: 不确定度评估报告标题, 固定格式「{标准号} {仪器法}测定{基质}中{目标物}含量的不确定度评估」, {仪器法}必填不得省略——取自 instrument 仪器名去末尾「仪/计」加「法」(高效液相色谱仪→高效液相色谱法、气相色谱-质谱联用仪→气相色谱-质谱法、紫外可见分光光度计→紫外可见分光光度法), 不得只写「测定」; 如「ISO 17234-2:2011 高效液相色谱法测定染色皮革中4-氨基偶氮苯含量的不确定度评估」。\n"
    "- instrument: 该方法典型分析仪器(如 紫外可见分光光度计、高效液相色谱仪 HPLC-DAD、气相色谱-质谱联用仪 GC-MS、ICP-MS)。\n"
    "- analyte: 目标物/被测组分中文名(如 甲醛、禁用偶氮染料(芳香胺))。\n"
    "- matrix: 适用样品/基质(如 纺织品、食品、化妆品、水)。\n"
    "- std_name: 标准品/对照品(如 甲醛标准溶液、混合芳香胺标准品); 不确定用 null。\n"
    "- note: 一句话说明依据(如「乙酰丙酮分光光度法测游离甲醛」)。\n"
    "- methods: 该标准的方法数组(单方法也给一个元素的数组), 每项含:\n"
    "    name(方法名, 如「方法A」「方法B」「直接进样法」「顶空进样法」; 单方法可给 null)、\n"
    "    unit(该方法结果含量单位, 必须从 [\"mg/kg\",\"µg/kg\",\"g/kg\",\"%\"] 选最贴近的, 尽量给值不轻易用 null——痕量有机物/重金属常 mg/kg, 低含量 µg/kg, 高含量 %)、\n"
    "    round_mode(\"有效数字\"或\"小数位数\", 默认「有效数字」)、\n"
    "    round_nd(标准为「该方法」规定的修约位数整数; 标准明确就按标准, 未明确给惯例值 3; 系统会自动 +1)、\n"
    "    prep_flow(该方法的前处理流程中文描述, 含称样量/提取溶剂/定容体积等关键量)。\n"
    "    若该标准含多个方法且单位/修约/前处理不同(如方法A=mg/kg、方法B=%), 必须分多项并列, 每项各自的 unit/round_mode/round_nd/prep_flow; 单方法也用一项。\n"
    "- target_mode: \"single\"(单一被测物, 如甲醛、某一具体物质) 或 \"multi\"(一组同类被测物, 如苯系物、可溶性重金属、多农残); 不确定用 null。\n"
    "规则: 拿不准的字段用 null, 不要编造; 用户给的编号不要改写成别的标准。输出严格为 JSON。\n"
    "    准确性优先: 必须按该编号标准真实的适用对象/被测物填写; 拿不准宁可留 null 并在 note 注明「该标准不确定」, 严禁张冠李戴(例如把测定苯系物的标准误填成测定重金属/可溶性有害元素)。被测物(analyte)严格按标准原文列举的组分, 不要自行添加标准未规定的物质; 标准规定几种就写几种。\n"
    "示例: 用户「GB/T 2912.1」→ {\"basis\":\"GB/T 2912.1-2009《纺织品 甲醛的测定 第1部分:游离和水解》\","
    "\"title\":\"GB/T 2912.1-2009 分光光度法测定纺织品中游离和水解甲醛含量的不确定度评估\","
    "\"instrument\":\"紫外可见分光光度计\",\"analyte\":\"甲醛\",\"matrix\":\"纺织品\","
    "\"std_name\":\"甲醛标准溶液\",\"note\":\"乙酰丙酮分光光度法测游离甲醛\","
    "\"methods\":[{\"name\":null,\"unit\":\"mg/kg\",\"round_mode\":\"有效数字\",\"round_nd\":2,\"prep_flow\":\"称取约 1.0 g 剪碎的纺织品样品, 加 100 mL 水萃取, 加入乙酰丙酮显色剂, 40℃ 水浴 30 min, 冷却后取萃取液于 412 nm 测吸光度\"}],\"target_mode\":\"single\"}\n"
    "多方法示例: 某涂料标准含方法A(绝对量)与方法B(相对量) → \"methods\":[{\"name\":\"方法A\",\"unit\":\"mg/kg\",\"round_mode\":\"有效数字\",\"round_nd\":3,\"prep_flow\":\"A法前处理…\"},{\"name\":\"方法B\",\"unit\":\"%\",\"round_mode\":\"有效数字\",\"round_nd\":2,\"prep_flow\":\"B法前处理…\"}] (同一标准的不同方法各自一项, unit/round/prep_flow 各填各的)"
)

# 模型常回中文器具名, 就近平铺成三个代号; 没命中→None(上层跳过定容)。
_KIND_ALIASES = {
    "flask": "flask", "容量瓶": "flask", "量瓶": "flask", "volumetric": "flask", "volumetricflask": "flask",
    "pip_s": "pip_s", "单标": "pip_s", "单标线": "pip_s", "单标吸量管": "pip_s", "移液管": "pip_s", "pipette": "pip_s",
    "pip_g": "pip_g", "分度": "pip_g", "刻度": "pip_g", "分度吸量管": "pip_g", "刻度吸量管": "pip_g",
}


def _norm_kind(v):
    """把模型给的 vessel_kind 规整成 flask/pip_s/pip_g 之一, 认不出返回 None。"""
    if v is None:
        return None
    s = str(v).strip()
    return _KIND_ALIASES.get(s) or _KIND_ALIASES.get(s.lower().replace(" ", ""))


def _to_float(v):
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _to_int(v):
    if v is None:
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _to_str(v):
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _norm_mode(v):
    """模型给的 mode → single/mixed/multi 之一, 其它→None。"""
    s = str(v).strip().lower() if v is not None else ""
    return s if s in ("single", "mixed", "multi") else None


def _norm_round(v):
    """模型给的修约方式 → 有效数字/小数位数 之一, 其它→None。"""
    s = str(v).strip() if v is not None else ""
    return s if s in ("有效数字", "小数位数") else None


def _norm_target(v):
    """模型给的目标物模式 → single/multi 之一, 其它→None。"""
    s = str(v).strip().lower() if v is not None else ""
    return s if s in ("single", "multi") else None


def _coerce_methods(raw):
    """模型给的 methods → list[{name,unit,round_mode,round_nd,prep_flow}], 丢空项, 保序。"""
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        m = {"name": _to_str(item.get("name")),
             "unit": _to_str(item.get("unit")),
             "round_mode": _norm_round(item.get("round_mode")),
             "round_nd": _to_int(item.get("round_nd")),
             "prep_flow": _to_str(item.get("prep_flow"))}
        if any(v is not None for v in m.values()):
            out.append(m)
    return out


def _coerce_vessels(raw):
    """模型给的 vessels → 规整 list[{solvent,volume,kind,cas,alpha}], 丢弃全空项, 上限 6(多次定容最多 6 行)。"""
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        kind = _norm_kind(item.get("kind"))
        vol = _to_float(item.get("volume_ml") if "volume_ml" in item else item.get("volume"))
        solv = _to_str(item.get("solvent"))
        cas = _to_str(item.get("cas"))
        alpha = _to_float(item.get("alpha"))
        if kind is None and vol is None and solv is None and cas is None and alpha is None:
            continue
        out.append({"solvent": solv, "volume": vol, "kind": kind, "cas": cas, "alpha": alpha})
        if len(out) >= 6:
            break
    return out


def _coerce_influences(raw):
    """模型给的 influences → 规整 list[str], strip/去空/去重(保序)/限长 8。"""
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        s = str(item).strip()
        if s and s not in out:
            out.append(s)
        if len(out) >= 8:
            break
    return out


def _extract_json(content):
    """从模型回复里抠首个 JSON 对象(容许 ```json 围栏 / 前后噪声)。失败抛 ValueError。"""
    s = (content or "").strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", s, re.S)
    if fence:
        s = fence.group(1)
    if "{" not in s or "}" not in s:
        raise ValueError("模型未返回 JSON")
    s = s[s.index("{"):s.rindex("}") + 1]
    return json.loads(s)


def _post_chat(base_url, model, api_key, user_text, timeout, system_prompt=_SYSTEM_PROMPT):
    """OpenAI 兼容 /chat/completions。返回 assistant 文本。网络/HTTP 错抛带提示 RuntimeError。
    system_prompt 默认走前处理流程解析; 方法信息解析传 _METHOD_PROMPT。"""
    url = base_url.rstrip("/") + "/chat/completions"
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text or ""},
        ],
        "temperature": 0,
    }, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json; charset=utf-8",
                 "Authorization": f"Bearer {api_key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        snippet = ""
        try:
            snippet = e.read().decode("utf-8", "replace")[:200]
        except Exception:
            pass
        raise RuntimeError(f"AI 接口返回 HTTP {e.code}: {snippet}".strip()) from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        # socket 读/连超时在 py3.10+ 是 TimeoutError, 不是 URLError 子类, 需单列(否则裸抛"read timed out")。
        reason = getattr(e, "reason", None) or e
        if isinstance(e, TimeoutError) or "timed out" in str(reason).lower():
            raise RuntimeError(f"AI 响应超时(中转站较慢), 请重试或换更快的模型: {reason}") from None
        raise RuntimeError(f"无法连接 AI 接口({url}): {reason}") from None
    try:
        return json.loads(raw)["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError):
        raise RuntimeError(f"AI 返回格式异常: {raw[:200]}") from None


def parse_prep_flow(prep_flow, *, base_url, model, api_key, timeout=60):
    """解析前处理流程文本 → {m_sample, n_weighings, mode, vessels, vessel_kind, vessel_volume, note, influences}。
    mode: single/mixed/multi/None。vessels: [{solvent,volume,kind},...]。
    vessel_kind/vessel_volume: mixed 的单一量器(也作旧字段回退源)。influences: 4.5 重复性随机影响量短名列表。
    网络/HTTP/鉴权/格式错 → 抛 RuntimeError。"""
    content = _post_chat(base_url, model, api_key, prep_flow, timeout)
    try:
        obj = _extract_json(content)
    except ValueError as e:
        raise RuntimeError(f"AI 未返回可解析 JSON: {e}; 原文: {content[:200]}") from None
    vessels = _coerce_vessels(obj.get("vessels"))
    mode = _norm_mode(obj.get("mode"))
    vkind = _norm_kind(obj.get("vessel_kind"))
    vvol = _to_float(obj.get("vessel_volume_ml") if "vessel_volume_ml" in obj else obj.get("vessel_volume"))
    if not vessels:   # 容错: 模型仍用旧单字段(vessel_kind/vessel_volume/makeup_solvent) → 合成单元素
        s = _to_str(obj.get("makeup_solvent"))
        if vkind is not None or vvol is not None or s is not None:
            vessels = [{"solvent": s, "volume": vvol, "kind": vkind, "cas": None, "alpha": None}]
            mode = mode or "single"
    if mode is None and vessels:   # 模型没给 mode → 按结构推断
        if len(vessels) == 1:
            mode = "single"
        elif vkind:                # 多组分 + 共用量器 → 混合试剂
            mode = "mixed"
        else:                      # 多组分各自器皿 → 多次定容
            mode = "multi"
    return {
        "m_sample": _to_float(obj.get("m_sample")),
        "n_weighings": _to_int(obj.get("n_weighings")),
        "mode": mode,
        "vessels": vessels,
        "vessel_kind": vkind,
        "vessel_volume": vvol,
        "note": str(obj.get("note") or ""),
        "influences": _coerce_influences(obj.get("influences")),
    }


def parse_method_info(std_no, *, base_url, model, api_key, timeout=60):
    """按检测标准编号 → {basis,title,instrument,analyte,matrix,std_name,note,
    methods:[{name,unit,round_mode,round_nd,prep_flow}],target_mode}。
    methods 至少一项(模型给 flat 字段时合成单方法)。网络/HTTP/鉴权/格式错 → 抛 RuntimeError。"""
    content = _post_chat(base_url, model, api_key, std_no, timeout, system_prompt=_METHOD_PROMPT)
    try:
        obj = _extract_json(content)
    except ValueError as e:
        raise RuntimeError(f"AI 未返回可解析 JSON: {e}; 原文: {content[:200]}") from None
    methods = _coerce_methods(obj.get("methods"))
    if not methods:   # 模型仍用 flat 字段 → 合成单方法一项
        methods = [{"name": None,
                    "unit": _to_str(obj.get("unit")),
                    "round_mode": _norm_round(obj.get("round_mode")),
                    "round_nd": _to_int(obj.get("round_nd")),
                    "prep_flow": _to_str(obj.get("prep_flow"))}]
    return {
        "basis": _to_str(obj.get("basis")),
        "title": _to_str(obj.get("title")),
        "instrument": _to_str(obj.get("instrument")),
        "analyte": _to_str(obj.get("analyte")),
        "matrix": _to_str(obj.get("matrix")),
        "std_name": _to_str(obj.get("std_name")),
        "note": _to_str(obj.get("note")),
        "methods": methods,
        "target_mode": _norm_target(obj.get("target_mode")),
    }


def load_config(path=None):
    """读 ai_config.toml。文件不存在返回 None; TOML 语法错抛 tomllib.TOMLDecodeError。"""
    p = Path(path) if path else CONFIG_PATH
    if not p.exists():
        return None
    with open(p, "rb") as f:
        return tomllib.load(f)
