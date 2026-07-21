# -*- coding: utf-8 -*-
"""LIMS 登录凭据（读仓库根 lims_config.toml，仿 ai_fill.load_config；不进 git）。

三键 [lims]: base_url / username / password。文件缺失或键不全 → get_credentials() 返回 None，
上层(app.py)提示用户去配置。
"""
from pathlib import Path

try:
    import tomllib  # py3.11+ 标准库
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore

CONFIG_PATH = Path(__file__).resolve().parent.parent / "lims_config.toml"


def load_config(path=None):
    """读 lims_config.toml。文件不存在返回 None；TOML 语法错抛 tomllib.TOMLDecodeError。"""
    p = Path(path) if path else CONFIG_PATH
    if not p.exists():
        return None
    with open(p, "rb") as f:
        return tomllib.load(f)


def get_credentials():
    """返回 (base_url, username, password)；未配置(缺文件/缺键)返回 None。"""
    cfg = load_config()
    if not cfg:
        return None
    lims = cfg.get("lims") or {}
    base_url = str(lims.get("base_url") or "").strip()
    username = str(lims.get("username") or "").strip()
    password = str(lims.get("password") or "").strip()
    if not (base_url and username and password):
        return None
    return base_url, username, password


def get_std_backend_url():
    """标准品管理后端地址(lims_config.toml [lims] std_backend_url)，供 mup-web 调溯源 API；
    未配置返回 ''。"""
    cfg = load_config()
    if not cfg:
        return ""
    return str((cfg.get("lims") or {}).get("std_backend_url") or "").strip()
