"""Launch the real desktop twice; verify persisted state and process-tree exit.

Only a synthetic local clip is prepared. No platform or paid model is called.
"""

import argparse
import ctypes
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.database import build_session_factory
from app.models import VideoRecord


def process_alive(pid):
    if not pid:
        return False
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.OpenProcess(0x1000, 0, pid)
    if not handle:
        return False
    exit_code = ctypes.c_ulong()
    kernel.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    result = kernel.GetExitCodeProcess(handle, ctypes.byref(exit_code))
    kernel.CloseHandle(handle)
    return bool(result and exit_code.value == 259)


def run(executable, output):
    work = ROOT / '.media' / 'desktop-smoke'
    data = work / 'data'
    work.mkdir(parents=True, exist_ok=True)
    media = work / 'synthetic-video.mp4'
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i',
                    'color=c=black:s=128x96:r=4:d=1', '-c:v', 'mpeg4', str(media)],
                   check=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    factory, engine = build_session_factory(data)
    try:
        with factory.begin() as session:
            video = session.query(VideoRecord).filter_by(platform='test_fixture', platform_video_id='desktop-smoke').first()
            if video is None:
                video = VideoRecord(platform='test_fixture', platform_video_id='desktop-smoke',
                    author_platform_id='fixture', title='合成本地媒体测试样本', source_url='fixture://desktop-smoke',
                    media_path=str(media), processing_status='media_ready')
                session.add(video)
                session.flush()
            video_id = video.id
    finally:
        engine.dispose()
    reports = []
    for iteration in range(2):
        report_path = work / f'host-{iteration}.json'
        report_path.unlink(missing_ok=True)
        env = {**os.environ, 'ANALYST_SMOKE_DATA_DIR': str(data), 'ANALYST_SMOKE_REPORT': str(report_path),
               'ANALYST_SMOKE_VIDEO_ID': video_id, 'ANALYST_ENABLE_LIVE': '0'}
        env['PATH'] = str(Path(os.environ['SystemRoot']) / 'System32')
        with (work / f'host-{iteration}.log').open('wb') as log:
            process = subprocess.Popen([str(executable), '--smoke-test'], env=env, stdout=log, stderr=log,
                                       creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                process.wait(timeout=120)
            except subprocess.TimeoutExpired:
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True,
                               creationflags=subprocess.CREATE_NO_WINDOW)
                raise RuntimeError('Desktop did not finish the smoke test; inspect .media/desktop-smoke logs')
        if not report_path.exists():
            raise RuntimeError(f'Desktop produced no smoke report (exit {process.returncode}); inspect {work}')
        report = json.loads(report_path.read_text(encoding='utf8'))
        assert report.get('ok'), report
        assert process.returncode == 0, process.returncode
        assert not process_alive(report.get('sidecar_pid')), 'sidecar process remained after desktop exit'
        assert not process_alive(report.get('backend_pid')), 'backend process remained after desktop exit'
        report['process_tree_terminated'] = True
        reports.append(report)
    assert reports[1]['previous_task_count'] > reports[0]['previous_task_count']
    result = {'type': 'WINDOWS_DESKTOP_LIFECYCLE_SMOKE', 'tauri_process_lifecycle_tested': True,
              'persisted_history_after_restart': True, 'runs': reports}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8', newline='\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('executable', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'docs/testing/desktop-smoke.json')
    arguments = parser.parse_args()
    run(arguments.executable.resolve(strict=True), arguments.output)
