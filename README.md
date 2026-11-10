# 抖音博主内容分析

Windows 本地桌面应用：Tauri 2 + React + Python 3.12 / FastAPI + SQLite，支持任务管理、本地视频分析、可选抖音采集、字幕与证据定位、博主报告导出。

当前已有 Windows 安装版。0.1.5 的普通 Edge 浏览器通道已用指定主页和作品完成作者、第二页和真实媒体验证；原作品及 10 条主页样本已完成真实 Whisper 转写与官方 ChatGPT 套餐分析，暂停恢复和导出验证通过。10 条验收走源码 Worker；30 条整批、分类归并质量和人工效果仍待验证。覆盖范围及安装结果以 docs/testing 的记录为准。当前采用固定流程与轻量 harness，LangGraph 审查 Agent 暂缓实现。

## 开始使用

安装程序生成于：

```text
frontend/src-tauri/target/release/bundle/nsis/Douyin Analyst_0.1.5_x64-setup.exe
```

启动应用，打开左侧 **模型与采集设置**：

1. 选择“使用 ChatGPT 套餐”，完成官方浏览器登录授权并选择可用模型；或选择 API Key 并填写 OPENAI_BASE_URL、OPENAI_API_KEY、OPENAI_MODEL。点击“保存并测试所选模型”。
2. 填写 Whisper 模型名（默认 small）或已有本地模型目录。首次使用模型名需下载权重，语音识别在本机运行。
3. 在任务中心点击“选择本地视频分析”，先独立测试字幕、摘要及证据。
4. 需要测试抖音时，展开“抖音采集设置”，选择 **浏览器采集（打开普通 Edge）**，开启真实采集并保存。按 [Cookie 说明](docs/douyin-cookie.md) 在本机导入自己的登录状态；出现平台登录或验证时在 Edge 窗口自行完成。支持作品、主页和分享文本，最多处理 10/30 条。

API Key 模式须兼容 Chat Completions、JSON mode 和 max_tokens；ChatGPT 套餐模式使用官方 Responses 授权通道。连接测试会产生少量所选服务用量，不采集视频。API 密钥保存在本机数据目录，Windows 使用当前用户 DPAPI 加密，页面不回显，配置不进入 Git。分析字幕会发送给所配置的模型服务。

分发及空配置检查见 [独立复现说明](docs/reproducibility.md)。

详见 [API 接入与真实测试](docs/api-setup.md)、[实际进度](docs/progress.md)、[Harness 取舍](docs/research/harness-decision.md)。

## 已实现

- 任务创建、历史、阶段状态、暂停/取消/恢复与重启持久化。
- 本地视频导入、普通 Edge 页面响应采集、F2 兼容接口、分页去重及稳定作品 ID；保留范围以用户选择的 10/30 条为限。
- 内置 FFmpeg/FFprobe，faster-whisper 可选权重推理，带时间戳及版本的字幕。
- 真实兼容接口请求、有限重试、长字幕固定分段与汇总；每次执行最多 12 次请求。API Key 模式每次输出上限 4096 tokens；套餐通道采用超时和接收字符限制，不提供输出 token 费用硬上限。
- Pydantic、字幕段引用和证据版本校验；报告到字幕定位及签名媒体 Range。
- 领域/主题程序统计，明确区分说话人归属；公开证据不足时不推断主营业务或博主个人偏好。
- Markdown/JSON 报告、SRT/VTT 字幕，通过原生保存对话框导出。
- 官方 ChatGPT 套餐登录、模型列表、用量管理与断开连接；API Key 为单独选择，不自动回退。
- 独立采集检测和 JSON 导出，逐步核对分享解析、作者、作品、第二页和真实媒体，不需要模型配置。
- 模型设置和连接测试，Windows 密钥加密保存，分析执行记录保留调用次数与服务商返回的用量。
- Rust 管理 Sidecar 与 Windows Job 进程树，NSIS 安装版包含 Python 运行库、采集/语音组件及本次构建选择的媒体工具；模型权重由用户另行下载。

引用 ID 和 JSON 检查确认结构及材料存在性，不保证模型的语义结论正确。主体身份核实、通用主题同义归并、真实分析效果和界面中实际播放体验仍需样本测试。

## 开发与测试

需要 Python 3.12、Node 20+、Rust MSVC 工具链、Visual Studio C++ Build Tools / Windows SDK 及 WebView2。FFmpeg 用于测试和选择内置媒体工具的构建。

构建脚本支持查找仓库上一级 `.toolchains` 内的 Rust 工具链。登录桥接构建固定使用 Node.js 22.20.0。全新环境可使用 Python 自带 venv 和 pip：

```powershell
py -3.12 -m venv backend\.venv
.\backend\.venv\Scripts\python.exe -m pip install -r backend\requirements-windows.lock
.\backend\.venv\Scripts\python.exe -m pip install -e .\backend --no-deps
```

若虚拟环境由 uv 创建，用 `uv pip install --python backend\.venv\Scripts\python.exe` 安装上述依赖，无需假定环境内带有 pip。非 Windows 后端开发可安装 `backend[test]`，不要使用 Windows 专用锁文件。

```powershell
.\backend\.venv\Scripts\python.exe -m pytest -q -c backend\pyproject.toml backend\tests
cd frontend
npm ci
npm run build
cd ..
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\build-desktop.ps1 -BundleMediaTools
.\backend\.venv\Scripts\python.exe scripts\smoke_desktop.py 'E:\安装目录\douyin-analyst-desktop.exe'
```

ExecutionPolicy 参数仅用于运行当前已审阅的本地脚本，不修改系统策略。`smoke_desktop.py` 使用独立 `.media/desktop-smoke` 数据目录及合成视频，不调用平台和模型；不等于 WebView 中的视频实际播放验收。

## 真实验证入口

```powershell
.\backend\.venv\Scripts\python.exe scripts\analyze_local_video.py 'E:\有权处理的视频.mp4'
.\backend\.venv\Scripts\python.exe scripts\live_douyin_probe.py `
  --collector browser `
  --data-dir "$env:LOCALAPPDATA\com.douyinanalyst.desktop" `
  --profile 'https://www.douyin.com/user/真实主页ID' `
  --video 'https://www.douyin.com/video/真实作品ID' `
  --media-dir '.media\r0' --output 'docs\testing\live-r0.json'
```

R0 必须实际证明作者识别、第二页不同作品 ID 和下载后 FFprobe 成功。网络、授权或平台拒绝时保留失败记录，不绕过访问控制。

## 源码结构

`backend/app` 为后端，`frontend/src` 为界面，`frontend/src-tauri` 为桌面宿主，`scripts` 为验证及构建入口。技术复用和许可证来源记录于 [GitHub 调研](docs/research/github-review.md)。
