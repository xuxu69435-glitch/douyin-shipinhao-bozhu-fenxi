"""Run the *actual* local Python sidecar as a child process; test loopback HTTP persistence."""

import json
import argparse
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
EXECUTABLE = None
VIDEO = "https://www.douyin.com/video/7444000000000012345"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_process(data_dir: str, port: int, token: str):
    env = {**os.environ, "ANALYST_DATA_DIR": data_dir, "ANALYST_BACKEND_PORT": str(port),
           "ANALYST_BACKEND_TOKEN": token, "ANALYST_ENABLE_LIVE": "0"}
    command = [str(EXECUTABLE)] if EXECUTABLE else [sys.executable, str(ROOT / "backend" / "sidecar.py")]
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    return subprocess.Popen(command, env=env, cwd=ROOT, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, **options)


def wait_ready(port: int, token: str):
    url = f"http://127.0.0.1:{port}/api/health"
    for _ in range(100):
        try:
            answer = httpx.get(url, headers={"X-Analyst-Token": token}, timeout=1)
            if answer.status_code == 200 and answer.json().get("status") == "ok":
                return
        except httpx.HTTPError:
            pass
        time.sleep(.1)
    raise RuntimeError("backend process did not become ready")


def stop_process(process, port, token):
    try:
        httpx.post(f"http://127.0.0.1:{port}/api/shutdown", headers={"X-Analyst-Token": token}, timeout=3)
        process.wait(timeout=5)
        return
    except (httpx.HTTPError, subprocess.TimeoutExpired):
        pass
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def run():
    token = secrets.token_hex(24)
    port = free_port()
    with tempfile.TemporaryDirectory() as data_dir:
        process = start_process(data_dir, port, token)
        try:
            wait_ready(port, token)
            base = f"http://127.0.0.1:{port}/api"
            assert httpx.get(f"{base}/tasks", timeout=3).status_code == 401
            headers = {"X-Analyst-Token": token}
            fixture_cookie = 'prefs={"volume":0.5}; theme=dark; theme=light; unnamed-fixture; sessionid=fixture-cookie-secret'
            session = httpx.post(f"{base}/douyin/session", headers=headers,
                                 json={"cookie": fixture_cookie}, timeout=5)
            assert session.status_code == 200 and session.json()["cookie_count"] == 5, session.status_code
            assert session.json()["login_marker_present"]
            assert "fixture-cookie-secret" not in session.text
            assert "fixture-cookie-secret" not in (Path(data_dir) / "douyin-session.json").read_text()
            configuration = {"OPENAI_BASE_URL": "https://example.invalid/v1", "OPENAI_MODEL": "fixture-model",
                             "OPENAI_API_KEY": "fixture-desktop-settings-key", "enable_live": False}
            settings = httpx.post(f"{base}/settings", headers=headers, json=configuration, timeout=5)
            assert settings.status_code == 200 and settings.json()["api_key_configured"], settings.text
            assert "fixture-desktop-settings-key" not in settings.text
            if os.name == "nt":
                assert "fixture-desktop-settings-key" not in (Path(data_dir) / "model-settings.json").read_text()
            synthetic = Path(data_dir) / "中文无声视频.mp4"
            subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                            "-i", "color=c=black:s=128x96:r=4:d=1", "-c:v", "mpeg4", "-metadata",
                            "title=中文标题", str(synthetic)], check=True, capture_output=True,
                           **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}))
            imported = httpx.post(f"{base}/local-videos", headers=headers,
                                  json={"path": str(synthetic)}, timeout=10)
            assert imported.status_code == 201, imported.text
            for _ in range(100):
                local = httpx.get(f"{base}/tasks/{imported.json()['id']}", headers=headers, timeout=3).json()
                if local["status"] in {"completed", "failed", "blocked"}:
                    break
                time.sleep(.05)
            assert local["status"] == "completed" and local["no_speech_count"] == 1, local
            response = httpx.post(f"{base}/tasks", headers=headers, json={"input_text": VIDEO}, timeout=3)
            assert response.status_code == 201, response.text
            task_id = response.json()["id"]
            for _ in range(80):
                task = httpx.get(f"{base}/tasks/{task_id}", headers=headers, timeout=3).json()
                if task["status"] == "blocked":
                    break
                time.sleep(.05)
            assert task["status"] == "blocked" and task["error_code"] == "R0_LIVE_COLLECTION_NOT_VERIFIED", task
            plan = {**configuration, "OPENAI_API_KEY": None, "model_provider": "chatgpt", "CHATGPT_MODEL": "fixture-model"}
            assert httpx.post(f"{base}/settings", headers=headers, json=plan, timeout=5).status_code == 200
            state = httpx.get(f"{base}/chatgpt/status", headers=headers, timeout=15).json()
            assert state == {"status": "disconnected", "sharing": False}, state
            # No account means no remote request. This verifies the bundled Node runtime.
            models = httpx.get(f"{base}/chatgpt/models", headers=headers, timeout=15)
            assert models.status_code == 502 and "sign_in_required" in models.text, models.text
            check = httpx.post(f"{base}/diagnostics/douyin", headers=headers,
                               json={"input_text": VIDEO}, timeout=50)
            assert check.status_code == 200 and check.json()["steps"][0]["status"] == "passed", check.text
            assert not check.json()["model_called"] and not check.json()["complete"]
        finally:
            stop_process(process, port, token)
        assert process.poll() is not None
        restarted = start_process(data_dir, port, token)
        try:
            wait_ready(port, token)
            saved = httpx.get(f"{base}/tasks/{task_id}", headers=headers, timeout=3)
            assert saved.status_code == 200 and saved.json()["id"] == task_id
            settings = httpx.get(f"{base}/settings", headers=headers, timeout=3)
            assert settings.json()["api_key_configured"] and settings.json()["OPENAI_MODEL"] == "fixture-model"
            session = httpx.get(f"{base}/douyin/session", headers=headers, timeout=3)
            assert session.json()["configured"] and session.json()["cookie_count"] == 5
            assert "fixture-cookie-secret" not in session.text
            cleared = httpx.post(f"{base}/douyin/session/clear", headers=headers, timeout=3)
            assert cleared.status_code == 200 and not cleared.json()["configured"]
        finally:
            stop_process(restarted, port, token)
        return {
            "type": "PACKAGED_SIDECAR_SMOKE" if EXECUTABLE else "REAL_LOCAL_PYTHON_PROCESS_SMOKE",
            "python": sys.version.split()[0],
            "platform": sys.platform,
            "loopback_health": "passed",
            "invalid_token_rejected": True,
            "persisted_task_after_restart": True,
            "worker_block_status_expected": True,
            "python_child_terminated": process.poll() is not None and restarted.poll() is not None,
            "private_settings_persisted": True,
            "synthetic_chinese_silent_video_imported": True,
            "real_asr_llm_tested": False,
            "tauri_process_lifecycle_tested": False,
            "douyin_live_tested": False,
            "chatgpt_bridge_disconnected_state": "passed",
            "chatgpt_no_account_blocks_without_api_fallback": True,
            "isolated_collection_probe_without_llm": "passed",
            "synthetic_cookie_import_encryption_restart_clear": "passed",
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--executable", type=Path)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    EXECUTABLE = arguments.executable.resolve(strict=True) if arguments.executable else None
    report = json.dumps(run(), ensure_ascii=False, indent=2)
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(report + "\n", encoding="utf8", newline="\n")
    print(report)
