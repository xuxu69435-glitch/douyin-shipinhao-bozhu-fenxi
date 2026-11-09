"""Explicit local-video entry using the same real analysis pipeline as collection."""

import shutil
from pathlib import Path

from .insights import OpenAICompatibleInsightGenerator
from .models import TaskRecord, TaskVideoRecord
from .pipeline import analyze_media, sha256_file
from .transcription import FasterWhisperTranscriber
from .worker import PrerequisiteMissing


def import_local_video(path: Path, data_dir: Path):
    if not path.is_file() or path.suffix.lower() not in {".mp4", ".mov", ".mkv", ".webm", ".avi"}:
        raise ValueError("请选择存在的 MP4、MOV、MKV、WebM 或 AVI 视频")
    if not 0 < path.stat().st_size <= 500_000_000:
        raise ValueError("视频文件须大于 0 且不超过 500 MB")
    fingerprint = sha256_file(path)
    destination = data_dir / "media" / "local" / f"{fingerprint}{path.suffix.lower()}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        temporary = destination.with_suffix(destination.suffix + ".part")
        try:
            shutil.copyfile(path, temporary)
            if sha256_file(temporary) != fingerprint:
                raise ValueError("视频在导入期间发生变化，请重试")
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
    return destination, fingerprint


async def run_local_task(task_id, control, factory, data_dir, configuration):
    from .chatgpt_plan import make_generator
    generator = make_generator(configuration, data_dir)
    await control.checkpoint()
    with factory.begin() as session:
        task = session.get(TaskRecord, task_id)
        task.phase = "local_video_analysis"
        path = Path(task.input_text)
        title = task.source_url
        fingerprint = task.platform_id
    result = await analyze_media(
        file_path=path, factory=factory, scratch_dir=data_dir / "scratch",
        platform="local", platform_video_id=fingerprint,
        author_platform_id="local-file-no-platform-author", title=title,
        source_url=f"local://sha256/{fingerprint}",
        transcriber=FasterWhisperTranscriber(configuration.whisper_model),
        generator=generator,
    )
    await control.checkpoint()
    with factory.begin() as session:
        task = session.get(TaskRecord, task_id)
        link = session.query(TaskVideoRecord).filter_by(task_id=task_id, video_id=result.video_id).first()
        if link is None:
            link = TaskVideoRecord(task_id=task_id, video_id=result.video_id)
            session.add(link)
        link.phase = "finished"
        link.status = "completed" if result.status == "analyzed" else "no_speech"
        task.success_count = int(result.status == "analyzed")
        task.no_speech_count = int(result.status == "no_speech")
        task.failure_count = 0
        task.phase = "finished"
        task.stop_reason = "local_video"
