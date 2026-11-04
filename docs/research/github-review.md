# R0 — GitHub source review and reuse decisions

Date: 2026-11-04. Research method: GitHub connector read of concrete source files, directory trees, issue #435, license files, repository HEADs; Douyin open platform and Tauri official docs. This is **source inspection**, not a claim that the remote projects were installed or executed locally.

## 1. Repositories and adoption

| Repository | Ref reviewed | License verified in source | Key source files and actual observed functionality | Dependencies / costs | Decision | Tests in this R0 |
| --- | --- | --- | --- | --- | --- | --- |
| [Johnserf-Seed/f2](https://github.com/Johnserf-Seed/f2) | `f6be8c0ffba9a127075bbeafe4838716650b6325`, default branch `v0.0.1.8-pw3`; `f2/__init__.py` still says `0.0.1.7` | [Apache-2.0](https://github.com/Johnserf-Seed/f2/blob/v0.0.1.8-pw3/LICENSE) | [`f2/apps/douyin/utils.py`](https://github.com/Johnserf-Seed/f2/blob/f6be8c0ffba9a127075bbeafe4838716650b6325/f2/apps/douyin/utils.py): `SecUserIdFetcher`, `AwemeIdFetcher`; [`crawler.py`](https://github.com/Johnserf-Seed/f2/blob/f6be8c0ffba9a127075bbeafe4838716650b6325/f2/apps/douyin/crawler.py): `fetch_user_profile`, `fetch_user_post`, `fetch_post_detail`; [`handler.py`](https://github.com/Johnserf-Seed/f2/blob/f6be8c0ffba9a127075bbeafe4838716650b6325/f2/apps/douyin/handler.py): `fetch_user_post_videos` loops `max_cursor`, `has_more`, stops when cursor not advancing; [`filter.py`](https://github.com/Johnserf-Seed/f2/blob/f6be8c0ffba9a127075bbeafe4838716650b6325/f2/apps/douyin/filter.py) exposes `aweme_id`, `sec_user_id`, `video_play_addr` | `httpx`, `httpx-socks`, `curl_cffi`, `pydantic`, crypto and signature dependencies, optional authorized user cookie; platform reliability varies | **Primary candidate**; implemented an optional, isolated `F2Collector` and pure pagination normalization; not yet switched into production worker | **Code inspection passed; synthetic pagination tests passed; live platform NOT RUN** |
| [JefferyHcool/BiliNote](https://github.com/JefferyHcool/BiliNote) | `90940fde4d224d0f69ad99674f4af0a1ea52d3c4`; Tauri config `2.4.5` | [MIT](https://github.com/JefferyHcool/BiliNote/blob/master/LICENSE) | [`BillNote_frontend/src-tauri/src/lib.rs`](https://github.com/JefferyHcool/BiliNote/blob/90940fde4d224d0f69ad99674f4af0a1ea52d3c4/BillNote_frontend/src-tauri/src/lib.rs) uses `ShellExt`/`CommandChild`, readiness probe, startup and Exit/ExitRequested kill; [`tauri.conf.json`](https://github.com/JefferyHcool/BiliNote/blob/90940fde4d224d0f69ad99674f4af0a1ea52d3c4/BillNote_frontend/src-tauri/tauri.conf.json) has `externalBin`; [`backend/build.bat`](https://github.com/JefferyHcool/BiliNote/blob/90940fde4d224d0f69ad99674f4af0a1ea52d3c4/backend/build.bat) uses PyInstaller and Rust target triple; [`backend/main.py`](https://github.com/JefferyHcool/BiliNote/blob/90940fde4d224d0f69ad99674f4af0a1ea52d3c4/backend/main.py) serves FastAPI; [`CLAUDE.md`](https://github.com/JefferyHcool/BiliNote/blob/master/CLAUDE.md) documents pipeline | Very large dependencies (Celery, Redis, ChromaDB, etc.). Existing build script copies example `.env` into packaged backend, **not adopted** | **Adopt patterns, not full code**. This scaffold keeps one worker, uses a private Rust HTTP proxy, random loopback port and short-lived token, never bundles model API keys | **Source inspection passed; Rust build/Windows lifecycle NOT RUN** |
| [NanmiCoder/MediaCrawler](https://github.com/NanmiCoder/MediaCrawler) | `d172fc8369d8479c96793a5b1e4d89fac43914c2` | [Non-Commercial Learning License 1.1](https://github.com/NanmiCoder/MediaCrawler/blob/main/LICENSE) — expressly restricts commercial use | `media_platform/douyin/{client,core,login}.py` module structure; README documents account/profile collection using browser context | Playwright, browser login, storage and optional proxies; licensing constraint | **Research only. No code copied or bundled.** Explicit permission required for incompatible/commercial reuse | **Read only** |
| [SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper) | `2a3a857737d17d974f30d818ebec69ce11929e5c` | [MIT](https://github.com/SYSTRAN/faster-whisper/blob/master/LICENSE) | [`faster_whisper/transcribe.py`](https://github.com/SYSTRAN/faster-whisper/tree/master/faster_whisper), README demonstrate `WhisperModel` segments and timestamp output | `ctranslate2`, `av`, model weights; CPU int8 possible; GPU requires compatible CUDA/cuBLAS/cuDNN | **Chosen for M1** with lazy initialization, model version storage and explicit no-speech handling | **Not installed or transcribed yet** |
| [Evil0ctal/Douyin_TikTok_Download_API](https://github.com/Evil0ctal/Douyin_TikTok_Download_API) | `5aa03528d2e974a0de23faf86597b5af3420df55`; [`pyproject.toml`](https://github.com/Evil0ctal/Douyin_TikTok_Download_API/blob/main/pyproject.toml) version `5.1.10` | [Apache-2.0](https://github.com/Evil0ctal/Douyin_TikTok_Download_API/blob/main/LICENSE) | Full self-hosted API with scheduler, identity management, HTTP download abstractions | Requires PostgreSQL, Redis, `asyncpg`, scheduler and identity pool; conflicts with V5's minimal SQLite + one worker architecture | **Fallback research only; not imported** | **Read only** |

## 2. Question-by-question verification

### A. Can a profile/video link resolve its creator?

**Code-level answer: yes, candidate implementation exists. Live verdict: UNVERIFIED.** F2 `SecUserIdFetcher.get_sec_user_id` can resolve profile URLs and `AwemeIdFetcher.get_aweme_id` can resolve video URLs; `DouyinCrawler.fetch_post_detail` returns `aweme_detail.author.sec_uid` when accessible. The adapter checks that an actual author ID exists instead of asserting the author from the URL string. This sandbox has no Douyin network connectivity and no supplied authorized live URLs, so no real author-ID assertion has been made.

### B. Can second-page works and playable media be retrieved?

**Code-level answer: F2 explicitly supports cursor pagination; live verdict: UNVERIFIED.** `handler.py` iterates `fetch_user_post` with `max_cursor` and `has_more`, and documents the guest-cookie case where page-two pagination data disappears. Related [issue #435](https://github.com/Johnserf-Seed/f2/issues/435) reports premature stopping around 20 works. Our `collect_author_pages` tests two pages with 30 unique mocked IDs, deduplication, missing pagination and unchanged cursor. An R0 live acceptance must show a second-page ID **not on page one**, the response's cursor progression, download a legitimate media sample and pass `ffprobe` on the resulting bytes. `scripts/live_douyin_probe.py` is provided for a permitted real-network Windows session; its results have **not** been executed or fabricated here.

### C. What is useful from BiliNote's desktop integration?

**Verified from concrete source:** `externalBin` packaging and target triple; Rust-managed `CommandChild`; startup readiness probe; explicit shutdown kill on both `ExitRequested` and `Exit`; FastAPI/PyInstaller integration. The original has a fixed port and a large feature/dependency set; this scaffold instead uses a random bound-to-loopback port, Rust-side session token and a narrowly scoped Tauri IPC proxy. Do not copy its entire backend or include `.env` in the PyInstaller executable.

## 3. Official API, platform policy and security

- [Douyin /video/list/ official documentation](https://open.douyin.com/platform/resource/docs/openapi/video-management/douyin/search-video/account-video-list): requires the account holder's OAuth authorization and the `video.list` scope. It does **not** authorize arbitrary unconsenting third-party creator retrieval. The list API supports `cursor` and `has_more` under that scope.
- [Douyin permissions](https://open.douyin.com/platform/resource/docs/accession-guide/type-and-permission): access to account/video scopes must be approved, and the provider's current terms govern use. If access is blocked, stop; do not defeat controls or mass scrape.
- [Tauri sidecar documentation](https://v2.tauri.app/develop/sidecar/): external binary must have the `-$TARGET_TRIPLE` suffix on disk; Rust API calls `sidecar("filename")`. Build scripts must match the target architecture.
- Credential policy: no automatic browser-cookie collection; any manually provided account access credentials remain in an ignored local file. Signed media URLs are not dumped to probe JSON. All API keys use the single `OPENAI_*` trio and stay out of Git and the installer.
- Security posture: no arbitrary URL downloading, redirect-based host escaping, or arbitrary Rust command execution from the renderer. Local media helper validates Douyin CDN hostnames at every HTTP redirect and caps download size.

## 4. How to execute the missing live acceptance

On Windows with authorized public sample profile and video URLs, install F2 and optional test dependencies, then:

```powershell
# Inside project root, after setting up backend/.venv:
.\backend\.venv\Scripts\python.exe .\scripts\live_douyin_probe.py `
  --profile "https://www.douyin.com/user/REAL_PUBLIC_SEC_USER_ID" `
  --video "https://www.douyin.com/video/REAL_PUBLIC_AWEME_ID" `
  --media-dir ".media\r0" --output "docs\testing\live-r0.json"
```

If authorized access needs a cookie, add `--cookie-file ".secrets\douyin-cookie.txt"`. This is not automatic cookie extraction. Do not share the cookie, signed URLs or video media without authorization. Verify that `page_2_confirmed` is `true` AND `media_playable_confirmed` is `true` in the real output, and inspect actual media ID/author fields for validity. A status of `false` is an R0 failure, not a reason to manufacture success.

**Missing right now:** the user's Windows repository and live networking, authorized sample URLs/access, Windows Tauri compile + child-process lifecycle tests. R0 live acceptance remains **NOT PASSED**.
