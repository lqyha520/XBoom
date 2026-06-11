# 小爆来咯 / AIWriteX

小爆来咯是一个面向本地桌面使用的 AI 内容创作工具。项目用 Python 作为主体，FastAPI 提供本地接口，PyWebView 提供桌面窗口，前端页面放在 `src/ai_write_x/web` 下。核心流程覆盖热点采集、素材整理、文章生成、模板排版、质量优化、多平台发布、定时任务和自动更新。

## 主要能力

- 本地桌面应用：启动后在本机随机端口运行 Web 服务，并通过 PyWebView 打开界面。
- 内容生成工作流：支持主题输入、热点选题、参考文章、批量生成、合集模式和发布后动作。
- 热点和爬虫：内置多来源新闻/热点采集器，采集结果可进入素材和生成流程。
- 模板和排版：支持分类模板、动态模板、文章预览和重新套版。
- 多平台发布：包含微信公众号、小红书、抖音、知乎、头条、百家号等适配器。
- 本地数据：默认使用应用数据目录下的 SQLite 数据库保存主题、文章、记忆、任务和设置。
- 自动更新：包含版本策略、下载安装包、SHA256 校验和退出后安装流程。

## 技术栈

- Python 3.10 到 3.12
- FastAPI / Uvicorn
- PyWebView / WebView2
- SQLModel / SQLite
- CrewAI / AIForge / OpenAI 兼容接口
- Jinja2 / 原生 HTML、CSS、JavaScript
- PyInstaller / Inno Setup

## 目录结构

```text
main.py                         # 桌面启动入口
src/ai_write_x/                 # 主应用包
src/ai_write_x/web/             # FastAPI、模板、静态资源和桌面 WebView
src/ai_write_x/core/            # 内容生成、工作流、质量、模板、调度、更新等核心逻辑
src/ai_write_x/tools/           # 爬虫、发布器、MCP 和工具封装
src/ai_write_x/database/        # SQLModel 模型、仓储和迁移
src/ai_write_x/config/          # 出厂默认配置，不放真实密钥
config/                         # 提示词、设计系统、监控配置等资源
knowledge/templates/            # 文章模板库
scripts/                        # 检查、打包、发布和运维脚本
tests/                          # 单元、集成、安全和质量门禁测试
```

## 本地启动

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

也可以使用项目根目录下的 Windows 启动脚本。桌面启动失败时，应用会尝试退回系统浏览器模式。

## 配置和密钥

不要把真实密钥、数据库密码、Token、私钥或本地用户数据提交进仓库。

推荐位置：

- API Key 和微信公众号凭证：`secrets/api_keys.yaml`
- 本地环境变量：`.env` 或系统环境变量
- 用户运行时配置：应用数据目录，由 `PathManager` 管理

仓库中的 `src/ai_write_x/config/config.yaml` 只保留出厂默认值。`menu_access.mysql.host/user/password` 必须保持为空；如果需要白名单能力，优先使用服务端 `menu_access.api_url`，客户端不应保存数据库账号密码。

## 开发检查

快速门禁：

```powershell
python scripts/run_quick_tests.py --skip-smoke
```

排查启动慢或后台组件问题时，可以临时跳过非核心启动任务：

```powershell
$env:AIWRITEX_SKIP_STARTUP_TASKS = "newshub,usage_stats,scheduler"
python main.py
```

发布前检查：

```powershell
python scripts/release_check.py
```

完整发布门禁，不会打包或发布：

```powershell
python scripts/release_gate.py
```

文档乱码审计：

```powershell
python scripts/audit_text_encoding.py README.md docs --fail
```

仅编译检查：

```powershell
python -m compileall -q main.py src\ai_write_x
```

完整 `pytest` 测试数量较多，可能耗时较长。默认开发建议先跑 quick gate，再按需跑指定测试文件。

## 打包发布

发布相关入口：

- `build_windows_installer.ps1`
- `aiwritex_windows.spec`
- `aiwritex_installer.iss`
- `scripts/release_gate.py`
- `scripts/release_check.py`
- `version-policy.json`

打包前会生成出厂配置，避免把本机配置和密钥带进安装包。发布版本需要保持以下版本号一致：

- `src/ai_write_x/version.py`
- `pyproject.toml`
- `aiwritex_installer.iss`
- `version-policy.json`

## 安全约定

- `*.pem`、`*.key`、`.env`、`secrets/api_keys.yaml` 不提交。
- `secrets/api_keys.yaml` 是本地运行时文件，可以存在于工作区；发布检查只警告，打包会使用 sanitized factory config。
- 运维脚本需要密码时从环境变量读取，例如 `XBOOM_DB_PASSWORD`。
- 发布包不得包含 `data/`、`output/`、`logs/`、本地 `secrets/` 或用户运行时配置。
- 修改配置、更新、发布、删除、路径读取相关逻辑后，至少运行 `scripts/run_quick_tests.py --skip-smoke`。

## 当前版本

运行时版本以 `src/ai_write_x/version.py` 为准。当前包版本为 `1.2.24`。
