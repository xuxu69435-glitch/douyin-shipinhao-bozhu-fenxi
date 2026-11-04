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
