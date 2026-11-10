import shutil
import subprocess

import pytest


@pytest.mark.asyncio
async def test_real_candidate_fallback_is_bounded_and_deduplicated(tmp_path):
    from app.media import download_media_candidates, InvalidMedia
    calls = []
    async def download(url, destination):
        calls.append(url)
        if url == 'fixture-second':
            return {'streams': ['audio', 'video']}
        raise InvalidMedia('fixture-denied')
    result = await download_media_candidates(['fixture-first','fixture-first','fixture-second'], tmp_path/'fixture.mp4', downloader=download)
    assert result['streams'] == ['audio', 'video'] and calls == ['fixture-first','fixture-second']
    calls.clear()
    with pytest.raises(InvalidMedia):
        await download_media_candidates(['a','b','c','d'], tmp_path/'fixture.mp4', downloader=download)
    assert calls == ['a','b','c']

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


@pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="FFmpeg not installed")
def test_chinese_video_path_and_utf8_metadata(tmp_path):
    video = tmp_path / "中文视频.mp4"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "color=c=black:s=80x80:r=5:d=1",
        "-c:v", "mpeg4", "-metadata", "title=中文标题", str(video)
    ], check=True, capture_output=True, timeout=45)
    assert probe_media(video)["format"]["tags"]["title"] == "中文标题"

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
