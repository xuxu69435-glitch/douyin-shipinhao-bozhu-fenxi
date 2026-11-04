"""Run the *actual* local Python sidecar as a child process; test loopback HTTP persistence."""

import json
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
VIDEO = "https://www.douyin.com/video/7444000000000012345"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_process(data_dir: str, port: int, token: str):
    env = {**os.environ, "ANALYST_DATA_DIR": data_dir, "ANALYST_BACKEND_PORT": str(port), "ANALYST_BACKEND_TOKEN": token}
    return subprocess.Popen([sys.executable, str(ROOT / "backend" / "sidecar.py")], env=env, cwd=ROOT,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


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


def stop_process(process):
    process.terminate()
    try:
        process.wait(timeout=10)
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
            response = httpx.post(f"{base}/tasks", headers=headers, json={"input_text": VIDEO}, timeout=3)
            assert response.status_code == 201, response.text
            task_id = response.json()["id"]
            for _ in range(80):
                task = httpx.get(f"{base}/tasks/{task_id}", headers=headers, timeout=3).json()
                if task["status"] == "blocked":
                    break
                time.sleep(.05)
            assert task["status"] == "blocked" and task["error_code"] == "R0_LIVE_COLLECTION_NOT_VERIFIED", task
        finally:
            stop_process(process)
        assert process.poll() is not None
        restarted = start_process(data_dir, port, token)
        try:
            wait_ready(port, token)
            saved = httpx.get(f"{base}/tasks/{task_id}", headers=headers, timeout=3)
            assert saved.status_code == 200 and saved.json()["id"] == task_id
        finally:
            stop_process(restarted)
        return {
            "type": "REAL_LOCAL_PYTHON_PROCESS_SMOKE",
            "python": sys.version.split()[0],
            "platform": sys.platform,
            "loopback_health": "passed",
            "invalid_token_rejected": True,
            "persisted_task_after_restart": True,
            "worker_block_status_expected": True,
            "python_child_terminated": process.poll() is not None and restarted.poll() is not None,
            "tauri_process_lifecycle_tested": False,
            "douyin_live_tested": False,
        }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
