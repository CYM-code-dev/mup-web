# -*- coding: utf-8 -*-
"""
不确定度评估报告生成器 — FastAPI 后端 + 静态前端 (mup-web)

包装 mup/tools 引擎 + engine_single.build_params_single (从 app.py 逐字抽出)。
前端只发草稿形状的 state, 参数装配留在后端 (parity 由同一段 Python 保证)。

启动: .venv/Scripts/python server.py
"""
import os
import re
import sys
import io
import json
from decimal import Decimal

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from uncertainty import (mup_cg248, GLASS_TOLERANCE, BASELINE_PARAMS,  # noqa: E402
                         UNIT_OPTIONS, UNIT_EXP, CONC_UNIT_OPTIONS, CONC_UNIT_EXP, PIPETTE_TOL)
from gen_report import render, render_multi  # noqa: E402
from engine_single import (build_params_single, KIND_LABELS, VOLUMES,  # noqa: E402
                           _PIP_OPTS, _FLASK_OPTS, apply_ai_single, apply_ai_method, apply_trace_single)
from engine_multi import build_params_multi, apply_ai_multi, _rows_to_groups  # noqa: E402
import solvents  # noqa: E402
import template as tmpl  # noqa: E402

DRAFTS_DIR = os.path.join(ROOT, "drafts")
app = FastAPI(title="不确定度评估报告生成 (mup-web)")


@app.middleware("http")
async def _nocache_static(req, call_next):
    """静态前端 no-cache (revalidate): 改 JS/CSS 即时生效; API 响应不动。"""
    resp = await call_next(req)
    if not req.url.path.startswith("/api"):
        resp.headers["Cache-Control"] = "no-cache, max-age=0"
    return resp


def _default(o):
    if isinstance(o, Decimal):
        return float(o)
    if isinstance(o, (set, tuple)):
        return list(o)
    raise TypeError(f"not JSON serializable: {type(o)}")


def _resp(obj):
    return JSONResponse(content=json.loads(json.dumps(obj, default=_default)))


def _build(state):
    """state → (params, errors)。errors 非空时调用方应 422。
    空草稿/缺字段时 build_params_single 解析中途可能抛 (前端允许空输入, DEF 无前端派生键)
    → 兜底成 errors (422 友好提示) 而非 500。"""
    try:
        out = build_params_single(state)
        return out["params"], out["errors"]
    except Exception as e:
        return None, [f"输入不完整或格式有误 — 请检查 ①~⑤ 各项填全 (称样量/定容量器/曲线点≥3/加标≥2)。({type(e).__name__})"]


# ---- meta ----
@app.get("/api/meta/constants")
def meta_constants():
    return _resp({
        "glass_tolerance": {f"{k[0]}@{k[1]}": v for k, v in GLASS_TOLERANCE.items()},
        "pipette_tol": {f"pip_p@{p}": f for p, f in PIPETTE_TOL.items()},   # 移液枪校准点允差 (分数)
        "baseline_params": BASELINE_PARAMS,
        "unit_options": list(UNIT_OPTIONS),
        "unit_exp": UNIT_EXP,
        "conc_unit_options": list(CONC_UNIT_OPTIONS),
        "conc_unit_exp": CONC_UNIT_EXP,
        "solvents": [dict(s) for s in solvents.SOLVENT_DB],
        "kind_labels": KIND_LABELS,
        "volumes": VOLUMES,
        "pip_opts": _PIP_OPTS,          # 量器选项串 (草稿存储值, 勿在前端重构)
        "flask_opts": _FLASK_OPTS,
    })


# ---- calc ----
@app.post("/api/calc/single")
def calc_single(state: dict):
    """前端路径: 发草稿形状 state → build_params_single → mup_cg248。"""
    params, errors = _build(state)
    if errors:
        raise HTTPException(422, "；".join(errors))
    return _resp({"result": mup_cg248(params), "params": params})


@app.post("/api/calc/engine")
def calc_engine(p: dict):
    """裸引擎 (parity 用): 直传 params → mup_cg248。"""
    return _resp(mup_cg248(p))


# ---- report / export (均服务端 build + render) ----
@app.post("/api/report/single")
def report_single(body: dict):
    params, errors = _build(body.get("state", body))
    if errors:
        raise HTTPException(422, "；".join(errors))
    result = mup_cg248(params)
    md = render({**params, "replicates": len(params["replicates"]),
                 "replicates_data": params["replicates"]}, result)
    return _resp({"md": md, "result": result})


