# 0.1.5 Windows 更新验证（2026-11-10）

普通 Edge 浏览器采集已接入任务处理与独立检测。原主页和作品分享链接在源码及打包后端中均完成作者识别、分页及真实媒体验证；原视频另完成一次真实转写与模型分析。

## 验证结果

| 项目 | 实际结果与记录 |
| --- | --- |
| 自动化 | 后端 124 passed，浏览器桥接 4 passed；前端 TypeScript/Vite、cargo check --locked、Rust release、PyInstaller、NSIS 构建通过。后端结果见 [测试输出](backend-pytest-0.1.5.txt)。 |
| 原作品 | 真实作者与作品 ID 核实，下载 28962553 字节、150.165 秒的音视频文件并通过 FFprobe。 |
| 原主页 | 2 页、30 条去重作品，第二页新增 12 条；第二页样本下载 56699567 字节、258.972 秒并通过 FFprobe。见 [源码实测](browser-source-r0-0.1.5.json)、[打包实测](browser-packaged-r0-0.1.5.json)。 |
| 真实分析 | 原作品 Whisper small CPU 产生 61 段字幕；已授权套餐模型完成真实分析，36 处字幕引用重验通过，SRT/VTT 导出成功。该次未使用 API Key；见 [分析记录](real-douyin-analysis-0.1.5.json)。 |
| 后续 10 条整批 | 源码 SingleWorker 完成 10/10、0 失败，580 段字幕及 351 处单视频引用重验通过，10 次模型请求均来自 ChatGPT 套餐；MD/JSON 报告和每条 SRT/VTT 导出成功。暂停时已落库的两条分析恢复后复用，版本不变且无额外模型请求。见 [批量](real-profile-10-chatgpt-0.1.5.json)、[恢复及导出](real-profile-resume-chatgpt-0.1.5.json)。该次不代表在安装版界面操作整批任务已验收。 |
| 空配置运行 | 打包及安装后端七项自检通过，包括 Node 与 Playwright 1.65.0 组件加载、检测到本机 Edge。该自检不启动浏览器、不联网、不读用户设置；见 [安装自检](installed-clean-data-0.1.5.json)。 |
| 独立源码环境 | 独立检出更新到 60a4af9，沿用此前独立锁定 Python 环境；前端和浏览器依赖重新 npm ci。124 项后端、4 项浏览器、前端构建与七项空配置检查通过；见 [复验记录](fresh-checkout-source-0.1.5.json)。仍为同机，没有在该目录重建完整 NSIS。 |
| 后端与桌面生命周期 | 发行版及安装版隔离检查覆盖认证、媒体 Range、历史重启及进程退出。见 [发行桌面](release-desktop-0.1.5-smoke.json)、[安装桌面](installed-desktop-0.1.5-smoke.json)、[安装后端](installed-backend-0.1.5-smoke.json)。合成媒体检查不代表 WebView 实际播放。 |
| 覆盖安装 | 退出码 0，原 3 条任务、模型设置、套餐授权及 Cookie 均保留；后端与打包文件一致。Tauri 桌面仅相差安装类型标记的 3 字节：安装版 NSS，随后 cargo check 将构建目录标记恢复为 UNK。规范化该标记后文件一致，详见 [安装清单](windows-installer-0.1.5.json)。 |

安装包为 `frontend/src-tauri/target/release/bundle/nsis/Douyin Analyst_0.1.5_x64-setup.exe`，305328079 字节（291.18 MiB）。SHA-256：`3692cad412fbc48565f99a0593e16eeed32fa413627352719419cfd6de2fb215`。

安装后已按本机选择启用浏览器采集；其他模型字段及原密钥密文保留。新用户须安装 Edge，并按 [复现步骤](../reproducibility.md) 选择采集模式、准备自己的登录状态和模型配置。

## 尚未完成的验收

- 真实 30 条全批转写、跨视频分析及人工质量核对；10 条自动链路、暂停恢复与导出已通过。
- 实际报告仍存在相近领域分列（如“娱乐”“剧情娱乐”）和同义主题未充分归并，分类质量待改进。
- Tauri WebView 中实际点击播放与原生文件对话框的人工交互。
- 不同机器、账户及更多作者的成功率。现有真实结果来自同一 Windows 机器的指定样本。
- F2 兼容通道仍为 HTTP 403；浏览器通道的通过不代表接口通道已经修复。

LangGraph 审查 Agent 按当前范围暂缓，固定流程与轻量 harness 保留。早期 prototype 和 403 报告是历史记录，当前结果以带 `0.1.5` 的最终报告为准。
