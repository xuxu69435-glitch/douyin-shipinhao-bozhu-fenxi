# Development status — 2026-11-04

Scope: Windows local, Douyin only. Status labels are literal; "implemented" != "Windows-verified".

## R0: GitHub research + real collection feasibility

- [x] Read actual GitHub source files, LICENSE, configuration and issue #435 in F2, BiliNote, MediaCrawler, faster-whisper, Douyin API.
- [x] Inspect Tauri's official sidecar docs and Douyin OAuth video-list scope.
- [x] Choose F2 as a **candidate**, implement SDK boundary and pure pagination rules.
- [x] Build `scripts/live_douyin_probe.py` for real page-two, author and media validation when permitted access becomes available.
- [ ] **REAL** Douyin profile author verified on an authorized sample. `NOT RUN`.
- [ ] **REAL** video link author verified on an authorized sample. `NOT RUN`.
- [ ] **REAL** second page has distinct works; successful HTTP video sample and FFprobe. `NOT RUN`.
- Blocker: sandbox has no external network DNS (`github.com` cannot resolve from shell) and no permitted live Douyin URLs/session. GitHub content review worked via connected GitHub service, but does not validate Douyin endpoints.
- Research document: [`research/github-review.md`](research/github-review.md).

## M0: Engineering skeleton

- [x] Create new standalone directory instead of editing unknown Windows repository.
- [x] FastAPI 0.1.0 with token-protected `/api/health`, create/list/get tasks and pause/resume/cancel.
- [x] Parse Douyin full profile, full video and shortened links; reject unrelated hosts.
- [x] SQLite SQLAlchemy task, video, task-video, transcript-segment, analysis-version and report-version schemas.
- [x] Single Python Worker with cooperative pause/cancel, persisted failures, restart-state reconciliation and explicit `blocked` state when R0 is not accepted.
- [x] React 18 + TypeScript + Vite task screen, history list and failure details; M1/M2 screens labelled as placeholders.
- [x] Tauri 2 Rust code, PyInstaller Windows script, random local port, per-launch session secret, Rust-only Sidecar control, token-protected Rust API proxy and exit kill.
- [x] Real local FFmpeg synthetic-media probe/extraction smoke test; not a live Douyin test.
- [x] Python automated backend test suite: **35 passed** in this execution environment. Command: `cd backend && python -m pytest -q` (Python 3.13.5, Linux). See `testing/backend-pytest.txt`.
- [ ] Frontend `npm install`, `npm run build`: `NOT RUN` (no npm network/cache).
- [ ] Rust/Tauri `cargo check`, Windows desktop start/exit, bundled sidecar smoke: `NOT RUN` (no Rust toolchain and this container is Linux).
- [ ] Python **3.12** execution: `NOT RUN` (this execution environment is Python 3.13.5).
- [ ] Sidecar shutdown and Windows installer persistence: `NOT RUN`.
- [ ] Real F2/ASR/LLM request pipeline: deliberately not enabled in M0.

## M1 — pending after R0/M0 acceptance

Implement the real collection → permitted media download → FFprobe → FFmpeg → faster-whisper → Pydantic-validated LLM analysis pipeline. Anchor evidence using `(video_id, transcript_version, segment_id)` and verify claimed timestamps against stored spans. Add video details, media playback, transcript export and failure-stage persistence.

## M2 — pending

Paginated creator history (10/30), stable IDs, task-video records, per-item failure counts, canonical themes, programmatic ratios, nuanced subject/speaker attribution, business inference only with explicit evidence and report export.

## M3 — pending

LangGraph bounded evidence-review Agent, step/tool/budget limits, audit decisions and resumable task checkpoints. No expanded collection by Agent.

## M4 — pending

Windows 11 PyInstaller bundle + `npm run tauri:build`, signed/installer tests if available, model config, media playback, restart persistence, clean Sidecar exit, packaging licenses, and real sample performance/accuracy evaluation.

## Next entry (exact commands)

1. On Windows, inspect your **real existing repo** with `git status --short`, branch and file tree before merging any scaffold files; this sandbox cannot inspect that machine.
2. Create Python 3.12 environment and run the 35 backend tests, followed by `scripts/live_douyin_probe.py` on authorized public samples. Preserve real outputs as `docs/testing/live-r0.json` without credentials or signed media URLs.
3. Install frontend dependencies, build Windows Sidecar using `scripts/build-sidecar.ps1`, then run `npm run tauri:dev` and `npm run tauri:build`. Verify process termination from Task Manager after closing the desktop app.
4. Only when R0 live collection and M0 packaging both pass, wire the F2 adapter into the single Worker and proceed to M1.

**Repository caveat:** Connected GitHub account returned no writable user project repository, and no Windows workspace was mounted. These commits, if present, belong only to the generated standalone scaffold, not a user's existing repository or remote.
