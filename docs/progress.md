# 开发记录

范围：仅抖音，Windows本地Tauri 2桌面应用。**“代码已实现”≠“真实抖音通过”≠“Windows安装包通过”。**

## 0.1.1 分享链接与界面修复（2026-11-06）

- 支持抖音移动分享页 `/share/user/` 和 `/share/video/`，统一为标准主页/作品地址并移除跟踪参数。两条真实分享短链均已通过实网跳转解析。
- 实际匿名 F2 作品读取返回 HTTP 403；此类平台拒绝按 `DOUYIN_ACCESS_DENIED` 保留为可恢复的阻塞，已解析的作品地址与单视频数量保留。真实作者详情、分页和下载尚未通过。
- 任务页采用紧凑的标题及左右布局，导航保持可见，历史记录每页 8 条并限制滚动区域；设置页使用双列字段，采集选项可折叠。
- 后端 76 项测试通过，包含分享文本、移动跳转、不安全跳转及平台拒绝后恢复任务的回归检查。前端构建与 Rust 检查通过。
- 0.1.1 NSIS 安装包构建及覆盖安装通过；发行版和安装版均通过两次隔离桌面自检。更新前后的原任务与模型配置校验一致。
- 详细验证与安装结果见 [0.1.1 更新验证](testing/windows-update-0.1.1.md)。

## 0.1.0 Windows 桌面交付（2026-11-04）

- 当前采用固定流程与轻量 harness，LangGraph 审查 Agent 暂缓；真实样本、模型 API 及效果测试待验证。
- Windows / Python 3.12.2，完整后端测试 **64 passed**。TypeScript/Vite 构建、Rust cargo check、发行版编译及 NSIS 构建均通过。
- 两次真实桌面离线自检通过：认证代理、密钥不回显、合成视频签名 Range、打包语音库加载、内置 FFmpeg/FFprobe、重启历史持久化与后端进程树退出。详见 testing/desktop-smoke.json；没有据此声称实际 WebView 播放、真实采集或真实模型推理通过。
- 已补基础 httpx 依赖、采集发布时间持久化、短链单视频数量修正、原生文件选择及导出保存、模型与采集设置、连接测试、Windows DPAPI 密钥保存、运行时组件打包及工作目录管理。
- 修复重复处理已有媒体时新 CDN 地址缺失导致无法复用的问题；从旧报告回看证据时选择其对应的分析/字幕版本，避免混用最新分析与旧字幕。
- 真实合成样本重现 Windows GBK 解码 FFprobe 中文路径/元数据时崩溃，已指定 UTF-8 并加入中文文件名及标题回归测试。
- 已补有限请求/输出/重试、长字幕分段汇总、模型服务参与缓存版本、缓存证据核查及 analysis_runs 运行记录；中断与失败不丢已有字幕。机制及取舍见 research/harness-decision.md。
- 依赖记录：backend/requirements-windows.lock、frontend/package-lock.json、frontend/src-tauri/Cargo.lock。Sidecar 带第三方许可库存清单，不携带模型权重或用户配置。
- API 接入位置与顺序见 api-setup.md。安装后的最终验证结果与路径在 testing/windows-desktop-delivery.md 中记录。
- 最终安装版已更新到 `E:\1bishe\Douyin Analyst`，安装后端与源码打包文件哈希一致；两次桌面自检及中文无声视频导入、加密配置和重启持久化检查通过，详见 testing/installed-desktop-smoke.json 与 testing/installed-backend-smoke.json。安装包 257.18 MiB，校验值见 testing/windows-installer.json。

### 待验证

真实抖音作者、第二页和可播放媒体；真实 ASR/LLM 质量与费用；WebView 实际播放和原生文件对话框交互；10/30 视频的真实恢复/失败表现；通用同义主题归并与主体身份核实。主营业务证据不足仍保持留空。M3 Agent 暂缓实现。

以下保留修复前的检查快照及早期 Linux 验证记录；不能用其中旧的“工具链缺失”描述覆盖上述最新结果。

## Windows 本机补充核查（修复前历史快照，2026-11-04）

- 已在 Windows / Python 3.12.2 隔离环境运行后端测试：**50 passed**；本地 Python 子进程的健康检查、认证、重启持久化与退出检查通过，不代表 Tauri/PyInstaller 生命周期通过。
- 前端依赖安装成功，**完整 TypeScript 检查及 Vite 构建通过**。实际执行 `npm run tauri:build` 因缺少 cargo 失败，没有生成 Windows 安装包。
- 纯基础后端安装缺少 httpx 运行依赖，实际导入失败；F2 SDK 可选依赖可安装，但导入采集模块会请求远端令牌，受限网络下失败；R0、真实 ASR/LLM、M3 和 Windows 安装包仍未通过。
- 新发现的发布时间落库、固定主题别名、主体核实及 Sidecar 打包等缺漏，连同前端安装/构建结果，统一记录在 [Windows 运行就绪检查](testing/windows-readiness-2026-11-04.md)。以下原阶段矩阵与 Linux 执行证据保留为历史记录。

## 阶段验收矩阵（早期记录）

