"""Official local DevKit bridge; never reads another application's login state."""

import asyncio
import base64
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit
import webbrowser

from .media import subprocess_options
from .runtime_settings import _crypt_key


class ChatGPTPlanError(RuntimeError):
    def __init__(self, code, retryable=False):
        self.code = code
        self.retryable = retryable
        super().__init__(f"ChatGPT 套餐连接未完成（{code}），请检查登录、授权和套餐用量")


def bridge_files():
    if getattr(sys, "frozen", False):
        root = Path(sys._MEIPASS) / "chatgpt-bridge"
        return str(root / "node.exe"), root / "bridge.mjs"
    root = Path(__file__).resolve().parents[2] / "auth-helper"
    return shutil.which("node") or "node", root / "dist" / "bridge.mjs"


def private_environment():
    # No inherited API keys, Node preload/debug hooks, or account/project overrides.
    allowed = {"systemroot", "windir", "path", "pathext", "temp", "tmp", "userprofile",
               "localappdata", "appdata", "programfiles", "programfiles(x86)", "systemdrive"}
    return {key: value for key, value in os.environ.items() if key.lower() in allowed}


class ChatGPTPlanBridge:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self._thread = None
        self._cancel = threading.Event()
        self._error = None
        self._lock = threading.Lock()

    @property
    def connecting(self):
        return self._thread is not None and self._thread.is_alive()

    def call(self, op, args=None, timeout=35):
        node, script = bridge_files()
        if not script.is_file():
            raise ChatGPTPlanError("bridge_not_built")
        if os.name != "nt":
            raise ChatGPTPlanError("windows_encryption_required")
        try:
            process = subprocess.Popen([node, str(script)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=subprocess.DEVNULL, env=private_environment(), **subprocess_options())
        except OSError as exc:
            raise ChatGPTPlanError("bridge_runtime_unavailable") from exc
        messages = queue.Queue()

        def read():
            try:
                while line := process.stdout.readline(1_000_001):
                    if len(line) > 1_000_000:
                        break
                    messages.put(json.loads(line))
            except (ValueError, OSError):
                pass
            finally:
                messages.put(None)

        reader = threading.Thread(target=read, daemon=True)
        reader.start()

        def send(value):
            process.stdin.write((json.dumps(value, ensure_ascii=True) + "\n").encode("utf8"))
            process.stdin.flush()

        try:
            send({"op": op, "args": args or {}, "storageDir": str((self.data_dir / "chatgpt").resolve())})
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if op in {"sign-in", "generate"} and self._cancel.is_set():
                    raise ChatGPTPlanError("cancelled")
                try:
                    message = messages.get(timeout=min(0.2, max(0.01, deadline - time.monotonic())))
                except queue.Empty:
                    continue
                if message is None:
                    raise ChatGPTPlanError("bridge_interrupted")
                kind = message.get("type")
                if kind == "result":
                    return message.get("value")
                if kind == "error":
                    code = message.get("code", "bridge_operation_failed")
                    if not isinstance(code, str) or not code.replace("_", "").isalnum() or len(code) > 100:
                        code = "bridge_operation_failed"
                    raise ChatGPTPlanError(code, message.get("retryable") is True)
                if kind in {"encrypt", "decrypt"}:
                    try:
                        value = base64.b64decode(message["value"], validate=True)
                        reply = base64.b64encode(_crypt_key(value, decrypt=kind == "decrypt")).decode("ascii")
                        send({"id": message["id"], "value": reply})
                    except (OSError, ValueError):
                        send({"id": message["id"], "error": True})
                elif kind == "browser" and op == "sign-in":
                    url = message.get("value", "")
                    parsed = urlsplit(url)
                    if (parsed.scheme != "https" or parsed.hostname != "auth.openai.com"
                            or parsed.username or parsed.password or parsed.port not in (None, 443)):
                        raise ChatGPTPlanError("invalid_authorization_url")
                    if not webbrowser.open(url):
                        raise ChatGPTPlanError("browser_open_failed")
                    send({"id": message["id"], "value": True})
                else:
                    raise ChatGPTPlanError("invalid_bridge_message")
            raise ChatGPTPlanError("timeout", True)
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
            process.stdin.close()
            process.stdout.close()
            reader.join(timeout=1)

    def status(self):
        if self.connecting:
            return {"status": "connecting", "sharing": False}
        state = self.call("status", timeout=10)
        if self._error:
            state["error"] = {"code": self._error.code, "message": str(self._error)}
        return state

    def sign_in(self):
        with self._lock:
            if self.connecting:
                return {"status": "connecting", "sharing": False}
            self._cancel.clear()
            self._error = None

            def run():
                try:
                    self.call("sign-in", timeout=245)
                except ChatGPTPlanError as exc:
                    self._error = exc

            self._thread = threading.Thread(target=run, daemon=True)
            self._thread.start()
        return {"status": "connecting", "sharing": False}

    def cancel(self):
        self._cancel.set()
        if self._thread:
            self._thread.join(timeout=2)


def make_generator(configuration, data_dir):
    from .insights import OpenAICompatibleInsightGenerator
    from .worker import PrerequisiteMissing
    if configuration.model_provider == "chatgpt":
        if not configuration.CHATGPT_MODEL:
            raise PrerequisiteMissing("CHATGPT_NOT_CONFIGURED", "请使用 ChatGPT 登录，并选择账户可用的模型")
        return ChatGPTPlanInsightGenerator(data_dir, configuration.CHATGPT_MODEL)
    key = configuration.OPENAI_API_KEY.get_secret_value() if configuration.OPENAI_API_KEY else ""
    if not all((configuration.OPENAI_BASE_URL, key, configuration.OPENAI_MODEL)):
        raise PrerequisiteMissing("LLM_NOT_CONFIGURED", "请配置模型服务，或选择使用 ChatGPT 套餐并登录")
    return OpenAICompatibleInsightGenerator(configuration.OPENAI_BASE_URL, key, configuration.OPENAI_MODEL)


from .insights import OpenAICompatibleInsightGenerator, InsightDraft, EvidenceIntegrityError, SYSTEM_PROMPT


class ChatGPTPlanInsightGenerator(OpenAICompatibleInsightGenerator):
    """Reuse chunking/evidence harness while delegating OAuth and Responses to DevKit."""

    def __init__(self, data_dir, model):
        self.bridge = ChatGPTPlanBridge(data_dir)
        self.model = model
        self.cache_identity = "chatgpt-plan-responses-v1|" + model
        self.last_run = {}

    async def _request(self, client, content, allowed_ids):
        # This route does not support max_output_tokens. Do not claim a server token cap.
        self.last_run.update({"max_output_tokens": None, "max_output_characters": 32_768,
                              "provider": "chatgpt_plan", "usage_reported": False})
        if self.last_run["requests"] >= self.MAX_REQUESTS:
            raise ValueError("已达到单视频模型请求上限")
        self.last_run["requests"] += 1
        try:
            result = await asyncio.to_thread(self.bridge.call, "generate", {
                "model": self.model, "content": content, "instructions": SYSTEM_PROMPT}, 95)
        except asyncio.CancelledError:
            self.bridge.cancel()
            raise
        draft = InsightDraft.model_validate(json.loads(result["text"]))
        referenced = set(draft.summary_segment_ids)
        for statement in draft.key_claims + draft.explicitly_stated_preferences + draft.discussed_entities:
            referenced.update(statement.segment_ids)
        if not referenced <= allowed_ids:
            raise EvidenceIntegrityError("模型引用了当前材料中不存在的字幕段")
        return draft.model_dump()
