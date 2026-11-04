import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest

from app.insights import OpenAICompatibleInsightGenerator


def draft(segment_id=0):
    return {'summary': '测试摘要', 'summary_segment_ids': [segment_id], 'primary_domain': '科技',
            'secondary_topics': ['测试'], 'content_format': '解说',
            'key_claims': [], 'explicitly_stated_preferences': [], 'discussed_entities': []}


def install_transport(monkeypatch, handler):
    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))


def test_transient_error_retries_once_and_records_usage(monkeypatch):
    calls = []
    def handler(request):
        calls.append(json.loads(request.content))
        if len(calls) == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={'choices': [{'message': {'content': json.dumps(draft())}}],
                                        'usage': {'prompt_tokens': 20, 'completion_tokens': 30}})
    install_transport(monkeypatch, handler)
    generator = OpenAICompatibleInsightGenerator('https://example.org/v1', 'fixture-key', 'fixture-model')
    result = asyncio.run(generator.generate([SimpleNamespace(segment_id=0, start_ms=0, end_ms=1000, text='测试')]))
    assert result['summary'] == '测试摘要' and len(calls) == 2
    assert calls[0]['max_tokens'] == generator.MAX_OUTPUT_TOKENS
    assert generator.last_run['requests'] == 2 and generator.last_run['completion_tokens'] == 30


def test_invalid_evidence_is_rejected_after_bounded_retry(monkeypatch):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={'choices': [{'message': {'content': json.dumps(draft(999))}}]})
    install_transport(monkeypatch, handler)
    generator = OpenAICompatibleInsightGenerator('https://example.org/v1', 'fixture-key', 'fixture-model')
    with pytest.raises(ValueError, match='不存在'):
        asyncio.run(generator.generate([SimpleNamespace(segment_id=0, start_ms=0, end_ms=1000, text='测试')]))
    assert len(calls) == 2


def test_auth_failure_is_not_retried(monkeypatch):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(401)
    install_transport(monkeypatch, handler)
    generator = OpenAICompatibleInsightGenerator('https://example.org/v1', 'fixture-key', 'fixture-model')
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(generator.generate([SimpleNamespace(segment_id=0, start_ms=0, end_ms=1000, text='测试')]))
    assert len(calls) == 1


def test_long_transcript_chunks_then_synthesizes_with_fixed_budget(monkeypatch):
    bodies = []
    def handler(request):
        body = json.loads(request.content)
        bodies.append(body)
        content = body['messages'][1]['content']
        data = json.loads(content.split('\n', 1)[1])
        segment_id = data[0]['segment_id'] if '字幕逐段数据' in content else 0
        return httpx.Response(200, json={'choices': [{'message': {'content': json.dumps(draft(segment_id))}}]})
    install_transport(monkeypatch, handler)
    generator = OpenAICompatibleInsightGenerator('https://example.org/v1', 'fixture-key', 'fixture-model')
    segments = [SimpleNamespace(segment_id=i, start_ms=i * 1000, end_ms=(i + 1) * 1000, text='字' * 9000) for i in range(3)]
    result = asyncio.run(generator.generate(segments))
    assert result['summary_segment_ids'] == [0]
    assert generator.last_run['chunks'] == 3 and len(bodies) == 4
    assert len(bodies) <= generator.MAX_REQUESTS


def test_oversized_transcript_stops_before_request(monkeypatch):
    def handler(_request):
        pytest.fail('No HTTP request should occur after context budget rejection')
    install_transport(monkeypatch, handler)
    generator = OpenAICompatibleInsightGenerator('https://example.org/v1', 'fixture-key', 'fixture-model')
    segments = [SimpleNamespace(segment_id=i, start_ms=0, end_ms=1000, text='字' * 9000) for i in range(6)]
    with pytest.raises(ValueError, match='5 个分段'):
        asyncio.run(generator.generate(segments))
    assert generator.last_run['requests'] == 0
