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
