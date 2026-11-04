import shutil
import subprocess

import pytest

from app.media import InvalidMedia, extract_audio, probe_media


def test_reject_missing_media(tmp_path):
    with pytest.raises(InvalidMedia):
        probe_media(tmp_path / "does-not-exist.mp4")


@pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="FFmpeg not installed")
def test_real_ffmpeg_local_synthetic_media(tmp_path):
    video = tmp_path / "synthetic.mp4"
    audio = tmp_path / "audio.wav"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "color=c=black:s=80x80:r=5:d=1",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=16000:duration=1",
        "-shortest", "-c:v", "mpeg4", "-c:a", "aac", str(video)
    ], check=True, capture_output=True, timeout=45)
    assert any(stream.get("codec_type") == "video" for stream in probe_media(video)["streams"])
    assert extract_audio(video, audio) == audio
    assert audio.exists() and audio.stat().st_size > 0


@pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="FFmpeg not installed")
def test_video_without_audio(tmp_path):
    video = tmp_path / "silent.mp4"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "color=c=black:s=80x80:r=5:d=1",
        "-c:v", "mpeg4", str(video)
    ], check=True, capture_output=True, timeout=45)
    assert extract_audio(video, tmp_path / "none.wav") is None

@pytest.mark.parametrize("url,allowed", [
    ("https://v3.douyinvod.com/path", True),
    ("https://www.douyin.com/aweme/v1/play", True),
    ("https://douyinvod.com.evil.example/video", False),
    ("https://127.0.0.1/video", False),
    ("http://v3.douyinvod.com/path", False),
    ("https://someone@v3.douyinvod.com/path", False),
])
def test_media_url_allowlist(url, allowed):
    from app.media import media_url_allowed
    assert media_url_allowed(url) is allowed
