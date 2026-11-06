# Windows 桌面交付记录（2026-11-04）

## 可运行位置

- 已安装程序：`E:\1bishe\Douyin Analyst\douyin-analyst-desktop.exe`。
- NSIS 安装包：`frontend/src-tauri/target/release/bundle/nsis/Douyin Analyst_0.1.0_x64-setup.exe`。
- 真实 API 接入：打开应用左侧“模型与采集设置”，填写三项 OPENAI 配置；见 [接入说明](../api-setup.md)。

这是供本机真实样本测试的安装构建，不能据此宣布 R0、真实模型或全部产品体验验收完成。

最终安装包为 **257.18 MiB**，源码提交 `e6e815d`。SHA-256：`426af7546b7368353fed50450ab81364929c70da9759a21fe2b991213bb9c773`。详细版本与哈希见 [安装包清单](windows-installer.json)。安装后后端哈希与打包源文件一致。

## 已实际通过

| 检查 | 结果 |
| --- | --- |
| 后端测试 | Windows / Python 3.12.2，64 passed，10.76 秒；包含中文视频路径及 UTF-8 元数据回归 |
| 前端 | TypeScript 完整检查与 Vite 6.4.5 构建通过，33 个模块 |
| Rust | 工作区专用 rustc 1.99.1，MSVC / Windows SDK 10.0.22621.0，cargo check 和 release 编译通过 |
| Sidecar | PyInstaller 6.22.3 onedir 构建；真实可执行文件健康检查、认证拒绝、重启任务与加密设置持久化、进程退出通过 |
| 安装 | NSIS 安装程序运行并返回 0，安装目录包含桌面宿主、后端和 _internal 运行资源；最终包使用 zlib 压缩 |
| 安装后两次启动 | 认证代理、受限路径、配置不回显密钥、历史持久化、签名媒体 Range、退出无遗留后端进程均通过 |
| 独立依赖 | 将桌面子进程 PATH 限为 Windows System32，仍能找到内置 FFmpeg/FFprobe 并导入 ASR 本机库，无需系统 Python/Node/Rust |

证据：[安装后桌面自检 JSON](installed-desktop-smoke.json)、[安装后端及中文视频导入 JSON](installed-backend-smoke.json)、[打包后端自检 JSON](packaged-sidecar-smoke.json)、[首次发行版桌面自检 JSON](desktop-smoke.json)。桌面测试数据位于独立 `.media/desktop-smoke` 目录，后端自检使用临时目录，不进入用户正式分析数据。

本次安装包包含 F2 0.0.1.7、faster-whisper 1.2.1、CTranslate2 4.8.5、ONNX Runtime 1.31.1 及 FFmpeg/FFprobe；没有下载 Whisper 权重，没有调用付费模型或真实抖音采集。

自动化测试存在上游 Starlette TestClient 弃用提示及 Pydantic model_ 命名提示，测试均通过。

中文文件回归重现了 Windows 默认 GBK 解码 FFprobe UTF-8 输出时的异常。修复后，中文文件名和元数据标题验证通过；打包后端还用合成的中文无声视频走本地导入及 no_speech 完整路径，不触发模型推理。

## 待验证

- 真实主页/作品作者、真实第二页新 ID、下载后真实媒体播放。
- Whisper 权重实际转写、真实 API 响应质量、主题归并效果、主体归属或费用准确性。
- WebView 中实际播放、点击文件选择/保存对话框的人工交互验收。
- 真实 10/30 视频长任务的性能、费用和平台失败恢复率。

LangGraph 审查 Agent 暂缓实现。

## 验证方法与环境说明

安装后自检实际启动打包的 Tauri 宿主和 Sidecar；使用合成本地 MP4 检查 HMAC 媒体链接和 HTTP Range，不冒充真实平台样本或 HTML5 播放验收。两次启动后查询历史数量递增，桌面退出后检查宿主记录的后端 PID 已结束。

在受限执行环境中首次启动出现 Windows“拒绝访问”；同一构建在正常桌面权限下通过。应用退出时先请求正常关闭，再由 Windows Job 清理后代进程。

构建脚本只打包项目运行库与明确选择的媒体工具，不复制本机配置、Cookie 或模型权重。依赖及许可证清单位于 `_internal/THIRD_PARTY_NOTICES.txt`。
