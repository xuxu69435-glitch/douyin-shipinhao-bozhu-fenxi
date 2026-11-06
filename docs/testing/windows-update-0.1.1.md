# Windows 0.1.1 更新验证（2026-11-06）

## 分享链接

实际短链跳转采用公开 HTTP 请求，未调用语音识别或模型服务。

| 输入 | 实际识别结果 |
| --- | --- |
| `https://v.douyin.com/1MzzlZTuZcc/` | 主页：`https://www.douyin.com/user/MS4wLjABAAAAoDPbeBJwY9IpoMFWKaDAPR7WXPset_2zjILeb65yPeg` |
| `https://v.douyin.com/NE2hkgBNwHM/` | 作品：`https://www.douyin.com/video/7699679130752748809` |

原实现只识别 `/user/`、`/video/`，在两条短链返回 `/share/user/`、`/share/video/` 时拒绝地址。修复后直接规范化为主页或作品地址，不保存分享跟踪参数。

匿名 F2 0.0.1.7 读取作品详情仍返回 `APIResponseError` / HTTP 403。任务将保留已解析地址，进入 `DOUYIN_ACCESS_DENIED` 阻塞，可在处理访问问题后恢复。短链解析成功不表示作者详情、第二页、下载、ASR 或 LLM 已通过；完整真实采集仍待验证。实测记录见 [分享链接验证 JSON](share-links-0.1.1.json)。

## 界面

- 固定窗口内的导航及内容区域，长内容在主区域滚动。
- 缩小任务页顶部介绍，新建任务和历史记录并排显示。
- 历史任务每页 8 条，长列表与展开详情在限定区域滚动。
- 设置页双列排列基础字段，抖音采集选项可折叠。
- 在 1280 × 720 浏览器预览中，使用独立测试数据库的 12 条暂停任务验证分页：第一页 8 条，第二页 4 条；采集选项展开正常。测试未使用正式分析数据或真实 API 密钥。

## 检查结果

- Windows / Python 3.12.2：后端 76 项测试通过。
- TypeScript / Vite：完整构建通过。
- Rust：`cargo check --locked` 通过。
- PyInstaller 后端：健康检查、认证、设置持久化、中文无声视频导入及退出通过，见 [后端自检](packaged-backend-0.1.1-smoke.json)。
- 新发行版及安装后桌面各运行两次离线自检：认证代理、依赖加载、合成媒体 Range、重启历史和退出进程树检查通过，见 [发行版自检](desktop-0.1.1-smoke.json) 与 [安装后自检](installed-desktop-0.1.1-smoke.json)。

## 安装更新

- 程序位置：`E:\1bishe\Douyin Analyst\douyin-analyst-desktop.exe`，安装后版本为 `0.1.1`。
- 安装包：`frontend/src-tauri/target/release/bundle/nsis/Douyin Analyst_0.1.1_x64-setup.exe`，257.18 MiB，安装返回 0。
- SHA-256：`cc1ef78f5556dd1904c4e996f5c80ee31a1d2c779de17526725e0170af29f2b1`。
- 安装后端与打包源文件哈希相同；已有任务 ID 和模型配置文件哈希与更新前一致，见 [安装校验](windows-installer-0.1.1.json)。

更新时旧版实例未在正常关闭请求后结束；确认没有运行任务后结束旧实例，后端随 Windows Job 清理。上述新版本退出结果来自隔离自检，普通窗口关闭、播放器及原生文件对话框仍需人工确认。

更新后可在历史任务中展开原失败任务并点击“恢复”，使用新解析器继续处理。出现 `DOUYIN_ACCESS_DENIED` 时，应先处理平台访问问题，再恢复任务；重复恢复不会使被拒绝的访问自动成功。
