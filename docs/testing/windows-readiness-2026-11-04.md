# Windows 运行就绪检查（2026-11-04）

这是修复前的检查快照。运行依赖、发布时间、桌面工具链、设置、安装包及提交身份已在后续工作中更新，当前结果见 [桌面交付记录](windows-desktop-delivery.md) 与 [最新进度](../progress.md)。

## 结论与检查范围

检查源码基线：`a684e76`。检查目录：`E:\1bishe\douyin-analyst-v5`。

**后端测试及本地进程可以运行；当前尚不能作为已验收的抖音分析桌面应用交付。** 本次进行环境、依赖、测试和源码核查，没有修改业务实现，没有提交或推送。

GitHub 连接器读取目标仓库元数据及 contents API：仓库 `xuxu69435-glitch/douyin-shipinhao-bozhu-fenxi` 当前为空，contents API 返回 `This repository is empty.`。本地工程尚未配置 remote；因此当前可审查的业务代码来自本地目录，并非 GitHub 已发布代码。

## 本机环境与实际执行

| 项目 | 结果 | 边界 |
| --- | --- | --- |
| Python | Windows，3.12.2 | 已创建 `backend/.venv`，隔离安装基础及测试依赖 |
| Node / npm | 22.20.0 / 10.9.3 | 符合 README 的 Node 版本要求 |
| 前端依赖与构建 | **安装成功，`npm run build` 通过** | 完整 TypeScript 检查及 Vite 构建；没有执行桌面界面或播放器验收 |
| FFmpeg / FFprobe | PATH 中可用，FFmpeg 8.0 | 后端测试实际处理本地合成媒体，不代表真实抖音媒体 |
| Rust / Cargo | PATH 中未找到；用户默认 `.cargo/bin/rustc.exe` 也不存在 | 未执行 Rust 编译与 Tauri 桌面运行 |
| Tauri 安装包构建 | **失败：cargo metadata 的 cargo 程序不存在** | 已实际运行 `npm run tauri:build`，没有生成安装包 |
| 后端完整测试 | **50 passed，2.60 秒** | 真实采集、ASR、LLM仍使用明确标记的测试替身 |
| 后端依赖检查 | `uv pip check` 通过 | 仅代表已安装测试环境的依赖一致性 |
| Python 子进程检查 | **通过** | HTTP 健康检查、认证拒绝、任务重启持久化、默认 blocked、子进程退出；不覆盖 Tauri |
| 完整可选依赖解析 | dry-run 成功，82 个包 | 没有安装 ASR 或 PyInstaller，没有执行模型推理或打包 |
| F2 SDK | 独立环境安装 PyPI `0.0.1.7`；配置、主页及作品 ID 解析接口存在 | 导入 crawler/model 会进行远端令牌请求，受限网络下失败；没有获得真实作者、第二页或视频 |
| faster-whisper / LLM | 未运行真实权重或真实模型服务 | 不声称转写质量、分析质量或费用已经验证 |

后端测试命令（项目根目录）：

```powershell
.\backend\.venv\Scripts\python.exe -m pytest -q -c backend\pyproject.toml backend\tests --basetemp=.media\readiness-pytest-venv --tb=short -o addopts=''
.\backend\.venv\Scripts\python.exe scripts\smoke_backend.py
```

测试环境解析版本包括 FastAPI 0.162.0、SQLAlchemy 2.1.8、Pydantic 2.14.2、httpx 0.28.1、pytest 9.2.0、pytest-asyncio 1.4.1.post1。未生成依赖锁文件。

前端初次依赖安装遇到 npm registry TLS 断连（ECONNRESET）；复用缓存并降低下载并发重试后，76 个包安装成功。保留官方 registry，没有切换第三方镜像。构建版本为 TypeScript 5.6.3、Vite 6.4.5、React 18.3.1、Tauri JS API/CLI 2.12.4。检查时刻完整构建结果：

```text
> tsc -b && vite build
vite v6.4.5 building for production...
32 modules transformed.
dist/index.html                   0.43 kB
dist/assets/index-ChiAskZR.css    8.71 kB
dist/assets/index-DIIwd77I.js   161.21 kB
built in 425ms
```

构建产物保留在被忽略的 `frontend/dist` 中。没有生成或提交 package-lock.json。

系统 Python 最初缺少 pytest-asyncio，结果是 47 passed / 3 failed；补齐项目隔离环境后为 50 passed，不能将最初的依赖缺失当作三项业务缺陷。第一次自定义 pytest 临时路径未建立父目录的错误也已修正，不计入项目缺陷。

