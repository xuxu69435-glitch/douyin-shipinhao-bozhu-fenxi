# 抖音博主内容分析智能体 — V5 起步工程（R0调研 + M0代码）

这是一个**可交给Codex继续开发的独立工程**，不是已完成的抖音分析应用。本轮只支持抖音。已实现工程骨架和可执行的35项后端测试，**真实平台数据尚未验收，Windows版尚未打包**。

## 已包含

- Tauri 2 + React 18 + TypeScript + Vite：任务创建、历史、暂停/取消/恢复、阻塞原因展示。视频/报告页面是明确标注的待实现入口。
- Python FastAPI + Pydantic + SQLAlchemy + SQLite：单Worker，任务状态与单视频、字幕、分析/报告的独立持久化表。
- F2可选SDK适配器与分页、作品归属及ID去重逻辑；真实采集默认未接入Worker，防止假成功。
- FFprobe/FFmpeg真实执行的本地合成媒体测试及受限下载辅助函数；真实ASR/LLM待M1。
- Rust Sidecar进程所有权、临时本机端口、随机会话凭据、最小化Tauri IPC代理，打包Windows脚本。
- 源码许可证调研和验收日志：`docs/research/github-review.md` / `docs/progress.md`。

## 目录

```text
backend/app/             FastAPI, SQLite models, Worker, F2 boundary, media
backend/tests/           35 automated tests (mock pagination + real local FFmpeg)
frontend/src/            React task screen and typed Rust proxy
frontend/src-tauri/      Tauri 2 Rust process owner, capabilities, Windows icons
scripts/                 Windows PyInstaller and explicit R0 live probe
AGENTS.md                Codex integration and acceptance instructions
docs/                    GitHub research, architecture, honest progress
```

## Windows 11 首次验证

安装Python **3.12**、Node.js 20+、Rust/MSVC工具链、Tauri 2 Windows WebView2构建所需工具。进入PowerShell：

```powershell
# 项目根目录
py -3.12 -m venv backend\.venv
.\backend\.venv\Scripts\python.exe -m pip install -e ".\backend[test,packaging]"
.\backend\.venv\Scripts\python.exe -m pytest -q -c backend\pyproject.toml backend\tests

# Windows PyInstaller sidecar；会复制目标三元组后缀的exe
.\scripts\build-sidecar.ps1

cd frontend
npm install
npm run build
npm run tauri:dev
# Windows集成确认后才执行：npm run tauri:build
```

如果使用`backend`作为当前目录执行测试：

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
```

Tauri启动时生成独立令牌、随机本地端口，并启动Python Sidecar。关闭Tauri窗口应终止它；**该行为仍需Windows真机测试**。数据目录由Tauri提供（App Local Data），不会保存在安装目录中。

## R0 真实试验（尚未执行）

在合法可访问的真实抖音样本上，安装F2可选依赖：

```powershell
.\backend\.venv\Scripts\python.exe -m pip install -e ".\backend[collector-f2]"
.\backend\.venv\Scripts\python.exe .\scripts\live_douyin_probe.py `
  --profile "https://www.douyin.com/user/REAL_USER_ID" `
  --video "https://www.douyin.com/video/REAL_VIDEO_ID" `
  --media-dir ".media\r0" --output "docs\testing\live-r0.json"
```

当需要合法授权时，可显式使用`--cookie-file ".secrets\douyin-cookie.txt"`。不自动从浏览器导出Cookie，不提交凭据，不尝试绕过访问控制。真实测试必须确认作者、第二页新作品和FFprobe通过；否则R0继续为未通过。

## 模型配置

仅使用`OPENAI_BASE_URL`、`OPENAI_API_KEY`、`OPENAI_MODEL`；此M0工程尚未发起模型调用。后续M1从本机用户配置读取真实凭据，绝不把`.env`或密钥打入安装包。

## 当前限制

源码在独立容器生成，不能看到或修改你Windows上的原有仓库；Github连接没有提供可写的目标仓库。容器内Python为3.13.5，没有Rust、npm依赖缓存和外网DNS，因此**Tauri编译、Windows安装包、F2实采、Whisper及LLM均没有实际执行**。不要将Python本地测试与这些待办混淆。
