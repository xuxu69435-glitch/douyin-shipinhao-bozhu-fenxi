"""Loopback-only FastAPI application; all APIs require per-process token."""

from contextlib import asynccontextmanager
from pathlib import Path
import secrets
import hashlib
import hmac
import time
import uuid

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import build_session_factory
from .links import InvalidDouyinLink, parse_douyin_input
from .models import TaskRecord, TaskVideoRecord, VideoRecord, VideoAnalysis, TranscriptSegment, CreatorReport  # registers tables
from . import models  # noqa: F401; registers evidence tables
from .schemas import CreateTask, HealthView, TaskView, VideoView, SegmentView, SubtitleExport
from .worker import Processor, SingleWorker, apply_action, missing_collector, PrerequisiteMissing
from .evidence import segments_for_version, subtitles_text, assert_analysis_integrity, assert_report_integrity
from .reporting import build_creator_report, export_report_markdown, ReportNotReady
import json


def create_app(data_dir: Path, token: str, processor: Processor = missing_collector,
               enable_live: bool = False) -> FastAPI:
    if len(token) < 16:
        raise ValueError("Unsafe short backend token")
    factory, engine = build_session_factory(data_dir)
    if enable_live:
        from .job_processor import build_opt_in_live_processor
        try:
            processor = build_opt_in_live_processor(factory, data_dir)
        except (PrerequisiteMissing, OSError, RuntimeError, ValueError) as exc:
            # Preserve backend diagnostics and task history even when local config
            # cannot start the real pipeline. Never silently run synthetic data.
            explanation = str(exc)
            async def config_blocked(_task_id, _control):
                raise PrerequisiteMissing("LIVE_PIPELINE_CONFIG_BLOCKED", explanation)
            processor = config_blocked
    worker = SingleWorker(factory, processor)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await worker.start()
        try:
            yield
        finally:
            await worker.stop()
            engine.dispose()

    app = FastAPI(title="Douyin Analyst", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://tauri.localhost", "tauri://localhost", "http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["X-Analyst-Token", "Content-Type"],
    )

    def require_token(x_analyst_token: str | None = Header(default=None)):
        if not x_analyst_token or not secrets.compare_digest(x_analyst_token, token):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid desktop session token")

    api = APIRouter(prefix="/api", dependencies=[Depends(require_token)])

    @api.get("/health", response_model=HealthView)
    def health():
        return HealthView()

    @api.post("/tasks", response_model=TaskView, status_code=status.HTTP_201_CREATED)
    def create_task(body: CreateTask):
        try:
            target = parse_douyin_input(body.input_text)
        except InvalidDouyinLink as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        limit = 1 if target.kind == "video" else body.max_videos
        with factory.begin() as session:
            task = TaskRecord(
                input_text=body.input_text,
                source_url=target.url,
                source_kind=target.kind,
                platform_id=target.platform_id,
                max_videos=limit,
            )
            session.add(task)
            session.flush()
            result = TaskView.model_validate(task)
        worker.enqueue(result.id)
        return result

    @api.get("/tasks", response_model=list[TaskView])
    def list_tasks():
        with factory() as session:
            return [TaskView.model_validate(x) for x in session.scalars(select(TaskRecord).order_by(TaskRecord.created_at.desc()).limit(200))]

    @api.get("/tasks/{task_id}", response_model=TaskView)
    def get_task(task_id: str):
        with factory() as session:
            task = session.get(TaskRecord, task_id)
            if task is None:
                raise HTTPException(status_code=404, detail="task not found")
            return TaskView.model_validate(task)

    @api.post("/tasks/{task_id}/{action}", response_model=TaskView)
    def change_task(task_id: str, action: str):
        if action not in {"pause", "resume", "cancel"}:
            raise HTTPException(status_code=404, detail="action not found")
        try:
            task = apply_action(factory, task_id, action)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if task is None:
            raise HTTPException(status_code=404, detail="task not found")
        if action == "resume":
            worker.enqueue(task.id)
        return TaskView.model_validate(task)

    @api.get("/tasks/{task_id}/videos", response_model=list[VideoView])
    def task_videos(task_id: str):
        with factory() as session:
            if session.get(TaskRecord, task_id) is None:
                raise HTTPException(status_code=404, detail="task not found")
            rows = session.scalars(select(VideoRecord).join(
                TaskVideoRecord, TaskVideoRecord.video_id == VideoRecord.id
            ).where(TaskVideoRecord.task_id == task_id).limit(100)).all()
            return [VideoView.model_validate(x) for x in rows]

    @api.get("/videos", response_model=list[VideoView])
    def list_videos():
        with factory() as session:
            rows = session.scalars(select(VideoRecord).order_by(VideoRecord.id).limit(200)).all()
            return [VideoView.model_validate(x) for x in rows]

    @api.get("/videos/{video_id}")
    def video_detail(video_id: str):
        with factory() as session:
            video = session.get(VideoRecord, video_id)
            if video is None:
                raise HTTPException(status_code=404, detail="video not found")
            analyses = list(session.scalars(select(VideoAnalysis).where(
                VideoAnalysis.video_id == video_id
            ).order_by(VideoAnalysis.created_at.desc())))
            versions = list(session.scalars(select(TranscriptSegment.transcript_version).where(
                TranscriptSegment.video_id == video_id
            ).distinct()))
            return {
                "video": VideoView.model_validate(video),
                "transcript_versions": versions,
                "analyses": [{"analysis_version": x.analysis_version,
                              "transcript_version": x.transcript_version,
                              "model_id": x.model_id,
                              "created_at": x.created_at.isoformat()} for x in analyses],
            }

    @api.get("/videos/{video_id}/transcripts/{version}", response_model=list[SegmentView])
    def video_transcript(video_id: str, version: str):
        with factory() as session:
            if session.get(VideoRecord, video_id) is None:
                raise HTTPException(status_code=404, detail="video not found")
            rows = segments_for_version(session, video_id, version)
            if not rows:
                raise HTTPException(status_code=404, detail="transcript version not found")
            return [SegmentView.model_validate(x) for x in rows]

    @api.get("/videos/{video_id}/subtitles/{version}/{fmt}", response_model=SubtitleExport)
    def video_subtitle_export(video_id: str, version: str, fmt: str):
        if fmt not in {"srt", "vtt"}:
            raise HTTPException(status_code=404, detail="unsupported subtitle format")
        with factory() as session:
            if session.get(VideoRecord, video_id) is None:
                raise HTTPException(status_code=404, detail="video not found")
            rows = segments_for_version(session, video_id, version)
            if not rows:
                raise HTTPException(status_code=404, detail="transcript version not found")
            return SubtitleExport(
                filename=f"{video_id}-{version}.{fmt}",
                content=subtitles_text(rows, fmt), format=fmt,
            )

    @api.get("/videos/{video_id}/analyses/{version}")
    def video_analysis(video_id: str, version: str):
        with factory() as session:
            row = session.scalar(select(VideoAnalysis).where(
                VideoAnalysis.video_id == video_id, VideoAnalysis.analysis_version == version,
            ))
            if row is None:
                raise HTTPException(status_code=404, detail="analysis version not found")
            try:
                assert_analysis_integrity(session, row)
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            return row.result

    @api.get("/videos/{video_id}/evidence/{version}/{segment_id}", response_model=SegmentView)
    def source_evidence(video_id: str, version: str, segment_id: int):
        with factory() as session:
            row = session.scalar(select(TranscriptSegment).where(
                TranscriptSegment.video_id == video_id,
                TranscriptSegment.transcript_version == version,
                TranscriptSegment.segment_id == segment_id,
            ))
            if row is None:
                raise HTTPException(status_code=404, detail="evidence segment not found")
            return SegmentView.model_validate(row)

    @api.post("/tasks/{task_id}/reports/build")
    def build_report(task_id: str):
        try:
            with factory.begin() as session:
                report = build_creator_report(session, task_id)
                return {"id": report.id, "task_id": task_id,
                        "report_version": report.report_version,
                        "evidence_version": report.evidence_version}
        except (ReportNotReady, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @api.get("/tasks/{task_id}/reports")
    def list_reports(task_id: str):
        with factory() as session:
            if session.get(TaskRecord, task_id) is None:
                raise HTTPException(status_code=404, detail="task not found")
            rows = session.scalars(select(CreatorReport).where(
                CreatorReport.task_id == task_id
            ).order_by(CreatorReport.created_at.desc())).all()
            return [{"id": x.id, "task_id": task_id,
                     "report_version": x.report_version,
                     "evidence_version": x.evidence_version,
                     "created_at": x.created_at.isoformat()} for x in rows]

    @api.get("/reports/{report_id}")
    def get_report(report_id: str):
        with factory() as session:
            row = session.get(CreatorReport, report_id)
            if row is None:
                raise HTTPException(status_code=404, detail="report not found")
            try:
                assert_report_integrity(session, row.result)
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            return row.result

    @api.get("/reports/{report_id}/export/{fmt}")
    def export_report(report_id: str, fmt: str):
        if fmt not in {"json", "md"}:
            raise HTTPException(status_code=404, detail="unsupported export")
        with factory() as session:
            row = session.get(CreatorReport, report_id)
            if row is None:
                raise HTTPException(status_code=404, detail="report not found")
            try:
                assert_report_integrity(session, row.result)
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            content = (json.dumps(row.result, ensure_ascii=False, indent=2)
                       if fmt == "json" else export_report_markdown(row.result))
            return {"filename": f"report-{row.task_id}-{row.report_version}.{fmt}",
                    "format": fmt, "content": content}

    @app.get("/media/{video_id}")
    def play_media(video_id: str, expires: int = Query(...), signature: str = Query(...)):
        # HTML5 video cannot send custom auth headers. Grant playback through a
        # short-lived per-video HMAC signed by Rust; never include the master token
        # in a URL or reveal arbitrary filesystem paths to the renderer.
        try:
            uuid.UUID(video_id)
        except ValueError:
            raise HTTPException(status_code=404, detail="invalid video ID")
        now = int(time.time())
        if expires < now or expires > now + 600:
            raise HTTPException(status_code=403, detail="media ticket expired")
        expected = hmac.new(token.encode(), f"{video_id}:{expires}".encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise HTTPException(status_code=403, detail="invalid media ticket")
        with factory() as session:
            video = session.get(VideoRecord, video_id)
            if not video or not video.media_path:
                raise HTTPException(status_code=404, detail="video media unavailable")
            path = Path(video.media_path)
            if not path.is_file() or path.stat().st_size == 0:
                raise HTTPException(status_code=404, detail="media file unavailable")
            return FileResponse(path, media_type="video/mp4")

    app.include_router(api)
    app.state.worker = worker
    app.state.session_factory = factory
    return app
