"""Bounded, model-independent collection acceptance with partial results."""

import asyncio
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time

from pydantic import BaseModel, Field

from .links import parse_douyin_input, resolve_short_link
from .media import download_verified_media, subprocess_options


class ProbeInput(BaseModel):
    input_text: str = Field(min_length=1, max_length=5000)


def new_report():
    return {"test_type": "real_network", "model_called": False, "complete": False,
            "steps": [{"name": key, "status": "pending", "message": "等待检测"}
                      for key in ("link", "author", "works", "page2", "media")]}


async def probe(text, allow_collection, cookie_file, scratch_dir, publish=lambda report: None, collector=None, cookie=None):
    report = new_report()

    def step(name, status, message):
        row = next(row for row in report["steps"] if row["name"] == name)
        row.update(status=status, message=message)
        publish(report)

    active = "link"
    try:
        link = parse_douyin_input(text)
        if link.kind == "short":
            link = await resolve_short_link(link.url)
        report.update(resolved_url=link.url, source_kind=link.kind, platform_id=link.platform_id)
        step("link", "passed", "分享地址已解析")
        if not allow_collection:
            step("author", "blocked", "请先在设置中启用真实抖音采集；链接解析不需要模型配置")
            return report
        active = "author"
        if collector is None:
            from .collector import F2Collector
            if cookie is None and cookie_file:
                from .douyin_session import read_cookie_file
                cookie = read_cookie_file(cookie_file)
            collector = F2Collector(cookie)
        report["access_mode"] = "user_imported_cookie" if cookie else "anonymous"
        if link.kind == "profile":
            author_id = await collector.profile_id(link.url)
            active = "works"
            works = await collector.author_works(author_id, 30)
            if not works.videos:
                raise ValueError("empty_works")
            report["author_id"] = author_id
            step("author", "passed", "已从真实作品验证作者归属")
            report["works"] = {"pages": works.pages_fetched, "unique": len(works.videos),
                               "second_page_new_ids": works.second_page_new_ids, "stop_reason": works.stop_reason}
            step("works", "passed", f"取得 {len(works.videos)} 条去重作品")
            step("page2", "passed" if works.second_page_new_ids > 0 else "blocked",
                 f"第二页新增 {works.second_page_new_ids} 个作品 ID")
            sample = works.second_page_sample or works.videos[0]
        else:
            sample = await collector.video_detail(link.url)
            report.update(author_id=sample.author_platform_id, video_id=sample.platform_video_id)
            step("author", "passed", "已从真实作品详情取得作者")
            step("works", "skipped", "单视频检测不请求作者作品列表")
            step("page2", "skipped", "单视频检测不检查分页")
        active = "media"
        if not sample.media_url:
            raise ValueError("missing_media")
        scratch_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="douyin-probe-", dir=scratch_dir) as temporary:
            info = await download_verified_media(sample.media_url, Path(temporary) / "sample.mp4")
        report["media"] = info
        step("media", "passed", "真实下载文件已通过 FFprobe 视频流校验")
        report["complete"] = all(row["status"] in {"passed", "skipped"} for row in report["steps"])
    except Exception as exc:
        status = getattr(exc, "status_code", None)
        response = getattr(exc, "response", None)
        status = status or getattr(response, "status_code", None)
        # Exception text may contain a signed CDN URL or Cookie. Keep only class/status.
        if status in (401, 403, 429):
            message = f"平台返回 HTTP {status}，当前访问未获准；尚未取得作者、作品或媒体证据"
        else:
            message = f"检测未通过（{type(exc).__name__}），请检查网络、访问权限和本机依赖"
        report["error_code"] = f"HTTP_{status}" if isinstance(status, int) else type(exc).__name__
        if active == "works":
            step("author", "blocked", "主页地址已解析，但尚未从真实作品验证作者归属")
        step(active, "blocked", message)
    finally:
        for row in report["steps"]:
            if row["status"] == "pending":
                row.update(status="skipped", message="前置步骤未通过，未执行")
        publish(report)
    return report


def run_isolated_probe(text, allow_collection, cookie_file, scratch_dir, timeout=45, *, cookie=None):
    command = ([sys.executable, "--collection-probe"] if getattr(sys, "frozen", False) else
               [sys.executable, str(Path(__file__).resolve().parents[1] / "sidecar.py"), "--collection-probe"])
    # Never pass model credentials into the probe, even through inherited environment.
    from .chatgpt_plan import private_environment
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, env=private_environment(), **subprocess_options())
    updates = queue.Queue()

    def read():
        try:
            for line in process.stdout:
                try:
                    value = json.loads(line)
                    if value.get("test_type") == "real_network":
                        updates.put(value)
                except (ValueError, AttributeError):
                    pass  # Ignore SDK logging; it never becomes the exported report.
        finally:
            updates.put(None)

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    report = new_report()
    finished = False
    try:
        process.stdin.write(json.dumps({"text": text, "allow_collection": allow_collection,
            "cookie_file": cookie_file, "cookie": cookie, "scratch_dir": str(scratch_dir)}, ensure_ascii=True).encode("utf8"))
        process.stdin.close()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                update = updates.get(timeout=min(0.2, max(0.01, deadline - time.monotonic())))
            except queue.Empty:
                continue
            if update is None:
                finished = True
                break
            report = update
        if not finished:
            report["error_code"] = "PROBE_TIMEOUT"
        elif process.wait(timeout=2) != 0:
            report["error_code"] = "PROBE_PROCESS_FAILED"
        if report.get("error_code") in {"PROBE_TIMEOUT", "PROBE_PROCESS_FAILED"}:
            report["complete"] = False
            pending = next((row for row in report["steps"] if row["status"] == "pending"), None)
            if pending:
                pending.update(status="blocked", message="检测超时或子进程中断；此前结果已保留")
            for row in report["steps"]:
                if row["status"] == "pending":
                    row.update(status="skipped", message="前置步骤未完成，未执行")
        return report
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        process.stdout.close()
        reader.join(timeout=1)


def probe_main():
    payload = json.loads(sys.stdin.buffer.read())
    def publish(report):
        print(json.dumps(report, ensure_ascii=True), flush=True)
    asyncio.run(probe(payload["text"], payload["allow_collection"], payload["cookie_file"],
                      Path(payload["scratch_dir"]), publish, cookie=payload.get("cookie")))
