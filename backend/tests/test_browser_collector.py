import pytest

from app.browser_collector import BrowserCollector, browser_candidate
from app.collector import CollectorError


def raw(identity, author='MS4wfixture'):
    return {'aweme_id': str(identity), 'desc': 'fixture', 'author': {'sec_uid': author},
            'video': {'play_addr': {'url_list': [
                'https://www.douyin.com/aweme/v1/play/?fixture', 'https://v3.douyinvod.com/fixture.mp4']}}}


def test_browser_media_uses_actual_permitted_cdn():
    candidate = browser_candidate(raw(7699679130752748809))
    assert candidate.media_url == 'https://v3.douyinvod.com/fixture.mp4'
    assert candidate.author_platform_id == 'MS4wfixture'
    with pytest.raises(CollectorError):
        browser_candidate({'aweme_id': '7699679130752748809'})


@pytest.mark.asyncio
async def test_observed_pages_deduplicate_and_respect_limit(monkeypatch):
    async def request(self, url, limit):
        assert limit == 30
        return {'pages': [
            {'request_cursor': '0', 'max_cursor': 20, 'aweme_list': [raw(7000000000000000000+i) for i in range(20)]},
            {'request_cursor': '20', 'max_cursor': 40, 'aweme_list': [raw(7000000000000000000+i) for i in range(19, 40)]}],
            'stop_reason': 'limit_reached'}
    monkeypatch.setattr(BrowserCollector, '_request', request)
    works = await BrowserCollector().author_works('MS4wfixture', 30)
    assert len(works.videos) == 30 and works.second_page_new_ids == 10
    assert works.second_page_sample.platform_video_id == '7000000000000000020'


@pytest.mark.asyncio
async def test_browser_other_author_is_not_attributed(monkeypatch):
    async def request(*args):
        return {'pages':[{'aweme_list':[raw(7699679130752748809, 'MS4wother')]}]}
    monkeypatch.setattr(BrowserCollector, '_request', request)
    with pytest.raises(CollectorError, match='其他作者'):
        await BrowserCollector().author_works('MS4wfixture', 10)


@pytest.mark.asyncio
async def test_browser_video_identity_must_match_input(monkeypatch):
    async def request(*args):
        return {'detail':raw(7699679130752748810)}
    monkeypatch.setattr(BrowserCollector, '_request', request)
    with pytest.raises(CollectorError, match='ID'):
        await BrowserCollector().video_detail('https://www.douyin.com/video/7699679130752748809')


@pytest.mark.asyncio
async def test_interrupted_bridge_terminates_its_own_process(tmp_path, monkeypatch):
    import asyncio
    import subprocess
    import sys
    from app import browser_collector
    script = tmp_path / 'synthetic-slow-bridge.py'
    script.write_text('import time\ntime.sleep(60)\n', encoding='utf8')
    monkeypatch.setattr(browser_collector, 'browser_bridge_files', lambda: (sys.executable, script))
    original = subprocess.Popen
    children = []
    def start(*args, **kwargs):
        child = original(*args, **kwargs)
        children.append(child)
        return child
    monkeypatch.setattr(subprocess, 'Popen', start)
    task = asyncio.create_task(BrowserCollector()._request('https://www.douyin.com/video/7699679130752748809', 10))
    await asyncio.sleep(.2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert children and children[0].poll() is not None
