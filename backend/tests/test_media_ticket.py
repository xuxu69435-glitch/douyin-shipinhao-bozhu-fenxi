"""HTML5 media playback tickets must be short-lived and bound to one video."""

import hashlib
import hmac
import time

from fastapi.testclient import TestClient

from app.main import create_app
from app.models import VideoRecord


def test_signed_media_supports_range_and_prevents_tokenless_download(tmp_path):
    token = "this-is-a-local-random-token-123456"
    app = create_app(tmp_path, token)
    file = tmp_path / "fake-for-range-test.mp4"
    file.write_bytes(b"0" * 256)  # Range test only; NOT a playable media file.
    with app.state.session_factory.begin() as session:
        video = VideoRecord(platform="local", platform_video_id="fake-file",
                            author_platform_id="fixture", source_url="local://fixture",
                            media_path=str(file))
        session.add(video)
        session.flush()
        video_id = video.id
    expires = int(time.time()) + 300
    sig = hmac.new(token.encode(), f"{video_id}:{expires}".encode(), hashlib.sha256).hexdigest()
    with TestClient(app) as client:
        prefix = f"/media/{video_id}?expires={expires}&signature="
        assert client.get(prefix + "bad").status_code == 403
        assert client.get(f"/media/{video_id}").status_code == 422
        assert client.get(prefix + sig, headers={"Range": "bytes=0-31"}).status_code == 206
        assert len(client.get(prefix + sig, headers={"Range": "bytes=0-31"}).content) == 32
        assert client.get(prefix + sig, headers={"Range": "bytes=1000-2000"}).status_code == 416
        old_exp = int(time.time()) - 200
        old_sig = hmac.new(token.encode(), f"{video_id}:{old_exp}".encode(), hashlib.sha256).hexdigest()
        assert client.get(f"/media/{video_id}?expires={old_exp}&signature={old_sig}").status_code == 403
        assert client.get(f"/media/{'0' * 36}?expires={expires}&signature={sig}").status_code in (403, 404)
