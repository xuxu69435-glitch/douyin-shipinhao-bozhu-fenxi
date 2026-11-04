"""Opt-in, REAL local-media ASR + LLM smoke path. Never runs on test fixtures."""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.database import build_session_factory
from app.insights import OpenAICompatibleInsightGenerator
from app.models import TranscriptSegment  # ensure all tables registered
from app import models  # noqa: F401
from app.pipeline import analyze_local_file
from app.transcription import FasterWhisperTranscriber
from app.runtime_settings import load_runtime_settings


def main():
    parser = argparse.ArgumentParser(description="True local ASR + LLM with persisted evidence")
    parser.add_argument("path", type=Path, help="local MP4/MOV/MKV with permission to analyze")
    parser.add_argument("--data-dir", type=Path,
                        default=Path(os.getenv("LOCALAPPDATA") or Path.home() / ".local" / "share") / "com.douyinanalyst.desktop")
    parser.add_argument("--whisper-model")
    args = parser.parse_args()
    configuration = load_runtime_settings(args.data_dir)
    generator = OpenAICompatibleInsightGenerator(configuration.OPENAI_BASE_URL,
        configuration.OPENAI_API_KEY.get_secret_value() if configuration.OPENAI_API_KEY else "", configuration.OPENAI_MODEL)
    factory, engine = build_session_factory(args.data_dir)
    try:
        result = asyncio.run(analyze_local_file(
            args.path, factory, args.data_dir / "tmp",
            FasterWhisperTranscriber(model_name=args.whisper_model or configuration.whisper_model), generator,
        ))
        print(json.dumps(result.__dict__, ensure_ascii=False, indent=2))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
