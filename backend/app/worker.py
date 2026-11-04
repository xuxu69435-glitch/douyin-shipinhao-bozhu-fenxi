"""One worker; persisted state transitions; honest R0 blocker until live collector is validated."""

import asyncio
from collections.abc import Awaitable, Callable
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .models import TaskRecord, AnalysisRun


class PrerequisiteMissing(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class TaskPaused(Exception):
    pass


class TaskCancelled(Exception):
    pass


class WorkerControl:
    def __init__(self, factory: sessionmaker[Session], task_id: str):
        self.factory = factory
        self.task_id = task_id

    async def checkpoint(self):
        with self.factory() as session:
            task = session.get(TaskRecord, self.task_id)
            if task is None or task.status == "cancelling":
                raise TaskCancelled()
            if task.status == "pausing":
                raise TaskPaused()
        await asyncio.sleep(0)


Processor = Callable[[str, WorkerControl], Awaitable[None]]


async def missing_collector(_task_id: str, _control: WorkerControl):
    raise PrerequisiteMissing(
        "R0_LIVE_COLLECTION_NOT_VERIFIED",
        "当前仅完成工程骨架。抖音作者识别、第二页和真实媒体尚未通过合法的实测验收；不会虚构采集成功。",
    )


class SingleWorker:
    def __init__(self, factory: sessionmaker[Session], processor: Processor = missing_collector):
        self.factory = factory
        self.processor = processor
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.runner: asyncio.Task | None = None
        self.loop: asyncio.AbstractEventLoop | None = None

    async def start(self):
        if self.runner is not None:
            return
        self.loop = asyncio.get_running_loop()
        with self.factory.begin() as session:
            for run in session.scalars(select(AnalysisRun).where(AnalysisRun.status == "running")):
                run.status = "interrupted"
                run.error_code = "InterruptedByRestart"
            for task in session.scalars(select(TaskRecord).where(TaskRecord.status.in_(["running", "cancelling", "pausing"]))):
                task.status = {"running": "queued", "cancelling": "cancelled", "pausing": "paused"}[task.status]
                task.stop_reason = "interrupted_by_restart"
            # Flush status recovery before collecting tasks to requeue.
            session.flush()
            queued = [task.id for task in session.scalars(select(TaskRecord).where(TaskRecord.status == "queued").order_by(TaskRecord.created_at))]
        self.runner = asyncio.create_task(self._run(), name="single-douyin-worker")
        for task_id in queued:
            self.enqueue(task_id)

    def enqueue(self, task_id: str):
        # FastAPI sync endpoints execute in AnyIO worker threads. Never mutate
        # an asyncio.Queue from those threads: put_nowait might not wake its waiter.
        if self.loop is None or not self.loop.is_running():
            raise RuntimeError("single worker event loop has not started")
        self.loop.call_soon_threadsafe(self.queue.put_nowait, task_id)

    async def stop(self):
        if self.runner is None:
            return
        self.runner.cancel()
        try:
            await self.runner
        except asyncio.CancelledError:
            pass
        self.runner = None
        self.loop = None

    async def _run(self):
        while True:
            task_id = await self.queue.get()
            try:
                with self.factory.begin() as session:
                    task = session.get(TaskRecord, task_id)
                    if task is None or task.status != "queued":
                        continue
                    task.status = "running"
                    task.phase = "collector"
                    task.error_code = None
                    task.error_message = None
                await self.processor(task_id, WorkerControl(self.factory, task_id))
                with self.factory.begin() as session:
                    task = session.get(TaskRecord, task_id)
                    if task:
                        task.status = {"cancelling": "cancelled", "pausing": "paused"}.get(task.status, "completed")
                        if task.status == "cancelled":
                            task.stop_reason = "user_cancelled"
                        elif task.status == "paused":
                            task.stop_reason = "user_paused"
                        elif not task.stop_reason:
                            task.stop_reason = "finished"
            except TaskPaused:
                self._set_state(task_id, "paused", "user_paused")
            except TaskCancelled:
                self._set_state(task_id, "cancelled", "user_cancelled")
            except PrerequisiteMissing as exc:
                self._set_state(task_id, "blocked", "requires_live_validation", exc.code, str(exc))
            except asyncio.CancelledError:
                self._set_state(task_id, "queued", "interrupted_by_shutdown")
                raise
            except Exception as exc:
                self._set_state(task_id, "failed", "processor_exception", type(exc).__name__, str(exc))
            finally:
                self.queue.task_done()

    def _set_state(self, task_id: str, status: str, stop_reason: str, code: str | None = None, message: str | None = None):
        with self.factory.begin() as session:
            task = session.get(TaskRecord, task_id)
            if task:
                task.status = status
                task.stop_reason = stop_reason
                task.error_code = code
                task.error_message = message


def apply_action(factory: sessionmaker[Session], task_id: str, action: str) -> TaskRecord | None:
    with factory.begin() as session:
        task = session.get(TaskRecord, task_id)
        if task is None:
            return None
        permitted = {
            "pause": {"queued", "running", "blocked"},
            "resume": {"paused", "blocked", "failed"},
            "cancel": {"queued", "running", "paused", "blocked", "failed"},
        }
        if task.status not in permitted[action]:
            raise ValueError(f"{action} not permitted from {task.status}")
        if action == "pause":
            task.status = "pausing" if task.status == "running" else "paused"
        elif action == "resume":
            task.status = "queued"
            task.stop_reason = None
        else:
            task.status = "cancelling" if task.status == "running" else "cancelled"
            if task.status == "cancelled":
                task.stop_reason = "user_cancelled"
        session.flush()
        session.expunge(task)
        return task
