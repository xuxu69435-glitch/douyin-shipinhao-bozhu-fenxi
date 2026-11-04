# M1/M2 validation boundaries — 2026-11-04

## PASS in this Linux executor

- Python 3.13.5, pytest: `50 passed` (see `backend-pytest.txt`).
- Uses actual FFmpeg/FFprobe on locally generated 2-second synthetic MP4s (both with audio and video without an audio track).
- Single-video ASR+LLM domain interfaces tested with explicitly named `FakeASR`, `FakeLLM`, `ASRFixture`, `LLMFixture`. Models are **not** downloaded or called.
- Strictly rejects nonexistent/fabricated transcript segment IDs and extra model metadata fields; propagates correct video/version/time from SQLite.
- Verifies stage-level cache reuse and successful re-analysis after a deliberate invalid LLM response while retaining already-transcribed segments.
- Exercises task worker integration with two synthetic video candidates from `ProviderFixture`; one case succeeds, another fails one video while preserving sample denominators and error records.
- Verifies created report fields and ratio calculation from analyzed video counts; prevents unsupported personal preference attribution.
- Re-checks transcript evidence during report exports. Tampered/deleted evidence triggers HTTP 409.
- Tests short-lived HMAC media tickets, invalid/expired signatures and HTTP Range 206/416. The Range fixture is random bytes, **not** a playable media test.
- TypeScript syntax transpilation on four TS/TSX source files: 0 parse errors (NOT a full build).

## NOT RUN / NOT PASSED

- Authorized real Douyin profile/video author, second page, real media bytes: **NOT RUN**.
- A real faster-whisper inference on a speech recording: **NOT RUN**.
- A real OpenAI-compatible model response and billing: **NOT RUN**.
- React dependency installation and build: **BLOCKED by offline npm cache/DNS**.
- Tauri Rust compile, PyInstaller optional imports, Windows NSIS, process cleanup, actual media HTML5 playback: **NOT RUN**.
- LangGraph evidence review Agent: **NOT IMPLEMENTED**.

No PASS in the first section is evidence for claims in the second.
