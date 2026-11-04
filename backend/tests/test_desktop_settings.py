import os
import datetime as dt
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.models import TaskRecord, VideoRecord
from app.runtime_settings import load_runtime_settings
from app.job_processor import LiveTaskProcessor
from app.collector import VideoCandidate


def test_settings_key_is_private_persistent_and_clearable(tmp_path, auth):
    app = create_app(tmp_path, auth['X-Analyst-Token'])
    with TestClient(app) as client:
        assert client.get('/api/settings').status_code == 401
        body = {'OPENAI_BASE_URL': 'https://example.org/v1/', 'OPENAI_MODEL': 'test-model',
                'OPENAI_API_KEY': 'fixture-api-secret', 'enable_live': False}
        saved = client.post('/api/settings', headers=auth, json=body)
        assert saved.status_code == 200, saved.text
        assert saved.json()['api_key_configured'] is True
        assert 'fixture-api-secret' not in saved.text
        assert 'fixture-api-secret' not in client.get('/api/settings', headers=auth).text
        assert saved.json()['OPENAI_BASE_URL'] == 'https://example.org/v1'
        assert load_runtime_settings(tmp_path).OPENAI_API_KEY.get_secret_value() == 'fixture-api-secret'
        if os.name == 'nt':
            assert 'fixture-api-secret' not in (tmp_path / 'model-settings.json').read_text()
        body['OPENAI_API_KEY'] = None
        assert client.post('/api/settings', headers=auth, json=body).json()['api_key_configured']
        body['OPENAI_API_KEY'] = ''
        assert not client.post('/api/settings', headers=auth, json=body).json()['api_key_configured']
    restarted = create_app(tmp_path, auth['X-Analyst-Token'])
    with TestClient(restarted) as client:
        saved = client.get('/api/settings', headers=auth).json()
        assert saved['OPENAI_MODEL'] == 'test-model' and not saved['api_key_configured']


def test_invalid_settings_and_active_task_are_rejected(client, auth):
    for address in ('http://example.org/v1', 'https://user:secret@example.org/v1',
                    'https://example.org/v1?key=secret', 'https://example.org/v1/chat/completions'):
        assert client.post('/api/settings', headers=auth, json={'OPENAI_BASE_URL': address}).status_code == 422
    with client.app.state.session_factory.begin() as session:
        session.add(TaskRecord(input_text='test', source_url='test', source_kind='local', max_videos=1,
                               status='running'))
    assert client.post('/api/settings', headers=auth, json={}).status_code == 409


def test_local_import_rejects_invalid_files_and_requires_model(client, auth, tmp_path):
    from test_job_processor import until_done
    missing = client.post('/api/local-videos', headers=auth, json={'path': str(tmp_path / 'missing.mp4')})
    assert missing.status_code == 422
    source = tmp_path / 'uploaded.mp4'
    source.write_bytes(b'fixture-file-no-real-video-or-model')
    created = client.post('/api/local-videos', headers=auth, json={'path': str(source)})
    assert created.status_code == 201
    task = until_done(client, auth, created.json()['id'])
    assert task['status'] == 'blocked' and task['error_code'] == 'LLM_NOT_CONFIGURED'
    assert task['source_kind'] == 'local' and task['source_url'] == source.name
    source.unlink()
    with client.app.state.session_factory() as session:
        imported = Path(session.get(TaskRecord, task['id']).input_text)
        assert imported.is_file() and imported.read_bytes() == b'fixture-file-no-real-video-or-model'


def test_diagnostics_does_not_import_f2_or_download_models(client, auth):
    diagnostics = client.get('/api/diagnostics', headers=auth)
    assert diagnostics.status_code == 200
    assert diagnostics.json()['agent_enabled'] is False
    assert set(diagnostics.json()['packages']) == {'f2', 'faster-whisper'}


def test_model_test_validates_contract_without_saving_video(client, auth, monkeypatch):
    from app.insights import OpenAICompatibleInsightGenerator
    from test_m1_pipeline import FakeLLM
    async def fixture_generate(self, _segments):
        draft = await FakeLLM().generate(_segments)
        draft['summary_segment_ids'] = [0]
        draft['explicitly_stated_preferences'] = []
        return draft
    monkeypatch.setattr(OpenAICompatibleInsightGenerator, 'generate', fixture_generate)
    configuration = {'OPENAI_BASE_URL': 'https://example.org/v1', 'OPENAI_MODEL': 'fixture-model',
                     'OPENAI_API_KEY': 'fixture-key'}
    assert client.post('/api/settings', headers=auth, json=configuration).status_code == 200
    tested = client.post('/api/settings/test', headers=auth)
    assert tested.status_code == 200, tested.text
    assert client.get('/api/videos', headers=auth).json() == []


def test_collected_publish_time_is_persisted(tmp_path):
    from app.database import build_session_factory
    factory, engine = build_session_factory(tmp_path)
    try:
        with factory.begin() as session:
            task = TaskRecord(input_text='test', source_url='test', source_kind='profile', max_videos=10)
            session.add(task)
            session.flush()
            task_id = task.id
        candidate = VideoCandidate('7444000000000012345', 'creator-test', 'test', 1700000000,
                                   'https://www.douyin.com/video/7444000000000012345', None)
        processor = LiveTaskProcessor(factory, tmp_path, None, None, None, provenance='test_fixture')
        video_id, _ = processor.associate(task_id, candidate)
        with factory() as session:
            published = session.get(VideoRecord, video_id).published_at
            assert published.replace(tzinfo=dt.timezone.utc).timestamp() == candidate.published_at_unix
    finally:
        engine.dispose()
