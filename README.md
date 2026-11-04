# 抖音博主内容分析智能体 — 可继续开发的独立源码工程

**版本：2026-11-04 R0研究 + M0骨架 + M1/M2可测试实现。** 本工程不是已完成安装的Windows产品；真实抖音采集、真实Whisper/LLM调用、Windows Tauri编译和安装包尚未验证。测试不能替代这些验收。

## 已有能力

- **桌面**：Tauri 2 + React 18 + TypeScript + Vite，任务中心、视频与带时间戳的字幕/证据定位、博主统计报告及Markdown/JSON和SRT/VTT导出。Rust管理Python Sidecar的启动、退出和本机令牌认证。播放器通过10分钟有效期的签名URL和Range HTTP支持，尚待Windows真实播放测试。
- **后端**：Python 3.12目标、FastAPI、Pydantic、SQLite/SQLAlchemy和单Worker；任务/视频阶段持久化，暂停、取消、恢复与重启状态收敛。
- **采集**：F2可选SDK适配器，解析抖音主页/作品和分享短链，分页、作者校验、去重、10/30上限及失败记录。默认不开启真实采集；R0仍未获得真实验收样本。
- **分析**：FFprobe、FFmpeg、faster-whisper接口、OpenAI兼容请求；由程序验证并生成不可伪造的`(video_id, transcript_version, segment_id, start_ms, end_ms)`证据锚点，模型不能直接指定视频ID和时间戳。模型说话人身份不会自动视为已认证的博主身份。
- **报告**：程序统一领域/主题名、计算各视频频率与占比，跨视频整理有证据的观点和讨论对象。主营业务证据不足时明确留空；导出前重新校验引用完整性。
- **可复现实验**：50项后端自动化测试已通过（Linux Python 3.13.5）。包含真实FFmpeg处理，但采集/ASR/LLM使用显式测试替身。

最新矩阵请看[`docs/progress.md`](docs/progress.md)，GitHub源码及许可证核查请看[`docs/research/github-review.md`](docs/research/github-review.md)。开发承接说明见[`AGENTS.md`](AGENTS.md)。

## 目录

```text
backend/app/           API、SQLite、任务Worker、采集、媒体、ASR、LLM、证据、报告
backend/tests/         单元/集成测试；采集和模型替身明确标注
frontend/src/          React任务、视频/字幕、报告页面
frontend/src-tauri/    Tauri 2 Rust Sidecar与带签名播放URL
scripts/               真实抖音R0探针、本地视频分析、Windows Sidecar打包
docs/                  调研、架构、进度、可复核测试日志
```

## Windows 11准备与开发运行

需在**用户本机**已安装Python 3.12、Node.js 20+、Rust/MSVC、Tauri 2所需WebView2工具链及FFmpeg/FFprobe。命令在PowerShell中从项目根目录运行：

```powershell
py -3.12 -m venv backend\.venv
.\backend\.venv\Scripts\python.exe -m pip install -e ".\backend[test,collector-f2,asr,packaging]"
.\backend\.venv\Scripts\python.exe -m pytest -q -c backend\pyproject.toml backend\tests

# 查看脚本，然后尝试Windows Sidecar打包（首次打包可能需要调整可选依赖收集）
.\scripts\build-sidecar.ps1
cd frontend
npm install
npm run build
npm run tauri:dev
# 开发/真实集成确认通过后，才执行：npm run tauri:build
```

默认任务**会明确进入`blocked`**，表示不允许把未验收抖音采集当成成功。普通源码测试无须实际平台请求。

## R0真实平台探针

需要平台许可的真实主页/作品URL。以下是说明性的参数占位符，不是可运行的真实数据：

```powershell
.\backend\.venv\Scripts\python.exe .\scripts\live_douyin_probe.py `
  --profile "https://www.douyin.com/user/REAL_SEC_USER_ID" `
  --video "https://www.douyin.com/video/REAL_VIDEO_ID" `
  --media-dir ".media\r0" --output "docs\testing\live-r0.json"
```

如需账号持有者合法提供的访问状态，可加`--cookie-file ".secrets\douyin-cookie.txt"`。不自动读取浏览器Cookie，不打包凭据，不绕过平台访问控制。只有实测作者ID、**真实第二页不同作品ID**和视频下载后**FFprobe成功**，才能认定R0通过。仅运行代码级分页测试不算。

## 真实本地视频→Whisper→LLM链路

在本机设置并保管统一模型环境变量（不要填写到仓库或上传日志）：

```powershell
$env:OPENAI_BASE_URL = "https://你的模型服务/v1"
$env:OPENAI_API_KEY = "<本机密钥>"
$env:OPENAI_MODEL = "<实际模型名称>"
.\backend\.venv\Scripts\python.exe .\scripts\analyze_local_video.py `
  "C:\Users\Public\Videos\你有权限分析的视频.mp4" --data-dir ".media\local-testing"
```

首次faster-whisper推理可能需要下载模型权重。结果写到选定`--data-dir`的SQLite中；重复同一文件/模型会复用有版本的字幕和分析结果。此命令发起**真实ASR和真实HTTP模型请求**，但本次在执行环境中没有运行到外部模型服务，因此不声称已有真实转写结果。

## 显式实验性真实采集开关

在完成R0并遵守访问要求后，在**本地Tauri进程环境**中同时提供：

```powershell
$env:ANALYST_ENABLE_LIVE = "1"
$env:OPENAI_BASE_URL = "https://你的模型服务/v1"
$env:OPENAI_API_KEY = "<本机密钥>"
$env:OPENAI_MODEL = "<实际模型名称>"
# 可选：一个你有权使用的、只存储在本机忽略目录下的Cookie文本文件
$env:ANALYST_DOUYIN_COOKIE_FILE = ".secrets\douyin-cookie.txt"
```

此时Sidecar会尝试通过真实F2、真实媒体下载、Whisper和LLM处理任务。**只设置开关并不保证真实采集能成功**。所有失败在任务/单视频记录中保留，无证据不产出报告。请保留少量真实样本的去敏验收记录，并避免高频请求。

## 未完成与风险

M3 LangGraph证据审查Agent、Windows安装包验证、真实采集成功率、完整前端类型检查、模型费用和性能实验均未完成。Windows打包脚本尚未在具备完整采集/ASR可选依赖的机器上验证是否需要额外`--collect-all`和FFmpeg资源配置。请以[`docs/progress.md`](docs/progress.md)为准。

**仓库说明**：这是单独生成的Git仓库，不是你Windows电脑上的原项目。导入已有工程前务必先查看目标工程的未提交修改。
