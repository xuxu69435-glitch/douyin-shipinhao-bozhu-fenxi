# 项目开发约定 — 抖音博主内容分析

先阅读 docs/progress.md、docs/research/github-review.md、docs/research/harness-decision.md、README.md 和实际 Git 状态。不要覆盖未提交的用户工作。

## 当前状态

- 仅开发抖音，不开发微信视频号。
- Windows / Python 3.12.2 后端 118 项测试通过；前端完整构建、Rust 编译、PyInstaller Sidecar 及 NSIS 安装包已运行验证。具体生命周期与安装结果以 docs/testing 下的真实记录为准。
- 分享短链的 `/share/user/`、`/share/video/` 跳转已验证；匿名及手动登录状态的 F2 作品读取仍返回 HTTP 403，真实 UIFID 补齐后确认缺少网页安全签名，不能声称真实采集通过。正常浏览器中作品实际播放已观察到，与软件内的媒体获取验收分别记录。
- 真实抖音作者、第二页、下载可播放性及真实视频分析质量仍待样本验证。合成语音的真实 Whisper 推理和套餐模型调用已通过，合成媒体与测试替身结果应单独记录。
- LangGraph Agent 暂缓实现，当前采用固定流程与轻量 harness，见 harness-decision.md。不要擅自加入自主工具循环或多 Agent。
- 模型入口为“模型与采集设置”：API Key 使用 OPENAI_BASE_URL、OPENAI_API_KEY、OPENAI_MODEL；ChatGPT 套餐使用官方独立授权与 CHATGPT_MODEL，禁止隐式回退至 API Key。Windows 凭据用 DPAPI，API 不回显令牌或密钥。真实采集默认关闭，独立采集检测不得加载模型凭据。
- 支持手动粘贴 Cookie 并用 DPAPI 加密保存；获取与导入说明见 docs/douyin-cookie.md。独立复现说明及 --self-check 入口见 docs/reproducibility.md。默认 small 权重固定 revision；凭据不得进入日志、请求参数或测试记录。
- 保持仓库现有 Git 提交身份。远端推送由维护者手动执行。

## 实现与验证边界

采集 app/collector.py → 任务 app/job_processor.py / app/local_processor.py → 媒体 app/media.py → ASR app/transcription.py → LLM app/insights.py / app/pipeline.py → SQLite app/models.py → 报告 app/reporting.py。app/evidence.py 负责导出前的证据及版本校验。

- 保持 Tauri 2、React、FastAPI、SQLite、单 Worker，不引入 Redis、Celery、微服务、向量数据库。
- 模型只能选择已有字幕段 ID；时间戳、视频 ID 和版本由程序生成。JSON 及存在性校验不等于语义事实审查。
- 不把旁白、嘉宾、引用对象或未核实的表达断言为博主个人喜好；没有公开证据不推断主营业务。
- 不自动读取浏览器 Cookie，不绕过平台访问控制；密钥、Cookie、日志、媒体和安装包不得进入源码提交。
- 真实与模拟结果严格区分，测试替身标为 test_fixture。
- 每次分析的请求、输出、分段及重试上限必须保持明确，失败与中断保留记录，禁止无限重试。
- Rust 持有主令牌，通过受限 IPC 代理 API；媒体使用签名链接，文件选择和导出由原生对话框确认路径。Windows Job 约束 Sidecar 全部后代，退出时先请求正常关闭，再兜底清理。

## 工作顺序

1. 检查 git status、分支和已有改动，仅修改当前任务相关内容。
2. 对有实际行为变化的功能补充必要验证；运行后端测试与前端构建。
3. 桌面改动时运行 cargo check、打包 Sidecar、构建安装包和 scripts/smoke_desktop.py。自检使用独立目录，不能调用付费模型或污染用户分析数据。
4. 受限工具环境中的 WebView2/Windows Job 访问拒绝，应在正常桌面权限下验证，不应通过删除退出保护来规避。PowerShell 脚本可使用进程级 ExecutionPolicy 参数，不修改系统策略。
5. 更新 docs/progress.md，分别记录通过、未通过及尚待真实验证的内容。
