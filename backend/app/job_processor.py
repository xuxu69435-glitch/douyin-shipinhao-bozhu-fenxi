"""Opt-in real F2 -> media -> ASR -> model -> versioned creator report.

Never selected by default. The desktop host must set ANALYST_ENABLE_LIVE=1
and provide authorized access and model credentials. No crawling is triggered
by module import or tests. One SingleWorker invokes this sequentially.
"""

import asyncio
import re
import datetime as dt
from pathlib import Path
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .collector import AuthorWorks, F2Collector, VideoCandidate
from .insights import OpenAICompatibleInsightGenerator
from .links import ParsedLink, resolve_short_link
from .media import download_verified_media, probe_media
from .models import TaskRecord, TaskVideoRecord, VideoRecord
from .pipeline import analyze_media, sha256_file
from .reporting import ReportNotReady, build_creator_report
from .transcription import FasterWhisperTranscriber
from .worker import PrerequisiteMissing, WorkerControl


class CollectionProvider(Protocol):
    async def profile_id(self, profile_url: str) -> str: ...
    async def video_detail(self, video_url: str) -> VideoCandidate: ...
    async def author_works(self, author_id: str, max_videos: int) -> AuthorWorks: ...


def safe_error(error: Exception) -> str:
    """Avoid embedding URL query signatures or credentials in saved failures."""
    value = str(error)
    value = re.sub(r"https?://[^\s]+", "[source-url-redacted]", value)
    value = re.sub(r"(?i)(?:cookie|bearer|api[_ -]?key)[=: ]+[^\s;]+", "[secret-redacted]", value)
    return value[:600]


