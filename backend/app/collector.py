"""F2 boundary and deterministic pagination rules.

F2 is optional and imported lazily. These methods are code-level adapters, NOT
proof that current Douyin endpoints are reachable from a given network/account.
"""

import asyncio
from dataclasses import dataclass
from typing import Any

from .links import ParsedLink


class CollectorError(RuntimeError):
    pass


@dataclass(frozen=True)
class VideoCandidate:
    platform_video_id: str
    author_platform_id: str
    title: str
    published_at_unix: int | None
    source_url: str
    media_url: str | None


@dataclass(frozen=True)
class WorkPage:
    videos: list[VideoCandidate]
    has_more: bool
    next_cursor: int | None
    stop_reason: str | None


@dataclass(frozen=True)
class AuthorWorks:
    author_id: str
    videos: list[VideoCandidate]
    pages_fetched: int
    stop_reason: str
    second_page_new_ids: int = 0
    second_page_sample: VideoCandidate | None = None


def normalize_f2_page(payload: dict[str, Any], author_id: str, current_cursor: int) -> WorkPage:
    """Interpret response transparently: missing has_more is not 'end of list'."""
    if not isinstance(payload, dict):
        raise CollectorError("采集响应不是对象")
    status = payload.get("status_code")
    if status not in (0, None):
        raise CollectorError(f"平台返回不可用状态: {status}")
    raw_items = payload.get("aweme_list") or []
    if not isinstance(raw_items, list):
        raise CollectorError("作品列表字段类型错误")
    videos: list[VideoCandidate] = []
    for raw in raw_items:
        if not isinstance(raw, dict) or not raw.get("aweme_id"):
            continue
        author = raw.get("author") or {}
        actual_id = str(author.get("sec_uid") or "")
        if not actual_id or actual_id != author_id:
            # An untrusted API item must not be incorrectly attributed to this creator.
            continue
        video = raw.get("video") or {}
        addresses = ((video.get("play_addr") or {}).get("url_list") or [])
        playable = next((x for x in addresses if isinstance(x, str) and x.startswith("https://")), None)
        timestamp = raw.get("create_time")
        videos.append(VideoCandidate(
            platform_video_id=str(raw["aweme_id"]),
            author_platform_id=actual_id,
            title=str(raw.get("desc") or ""),
            published_at_unix=int(timestamp) if isinstance(timestamp, (int, float)) else None,
            source_url=f"https://www.douyin.com/video/{raw['aweme_id']}",
            media_url=playable,
        ))
    if payload.get("has_more") is None:
        return WorkPage(videos=videos, has_more=False, next_cursor=None, stop_reason="missing_pagination_info")
    if not bool(payload["has_more"]):
        return WorkPage(videos=videos, has_more=False, next_cursor=None, stop_reason="end_of_list")
    next_cursor = payload.get("max_cursor")
    if isinstance(next_cursor, bool) or not isinstance(next_cursor, (int, str)):
        return WorkPage(videos=videos, has_more=False, next_cursor=None, stop_reason="missing_cursor")
    try:
        normalized = int(next_cursor)
    except (ValueError, TypeError):
        return WorkPage(videos=videos, has_more=False, next_cursor=None, stop_reason="invalid_cursor")
    if normalized == current_cursor:
        return WorkPage(videos=videos, has_more=False, next_cursor=None, stop_reason="cursor_not_advanced")
    return WorkPage(videos=videos, has_more=True, next_cursor=normalized, stop_reason=None)


async def collect_author_pages(fetch_page, author_id: str, max_videos: int, page_size: int = 20) -> AuthorWorks:
    """Deduplicate platform IDs and stop on missing pagination; caller provides API fetch."""
    if max_videos not in (10, 30):
        raise ValueError("max_videos must be 10 or 30")
    seen: set[str] = set()
    all_videos: list[VideoCandidate] = []
    cursor = 0
    pages = 0
    second_page_new_ids = 0
    second_page_sample = None
    for _ in range(20):  # Hard safety cap; avoid infinite upstream loops.
        raw = await fetch_page(author_id, cursor, min(page_size, max_videos - len(all_videos)))
        pages += 1
        page = normalize_f2_page(raw, author_id, cursor)
        before = len(all_videos)
        for item in page.videos:
            if item.platform_video_id not in seen:
                seen.add(item.platform_video_id)
                all_videos.append(item)
            if len(all_videos) == max_videos:
                break
        if pages == 2:
            second_page_new_ids = len(all_videos) - before
            if second_page_new_ids:
                second_page_sample = all_videos[before]
        if len(all_videos) == max_videos:
            return AuthorWorks(author_id, all_videos, pages, "limit_reached", second_page_new_ids, second_page_sample)
        if page.stop_reason:
            return AuthorWorks(author_id, all_videos, pages, page.stop_reason, second_page_new_ids, second_page_sample)
        if not page.videos:
            return AuthorWorks(author_id, all_videos, pages, "empty_page", second_page_new_ids, second_page_sample)
        cursor = page.next_cursor  # type: ignore[assignment]
    return AuthorWorks(author_id, all_videos, pages, "page_safety_limit", second_page_new_ids, second_page_sample)


class F2Collector:
    """Thin optional SDK adapter. Provider registration stays disabled until live R0 acceptance."""

    def __init__(self, cookie: str | None = None):
        self.cookie = cookie

    def _options(self) -> dict:
        try:
            from f2.apps.douyin.utils import ClientConfManager
        except ImportError as exc:
            raise CollectorError("F2未安装；请安装 backend[collector-f2]") from exc
        # Never auto-harvest browser cookies or print credentials.
        return {"headers": ClientConfManager.headers(), "cookie": self.cookie or "", "timeout": 2}

    async def profile_id(self, profile_url: str) -> str:
        from f2.apps.douyin.utils import SecUserIdFetcher
        return await SecUserIdFetcher.get_sec_user_id(profile_url)

    async def video_detail(self, video_url: str) -> VideoCandidate:
        from f2.apps.douyin.utils import AwemeIdFetcher
        from f2.apps.douyin.crawler import DouyinCrawler
        from f2.apps.douyin.model import PostDetail
        aweme_id = await AwemeIdFetcher.get_aweme_id(video_url)
        async with DouyinCrawler(self._options()) as crawler:
            response = await crawler.fetch_post_detail(PostDetail(aweme_id=aweme_id))
        raw = response.get("aweme_detail") if isinstance(response, dict) else None
        if not isinstance(raw, dict):
            raise CollectorError("作品详情不可用，可能需要授权或作品不可访问")
        author_id = str((raw.get("author") or {}).get("sec_uid") or "")
        if not author_id:
            raise CollectorError("真实作品没有可核实的作者ID")
        page = normalize_f2_page({"status_code": 0, "aweme_list": [raw], "has_more": False}, author_id, 0)
        if not page.videos:
            raise CollectorError("未提取到作品字段")
        return page.videos[0]

    async def author_works(self, author_id: str, max_videos: int) -> AuthorWorks:
        from f2.apps.douyin.crawler import DouyinCrawler
        from f2.apps.douyin.model import UserPost

        pages_started = 0

        async def fetch_page(sec_id: str, cursor: int, count: int):
            nonlocal pages_started
            if pages_started > 0:
                await asyncio.sleep(2)  # conservative page pacing
            pages_started += 1
            async with DouyinCrawler(self._options()) as crawler:
                return await crawler.fetch_user_post(UserPost(sec_user_id=sec_id, max_cursor=cursor, count=count))

        return await collect_author_pages(fetch_page, author_id, max_videos)
