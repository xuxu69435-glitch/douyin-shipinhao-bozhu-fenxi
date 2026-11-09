"""Timestamp-preserving, optional local ASR; no network in unit tests.

A production model can download weights the first time it runs. Callers must
report the model identity and whether segments represent a real ASR inference.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from importlib.metadata import version, PackageNotFoundError

# Public model revision used in the Windows real-speech acceptance test.
SMALL_MODEL_REVISION = "536b0662742c02347bc0e980a01041f333bce120"


@dataclass(frozen=True)
class AsrSegment:
    segment_id: int
    start_ms: int
    end_ms: int
    text: str


@dataclass(frozen=True)
class AsrResult:
    model_version: str
    segments: tuple[AsrSegment, ...]
    language: str | None = None


class Transcriber(Protocol):
    def transcribe(self, audio_path: Path) -> AsrResult: ...


def normalize_asr_segments(items, model_version: str, language: str | None = None) -> AsrResult:
    """Normalize Whisper seconds to nonempty, stable millisecond spans."""
    segments: list[AsrSegment] = []
    for item in items:
        text = str(getattr(item, "text", "")).strip()
        if not text:
            continue
        start = round(float(item.start) * 1000)
        end = round(float(item.end) * 1000)
        if start < 0 or end <= start:
            raise ValueError(f"ASR returned invalid time span: {start}..{end}")
        if segments and start < segments[-1].start_ms:
            raise ValueError("ASR segments are not ordered")
        segments.append(AsrSegment(len(segments), start, end, text))
    return AsrResult(model_version=model_version, segments=tuple(segments), language=language)


class FasterWhisperTranscriber:
    """Real faster-whisper engine, loaded lazily to avoid startup/model downloads."""

    def __init__(self, model_name: str = "small", device: str = "cpu", compute_type: str = "int8"):
        if not model_name.strip():
            raise ValueError("model_name must not be blank")
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self.revision = SMALL_MODEL_REVISION if model_name == "small" else None
        self._model = None

    @property
    def model_version(self) -> str:
        try:
            engine_version = version("faster-whisper")
        except PackageNotFoundError:
            engine_version = "not-installed"
        model_identity = self.model_name + ("@" + self.revision if self.revision else "")
        return f"faster-whisper/{engine_version}:{model_identity}:{self.device}:{self.compute_type}:vad1:beam5"

    def transcribe(self, audio_path: Path) -> AsrResult:
        if not audio_path.is_file():
            raise FileNotFoundError(audio_path)
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise RuntimeError("faster-whisper未安装；请安装 backend[asr]") from exc
            self._model = WhisperModel(self.model_name, device=self.device, compute_type=self.compute_type,
                                       revision=self.revision, use_auth_token=False)
        items, info = self._model.transcribe(
            str(audio_path), vad_filter=True, beam_size=5, condition_on_previous_text=False,
        )
        return normalize_asr_segments(items, self.model_version, getattr(info, "language", None))
