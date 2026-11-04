# Codex execution requirements for this scaffold

This repository was generated as a separate artifact. Before integrating it, inspect the actual destination repository, `git status`, branch history, existing files and tests. Never overwrite an unrelated existing project. Do not treat docs/progress.md checked boxes as proof of a live Douyin integration.

1. Read `docs/research/github-review.md` and `docs/progress.md` first.
2. Resolve R0 live acceptance using only public/authorized content and official platform constraints. Validate actual second-page distinct IDs and downloaded media via FFprobe; never log credentials or expiring CDN signatures. Use `scripts/live_douyin_probe.py` as a starting point. If access fails, record the precise reason instead of inventing a passing result.
3. On Windows 11 with Python 3.12, run backend tests. Install frontend dependencies and Rust, build Sidecar, then run the Tauri application and exit/lifecycle smoke test. Do not claim success without Windows results. Use `OPENAI_BASE_URL`, `OPENAI_API_KEY`, `OPENAI_MODEL` only for LLM settings; never commit their values.
4. Wire the F2 provider and implement real M1 only after accepted R0 and M0: media, ASR, real LLM, validated evidence refs, video UI. Continue M2 then M3 then M4 per user V5; no multiagent/microservices/Redis/Celery/vector DB.
5. Maintain `docs/progress.md` and stage-specific real-vs-mock test records. Commit each successful milestone with its test results and unfinished items. Do not silently bypass authentication, permissions or license restrictions.

Minimal commands:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
cd ..
.\scripts\build-sidecar.ps1
cd frontend
npm run build
npm run tauri:dev
```