受限执行下，隔离环境的进程检查两次在清理临时 SQLite 文件时出现 WinError 32。同一环境允许正常本机执行后通过，未确认是应用缺陷；Tauri/PyInstaller 的退出与进程树清理仍须独立验收。

## 已确认的缺漏

1. **基础运行依赖遗漏。** `backend/app/insights.py` 顶层导入 httpx，而 `backend/pyproject.toml` 只在 test extra 中直接声明 httpx。另建纯基础依赖环境执行 `from app.main import create_app`，实际得到 `ModuleNotFoundError: No module named 'httpx'`。应把 httpx 声明为运行依赖，不能依靠测试依赖或 F2 的传递依赖。
2. **R0 未通过。** 缺真实主页/作品作者核实、真实第二页不同作品 ID、下载文件的 FFprobe 结果。F2 0.0.1.7 的 `model.py` 在类定义时调用远端令牌生成函数；导入失败发生在进入项目配置的请求超时之前，需要纳入异常、超时与初始化策略。没有通过改写第三方令牌逻辑或绕过访问控制来制造成功结果。
3. **M1/M2 真实链路未通过。** 没有真实 Whisper 转写、真实兼容模型输出、真实单视频和 10/30 视频批量分析的验收数据。默认 Worker 使用 missing_collector，新任务会进入 blocked，代码和 UI 都明确提示等待采集验收。
4. **主题归并有限。** `reporting.py` 使用少量固定领域和主题别名，并按规范化后的字符串统计；尚不能据此认定一般同义主题均能归并。
5. **主体核实与主营业务功能不完整。** 所有模型生成的偏好证据都不自动核实为博主本人；`business_claim` 固定为 None。保守输出避免误归属，但没有实现“存在充分公开证据时可核实并输出”的完整流程。
6. **发布时间未落库。** 采集候选结构保留 `published_at_unix`，但 `LiveTaskProcessor.associate` 创建 VideoRecord 时未写入已有的 published_at 字段，不满足完整保留作品发布时间的要求。
7. **M3 未实现。** 没有 LangGraph 审查图、工具调用、重分析/修订撤回流程、调用/token预算或审查决策审计表。已有证据引用校验不等于证据审查 Agent。
8. **桌面交付缺失。** Rust/MSVC/WebView2 构建条件未完整核实，Sidecar binaries 目录只有已跟踪的 .gitkeep，没有后端可执行文件。FFmpeg、ASR 动态依赖、模型权重、NSIS 安装包、媒体播放、启动退出与安装后持久化均未验收。
9. **配置与长字幕体验欠缺。** 模型目前仅用环境变量配置，没有设置页面；字幕超过 48,000 字符直接报错，没有分段分析实现。暂停/取消在阶段检查点生效，尚未验证长时间 ASR 或模型请求期间的响应体验。
10. **复现与发布资料欠缺。** 没有 Python/Node/Rust 的已提交依赖锁文件、GitHub CI 或项目自身 LICENSE。第三方调研已记录部分许可证，但发布安装包前仍需按实际分发内容补充许可/NOTICE清单。

## 建议完成顺序

1. 修复运行依赖声明与发布时间持久化，补齐 Sidecar 可选依赖及媒体工具的打包配置；保留并复跑后端测试。
2. 明确采用并锁定与实际验证一致的 F2 版本；在允许的网络及样本条件下完成 R0 三项真实验证。
3. 用有权处理的本地含语音视频完成真实 ASR + LLM，再用真实抖音样本完成单视频及 10/30 视频验收。
4. 安装所需 Rust/MSVC 构建环境，完成前端与 Tauri 编译、配置及媒体播放检查。
5. 补齐 M3 审查、预算、修订/撤回与审计，最后完成 Windows 安装与卸载、进程退出和持久化验收。

## Git 提交注意事项

本地两条历史提交的作者和提交者使用生成工程时的助手身份。**只修改当前 user.name/user.email 不会改变这两条已有提交。** 当前没有推送，原始历史已保留。

首次发布建议将经过审阅的源码复制到另一个全新目录，排除 `.git`、虚拟环境、node_modules、媒体、凭据与构建产物，再以自己的 Git 身份建立新的初始提交。不要直接推送当前历史，也不需要强制推送或删除本地 .git。具体步骤见 [首次提交说明](../git-submission.md)。
