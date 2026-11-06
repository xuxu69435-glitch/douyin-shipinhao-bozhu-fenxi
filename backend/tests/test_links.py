import httpx
import pytest

from app.links import InvalidDouyinLink, parse_douyin_input, resolve_short_link


@pytest.mark.parametrize("text,kind,platform_id", [
    ("https://www.douyin.com/video/7444000000000012345?aid=1", "video", "7444000000000012345"),
    ("https://www.douyin.com/note/7444000000000012345", "video", "7444000000000012345"),
    ("复制链接 8.22 https://www.douyin.com/user/MS4wLjABAAAA_TESTxyz123 复制", "profile", "MS4wLjABAAAA_TESTxyz123"),
    ("看作品 https://v.douyin.com/abcdef/。", "short", None),
    ("长按复制此条消息，打开抖音搜索，查看TA的更多作品。 https://v.douyin.com/1MzzlZTuZcc/", "short", None),
    ("2.56 kPX:/ :6pm v@F.uf 04/20 轻信大学生保姆级旅游攻略，好好休假差点变成极限拉练 #搞笑 https://v.douyin.com/NE2hkgBNwHM/ 复制此链接，打开Dou音搜索，直接观看视频！", "short", None),
    ("https://www.iesdouyin.com/share/user/MS4wLjABAAAA_TESTxyz123?sec_uid=MS4wLjABAAAA_TESTxyz123", "profile", "MS4wLjABAAAA_TESTxyz123"),
    ("https://www.iesdouyin.com/share/video/7699679130752748809/?share_sign=private", "video", "7699679130752748809"),
])
def test_parse(text, kind, platform_id):
    result = parse_douyin_input(text)
    assert result.kind == kind
    assert result.platform_id == platform_id


@pytest.mark.parametrize("text", [
    "https://www.douyin.com.evil.example/video/7444000000000012345",
    "https://evil.example/video/7444000000000012345",
    "http://www.douyin.com/video/7444000000000012345",
    "https://www.douyin.com:80/video/7444000000000012345",
    "https://www.douyin.com:invalid/video/7444000000000012345",
    "https://user:pass@www.douyin.com/video/7444000000000012345",
    "https://www.douyin.com/other/7444000000000012345",
    "no urls here",
    "x" * 5001,
])
def test_reject(text):
    with pytest.raises(InvalidDouyinLink):
        parse_douyin_input(text)


@pytest.mark.parametrize("short,target,kind,platform_id", [
    ("https://v.douyin.com/1MzzlZTuZcc/", "https://www.iesdouyin.com/share/user/MS4wLjABAAAAoDPbeBJwY9IpoMFWKaDAPR7WXPset_2zjILeb65yPeg?sec_uid=MS4wLjABAAAAoDPbeBJwY9IpoMFWKaDAPR7WXPset_2zjILeb65yPeg&did=private", "profile", "MS4wLjABAAAAoDPbeBJwY9IpoMFWKaDAPR7WXPset_2zjILeb65yPeg"),
    ("https://v.douyin.com/NE2hkgBNwHM/", "https://www.iesdouyin.com/share/video/7699679130752748809/?share_sign=private", "video", "7699679130752748809"),
])
@pytest.mark.asyncio
async def test_resolve_mobile_share_redirect(monkeypatch, short, target, kind, platform_id):
    requests = []
    def handler(request):
        requests.append(str(request.url))
        return httpx.Response(302, headers={"location": target})
    client_type = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: client_type(transport=httpx.MockTransport(handler), **kwargs))
    result = await resolve_short_link(short)
    assert result.kind == kind
    assert result.platform_id == platform_id
    assert result.url == f"https://www.douyin.com/{'user' if kind == 'profile' else 'video'}/{platform_id}"
    assert "?" not in result.url
    assert requests == [short]


@pytest.mark.parametrize("location", [
    "https://www.douyin.com.evil.example/share/video/7699679130752748809/",
    "http://www.iesdouyin.com/share/video/7699679130752748809/",
    "https://user:password@www.iesdouyin.com/share/video/7699679130752748809/",
    "https://www.iesdouyin.com:invalid/share/video/7699679130752748809/",
    "https://www.iesdouyin.com:8080/share/video/7699679130752748809/",
])
@pytest.mark.asyncio
async def test_reject_unsafe_share_redirect(monkeypatch, location):
    client_type = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(302, headers={"location": location}))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: client_type(transport=transport, **kwargs))
    with pytest.raises(InvalidDouyinLink):
        await resolve_short_link("https://v.douyin.com/abcdef/")
