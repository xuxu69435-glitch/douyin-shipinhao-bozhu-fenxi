"""Manual R0 live probe: never run silently in automated tests.

Read-only F2 public/authorized data access. This script does not bypass controls,
and cannot declare media playability until an actual file is probed.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.collector import F2Collector
from app.links import parse_douyin_input
from app.media import download_verified_media


async def run(profile_url: str | None, video_url: str | None, cookie: str | None, media_dir: Path | None):
    collector = F2Collector(cookie)
    result = {"test_type": "LIVE_REQUIRES_NETWORK_AND_PERMISSION", "author": None, "video": None, "page_2_confirmed": False, "media_playable_confirmed": False}
    media_sample = None
    if profile_url:
        link = parse_douyin_input(profile_url)
        if link.kind != "profile":
            raise ValueError("--profile must be a full profile URL; resolve short links separately")
        author_id = await collector.profile_id(link.url)
        result["author"] = {"sec_user_id": author_id, "resolved": bool(author_id)}
        works = await collector.author_works(author_id, 30)
        result["works"] = {"page_count": works.pages_fetched, "total_unique": len(works.videos), "stop_reason": works.stop_reason, "second_page_new_ids": works.second_page_new_ids,
                           "platform_video_ids": [v.platform_video_id for v in works.videos]}
        result["page_2_confirmed"] = works.pages_fetched >= 2 and works.second_page_new_ids > 0
        media_sample = works.second_page_sample
    if video_url:
        link = parse_douyin_input(video_url)
        if link.kind != "video":
            raise ValueError("--video must be a full video URL; resolve short links separately")
        item = await collector.video_detail(link.url)
        result["video"] = {"video_id": item.platform_video_id, "author_id": item.author_platform_id, "title": item.title,
                           "source_url": item.source_url, "media_address_present": bool(item.media_url)}
        if media_sample is None:
            media_sample = item
        # Never dump expiring signed CDN URLs or cookies to the probe report.
    if media_dir is not None:
        if media_sample is None or not media_sample.media_url:
            result["media_failure"] = "no_permitted_media_url"
        else:
            media_path = media_dir / (media_sample.platform_video_id + ".mp4")
            media_info = await download_verified_media(media_sample.media_url, media_path)
            result["media"] = {"platform_video_id": media_sample.platform_video_id, "local_path": str(media_path), **media_info}
            result["media_playable_confirmed"] = True  # actual file passed ffprobe
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", help="public/authorized full Douyin profile URL")
    parser.add_argument("--video", help="public/authorized full Douyin video URL")
    parser.add_argument("--cookie-file", type=Path, help="optional user-provided local credential file (never committed)")
    parser.add_argument("--output", type=Path, help="output JSON file (contains platform IDs)")
    parser.add_argument("--media-dir", type=Path, help="download one authorized sample to this local dir and verify with ffprobe")
    args = parser.parse_args()
    if not args.profile and not args.video:
        parser.error("provide --profile or --video")
    cookie = args.cookie_file.read_text(encoding="utf8").strip() if args.cookie_file else None
    result = asyncio.run(run(args.profile, args.video, cookie, args.media_dir))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf8")
        print("Wrote live probe results to", args.output)
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
