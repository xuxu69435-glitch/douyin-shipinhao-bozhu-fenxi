# Windows 独立复现说明

目标是让使用者从自己的空配置开始完成检查。应用不携带开发机 Cookie、账户授权、密钥、模型目录或数据库。平台允许访问、账户授权成功与软件离线运行是不同的验收项目。

## 安装版：无需开发工具

环境为 Windows x64，桌面需要 WebView2 Runtime；安装程序按 Tauri 配置检查该组件。当前本机验证 Windows 11，其他 Windows 安装环境仍需分别记录结果。

1. 获取同一版本的 Windows 安装程序，按 `docs/testing/windows-installer-版本号.json` 的 SHA256 核对文件。安装到自己选择的目录。
2. 应用内置 Python 后端、FFmpeg/FFprobe、语音运行库与 Node 登录桥接；最终用户无需另装 Python、Node、Rust 或 FFmpeg。Whisper 模型权重在首次使用时独立下载。
3. 运行不读取已有设置的离线自检。下例路径换成自己的安装目录：

```powershell
& 'C:\你的安装目录\douyin-analyst-backend.exe' --self-check --output "$env:TEMP\douyin-check.json"
Get-Content -LiteralPath "$env:TEMP\douyin-check.json"
```

也可在源码目录运行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\verify-installation.ps1 `
  -InstallDirectory 'C:\你的安装目录'
```

自检在新的临时目录中检查运行依赖、合成音视频、真实 PCM 解码、SQLite 重开持久化、合成凭据 DPAPI 加密及无账户的内置登录组件；不联网、不调用模型、不加载权重、不读取已有设置。`offline_checks_passed:true` 只表示这些离线项目通过，不代表抖音和模型验收完成。失败时可提供该 JSON，不要提供登录状态文件。

## 每个人独立接入

- **抖音**：使用自己的浏览器登录，按 [Cookie 获取与导入](douyin-cookie.md) 手动导入。软件只在用户操作后保存该内容，不自动读取其他浏览器资料。密文绑定当前 Windows 用户，不应复制给别人。
- **文字模型**：按 [模型接入说明](api-setup.md)，选择官方 ChatGPT 套餐登录或自己的兼容 API。不能使用开发者的套餐授权或 API Key，失败时不自动切换通道。
- **语音模型**：默认 `small` 固定为 `Systran/faster-whisper-small` 的 `536b0662742c02347bc0e980a01041f333bce120`，公共权重无需 Hugging Face Token。网络不可用时可在另一台有网络的机器准备相同权重目录，再在设置中填写自己的本地目录。其他模型或自定义目录必须另外记录来源、版本及权重，不能认为同名即相同。
- **数据**：每个 Windows 用户使用自己的应用数据目录，界面底部显示实际位置。导入媒体、字幕、报告和凭据均不随源码提供。

## 真实验收顺序

| 阶段 | 操作 | 通过标准 |
| --- | --- | --- |
| 模型 | 保存并测试所选模型 | 完整模型响应、JSON 与证据引用校验通过 |
| 本地视频 | 导入自己的有声 MP4 | 真实时间戳字幕、摘要、可回看证据及字幕导出 |
| 单作品 | 分享文本 → 采集检测 | 真实作者、作品详情、实际下载及 FFprobe 成功 |
| 主页 | 主页分享 → 采集检测 | 真实作品、去重、第二页新增 ID 及实际媒体 |
| 批量 | 分别创建 10/30 条任务 | 成功/失败/无语音计数、停止原因、恢复、报告与证据核对 |

检测 401/403/429 要记录失败阶段，不应无限重试。Cookie 过期、作品下架、账号权限、平台接口或网络环境可能让同一链接结果改变；没有带登录状态的真实通过证据时，不能把“脚本存在”或“匿名解析成功”作为完整采集复现。

## 源码构建

本轮已核对的环境：CPython 3.12.2、Node 22.20.0、Rust 1.99.1 MSVC、FFmpeg/FFprobe 8.0 Windows full build。Python 的 81 项锁定依赖与本机一致。还需安装 Visual Studio C++ 构建工具和 Windows SDK，参考 [Tauri Windows 前置依赖](https://v2.tauri.app/start/prerequisites/)。不同编译器和时间戳不保证安装包逐字节相同，必须记录实际版本与校验值。

在新的检出目录按顺序运行：

```powershell
py -3.12 -m venv backend\.venv
.\backend\.venv\Scripts\python.exe -m pip install -r backend\requirements-windows.lock
.\backend\.venv\Scripts\python.exe -m pip install -e .\backend --no-deps
npm.cmd ci --prefix auth-helper --ignore-scripts --no-audit --no-fund
npm.cmd run build --prefix auth-helper
npm.cmd ci --prefix frontend --no-audit --no-fund
.\backend\.venv\Scripts\python.exe -m pytest backend\tests -q -o addopts=''
npm.cmd test --prefix auth-helper
npm.cmd run build --prefix frontend
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\build-desktop.ps1 -BundleMediaTools
```

FFmpeg 和 FFprobe 必须在构建机 PATH 中可用，打包脚本会将它们复制到安装资源。前端、登录桥接使用各自 package-lock.json；Rust 使用 Cargo.lock 和 `--locked`；Python 使用 requirements-windows.lock。构建脚本只复制生成运行库，不打包用户设置或模型缓存。

构建后在另一个空目录运行自检，再按上表记录真实验收。`docs/testing` 中的历史记录均有各自样本类型和验收范围，不代表已经在所有机器上通过。
