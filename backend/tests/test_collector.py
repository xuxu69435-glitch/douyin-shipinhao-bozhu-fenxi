import pytest

from app.collector import CollectorError, collect_author_pages, normalize_f2_page


def make_video(video_id: int, creator="creator123456"):
    return {
        "aweme_id": str(video_id), "author": {"sec_uid": creator}, "desc": f"视频{video_id}",
        "create_time": 1700000000,
        "video": {"play_addr": {"url_list": [f"https://v3.douyinvod.com/test/{video_id}.mp4"]}},
    }


@pytest.mark.asyncio
async def test_second_page_and_dedup():
    cursor_calls = []

    async def fetch(author, cursor, count):
        cursor_calls.append((cursor, count))
        if cursor == 0:
            return {"status_code": 0, "aweme_list": [make_video(i) for i in range(1, 21)], "has_more": 1, "max_cursor": 12345}
        return {"status_code": 0, "aweme_list": [make_video(20)] + [make_video(i) for i in range(21, 31)], "has_more": 0, "max_cursor": 67890}

    result = await collect_author_pages(fetch, "creator123456", 30)
    assert result.pages_fetched == 2
    assert result.second_page_new_ids == 10
    assert result.second_page_sample and result.second_page_sample.platform_video_id == "21"
    assert len(result.videos) == 30
    assert result.stop_reason == "limit_reached"
    assert cursor_calls == [(0, 20), (12345, 10)]


@pytest.mark.asyncio
async def test_guest_missing_pagination_is_not_end_of_list():
    async def fetch(author, cursor, count):
        return {"status_code": 0, "aweme_list": [make_video(1)]}
    result = await collect_author_pages(fetch, "creator123456", 30)
    assert result.stop_reason == "missing_pagination_info"
    assert result.pages_fetched == 1


@pytest.mark.asyncio
async def test_repeated_cursor_stops():
    async def fetch(author, cursor, count):
        return {"status_code": 0, "aweme_list": [make_video(1)], "has_more": 1, "max_cursor": cursor}
    result = await collect_author_pages(fetch, "creator123456", 30)
    assert result.stop_reason == "cursor_not_advanced"


def test_author_spoof_cannot_be_attributed():
    page = normalize_f2_page({"aweme_list": [make_video(1, "another_creator")], "has_more": False}, "creator123456", 0)
    assert page.videos == []


def test_error_status_not_success():
    with pytest.raises(CollectorError):
        normalize_f2_page({"status_code": 101}, "creator123456", 0)


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['ok', 'denied', 'offsite', 'gateway_uifid_missing', 'gateway_signature_missing'])
async def test_sdk_client_verifies_tls_and_keeps_cookie_on_douyin_only(monkeypatch, mode):
    import sys
    from types import SimpleNamespace
    import httpx
    from app.collector import F2Collector, CollectorAccessDenied

    requests = []
    class SDK:
        def __init__(self, options):
            self.crawler_headers = {'Cookie': options['cookie'], 'User-Agent': 'fixture-agent'}
            self._aclient = None
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            await self._aclient.aclose()
    monkeypatch.setitem(sys.modules, 'f2.apps.douyin.crawler', SimpleNamespace(DouyinCrawler=SDK))
    monkeypatch.setattr(F2Collector, '_options', lambda self: {'cookie': self.cookie})
    original = httpx.AsyncClient
    def respond(request):
        requests.append(request)
        if mode == 'denied':
            return httpx.Response(403, text='fixture-sensitive-response')
        if mode.startswith('gateway_'):
            detail = 'Uifid Not Found' if mode == 'gateway_uifid_missing' else 'Signature Not Found'
            return httpx.Response(403, text='Blocked by ArgusSecurityPlugin ' + detail + ' fixture-sensitive-response')
        if mode == 'offsite':
            return httpx.Response(302, headers={'location': 'https://example.invalid/steal'})
        return httpx.Response(200, json={'status_code': 0})
    def client(**kwargs):
        assert kwargs['verify'] is True
        return original(**kwargs, transport=httpx.MockTransport(respond))
    monkeypatch.setattr(httpx, 'AsyncClient', client)
    async with F2Collector('sessionid=fixture-cookie')._crawler() as sdk:
        if mode == 'ok':
            response = await sdk._aclient.get('https://www.douyin.com/aweme/v1/web/test/')
            assert response.status_code == 200
        else:
            with pytest.raises(CollectorError) as error:
                await sdk._aclient.get('https://www.douyin.com/aweme/v1/web/test/', follow_redirects=True)
            assert 'fixture-cookie' not in str(error.value) and 'fixture-sensitive' not in str(error.value)
            if mode == 'denied' or mode.startswith('gateway_'):
                assert isinstance(error.value, CollectorAccessDenied) and error.value.status_code == 403
                assert error.value.reason == (mode if mode.startswith('gateway_') else None)
    assert len(requests) == 1
    assert requests[0].headers['cookie'] == 'sessionid=fixture-cookie'


@pytest.mark.parametrize('cookie,expected', [
    ('sessionid=fixture; UIFID=real-fixture-id; UIFID_TEMP=temporary-fixture', 'real-fixture-id'),
    ('sessionid=fixture; UIFID_TEMP=temporary-fixture', 'temporary-fixture'),
    ('sessionid=fixture; UIFID', None),
])
def test_client_identifier_uses_only_real_imported_value(monkeypatch, cookie, expected):
    import sys
    from types import SimpleNamespace
    from app.collector import F2Collector
    monkeypatch.setitem(sys.modules, 'f2.apps.douyin.utils', SimpleNamespace(
        ClientConfManager=SimpleNamespace(headers=lambda: {'User-Agent': 'fixture-agent'})))
    options = F2Collector(cookie)._options()
    assert options['headers'].get('uifid') == expected
    assert 'x-tt-argus' not in options['headers']
    assert options['cookie'] == cookie
