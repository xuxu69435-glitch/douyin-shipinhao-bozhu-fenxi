# 开发记录

范围：仅抖音，Windows本地Tauri 2桌面应用。**“代码已实现”≠“真实抖音通过”≠“Windows安装包通过”。**

## 0.1.5 普通浏览器采集与真实分析（2026-11-10）

- 新增固定版本 playwright-core 1.65.0 的 Node 桥接，用普通 Edge 临时上下文加载实际页面，观察其正常作品响应；Cookie 只来自用户手动导入状态，经私有 stdin 传递。不添加占位安全头、不使用隐身补丁、不读取日常浏览器资料。
- 设置可选择浏览器采集或 F2 兼容模式，任务和独立检测使用同一适配器。浏览器采集最多等待 90 秒并自动关闭；中断清理覆盖合成子进程测试，Windows 桌面退出仍保留 Job 进程树保护。诊断 IPC 超时调整到 150 秒。
- 控制保留样本为 10/30 条，忽略超过范围的网页预加载；程序检查作者、分页游标、作品 ID 和去重。实测某个 CDN 返回 403 而同作品另一地址正常，新增最多 3 个真实媒体候选的有限回退。
- 两条原分享链接在源码及打包后端的浏览器通道均完成采集验收：主页 2 页、30 条去重作品、第二页新增 12 条；原作品 150.165 秒、28962553 字节，第二页样本 258.972 秒、56699567 字节，均含音视频流并通过 FFprobe。见 testing/browser-source-r0-0.1.5.json、testing/browser-packaged-r0-0.1.5.json。
- 原作品真实 Whisper small CPU 转写与已授权 ChatGPT 套餐模型分析完成，61 段字幕、36 处证据引用重验通过，SRT/VTT 导出成功；未使用 API Key。见 testing/real-douyin-analysis-0.1.5.json。
- 后续 10 条主页真实样本经源码 SingleWorker 完成整批处理，10 成功、0 失败、0 无语音；总媒体 1594.488 秒，580 段字幕、351 处单视频引用重验通过，Markdown/JSON 博主报告及 10 份 SRT、10 份 VTT 导出成功。模型均为保存的 ChatGPT 套餐 gpt-6.1-sol，共 10 次真实请求，未加载或使用 API Key。见 testing/real-profile-10-chatgpt-0.1.5.json。
- 实测暂停后两条已落库分析在恢复时复用，原字幕/分析版本保持一致，各仍只有一次模型请求。报告样本和领域计数复核通过，10 份媒体复检、字幕末尾与时长检查通过，原模型设置校验保持一致。见 testing/real-profile-pause-chatgpt-0.1.5.json、testing/real-profile-resume-chatgpt-0.1.5.json。上述为自动链路验收，不代表人工质量或 Tauri 内实际播放通过。
- 新增 scripts/analyze_douyin_profile.py 真实验收入口，固定使用配置的 ChatGPT 套餐通道，独立数据目录，可恢复暂停/失败任务；不复制授权、不读取 API Key。语法、帮助入口及合成 API 模式拒绝检查通过。现有桌面配置入口保留，后端与桌面运行代码未在此后续验收中变更。
- 实际报告仍将“娱乐”和“剧情娱乐”等相近领域分列，同义主题归并不充分；计数正确不代表分类体系稳定，后续需改进并人工复核。30 条整批分析及人工质量验收尚未完成。
- 后端正常桌面权限下 124 项测试通过，浏览器桥接 4 项测试通过。首次受限环境中的进程清理测试未能使用 taskkill；正常桌面权限复验通过，没有删除退出保护。前端、cargo check、Rust release、PyInstaller 和 NSIS 构建完成；打包及安装空配置七项检查、发行及安装桌面各两次生命周期检查通过。
- 0.1.5 覆盖安装退出码 0；原 3 条任务、模型设置、Cookie 和授权保留，后端与构建一致。桌面仅相差 Tauri 安装类型标记的 3 字节，规范化后一致。保留校验之后按本机选择启用浏览器采集，其他模型字段及密钥密文保持一致。详见 testing/windows-update-0.1.5.md 和 testing/windows-installer-0.1.5.json。
- 已将现有独立检出更新到 60a4af9；独立 Python 环境更新 editable 包，前端及浏览器依赖重新 npm ci。124 项后端、4 项浏览器、前端构建和七项空配置检查通过，见 testing/fresh-checkout-source-0.1.5.json。此次未在该目录重建完整 NSIS，不等同于另一台机器验收。

## 0.1.4 浏览器 Cookie 兼容及网关定位（2026-11-10）

