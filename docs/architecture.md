# 架构与可信来源边界（2026-11-04）

```text
React 18 / TypeScript / Tauri 2 桌面窗口
 ├─ 任务中心（后端状态）
 ├─ 视频详情、播放器、SRT/VTT、字幕原文、精确证据跳转
 └─ 博主报告：领域/主题比例、证据来源、Markdown/JSON导出
       │ Tauri IPC (backend_request, backend_media_url)
       ▼
Rust Sidecar 管理器
 ├─ 为每次启动生成临时后端端口和随机口令
 ├─ 严格限制可代理的API路径与HTTP方法
 ├─ HMAC-SHA256签发单视频10分钟有效期播放URL（不暴露主口令）
 └─ 退出时终止持有的Python Sidecar
       │ 本机 127.0.0.1 + X-Analyst-Token (JSON)
       │ /media/{uuid}?expires=...&signature=... (HTTP Range)
       ▼
FastAPI（Python 3.12 目标） + SQLite SQLAlchemy
 ├─ CRUD / 控制：TaskRecord (queued / running / paused / blocked / failed / completed)
 ├─ 单Python Worker：串行消费任务，可暂停/取消/恢复，分阶段持久化
 │    ├─ 默认 missing_collector（R0未验收不产生假成功）
 │    └─ 显式本机 opt-in → F2Collector → 已授权视频/作者列表
 │        → 允许的CDN媒体 → FFprobe → FFmpeg → faster-whisper
 │        → OpenAI-compatible JSON → Pydantic → anchor_insight
 │        → CreatorAggregator + verified export
 ├─ VideoRecord（平台视频ID唯一）/ TaskVideoRecord（阶段与失败）
 ├─ TranscriptSegment(video_id, version, segment_id, times, model)
 ├─ VideoAnalysis(video_id, analysis_version, transcript_version, result)
 └─ CreatorReport(task_id, report_version, evidence_version, source refs)
```

## 关键不变式

1. **来源区别**：真实视频采集/Whisper/LLM输出与测试替身不得混合。`AnchoredInsight.provenance`和报告`provenance`包含`real_model`或`test_fixture`；后者只用于测试。
2. **可信证据**：LLM只能返回存在的字幕段ID。`anchor_insight`检验其对应同一视频、同一字幕版本，并从SQLAlchemy已存证据生成真实时间戳；导出前再核查字幕、版本、视频URL和起止时间。
3. **主体归属**：说话人枚举为creator/narrator/guest/quoted/unknown，模型自己认定为creator也不自动使`creator_identity_verified=true`。未验证身份的偏好只显示为“不归属于博主的表达”，不推断主营业务。
4. **来源保护**：分享短链只跟随允许的抖音HTTPS主机；媒体只下载已核验的抖音CDN域名和重定向，限制大小；不把密钥、Cookie、视频CDN签名URL写进数据库/日志。
5. **恢复/去重**：任务ID、作品ID与报告版本稳定。已完成视频若存在有效分析直接跳过；已成功ASR可在LLM失败后独立复用；重启时恢复队列而不丢任务状态。
6. **非证明事项**：源码支持分页≠在当前平台上取得了真实第二页；FFmpeg合成媒体成功≠真实抖音流可播放；测试替身 ASR/LLM≠真实模型推理。完整Windows打包、Python3.12、前端依赖、Rust编译均须在目标机器额外验收。

## 后续实现入口

M3单LangGraph证据审查Agent未实现。建议先把当前M1/M2链路在有权访问的真实公开视频上验证，再增加：有上限的`query_existing_segments`, `read_neighboring_context`, `reanalyze_saved_evidence`, `revise_or_retract`，每次操作写入SQLite审计日志，设置最大步骤/工具/模型请求/重分析/总token预算，不扩大采集。随后M4集成打包测试。