| 阶段 | 已实施并可核对 | 自动化结果 | 仍不通过/缺失 |
| --- | --- | --- | --- |
| **R0：GitHub调研、F2可行性** | GitHub真实源码、版本commit、许可证、关键文件及官方文档调研；F2接口适配器、分页去重逻辑；独立真实探针脚本 | 合成分页、链接安全测试通过 | **真实抖音主页作者、视频作者、第二页新作品、媒体FFprobe均未实测；R0验收未通过** |
| **M0：工程骨架** | SQLite/SQLAlchemy、FastAPI令牌API、单Worker状态机、Tauri Rust Sidecar及React任务UI、Windows打包脚本 | 后端自动化覆盖任务状态、重启恢复、异常和SQLite持久化 | Rust/Tauri/Node依赖缺失；React无法完成依赖安装与完整构建；Windows Sidecar与NSIS未验证 |
| **M1：单视频处理** | F2单视频作者归属接口；允许域名媒体下载与FFprobe；FFmpeg抽音；faster-whisper可选真实引擎；OpenAI兼容真实HTTP请求；Pydantic输出、字幕ID交叉校验和版本化复用；API SRT/VTT；Tauri签名媒体播放URL、Range响应；视频详情UI、字幕跳转 | 真实本地FFmpeg、测试替身ASR/LLM、HTTP API、非法引用拒绝、缓存重试、签名票据测试均通过 | 尚未安装并运行真实faster-whisper；未调用真实LLM；未从抖音实际下载；Tauri播放器真机运行未验收 |
| **M2：博主批量报告** | 可显式启用的F2单Worker流程；视频10/30上限、持久任务阶段、同ID去重及失败统计；领域/主题程序计算占比、别名归一；引用/说话人归属保守策略；带来源的JSON/Markdown报告；前端报告页面和报告到字幕定位 | 测试替身采集的两条视频和部分失败场景，真实FFmpeg媒体生成，假ASR/LLM，数据库报告闭环 | 真实博主作品分页、真实批量ASR/LLM和分析准确率未验证；主营业务判定始终保守留空，不编造 |
| **M3：LangGraph审查** | 确定按已有字幕和报告审查、限制调用与预算，不扩充采集范围 | 未测试 | **尚未实现**。前面的真实验收与依赖未满足 |
| **M4：Windows交付** | PowerShell打包脚本与Rust外部二进制配置存在 | 后端本地测试结果如下 | **没有Windows安装包或打包验收**。缺Rust、Node依赖和Windows构建环境 |

## 早期 Linux 验证记录

- OS/Python：Linux容器，Python **3.13.5**；目标Python 3.12仍需在Windows运行。
- 后端测试：`cd backend && python -m pytest -q -o addopts=''`，**50 passed**，见 [`testing/backend-pytest.txt`](testing/backend-pytest.txt)。
- FFmpeg：`ffmpeg 7.1.5`，运行媒体生成、FFprobe、FFmpeg音轨抽取、媒体HTTP Range。ASR和LLM均使用标记为`test_fixture`的测试替身，**不能算作真实模型测试**。
- TypeScript：全局TS `transpileModule`仅验证4个TS/TSX文件**语法**，0语法错误。`npm install --offline`失败`ENOTCACHED`；`npm run build`因缺React/Vite/Tauri依赖而失败。详情：[`testing/frontend-build.md`](testing/frontend-build.md)。
- Rust/Cargo/NSIS：未运行，本容器没有相应工具链和Windows环境。
- 网络：调研可读取 GitHub 源码；Linux shell 无法解析 `github.com` 和 `registry.npmjs.org`，未执行真实抖音端点调用。

## 代码控制与真实采集门槛

- 默认`create_app`的Worker是`missing_collector`，新建任务会如实进入`blocked`。
- **仅当用户自主在本机明确配置**`ANALYST_ENABLE_LIVE=1`、模型三项`OPENAI_BASE_URL`/`OPENAI_API_KEY`/`OPENAI_MODEL`，并安装F2/ASR依赖后才建立真实处理Worker。设置此环境变量**不等于**R0通过，也不保证平台接口可用。
- 可自行提供受平台规则允许的Cookie文件路径`ANALYST_DOUYIN_COOKIE_FILE`；不会从浏览器自动收集登录态，也不会打包该文件。
- `scripts/live_douyin_probe.py`是R0手工真实验收入口；`scripts/analyze_local_video.py`是**真实本地媒体→Whisper→真实LLM**独立入口。均不得将测试替身结果作为实测证据。
- 审核主体归属：模型说“creator”时也暂不设置`creator_identity_verified=true`；程序不会据此断言博主个人喜好。主营业务无公开核实证据则不推断。
- 报告/字幕导出时重新验证数据库对应的字幕版本、视频与时间范围；来源删除或修改则返回HTTP 409，不返回看似有效的旧证据。

## 后续验证入口

1. 按 [API 接入说明](api-setup.md) 配置模型服务，用有权处理的本地 MP4 验证转写、字幕时间、摘要及证据引用，记录模型版本、质量和费用。
2. 使用真实主页和作品链接运行 `scripts/live_douyin_probe.py`，保存去敏的 `docs/testing/live-r0.json`。主页作者、作品作者、第二页不同 ID 及下载文件 FFprobe 均成功后，R0 才可标为通过。
3. 在 Windows 安装版中人工验证媒体播放、文件选择及导出保存，并检查真实 10/30 视频任务的暂停、取消、恢复和失败记录。
4. 根据真实样本结果评估是否加入 M3 证据审查 Agent；继续限制在已存字幕内，不自动扩大采集范围。
