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


async def resolve_short_link(short_url: str) -> ParsedLink:
    """Resolve only explicitly allowed Douyin HTTPS redirects; never follow offsite."""
    import httpx
    current = parse_douyin_input(short_url)
    if current.kind != "short":
        return current
    async with httpx.AsyncClient(timeout=httpx.Timeout(12, connect=5), follow_redirects=False) as client:
        url = current.url
        for _ in range(6):
            response = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            if response.status_code not in (301, 302, 303, 307, 308):
                raise InvalidDouyinLink("分享短链未返回可识别的抖音主页或视频跳转")
            from urllib.parse import urljoin
            candidate = urljoin(url, response.headers.get("location", ""))
            parsed = urlsplit(candidate)
            if (parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS
                    or parsed.username or parsed.password or parsed.port not in (None, 443)):
                raise InvalidDouyinLink("分享链接跳转目标不属于允许的抖音站点")
            try:
                result = parse_douyin_input(candidate)
            except InvalidDouyinLink:
                # Intermediate Douyin redirect: another short-link hop is fine.
                if parsed.hostname == "v.douyin.com":
                    url = candidate
                    continue
                raise
            if result.kind != "short":
                return result
            url = candidate
    raise InvalidDouyinLink("分享短链跳转次数超过限制")
