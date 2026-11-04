"""Loopback-only FastAPI application; all APIs require per-process token."""

from contextlib import asynccontextmanager
from pathlib import Path
import secrets

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import build_session_factory
from .links import InvalidDouyinLink, parse_douyin_input
from .models import TaskRecord  # registers task table
from . import models  # noqa: F401; registers evidence tables
from .schemas import CreateTask, HealthView, TaskView
from .worker import Processor, SingleWorker, apply_action, missing_collector


def create_app(data_dir: Path, token: str, processor: Processor = missing_collector) -> FastAPI:
    if len(token) < 16:
        raise ValueError("Unsafe short backend token")
    factory, engine = build_session_factory(data_dir)
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

    app.include_router(api)
    app.state.worker = worker
    app.state.session_factory = factory
    return app
