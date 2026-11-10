# 0.1.3 Windows 安装复验

日期：2026-11-10。源码对应 `11ffb42`；本轮不调用文字模型，也不读取其凭据。

## 安装与运行

- NSIS 安装包 302163699 字节，SHA256 见 [安装清单](windows-installer-0.1.3.json)；覆盖安装退出码 0。
- 原有 3 条任务、模型配置、ChatGPT 授权与 Cookie 状态经更新前后校验保留，安装后端与构建文件一致。
- 打包后端及安装后端的合成 Cookie 导入、加密落盘、重启状态和清除通过；使用 JSON 内容、同名 Cookie 及登录标记验证此次修复，未用真实凭据作为测试样本。见 [打包后端](packaged-backend-0.1.3-smoke.json) 和 [安装后端](installed-backend-0.1.3-smoke.json)。
- 发行版与安装版各两次桌面隔离检查通过，涵盖认证、合成媒体 Range、FFmpeg/FFprobe、语音运行库加载、历史持久化与进程树退出。见 [发行版桌面](release-desktop-0.1.3-smoke.json) 和 [安装版桌面](installed-desktop-0.1.3-smoke.json)。
- 安装版仅保留 Windows System32 的 PATH，在新临时目录完成运行依赖、合成媒体、PCM 解码、SQLite、DPAPI 和无账户登录桥接六项自检；见 [安装版空配置检查](installed-clean-data-0.1.3.json)。不加载权重或已有用户设置。

## 独立检出

在同机另一个检出目录按 Windows 锁文件创建独立环境，111 项后端测试、前端构建及六项空配置自检通过。SDK 测试在前一检出版本为 56 项通过、1 项 Windows 不适用项跳过；此次未改 SDK。该记录不是独立硬件验证，也不保证构建产物逐字节一致。

独立检出环境的 PyInstaller 后端打包也成功，产物的六项自检及真实后端子进程复验通过，见 [独立打包自检](fresh-checkout-packaged-0.1.3.json) 和 [独立打包后端](fresh-checkout-packaged-backend-0.1.3-smoke.json)。未在此目录重复构建完整 NSIS 安装程序。

## 尚待真实验收

已在安装界面成功保存手动导入的 Cookie，并检测到常见登录标记。用户报告该值来自 imapi.douyin.com 消息接口；使用此值复测原主页与作品，解析成功，作品读取均仍 HTTP 403，见 [带登录状态的真实记录](share-links-cookie-0.1.3.json)。尚未取得真实作者、第二页或媒体；继续核对 www.douyin.com 来源及接口适配。匿名失败记录保留，不以离线检查覆盖。WebView 实际播放、真实视频分析质量和 10/30 视频任务仍须人工验收。
