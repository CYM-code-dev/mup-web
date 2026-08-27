# mup-web · 测量不确定度评估报告生成

FastAPI 后端 + 原生 JS 静态前端。对单物质 / 多物质方法计算测量不确定度（校准曲线、精密度、回收率），渲染 Markdown + DOCX 报告，并集成 LIMS（自动登录、回填、追溯）和 OpenAI 兼容中转站（AI 自动填充称样/定容）。

## 本地启动

```bash
# 首次：建虚拟环境 + 装依赖
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

# 生产式启动（无 reload，常驻可用）
.venv\Scripts\python -m uvicorn server:app --host 127.0.0.1 --port 8000

# 开发启动（带热重载，改 Python 即时生效）
.venv\Scripts\python server.py
```

浏览器开 `http://127.0.0.1:8000/`。

> 不要用 `python server.py` 做常驻服务——它在 `server.py:351` 写死了 `reload=True`，仅适合开发。

## 配置文件（机密，已 gitignore）

两个本地配置文件含密钥，**不进版本库**，需各自从模板复制后填写：

| 文件 | 模板 | 缺失时 |
|---|---|---|
| `ai_config.toml` | `ai_config.example.toml` | AI 自动填充按钮提示「配置缺项」，不阻塞 |
| `lims_config.toml` | `lims_config.example.toml` | LIMS 自动登录/回填/追溯不可用，不阻塞 |

```bash
cp ai_config.example.toml  ai_config.toml     # 填 ai_base_url / ai_model / ai_api_key
cp lims_config.example.toml lims_config.toml  # 填 [lims] base_url / username / password
```

## 部署（与标准品管理系统同一台 Windows 服务器）

部署模型与 `Management-of-Standard-Substance` 一致：服务器上跑 `.bat` → `git pull` GitHub → 注册/重启 NSSM Windows 服务。mup-web 作为独立服务 `MupWeb` 跑在 **8000** 端口（门户 Flask 是 5000，不冲突）。

**首次部署**（把 `deploy_server.bat` 拷到服务器一个空目录，如 `E:\`，双击/运行）：
- 前置：git、Python 3.12、nssm.exe（可从 `E:\Management-of-Standard-Substance\nssm.exe` 拷一份到项目目录或 PATH）。
- 自动：克隆仓库 → 建 `.venv` 装 `requirements.txt` → 注册并启动 `MupWeb`。
- 之后**手工**把真实的 `ai_config.toml`、`lims_config.toml` 放进项目根目录（gitignore，拉不到）。

**后续发版**（本地 `git push` 后，在服务器项目目录内）：
```bash
cd E:\server\mup-web
update_server.bat
```
等价于 `git reset --hard origin/main` + 重装依赖 + `nssm restart MupWeb`。

> `drafts/`（用户草稿）已 gitignore，`git reset --hard` **不会**清空服务器上用户新建的草稿——这是有意的数据保护。`server.py` 在首次保存草稿时会自动创建该目录。

**远程更新**（本机直接发版，不用 RDP 上服务器）：
- 服务器一次性启用 ssh（管理员 PowerShell，命令见 `update_remote.bat` 头部注释）：
  `Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.0.1.0` + `Start-Service sshd` + 设 `LocalAccountTokenFilterPolicy=1`（否则 ssh 登录的管理员是 UAC 过滤令牌，`nssm stop` 拒绝访问）。
- 之后本机跑 `update_remote.bat`（改好脚本里的 `SUSER`），ssh 远程执行服务器上的 `update_server.bat` 并轮询等服务恢复。传参可更新同服务器其他程序：`update_remote.bat E:\<其他程序>\update_server.bat`。

## parity 回归测试（可选）

比对当前引擎与旧 Streamlit 版本的输出是否一致。需额外依赖和样例草稿：

```bash
.venv\Scripts\pip install pandas streamlit
.venv\Scripts\python parity\check.py
```

注意：`parity/check.py` 用 `drafts/111.json` 作 `GOLDEN_111` 样例，而 `drafts/` 已 gitignore，新克隆环境需自行放入样例草稿。

## 目录速览

```
server.py            FastAPI 入口（路由 + 草稿 CRUD）
engine_single.py     单物质参数装配
engine_multi.py      多物质参数装配
tools/               引擎核心（uncertainty.py / gen_report.py / gen_docx.py / lims_*.py / ai_fill.py）
static/              前端（index.html + js/ + styles.css）
parity/              回归测试套件
deploy_server.bat    首次部署（服务器）
update_server.bat    发版刷新（服务器）
update_remote.bat    远程发版（本机 ssh 触发服务器 update_server.bat）
requirements.txt     运行时依赖
```
