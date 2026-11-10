"""Observe normal Edge page responses through a private, bounded Node helper."""

import asyncio
from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit

from .chatgpt_plan import private_environment, bridge_files
from .collector import AuthorWorks, CollectorError, normalize_f2_page
from .links import parse_douyin_input
from .media import media_url_allowed, subprocess_options


def browser_bridge_files():
    if getattr(sys, "frozen", False):
        return bridge_files()[0], Path(sys._MEIPASS) / "browser-bridge" / "main.mjs"
    return bridge_files()[0], Path(__file__).resolve().parents[2] / "browser-helper" / "main.mjs"


def browser_candidate(raw):
    author = str((raw.get("author") or {}).get("sec_uid") or "")
    page = normalize_f2_page({"aweme_list": [raw], "has_more": 0}, author, 0)
    if not page.videos:
        raise CollectorError("浏览器未返回可核实的作品作者")
    addresses = (raw.get("video") or {}).get("play_addr", {}).get("url_list", [])
    permitted = [url for url in addresses if isinstance(url, str) and media_url_allowed(url)]
    # The public web play endpoint can reject direct requests; prefer the actual
    # signed CDN address returned in the same normal page response.
    ordered = tuple(dict.fromkeys(sorted(permitted, key=lambda url: urlsplit(url).hostname == "www.douyin.com")))
    return replace(page.videos[0], media_url=next(iter(ordered), None), media_urls=ordered[:3])


class BrowserCollector:
    def __init__(self, cookie=None, timeout=90):
        self.cookie = cookie
        self.timeout = min(120, max(15, timeout))

    async def _request(self, url, limit):
        node, script = browser_bridge_files()
        if not script.is_file():
            raise CollectorError("浏览器采集组件未安装，请更新桌面安装程序")
        payload = {"url": url, "limit": limit, "timeout_ms": int(self.timeout * 1000), "cookie": self.cookie}
        process = subprocess.Popen([node, str(script)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, env=private_environment(), **subprocess_options())
        try:
            output, _ = await asyncio.wait_for(asyncio.to_thread(
                process.communicate, json.dumps(payload).encode("utf8"), timeout=self.timeout + 10), self.timeout + 12)
            if len(output) > 4_000_000:
                raise CollectorError("浏览器采集响应超过大小上限")
            final = None
            for line in output.splitlines():
                try:
                    value = json.loads(line)
                except (ValueError, UnicodeError):
                    continue
                if isinstance(value, dict) and isinstance(value.get("ok"), bool):
                    final = value
            if final is None or not final["ok"]:
                reason = final.get("error") if final else None
                messages = {"browser_closed_by_user": "浏览器窗口已关闭，可恢复任务重试",
                            "browser_platform_denied": "正常浏览器请求仍被平台拒绝，请在浏览器核对访问权限",
                            "browser_posts_not_observed": "未观察到作品列表，请在 Edge 完成所需登录或验证后重试",
                            "browser_detail_not_observed": "未观察到作品详情，请在 Edge 核对该作品是否可见"}
                raise CollectorError(messages.get(reason, "浏览器采集未完成，请确认本机已安装 Microsoft Edge"))
            return final["result"]
        except (asyncio.TimeoutError, subprocess.TimeoutExpired):
            raise CollectorError("浏览器采集超时，当前结果未标记为成功") from None
        finally:
            if process.poll() is None:
                if os.name == "nt":
                    await asyncio.to_thread(subprocess.run, ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                            capture_output=True, timeout=8, **subprocess_options())
                else:
                    process.kill()
                await asyncio.to_thread(process.wait, timeout=5)

    async def profile_id(self, profile_url):
        link = parse_douyin_input(profile_url)
        if link.kind != "profile" or not link.platform_id:
            raise CollectorError("需要已解析的抖音主页地址")
        return link.platform_id

    async def video_detail(self, video_url):
        link = parse_douyin_input(video_url)
        if link.kind != "video":
            raise CollectorError("需要已解析的抖音作品地址")
        result = await self._request(link.url, 10)
        candidate = browser_candidate(result.get("detail") or {})
        if candidate.platform_video_id != link.platform_id:
            raise CollectorError("浏览器返回的作品 ID 与输入不一致")
        return candidate

    async def author_works(self, author_id, max_videos):
        if max_videos not in (10, 30):
            raise ValueError("max_videos must be 10 or 30")
        result = await self._request(f"https://www.douyin.com/user/{author_id}", max_videos)
        videos, seen = [], set()
        second_ids, second_sample = 0, None
        cursor = "0"
        pages = result.get("pages") or []
        for index, page in enumerate(pages):
            if str(page.get("request_cursor", "0")) != cursor:
                raise CollectorError("浏览器分页游标不连续，不能确认第二页")
            before = len(videos)
            for raw in page.get("aweme_list") or []:
                candidate = browser_candidate(raw)
                if candidate.author_platform_id != author_id:
                    raise CollectorError("浏览器作品列表包含其他作者，已停止归属")
                if candidate.platform_video_id in seen or len(videos) >= max_videos:
                    continue
                seen.add(candidate.platform_video_id)
                videos.append(candidate)
            if index == 1:
                second_ids = len(videos) - before
                second_sample = videos[before] if second_ids else None
            cursor = str(page.get("max_cursor"))
        return AuthorWorks(author_id, videos, len(pages), result.get("stop_reason", "browser_page_timeout"),
                           second_ids, second_sample)