- 根据本机实际输入的去敏结构定位第 51 项为无名称 Cookie。保留其原始单行形式，不添加等号、不丢字段；无名称值不计为登录标记。合成回归、API 加密保存和重启检查覆盖该情形，不将真实凭据写入测试。
- 只从手动导入状态提取真实 UIFID，补齐客户端标识；在 403 中仅识别固定网关分类，响应原文、凭据和签名地址不入报告。独立检测可明确提示缺少网页安全签名，不继续把该情形统一归因于 Cookie。
- 后端 118 项测试通过；TypeScript/Vite、cargo check --locked、Rust release、PyInstaller 与 NSIS 构建通过。打包空配置六项自检、打包及安装后端进程检查、发行版与安装桌面各两次隔离生命周期检查通过。
- 0.1.4 覆盖安装退出码 0；原任务、模型配置及套餐授权校验一致，安装后端与构建文件一致。之后将用户提供的 70 项 Cookie 加密导入并完成往返校验，移除本任务临时明文文件。安装清单见 testing/windows-installer-0.1.4.json。
- 使用来自 www.douyin.com 的手动 Cookie（70 项、含登录标记）实测原主页和作品：链接解析通过，实际请求仍 HTTP 403 / gateway_signature_missing。作者、第二页和软件媒体获取尚未通过；见 testing/share-links-cookie-www-0.1.4.json。
- 最终安装后端经私有 stdin 接收本机已保存登录状态，再分别检测两条链接，结果与源码一致；见 testing/installed-share-links-cookie-0.1.4.json。未把凭据放入命令参数、环境变量或报告。
- 正常浏览器访问同一公开作品，标题及作者“开心锤锤”可见；DOM 记录 duration=150.166 秒、currentTime=68.036448 秒、readyState=4、paused=false。此为网页真实播放证据。页面使用 blob 媒体流，浏览器导出调用失败，没有取得可供 FFprobe 验证的文件，不能将播放替代采集验收。
- 已再次阅读 F2 PR #446、MediaCrawler 380b426 及其他方案；参考依据与未采用项见 research/github-review.md。正常浏览器加载路径值得后续验证，尚未实现为可分发的采集适配器。本轮未调用大模型。

## 0.1.3 安装及复现复验（2026-11-10）

- 修复版 NSIS 安装包构建完成并覆盖安装成功。原有 3 条任务、模型设置、独立套餐授权及 Cookie 状态均经更新前后校验保留；安装后端与构建文件一致。安装包校验见 testing/windows-installer-0.1.3.json。
- 打包及安装后端均通过合成 Cookie 导入、DPAPI 加密、重启读取和清除；安装版在仅含 Windows System32 的 PATH 下完成空配置六项自检，不依赖构建机的 Python、Node 或 FFmpeg PATH。
- 发行版及安装桌面各两次隔离生命周期检查通过：认证代理、内置媒体工具、合成媒体 Range、历史持久化及退出后的进程树清理。见 testing/release-desktop-0.1.3-smoke.json 和 testing/installed-desktop-0.1.3-smoke.json；不代表 WebView 实际播放已验收。
- 独立检出 `11ffb42`、独立 Python 虚拟环境及新 npm 安装完成 111 项后端测试、前端构建与六项空配置自检。仍为同一 Windows 机器，不冒充另一台机器的实测。
- 该独立环境也完成 PyInstaller 后端打包，生成产物通过六项空配置检查及后端进程复验；见 testing/fresh-checkout-packaged-0.1.3.json 和 testing/fresh-checkout-packaged-backend-0.1.3-smoke.json。确认此后端构建没有依赖主开发虚拟环境中额外安装的组件。
- 已成功加密保存手动导入的真实 Cookie（用户报告来源为 imapi.douyin.com），发现常见登录标记。用此状态分别实测原主页与作品短链，解析通过，作品接口均仍返回 HTTP 403；见 testing/share-links-cookie-0.1.3.json。尚未获得作者、第二页或媒体证据，继续核对 www.douyin.com 请求来源及当前接口适配。本轮没有调用大模型。

## 0.1.3 登录状态导入与独立复现（2026-11-09）

