# Architecture boundaries

```text
Tauri 2 / React UI
    │ Tauri invoke: backend_request(path, method, body)
    ▼
Rust process owner and loopback HTTP proxy
    │ random 127.0.0.1 port + 32-character per-process secret
    ▼
FastAPI app (one process)
    │ API: tasks/history/control, auth on all endpoints
    ├── SQLite + SQLAlchemy (tasks, videos, task_video stages, segments, analyses, reports)
    └── SingleWorker (one async consumer, resumable state) 
            │
            ├── DouyinCollector interface → F2 SDK (M1 live-gated)
            ├── MediaVerifier → FFprobe / FFmpeg (local routines tested)
            ├── ASR → faster-whisper (M1)
            ├── LLM → OpenAI-compatible API (M1)
            ├── CreatorAggregator (M2)
            └── LangGraph evidence reviewer (M3)
```

The production worker intentionally uses `missing_collector` in M0. It marks tasks `blocked` with a clear code. It does not generate fake results. `F2Collector` can only be enabled after permitted real R0 proof and media-download checks.

M0 fields for future evidence: `VideoRecord` uses `(platform, platform_video_id)` uniqueness, segments use `(video_id, transcript_version, segment_id)` uniqueness, analysis/results retain versions, and reports retain versions. Citation validation and speaker attribution are M1/M2 responsibilities; mere schema existence is not implementation.

The renderer cannot use Shell directly. Rust owns child process creation and termination. The HTTP backend listens on `127.0.0.1` only, requiring a token on all endpoints; the renderer invokes a narrow Rust proxy, avoiding Windows WebView2 mixed-content issues and keeping the token out of browser JS. A race between finding an ephemeral port and sidecar binding remains to test on Windows; an authenticated readiness probe prevents false success against a wrong process.

Future state machine: `queued → running → completed/failed/blocked`; `running → pausing → paused` and `running → cancelling → cancelled`; `paused/blocked/failed → queued` on user resume. Worker startup reconciles `running → queued`, `pausing → paused`, `cancelling → cancelled`. Results from partly processed videos must be persisted idempotently before implementing M1 processor.
