"""Opt-in real profile acceptance using the configured ChatGPT plan, never API keys."""

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import select

from app.browser_collector import BrowserCollector
from app.chatgpt_plan import ChatGPTPlanBridge, make_generator
from app.database import build_session_factory
from app.douyin_session import load_cookie
from app.evidence import assert_analysis_integrity, assert_report_integrity, segments_for_version, subtitles_text
from app.job_processor import LiveTaskProcessor
from app.links import parse_douyin_input, resolve_short_link
from app.models import AnalysisRun, CreatorReport, TaskRecord, TaskVideoRecord, VideoAnalysis, VideoRecord
from app.reporting import export_report_markdown
from app.runtime_settings import load_runtime_settings
from app.transcription import FasterWhisperTranscriber
from app.worker import SingleWorker, apply_action


async def run(args):
    configuration = load_runtime_settings(args.config_dir, include_api_key=False)
    if configuration.model_provider != "chatgpt" or not configuration.CHATGPT_MODEL:
        raise ValueError("此验收入口只使用已配置的 ChatGPT 套餐模型，请先在软件设置中选择并授权")
    if not configuration.enable_live or configuration.collector_provider != "browser":
        raise ValueError("请先在软件中启用浏览器采集并保存配置")
    if args.data_dir.resolve() == args.config_dir.resolve():
        raise ValueError("验收数据目录须与已有配置目录分开，以保留原有任务")
    state = await asyncio.to_thread(ChatGPTPlanBridge(args.config_dir).status)
    if state.get("status") != "connected" or not state.get("sharing"):
        raise ValueError("请在软件中完成 ChatGPT 登录及套餐用量授权")
    link = parse_douyin_input(args.input)
    if link.kind == "short":
        link = await resolve_short_link(link.url)
    if link.kind != "profile":
        raise ValueError("此入口需要博主主页或主页分享文本")
    cookie = load_cookie(args.config_dir, configuration.cookie_file)
    factory, engine = build_session_factory(args.data_dir)
    worker = SingleWorker(factory, LiveTaskProcessor(
        factory, args.data_dir, BrowserCollector(cookie),
        FasterWhisperTranscriber(configuration.whisper_model),
        make_generator(configuration, args.config_dir),
    ))
    started = time.monotonic()
    try:
        with factory.begin() as session:
            if args.resume_task:
                task = session.get(TaskRecord, args.resume_task)
                if task is None or task.source_url != link.url or task.max_videos != args.max_videos:
                    raise ValueError("恢复任务的主页或样本数量不一致")
                task_id = task.id
                resume_status = task.status
            else:
                task = TaskRecord(input_text=link.url, source_url=link.url, source_kind="profile",
                                  platform_id=link.platform_id, max_videos=args.max_videos, status="queued")
                session.add(task)
                session.flush()
                task_id = task.id
        if args.resume_task and resume_status != "queued":
            apply_action(factory, task_id, "resume")
        await worker.start()
        previous = None
        while True:
            with factory() as session:
                task = session.get(TaskRecord, task_id)
                progress = {"task_id": task_id, "status": task.status, "phase": task.phase,
                            "success": task.success_count, "failed": task.failure_count,
                            "no_speech": task.no_speech_count}
            if progress != previous:
                print(json.dumps(progress, ensure_ascii=False), flush=True)
                previous = progress
            if progress["status"] in {"completed", "failed", "blocked", "paused", "cancelled"}:
                break
            await asyncio.sleep(2)

        exports = args.data_dir / "exports"
        exports.mkdir(parents=True, exist_ok=True)
        with factory() as session:
            task = session.get(TaskRecord, task_id)
            linked = list(session.execute(select(VideoRecord, TaskVideoRecord).join(
                TaskVideoRecord, TaskVideoRecord.video_id == VideoRecord.id
            ).where(TaskVideoRecord.task_id == task_id)).all())
            runs = list(session.scalars(select(AnalysisRun).where(
                AnalysisRun.video_id.in_([video.id for video, _ in linked]))))
            samples, segment_count, reference_count = [], 0, 0
            for video, association in linked:
                analysis = session.scalar(select(VideoAnalysis).where(VideoAnalysis.video_id == video.id)
                                          .order_by(VideoAnalysis.created_at.desc()))
                sample = {"platform_video_id": video.platform_video_id, "status": association.status,
                          "error_code": association.error_code}
                if analysis and association.status == "completed":
                    assert_analysis_integrity(session, analysis)
                    segments = segments_for_version(session, video.id, analysis.transcript_version)
                    segment_count += len(segments)
                    refs = list(analysis.result.get("summary_evidence", []))
                    for name in ("key_claims", "explicitly_stated_preferences", "discussed_entities"):
                        refs.extend(ref for item in analysis.result.get(name, []) for ref in item.get("evidence", []))
                    reference_count += len(refs)
                    sample.update(segment_count=len(segments), evidence_references=len(refs),
                                  transcript_version=analysis.transcript_version, analysis_version=analysis.analysis_version)
                    for fmt in ("srt", "vtt"):
                        (exports / f"{video.platform_video_id}.{fmt}").write_text(subtitles_text(segments, fmt), encoding="utf8")
                samples.append(sample)
            report = session.scalar(select(CreatorReport).where(CreatorReport.task_id == task_id)
                                    .order_by(CreatorReport.created_at.desc()))
            if report:
                assert_report_integrity(session, report.result)
                (exports / "creator-report.json").write_text(json.dumps(report.result, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
                (exports / "creator-report.md").write_text(export_report_markdown(report.result), encoding="utf8")
            result = {
                "test_type": "REAL_DOUYIN_PROFILE_CHATGPT_ANALYSIS", "task_id": task_id,
                "model_provider": "official_chatgpt_plan", "model": configuration.CHATGPT_MODEL,
                "api_key_loaded": configuration.OPENAI_API_KEY is not None,
                "api_key_used": False,
                "requested_limit": args.max_videos, "status": task.status,
                "success_count": task.success_count, "failure_count": task.failure_count,
                "no_speech_count": task.no_speech_count, "stop_reason": task.stop_reason,
                "error_code": task.error_code, "report_saved": report is not None,
                "report_version": report.report_version if report else None,
                "evidence_revalidated": bool(segment_count and reference_count), "segment_count": segment_count,
                "evidence_references": reference_count, "model_requests": sum(run.metrics.get("requests", 0) for run in runs),
                "analysis_run_states": [run.status for run in runs],
                "analysis_run_providers": sorted({run.metrics.get("provider", "unknown") for run in runs}),
                "elapsed_seconds": round(time.monotonic() - started, 2), "videos": samples,
            }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
        print(json.dumps(result, ensure_ascii=False), flush=True)
        return 0 if result["status"] == "completed" and result["failure_count"] == 0 and result["report_saved"] else 1
    finally:
        await worker.stop()
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="author profile or original profile share text")
    parser.add_argument("--max-videos", type=int, choices=(10, 30), default=10)
    parser.add_argument("--config-dir", type=Path, default=Path(os.environ.get("LOCALAPPDATA", ".")) / "com.douyinanalyst.desktop")
    parser.add_argument("--data-dir", type=Path, required=True, help="separate persistent acceptance data directory")
    parser.add_argument("--output", type=Path, required=True, help="credential-free acceptance JSON")
    parser.add_argument("--resume-task", help="resume a paused, blocked or failed task in the same data directory")
    args = parser.parse_args()
    try:
        return asyncio.run(asyncio.wait_for(run(args), timeout=7200))
    except KeyboardInterrupt:
        print("已中断；阶段结果保留在验收数据目录。", file=sys.stderr)
        return 130
    except Exception as exc:
        # Exception text can contain credential paths or signed URLs. Keep type only.
        print(f"验收未完成（{type(exc).__name__}）；请检查已保存的任务阶段和模型授权。", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
