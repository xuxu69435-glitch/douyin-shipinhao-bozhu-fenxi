import asyncio
import json
from types import SimpleNamespace

from app.collection_probe import probe, run_isolated_probe
from app.collector import AuthorWorks, VideoCandidate


VIDEO = "https://www.douyin.com/video/7699679130752748809"
PROFILE = "https://www.douyin.com/user/MS4wLjABAAAAfixture"


def test_access_denial_keeps_short_resolution_without_claiming_author(tmp_path, monkeypatch):
    from app import collection_probe
    from app.links import parse_douyin_input
    async def resolve(url):
        assert isinstance(url, str)
        return parse_douyin_input(VIDEO)
    monkeypatch.setattr(collection_probe, "resolve_short_link", resolve)
    class Denied:
        async def video_detail(self, url):
            error = RuntimeError("fixture-sensitive-cookie-and-url")
            error.status_code = 403
            raise error
    result = asyncio.run(probe("分享 https://v.douyin.com/NE2hkgBNwHM/", True, "", tmp_path,
                               collector=Denied(), cookie="sessionid=fixture-private-cookie"))
    assert result["resolved_url"] == VIDEO
    assert result["steps"][0]["status"] == "passed"
    assert result["steps"][1]["status"] == "blocked"
    assert result["error_code"] == "HTTP_403"
    assert not result["complete"] and not result["model_called"]
    assert "fixture-sensitive" not in json.dumps(result)
    assert "author_id" not in result
    assert result["access_mode"] == "user_imported_cookie"
    assert "fixture-private-cookie" not in json.dumps(result)


def test_profile_id_in_url_does_not_verify_author_or_second_page(tmp_path):
    class Empty:
        async def profile_id(self, url):
            return "unverified-url-id"
        async def author_works(self, author, limit):
            return AuthorWorks(author, [], 1, "empty")
    result = asyncio.run(probe(PROFILE, True, "", tmp_path, collector=Empty()))
    assert "author_id" not in result and not result["complete"]


def test_real_media_validation_is_required_and_report_excludes_signed_url(tmp_path, monkeypatch):
    from app import collection_probe
    sample = VideoCandidate("7699679130752748809", "creator", "fixture", None, VIDEO,
                            "https://example.douyinvod.com/fixture?secret-signature")
    class Collector:
        async def video_detail(self, url):
            return sample
    async def download(url, destination):
        assert url == sample.media_url
        return {"sha256": "fixture-hash", "size_bytes": 42, "streams": ["video"]}
    monkeypatch.setattr(collection_probe, "download_verified_media", download)
    result = asyncio.run(probe(VIDEO, True, "", tmp_path, collector=Collector()))
    assert result["complete"] and result["steps"][-1]["status"] == "passed"
    assert "secret-signature" not in json.dumps(result)


def test_probe_api_does_not_decrypt_api_key(client, auth, monkeypatch):
    from app import runtime_settings, collection_probe
    def forbidden(*args, **kwargs):
        raise AssertionError("collection must not decrypt model credentials")
    monkeypatch.setattr(runtime_settings, "_crypt_key", forbidden)
    monkeypatch.setattr(collection_probe, "run_isolated_probe", lambda *args, **kwargs: {"model_called": False})
    assert client.post("/api/diagnostics/douyin", json={"input_text": VIDEO}).status_code == 401
    assert client.post("/api/diagnostics/douyin", headers=auth, json={"input_text": VIDEO}).json() == {"model_called": False}
    assert "model_called" in client.get("/api/diagnostics/douyin/export", headers=auth).json()["content"]


def test_isolated_process_really_exits_on_deadline_and_retains_result(tmp_path):
    report = run_isolated_probe(VIDEO, False, "", tmp_path)
    assert report["steps"][0]["status"] == "passed" and not report["complete"]
    # No network is required: an already exhausted deadline terminates before collection.
    timed_out = run_isolated_probe(VIDEO, False, "", tmp_path, timeout=0)
    assert timed_out["error_code"] == "PROBE_TIMEOUT" and not timed_out["complete"]
