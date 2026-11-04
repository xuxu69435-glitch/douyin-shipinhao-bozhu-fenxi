# Codex 承接指令 — 抖音博主内容分析智能体 V5

本目录是独立生成的源码仓库。先阅读`docs/progress.md`、`docs/research/github-review.md`、`docs/architecture.md`、`README.md`以及Git记录，再行动。

## 不得改变的事实

- GitHub源代码调研完成，但**R0真实平台测试没有通过**。不能凭F2源码或fixture测试宣布抖音作者识别、第二页或可播放性已实测。
- 本地Linux/Python 3.13.5后端测试**50 passed**。没有真正运行faster-whisper权重推理或OPENAI兼容服务；所有模拟结果写为`test_fixture`。
- M0/M1/M2有可测试源码、UI和受限开关，**不是已通过Windows打包和真实采集的成品**。
- M3 LangGraph审查尚未实现。M4 Windows安装包尚未生成；`npm install`被无DNS阻塞，Rust工具链缺失。
- 默认Worker使用`missing_collector`，不可为了演示把模拟数据冒充真实数据。可显式`ANALYST_ENABLE_LIVE=1`尝试真实链路，但实测验收仍须独立记录。

## 继续开发时的执行顺序

1. 首先检查实际目的仓库的`git status`, HEAD、未跟踪文件。合并前不要覆盖用户已有代码。此Git仓库可单独开发和提交。
2. 在Windows 11 Python 3.12安装依赖、运行50项backend测试；执行GitHub review中记录的授权R0探针。用明确样本验证作品/主页作者、真实第二页不同作品ID、下载文件FFprobe，保存去敏的真实日志（不是替身日志）。不获取受限内容，不绕过访问控制。
3. 完整安装frontend依赖并运行`npm run build`、`cargo check`、`npm run tauri:dev`、`npm run tauri:build`，先补充PyInstaller采集/ASR惰性导入、模型文件和FFmpeg的正确打包，核验启动退出、媒体播放、配置、数据持久化。当前环境没有做过这些验证。
4. 在真实采集许可通过后执行小样本单视频和10/30视频任务，检查媒体路径、Whisper版本、字幕对齐、LLM结构化输出、主题归并、证据引用、停止原因、恢复及费用；不能抄写假成功结论。
5. 再实现M3：单个LangGraph证据审查Agent，调用范围仅限数据库已有字幕与上下文，有限重分析，不许扩大采集；设硬性模型请求数、工具调用、步数、token预算和审计日志。保留每次修订/撤回的原因、版本、原始证据。
6. 每阶段完成适当测试并提交真实代码，更新`docs/progress.md`中通过/未通过条目。禁止提交`OPENAI_API_KEY`、Cookie、媒体大文件或签名URL。

## 核心边界

采集`app/collector.py` → 任务`app/job_processor.py` → 媒体`app/media.py` → ASR`app/transcription.py` → LLM/evidence`app/insights.py`/`app/pipeline.py` → 数据`app/models.py` → 报告`app/reporting.py`。`app/evidence.py`承担导出前的真实性和版本检验。桌面Rust只持有Sidecar进程和本机令牌，不将主令牌暴露给前端。不要引入Redis、Celery、微服务、向量数据库或多Agent。
