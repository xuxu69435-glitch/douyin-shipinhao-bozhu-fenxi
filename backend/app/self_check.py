"""Clean-data, offline installation checks. Never reads a user's settings."""

import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
import tempfile
import wave

from .media import media_executable, probe_media, subprocess_options


def run_self_check():
    from .schemas import HealthView
    report = {"test_type": "CLEAN_DATA_OFFLINE_INSTALLATION_CHECK", "version": HealthView().version,
              "platform": platform.system(), "architecture": platform.machine(),
              "python": platform.python_version(), "used_existing_settings": False,
              "real_douyin_tested": False, "real_model_tested": False, "checks": []}

    def check(name, action):
        try:
            details = action()
            report["checks"].append({"name": name, "status": "passed", "details": details})
        except Exception as exc:
            # Exceptions can include machine paths; diagnostics are safe to share.
            details = {"name": name, "status": "failed", "error_type": type(exc).__name__}
            if isinstance(exc, importlib.metadata.PackageNotFoundError):
                details["distribution"] = exc.name
            report["checks"].append(details)

    with tempfile.TemporaryDirectory(prefix="douyin-analyst-check-") as temporary:
        root = Path(temporary)

        def packages():
            values = {name: importlib.metadata.version(name) for name in
                      ("fastapi", "sqlalchemy", "f2", "faster-whisper", "av", "ctranslate2", "onnxruntime")}
            if int(values["av"].split(".")[0]) >= 19:
                raise RuntimeError("incompatible_pyav")
            return values
        check("runtime_packages", packages)

        audio = root / "synthetic.wav"
        with wave.open(str(audio), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(16000)
            output.writeframes(b"\x00\x00" * 16000)

        def media():
            versions = {}
            for tool in ("ffmpeg", "ffprobe"):
                process = subprocess.run([media_executable(tool), "-version"], capture_output=True, check=True,
                                         timeout=10, **subprocess_options())
                versions[tool] = process.stdout.decode("utf8", errors="replace").splitlines()[0]
            video = root / "synthetic.mp4"
            subprocess.run([media_executable("ffmpeg"), "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                            "-f", "lavfi", "-i", "color=c=black:s=128x96:r=4:d=1", "-i", str(audio),
                            "-shortest", "-c:v", "mpeg4", "-c:a", "aac", str(video)],
                           capture_output=True, check=True, timeout=20, **subprocess_options())
            streams = sorted({item["codec_type"] for item in probe_media(video)["streams"]})
            if streams != ["audio", "video"]:
                raise RuntimeError("missing_media_stream")
            return {**versions, "synthetic_streams": streams}
        check("bundled_media_tools", media)

        def decode():
            from faster_whisper.audio import decode_audio
            import ctranslate2
            import onnxruntime
            values = decode_audio(str(audio))
            if len(values) != 16000:
                raise RuntimeError("incorrect_sample_count")
            return {"samples": len(values), "weights_loaded": False,
                    "ctranslate2": ctranslate2.__version__, "onnxruntime": onnxruntime.__version__}
        check("real_audio_decode_without_weights", decode)

        def database():
            from .database import build_session_factory
            from .models import TaskRecord
            factory, engine = build_session_factory(root / "database")
            try:
                with factory.begin() as session:
                    item = TaskRecord(input_text="self-check-fixture", source_url="fixture://self-check",
                                      source_kind="local", max_videos=1, status="paused")
                    session.add(item)
                    session.flush()
                    identity = item.id
            finally:
                engine.dispose()
            factory, engine = build_session_factory(root / "database")
            try:
                with factory() as session:
                    if session.get(TaskRecord, identity).status != "paused":
                        raise RuntimeError("persistence_failed")
            finally:
                engine.dispose()
            return {"fresh_database": True, "persisted_after_reopen": True}
        check("sqlite_persistence", database)

        def encryption():
            from .douyin_session import save_session, load_cookie
            fixture = "sessionid=self-check-synthetic-credential"
            save_session(root / "encrypted", fixture)
            if fixture in (root / "encrypted" / "douyin-session.json").read_text():
                raise RuntimeError("plaintext_credential")
            if load_cookie(root / "encrypted") != fixture:
                raise RuntimeError("credential_roundtrip_failed")
            return {"provider": "windows_dpapi", "synthetic_only": True}
        check("credential_encryption", encryption)

        def bridge():
            from .chatgpt_plan import ChatGPTPlanBridge, bridge_files, private_environment
            process = subprocess.run([bridge_files()[0], "--version"], capture_output=True, check=True,
                                     timeout=10, env=private_environment(), **subprocess_options())
            state = ChatGPTPlanBridge(root / "new-account").call("status", timeout=10)
            if state != {"status": "disconnected", "sharing": False}:
                raise RuntimeError("unexpected_fresh_account")
            return {"node": process.stdout.decode("ascii").strip(), "fresh_account": "disconnected"}
        check("bundled_chatgpt_bridge", bridge)

        def browser_bridge():
            from .browser_collector import browser_bridge_files
            from .chatgpt_plan import private_environment
            node, script = browser_bridge_files()
            process = subprocess.run([node, str(script)], input=b'{"op":"status"}', capture_output=True,
                                     check=True, timeout=10, env=private_environment(), **subprocess_options())
            result = json.loads(process.stdout)
            if not result.get("ok"):
                raise RuntimeError("browser_bridge_failed")
            return {**result["result"], "browser_launched": False}
        check("normal_browser_bridge", browser_bridge)

    report["offline_checks_passed"] = all(item["status"] == "passed" for item in report["checks"])
    return report


def self_check_main():
    import argparse
    parser = argparse.ArgumentParser(description="Offline checks using fresh temporary data; no account or API use")
    parser.add_argument("--self-check", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run_self_check()
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf8")
    print(text)
    return 0 if report["offline_checks_passed"] else 1
