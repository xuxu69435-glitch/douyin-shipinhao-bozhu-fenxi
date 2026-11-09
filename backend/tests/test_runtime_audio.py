"""Decode real PCM bytes without downloading model weights or calling an API."""
import wave

import pytest


def test_faster_whisper_can_decode_with_locked_pyav(tmp_path):
    pytest.importorskip("faster_whisper")
    from faster_whisper.audio import decode_audio
    path = tmp_path / "真实音频解码回归.wav"
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(b"\x00\x00" * 8000)
    audio = decode_audio(str(path))
    assert audio.dtype.name == "float32" and audio.shape == (8000,)


def test_default_small_model_passes_fixed_revision_without_hf_credentials(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace
    from app.transcription import FasterWhisperTranscriber, SMALL_MODEL_REVISION
    calls = []
    class Model:
        def __init__(self, name, **kwargs):
            calls.append((name, kwargs))
        def transcribe(self, path, **kwargs):
            return [], SimpleNamespace(language='zh')
    monkeypatch.setitem(sys.modules, 'faster_whisper', SimpleNamespace(WhisperModel=Model))
    path = tmp_path / 'fixture.wav'
    path.write_bytes(b'fixture-no-model-download')
    transcriber = FasterWhisperTranscriber('small')
    assert SMALL_MODEL_REVISION in transcriber.model_version
    assert not transcriber.transcribe(path).segments
    assert calls[0][1]['revision'] == SMALL_MODEL_REVISION
    assert calls[0][1]['use_auth_token'] is False
