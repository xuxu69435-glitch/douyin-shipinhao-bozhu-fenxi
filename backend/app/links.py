"""Pure link parsing, no platform access and no unverifiable identity claims."""

import re
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field

ALLOWED_HOSTS = frozenset(
    {"douyin.com", "www.douyin.com", "m.douyin.com", "v.douyin.com", "iesdouyin.com", "www.iesdouyin.com"}
)
URL_PATTERN = re.compile(r"https?://[^\s<>\"'，。；！？、）】]+", re.IGNORECASE)
VIDEO_PATTERN = re.compile(r"^/(?:video|note)/(\d{8,25})(?:/|$)")
PROFILE_PATTERN = re.compile(r"^/user/([A-Za-z0-9_.-]{8,200})(?:/|$)")


class InvalidDouyinLink(ValueError):
    pass


class ParsedLink(BaseModel):
    kind: Literal["video", "profile", "short"]
    url: str = Field(max_length=2048)
    platform_id: str | None = None


def parse_douyin_input(text: str) -> ParsedLink:
    if len(text) > 5000:
        raise InvalidDouyinLink("分享文本过长（最多5000字符）")
    matches = URL_PATTERN.findall(text)
    if not matches:
        raise InvalidDouyinLink("未找到抖音链接")
    for match in matches:
        value = match.rstrip(".,!?:;)")
        try:
            url = urlsplit(value)
            port = url.port
        except ValueError:
            continue
        if url.scheme != "https" or not url.hostname or url.hostname.lower() not in ALLOWED_HOSTS:
            continue
        if url.username or url.password or (port is not None and port != 443):
            continue
        host = url.hostname.lower()
        video = VIDEO_PATTERN.match(url.path)
        profile = PROFILE_PATTERN.match(url.path)
        if video:
            return ParsedLink(kind="video", url=f"https://www.douyin.com/video/{video.group(1)}", platform_id=video.group(1))
        if profile:
            return ParsedLink(kind="profile", url=f"https://www.douyin.com/user/{profile.group(1)}", platform_id=profile.group(1))
        if host == "v.douyin.com" and re.fullmatch(r"/[A-Za-z0-9_-]{3,40}/?", url.path):
            return ParsedLink(kind="short", url=f"https://v.douyin.com{url.path}")
    raise InvalidDouyinLink("仅支持有效的抖音主页、作品或分享短链")