- 支持在设置中手动粘贴单行 Cookie 并用 Windows DPAPI 加密保存，只回显项数及登录标记状态；支持清除，也兼容带 UTF-8 BOM 或 Cookie: 前缀的原文件。不会自动读取浏览器资料。
- 固定采集和独立检测均使用同一登录状态入口；独立检测不加载模型密钥。Secret 请求格式错误不回显原始内容。
- F2 0.0.1.7 仍为适配依赖，限制请求源、启用 HTTPS 证书校验、禁止跨站发送登录状态，关闭 SDK 可能记录签名地址的日志；保留限流与拒绝状态，不添加网关绕过标头。
- Cookie 获取、导入及验收步骤见 douyin-cookie.md；安装/源码复现见 reproducibility.md。新增 --self-check，使用空临时目录检查媒体、音频解码、SQLite、合成凭据加密和内置登录桥接，不联网或加载用户设置。
- 默认 small 模型固定为已经验证的公开权重 revision，写入转写缓存版本；81 项 Windows Python 依赖与锁文件一致。
- 后端 111 项测试通过；源码空配置自检六项通过。匿名实测仍为 403，见 testing/share-links-anonymous-0.1.3.json。带用户手动导入状态的两条真实链接验收仍待执行，不标记采集成功。
- 实际导入界面出现 422 后，用合成数据复现旧 SimpleCookie 解析器拒绝 JSON 内容、静默丢失后续字段及合并同名 Cookie 的问题；现保留浏览器单行值和顺序，仅校验名称、边界、长度和控制字符。七项新增回归及独立源码进程的导入、加密、重启、清除通过；不读取用户输入来构造测试。

## 0.1.2 套餐授权与独立采集检测（2026-11-09）

- 接入官方 Sign in with ChatGPT DevKit 固定版本，支持浏览器授权、DPAPI 凭据存储、自动续期、实际账户模型列表、公开 Responses 流完成判断及断开连接。与 API Key 模式显式区分，不自动回退。
- 保留固定分析 harness；套餐通道不支持 max_output_tokens，记录接收字符/超时约束，且不把它当作费用硬上限。LangGraph Agent 继续暂缓。
- 任务页增加不调用模型的独立采集检测，隔离进程最多 45 秒，保留已通过阶段；检查链接、作者、作品、第二页、真实下载及 FFprobe。结果本机保存并可导出 JSON。
- 重新实测两条分享链接，解析通过；主页作品与作品详情均为 HTTP 403。作者核实、第二页及媒体未通过。详见 testing/share-links-2026-11-09.json；升级依赖不能替代访问权限验证。
- 后端 89 项测试通过；官方 SDK 56 项通过、1 项 Windows 不适用项跳过；真实 DPAPI 加密桥接和跨进程解密使用合成凭据验证。真实官方授权、账户模型列表和套餐文字请求已验证；合成语音视频的真实 small CPU 推理、套餐分析及证据入库通过，见 testing/chatgpt-plan-0.1.2.json 与 testing/real-asr-0.1.2.json。
- 真实推理重现 faster-whisper 1.2.1 与 PyAV 19 的 metadata_errors 接口不兼容；按上游已确认问题锁定 PyAV <19，Windows 锁文件使用 18.1.0，增加真实 PCM 解码回归。领域不足归为“未分类”，提示版本更新以避免旧缓存混用。
- 官方接入版本、许可、调用限制及验收边界见 research/chatgpt-plan.md。桌面构建与安装结果见 testing/windows-update-0.1.2.md。

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
- **仅当用户自主在本机明确配置**`ANALYST_ENABLE_LIVE=1`、所选模型通道（API Key 三项或官方 ChatGPT 套餐授权），并安装F2/ASR依赖后才建立真实处理Worker。设置此环境变量**不等于**R0通过，也不保证平台接口可用。
- 可自行提供受平台规则允许的Cookie文件路径`ANALYST_DOUYIN_COOKIE_FILE`；不会从浏览器自动收集登录态，也不会打包该文件。
- `scripts/live_douyin_probe.py`是R0手工真实验收入口；`scripts/analyze_local_video.py`是**真实本地媒体→Whisper→真实LLM**独立入口。均不得将测试替身结果作为实测证据。
- 审核主体归属：模型说“creator”时也暂不设置`creator_identity_verified=true`；程序不会据此断言博主个人喜好。主营业务无公开核实证据则不推断。
- 报告/字幕导出时重新验证数据库对应的字幕版本、视频与时间范围；来源删除或修改则返回HTTP 409，不返回看似有效的旧证据。

## 后续验证入口

1. 按 [API 接入说明](api-setup.md) 配置模型服务，用有权处理的本地 MP4 验证转写、字幕时间、摘要及证据引用，记录模型版本、质量和费用。
2. 使用真实主页和作品链接运行 `scripts/live_douyin_probe.py`，保存去敏的 `docs/testing/live-r0.json`。主页作者、作品作者、第二页不同 ID 及下载文件 FFprobe 均成功后，R0 才可标为通过。
3. 在 Windows 安装版中人工验证媒体播放、文件选择及导出保存，并检查真实 10/30 视频任务的暂停、取消、恢复和失败记录。
4. 根据真实样本结果评估是否加入 M3 证据审查 Agent；继续限制在已存字幕内，不自动扩大采集范围。
