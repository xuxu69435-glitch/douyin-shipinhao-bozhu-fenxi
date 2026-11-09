import json
import os

import pytest

from app.douyin_session import normalize_cookie, cookie_metadata, load_cookie, save_session, session_status, DouyinSessionError


def test_header_value_bom_and_equals_are_preserved():
    assert normalize_cookie('\ufeff Cookie: sessionid=fixture-only; token=abc== ') == 'sessionid=fixture-only; token=abc=='


@pytest.mark.parametrize('text', [
    'preferences={"volume":0.5}; sessionid=fixture-only',
    'sessionid=fixture-only; preferences={"volume":0.5}; token=abc==',
    'theme=dark; theme=light; sessionid=fixture-only',
    'empty=; prefs="a,b"; opaque=a/b+c==',
])
def test_browser_header_values_and_duplicate_names_are_preserved(text):
    assert normalize_cookie(text) == text


def test_metadata_handles_opaque_values_without_losing_login_marker():
    assert cookie_metadata('prefs={"volume":0.5}; theme=dark; theme=light; sessionid=fixture') == {
        'cookie_count': 4, 'login_marker_present': True,
    }


@pytest.mark.parametrize('text', ['', 'fixture-without-equals', 'sessionid=fixture\r\nX-Header: injected',
                                  '{"sessionid":"fixture"}', 'sessionid=中文', 'name=' + 'x' * 65536,
                                  'sessionid=fixture; HttpOnly', 'bad name=fixture'],
                         ids=['empty', 'missing-equals', 'injected-header', 'json', 'unicode', 'oversized',
                              'response-attribute', 'invalid-name'])
def test_invalid_cookie_never_echoes_credential(text):
    with pytest.raises(DouyinSessionError) as exc:
        normalize_cookie(text)
    assert 'fixture' not in str(exc.value)


@pytest.mark.skipif(os.name != 'nt', reason='Windows DPAPI')
def test_private_cookie_is_encrypted_and_independent_of_api_key(tmp_path, monkeypatch):
    from app import runtime_settings
    def forbidden(*args, **kwargs):
        raise AssertionError('must not load model settings')
    monkeypatch.setattr(runtime_settings, 'load_runtime_settings', forbidden)
    saved = save_session(tmp_path, 'sessionid=fixture-only-secret; msToken=fixture-token')
    assert saved['configured'] and saved['login_marker_present'] and saved['cookie_count'] == 2
    raw = (tmp_path / 'douyin-session.json').read_text()
    assert 'fixture-only-secret' not in raw and 'fixture-token' not in raw
    assert load_cookie(tmp_path) == 'sessionid=fixture-only-secret; msToken=fixture-token'
    assert session_status(tmp_path) == saved
    (tmp_path / 'douyin-session.json').write_text('{"version":1,"protected_cookie":"broken"}')
    with pytest.raises(DouyinSessionError, match='解密'):
        load_cookie(tmp_path)


def test_file_import_supports_utf8_bom_and_header_prefix(tmp_path):
    path = tmp_path / 'cookie.txt'
    path.write_text('Cookie: sessionid=fixture-only; token=abc==', encoding='utf-8-sig')
    assert load_cookie(tmp_path, str(path)) == 'sessionid=fixture-only; token=abc=='


def test_import_api_rejects_without_leaking_body(client, auth):
    assert client.post('/api/douyin/session', json={'cookie': 'fixture-sensitive'}).status_code == 401
    for body in ({'cookie':'sessionid=fixture-sensitive\r\nBad: header'}, {'cookie':['fixture-sensitive']}, ['fixture-sensitive']):
        response = client.post('/api/douyin/session', headers=auth, json=body)
        assert response.status_code == 422 and 'fixture-sensitive' not in response.text
    assert client.get('/api/douyin/session', headers=auth).json()['configured'] is False


@pytest.mark.skipif(os.name != 'nt', reason='Windows DPAPI')
def test_import_save_read_and_clear_do_not_reveal_cookie(client, auth, tmp_path):
    cookie = 'prefs={"volume":0.5}; theme=dark; theme=light; sessionid=fixture-private'
    response = client.post('/api/douyin/session', headers=auth, json={'cookie': cookie})
    assert response.status_code == 200 and response.json()['configured']
    assert response.json()['cookie_count'] == 4 and response.json()['login_marker_present']
    assert load_cookie(tmp_path) == cookie
    assert 'fixture-private' not in response.text
    assert 'fixture-private' not in client.get('/api/douyin/session', headers=auth).text
    assert client.post('/api/douyin/session/clear', headers=auth).json()['configured'] is False