class LiveTaskProcessor:
    def __init__(self, factory: sessionmaker[Session], data_dir: Path,
                 provider: CollectionProvider, transcriber, generator, downloader=download_verified_media,
                 provenance="real_model"):
        self.factory = factory
        self.data_dir = data_dir
        self.provider = provider
        self.transcriber = transcriber
        self.generator = generator
        if provenance not in ("real_model", "test_fixture"):
            raise ValueError("Unsupported provenance")
        self.downloader = downloader
        self.provenance = provenance

    def change_phase(self, task_id: str, phase: str):
        with self.factory.begin() as session:
            task = session.get(TaskRecord, task_id)
            if task:
                task.phase = phase

    def associate(self, task_id: str, candidate: VideoCandidate) -> tuple[str, str]:
        if not re.fullmatch(r"\d{8,25}", candidate.platform_video_id):
            raise ValueError("平台视频ID格式不合法")
        with self.factory.begin() as session:
            video = session.scalar(select(VideoRecord).where(
                VideoRecord.platform == "douyin", VideoRecord.platform_video_id == candidate.platform_video_id,
            ))
            if video is None:
                video = VideoRecord(platform="douyin", platform_video_id=candidate.platform_video_id,
                                    author_platform_id=candidate.author_platform_id,
                                    title=candidate.title, source_url=candidate.source_url,
                                    published_at=(dt.datetime.fromtimestamp(candidate.published_at_unix, dt.timezone.utc)
                                                  if candidate.published_at_unix is not None else None))
                session.add(video)
                session.flush()
            if video.author_platform_id != candidate.author_platform_id:
                raise ValueError("视频作者和数据库中的平台作者不一致")
            if video.published_at is None and candidate.published_at_unix is not None:
                video.published_at = dt.datetime.fromtimestamp(candidate.published_at_unix, dt.timezone.utc)
            task_video = session.scalar(select(TaskVideoRecord).where(
                TaskVideoRecord.task_id == task_id, TaskVideoRecord.video_id == video.id,
            ))
            if task_video is None:
                task_video = TaskVideoRecord(task_id=task_id, video_id=video.id)
                session.add(task_video)
                session.flush()
            return video.id, task_video.id

    def stage(self, task_id: str, task_video_id: str, phase: str, status: str,
              error: Exception | None = None):
        with self.factory.begin() as session:
            assoc = session.get(TaskVideoRecord, task_video_id)
            assoc.phase = phase
            assoc.status = status
            assoc.error_code = type(error).__name__[:100] if error else None
            assoc.error_message = safe_error(error) if error else None
            task = session.get(TaskRecord, task_id)
            task.phase = phase
            associated = list(session.scalars(select(TaskVideoRecord).where(TaskVideoRecord.task_id == task_id)))
            task.success_count = sum(x.status == "completed" for x in associated)
            task.failure_count = sum(x.status == "failed" for x in associated)
            task.no_speech_count = sum(x.status == "no_speech" for x in associated)

    async def resolve(self, task: TaskRecord) -> tuple[str, list[VideoCandidate], str]:
        target = ParsedLink(kind=task.source_kind, url=task.source_url,
                            platform_id=task.platform_id)
        if target.kind == "short":
            target = await resolve_short_link(target.url)
            with self.factory.begin() as session:
                record = session.get(TaskRecord, task.id)
                record.source_url = target.url
                record.source_kind = target.kind
                record.platform_id = target.platform_id
                if target.kind == "video":
                    record.max_videos = 1
        if target.kind == "video":
            video = await self.provider.video_detail(target.url)
            return video.author_platform_id, [video], "single_video"
        creator_id = await self.provider.profile_id(target.url)
        if not creator_id:
            raise RuntimeError("未得到可核实的作者平台ID")
        if target.platform_id and creator_id != target.platform_id:
            raise RuntimeError("作者平台ID和主页链接不一致")
        works = await self.provider.author_works(creator_id, task.max_videos)
        return creator_id, works.videos[:task.max_videos], works.stop_reason

    async def __call__(self, task_id: str, control: WorkerControl):
        with self.factory() as session:
            task = session.get(TaskRecord, task_id)
            if not task:
                raise ValueError("Task record disappeared")
            # Detached scalar data only; no ORM references retained across awaits.
            task_snapshot = TaskRecord(
                id=task.id, source_kind=task.source_kind, source_url=task.source_url,
                platform_id=task.platform_id, max_videos=task.max_videos,
            )
        await control.checkpoint()
        self.change_phase(task_id, "resolve_creator")
        try:
            creator_id, candidates, stop_reason = await self.resolve(task_snapshot)
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            if status in (401, 403, 429):
                raise PrerequisiteMissing(
                    "DOUYIN_ACCESS_DENIED",
                    f"链接已识别，但抖音采集组件的请求被平台拒绝（HTTP {status}）。"
                    "请检查链接在抖音中是否可访问、本机网络及采集组件；如需登录，可在设置中提供自己的 Cookie 文件。"
                    "处理后点击恢复重试，当前尚未取得可分析的视频。",
                ) from exc
            raise
        with self.factory.begin() as session:
            task = session.get(TaskRecord, task_id)
            task.platform_id = creator_id
            task.stop_reason = stop_reason
        if not candidates:
            raise PrerequisiteMissing("NO_ACCESSIBLE_WORKS", "无法获取公开且有权处理的作品列表")
        self.change_phase(task_id, "download_media")
        for candidate in candidates:
            await control.checkpoint()
            if candidate.author_platform_id != creator_id:
                raise ValueError("平台响应包含不同作者的作品，终止批量任务")
            video_id, assoc_id = self.associate(task_id, candidate)
            try:
                self.stage(task_id, assoc_id, "download_media", "running")
                destination = self.data_dir / "media" / "douyin" / f"{candidate.platform_video_id}.mp4"
                valid_existing = False
                if destination.is_file():
                    with self.factory() as session:
                        saved = session.get(VideoRecord, video_id)
                        if saved.media_sha256:
                            try:
                                await asyncio.to_thread(probe_media, destination)
                                valid_existing = (await asyncio.to_thread(sha256_file, destination)) == saved.media_sha256
                            except Exception:
                                pass
                if not valid_existing:
                    if not candidate.media_url:
                        raise RuntimeError("作品详情没有获准下载的媒体地址")
                    await self.downloader(candidate.media_url, destination)
                await control.checkpoint()
                self.stage(task_id, assoc_id, "transcribe_and_analyze", "running")
                result = await analyze_media(
                    file_path=destination, factory=self.factory,
                    scratch_dir=self.data_dir / "scratch",
                    platform="douyin", platform_video_id=candidate.platform_video_id,
                    author_platform_id=creator_id, title=candidate.title,
                    source_url=candidate.source_url, transcriber=self.transcriber,
                    generator=self.generator, provenance=self.provenance,
                )
                await control.checkpoint()
                if result.status == "no_speech":
                    self.stage(task_id, assoc_id, "transcription", "no_speech")
                else:
                    self.stage(task_id, assoc_id, "analysis", "completed")
            except Exception as exc:
                # User pauses/cancels propagate; do not convert them to an item failure.
                from .worker import TaskPaused, TaskCancelled
                if isinstance(exc, (TaskPaused, TaskCancelled, asyncio.CancelledError)):
                    raise
                self.stage(task_id, assoc_id, "processing_failed", "failed", exc)
        await control.checkpoint()
        with self.factory() as session:
            completed_task = session.get(TaskRecord, task_id)
            total_success = completed_task.success_count
            total_no_speech = completed_task.no_speech_count
            is_profile = completed_task.source_kind == "profile"
        if total_success == 0 and total_no_speech == 0:
            raise RuntimeError("所有候选视频均未能完成分析，详见每条视频的错误记录")
        if is_profile and total_success:
            with self.factory() as session:
                count = session.get(TaskRecord, task_id).success_count
            if count:
                self.change_phase(task_id, "creator_report")
                try:
                    with self.factory.begin() as session:
                        build_creator_report(session, task_id)
                except ReportNotReady as exc:
                    raise RuntimeError("跨视频证据报告生成失败") from exc
        self.change_phase(task_id, "finished")


def build_opt_in_live_processor(factory: sessionmaker[Session], data_dir: Path, configuration=None):
    """Explicit local opt-in; never loads a cookie from a browser or bundles it."""
    if configuration is None:
        from .runtime_settings import load_runtime_settings
        configuration = load_runtime_settings(data_dir)
    if not configuration.enable_live:
        raise RuntimeError("Live collector was not explicitly enabled")
    from .chatgpt_plan import make_generator
    generator = make_generator(configuration, data_dir)
    cookie_file = configuration.cookie_file
    cookie = Path(cookie_file).read_text(encoding="utf8").strip() if cookie_file else None
    return LiveTaskProcessor(
        factory, data_dir, F2Collector(cookie), FasterWhisperTranscriber(configuration.whisper_model),
        generator,
    )
