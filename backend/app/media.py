"""FFprobe / FFmpeg helpers for the future M1 media verification and ASR path."""

import json
import shutil
import subprocess
import os
import sys
from pathlib import Path


class InvalidMedia(RuntimeError):
    pass


def media_executable(name: str) -> str:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    bundled = root / "media-tools" / (name + (".exe" if os.name == "nt" else ""))
    return str(bundled) if bundled.is_file() else name


def subprocess_options():
    return {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}


def probe_media(path: Path) -> dict:
    if not path.is_file() or path.stat().st_size == 0:
        raise InvalidMedia("媒体文件不存在或为空")
    if shutil.which(media_executable("ffprobe")) is None:
        raise InvalidMedia("ffprobe未安装")
    try:
        process = subprocess.run(
            [media_executable("ffprobe"), "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30, check=True,
            **subprocess_options(),
        )
        data = json.loads(process.stdout)
    except (subprocess.SubprocessError, ValueError) as exc:
        raise InvalidMedia("ffprobe媒体校验失败") from exc
    if not any(stream.get("codec_type") == "video" for stream in data.get("streams", [])):
        raise InvalidMedia("媒体没有视频流")
    return data


def extract_audio(video: Path, audio: Path) -> Path | None:
    data = probe_media(video)
    if not any(stream.get("codec_type") == "audio" for stream in data.get("streams", [])):
        return None
    if shutil.which(media_executable("ffmpeg")) is None:
        raise InvalidMedia("ffmpeg未安装")
    audio.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [media_executable("ffmpeg"), "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", str(video),
             "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(audio)],
            check=True, timeout=180, capture_output=True,
            **subprocess_options(),
        )
    except subprocess.SubprocessError as exc:
        audio.unlink(missing_ok=True)
        raise InvalidMedia("FFmpeg音频提取失败") from exc
    if not audio.is_file() or audio.stat().st_size == 0:
        raise InvalidMedia("音频提取后文件为空")
    return audio


# Strictly limit HTTP media downloads to known Douyin CDN hosts. A redirect to
# localhost/private infrastructure or an unrecognized host is never followed.
ALLOWED_MEDIA_DOMAINS = (
    "douyin.com", "douyinvod.com", "bytecdn.cn", "byteimg.com",
    "bytedance.com", "snssdk.com", "amemv.com",
)


def media_url_allowed(url: str) -> bool:
    from urllib.parse import urlsplit
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
        return (parsed.scheme == "https" and not parsed.username and not parsed.password
                and parsed.port in (None, 443) and
                any(host == d or host.endswith("." + d) for d in ALLOWED_MEDIA_DOMAINS))
    except ValueError:
        return False


async def download_verified_media(url: str, destination: Path, max_bytes: int = 200_000_000) -> dict:
    """Only permitted public/authorized media; enforce host policy at every redirect."""
    import hashlib
    from urllib.parse import urljoin
    import httpx

    if not media_url_allowed(url):
        raise InvalidMedia("媒体来源不属于允许的抖音CDN域名")
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size = 0
    next_url = url
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(40, connect=10), follow_redirects=False) as client:
            for _ in range(6):
                if not media_url_allowed(next_url):
                    raise InvalidMedia("媒体跳转至不允许的目标主机")
                async with client.stream("GET", next_url, headers={"User-Agent": "Mozilla/5.0"}) as response:
                    if response.status_code in (301, 302, 303, 307, 308):
                        location = response.headers.get("location", "")
                        if not location:
                            raise InvalidMedia("媒体跳转没有Location")
                        next_url = urljoin(next_url, location)
                        continue
                    if response.status_code != 200:
                        raise InvalidMedia(f"媒体下载返回HTTP {response.status_code}")
                    with destination.open("wb") as output:
                        async for chunk in response.aiter_bytes():
                            size += len(chunk)
                            if size > max_bytes:
                                raise InvalidMedia("媒体文件超过采样下载上限")
                            digest.update(chunk)
                            output.write(chunk)
                    data = probe_media(destination)
                    return {
                        "sha256": digest.hexdigest(),
                        "size_bytes": size,
                        "duration_seconds": float(data.get("format", {}).get("duration", 0)),
                        "streams": sorted(set(x.get("codec_type", "") for x in data.get("streams", []))),
                    }
        raise InvalidMedia("媒体重定向超过5次")
    except Exception:
        destination.unlink(missing_ok=True)
        raise