def _md_for_export(body: dict):
    params, errors = _build(body.get("state", body))
    if errors:
        raise HTTPException(422, "；".join(errors))
    result = mup_cg248(params)
    md = render({**params, "replicates": len(params["replicates"]),
                 "replicates_data": params["replicates"]}, result)
    return md, params


@app.post("/api/export/docx")
async def export_docx(body: dict):
    from gen_docx import md_to_docx
    md, params = _md_for_export(body)
    data = md_to_docx(md, prep_flow=params.get("prep_flow"),
                      header=body.get("header"), multi=False)
    return Response(content=data,
                    media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


@app.post("/api/export/md")
def export_md(body: dict):
    md, _ = _md_for_export(body)
    return Response(content=md.encode("utf-8"), media_type="text/markdown")


# ---- drafts (single): 文件 CRUD (v1, 无迁移) ----
def _safe_name(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "", name).strip() or "draft"


@app.get("/api/drafts/single")
def drafts_list():
    if not os.path.isdir(DRAFTS_DIR):
        return []
    return sorted(f[:-5] for f in os.listdir(DRAFTS_DIR) if f.endswith(".json"))


@app.get("/api/drafts/single/{name}")
def drafts_load(name: str):
    p = os.path.join(DRAFTS_DIR, _safe_name(name) + ".json")
    if not os.path.isfile(p):
        raise HTTPException(404, "draft not found")
    with open(p, encoding="utf-8") as f:
        return JSONResponse(content=json.load(f))


@app.post("/api/drafts/single/{name}")
def drafts_save(name: str, body: dict):
    os.makedirs(DRAFTS_DIR, exist_ok=True)
    p = os.path.join(DRAFTS_DIR, _safe_name(name) + ".json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(body, f, ensure_ascii=False, indent=2)
    return {"ok": True}


@app.delete("/api/drafts/single/{name}")
def drafts_del(name: str):
    p = os.path.join(DRAFTS_DIR, _safe_name(name) + ".json")
    if os.path.isfile(p):
        os.remove(p)
    return {"ok": True}


# ---- AI 自动填充 (复杂逻辑在后端 apply_ai_single, 前端只套用) ----
@app.post("/api/ai/parse-prep-flow")
def ai_parse(body: dict):
    out = apply_ai_single(body.get("prep_flow", ""))
    return _resp(out)


@app.post("/api/ai/parse-method")
def ai_parse_method(body: dict):
    return _resp(apply_ai_method(body.get("std_no", "")))


@app.get("/api/ai/config-status")
def ai_config_status():
    from ai_fill import load_config
    try:
        cfg = load_config() or {}
    except Exception:
        return {"configured": False, "model": None, "missing": ["ai_config.toml 解析失败"]}
    need = ("ai_base_url", "ai_model", "ai_api_key")
    missing = [k for k in need if not str(cfg.get(k, "")).strip()]
    return {"configured": not missing, "model": cfg.get("ai_model"), "missing": missing}


# ---- NIST 密度 → β (库外溶剂 α 兜底; 出网) ----
@app.post("/api/solvents/alpha-by-cas")
def solv_alpha(body: dict):
    cas = (body.get("cas") or "").strip()
    pts_in = body.get("points")  # [[T,ρ],...] 手动三点
    if cas:
        try:
            raw = solvents.fetch_nist_density(cas, 15, 35, 5, p=1.0, timeout=15)
            rows = [(T, raw[T]) for T in (15, 20, 25) if T in raw]
        except Exception as e:
            raise HTTPException(502, f"NIST 抓取失败: {e}")
    elif pts_in:
        rows = sorted([(float(r[0]), float(r[1])) for r in pts_in if r[0] is not None and r[1] is not None],
                      key=lambda x: x[0])
    else:
        raise HTTPException(400, "需 cas 或 points")
    if len(rows) != 3:
        raise HTTPException(422, f"需恰好 3 个温度点 (现 {len(rows)})")
    (T1, r1), (T2, r2), (T3, r3) = rows
    b = solvents.calc_beta_from_density(r1, T1, r2, T2, r3, T3)
    if b is None:
        raise HTTPException(422, "算不出 β (端点温度相同 / 基准密度为 0 / 密度≤0)")
    hit = solvents.lookup(cas) if cas else []
    name = hit[0]["name_cn"] if hit else (f"CAS {cas}" if cas else "(密度法 β)")
    return {"alpha": float(b), "source": f"NIST 密度中心差分 {T1:g}/{T2:g}/{T3:g}℃",
            "points": [[T, float(r)] for T, r in rows], "name": name}


# ---- LIMS 工作液溯源 (登录缓存 + trace + 字段映射, 全在后端) ----
@app.post("/api/lims/trace")
def lims_trace(body: dict):
    out = apply_trace_single(body.get("code", ""))
    return _resp(out)


# ---- 多目标物 (engine_multi 装配 + render_multi + template 读写) ----
DRAFTS_MULTI_DIR = os.path.join(ROOT, "drafts", "multi")


def _build_multi(state):
    out = build_params_multi(state)
    return out, out["errors"]


def _multi_md(body):
    out, errors = _build_multi(body.get("state", body))
    if errors:
        raise HTTPException(422, "；".join(errors))
    results = [mup_cg248(p) for p in out["params_list"]]
    md = render_multi(out["method"], out["groups"], out["analytes"], results)
    return md, out, results


@app.post("/api/calc/multi")
def calc_multi(state: dict):
    out, errors = _build_multi(state)
    if errors:
        raise HTTPException(422, "；".join(errors))
    results = [mup_cg248(p) for p in out["params_list"]]
    return _resp({"results": results, "method": out["method"],
                  "groups": out["groups"], "analytes": out["analytes"]})


@app.post("/api/report/multi")
def report_multi(body: dict):
    md, out, results = _multi_md(body)
    return _resp({"md": md, "results": results, "method": out["method"],
                  "groups": out["groups"], "analytes": out["analytes"]})


@app.post("/api/export/multi/docx")
async def export_multi_docx(body: dict):
    md, out, _ = _multi_md(body)
    from gen_docx import md_to_docx
    data = md_to_docx(md, prep_flow=out["method"].get("prep_flow"),
                      header=body.get("header"), multi=True)
    return Response(content=data,
                    media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


@app.post("/api/template/multi/download")
def template_multi_download(body: dict):
    groups = [{"name": g["name"], "kind": g["kind"], "analytes": g["analytes"]}
              for g in _rows_to_groups(body.get("topo_rows") or [])]
    buf = io.BytesIO()
    tmpl.write_template(buf, groups=groups, curve_meta=body.get("curve_meta") or {},
                        n_points=int(body.get("n_points", 3)), n_reps=int(body.get("n_reps", 2)),
                        n_inj_point=int(body.get("n_inj_point", 1)), n_inj_meas=int(body.get("n_inj_meas", 1)))
    buf.seek(0)
    return Response(content=buf.read(),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": "attachment; filename=multi_template.xlsx"})


@app.post("/api/template/multi/upload")
async def template_multi_upload(file: UploadFile = File(...)):
    buf = io.BytesIO(await file.read())
    try:
        meas = tmpl.read_template(buf)
    except Exception as e:
        raise HTTPException(422, f"模板解析失败: {e}")
    return _resp({"meas": meas})


@app.get("/api/drafts/multi")
def drafts_multi_list():
    if not os.path.isdir(DRAFTS_MULTI_DIR):
        return []
    return sorted(f[:-5] for f in os.listdir(DRAFTS_MULTI_DIR) if f.endswith(".json"))


@app.get("/api/drafts/multi/{name}")
def drafts_multi_load(name: str):
    p = os.path.join(DRAFTS_MULTI_DIR, _safe_name(name) + ".json")
    if not os.path.isfile(p):
        raise HTTPException(404, "draft not found")
    with open(p, encoding="utf-8") as f:
        return JSONResponse(content=json.load(f))


@app.post("/api/drafts/multi/{name}")
def drafts_multi_save(name: str, body: dict):
    os.makedirs(DRAFTS_MULTI_DIR, exist_ok=True)
    p = os.path.join(DRAFTS_MULTI_DIR, _safe_name(name) + ".json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(body, f, ensure_ascii=False, indent=2)
    return {"ok": True}


@app.delete("/api/drafts/multi/{name}")
def drafts_multi_del(name: str):
    p = os.path.join(DRAFTS_MULTI_DIR, _safe_name(name) + ".json")
    if os.path.isfile(p):
        os.remove(p)
    return {"ok": True}


@app.post("/api/ai/parse-prep-flow-multi")
def ai_parse_multi(body: dict):
    return _resp(apply_ai_multi(body.get("prep_flow", "")))


# ---- 静态前端 (挂在 /mup 下; 访问 http://host:8000/mup) ----
@app.get("/")
def _root():
    return RedirectResponse("/mup")

app.mount("/mup", StaticFiles(directory=os.path.join(ROOT, "static"), html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True, reload_dirs=[ROOT])
