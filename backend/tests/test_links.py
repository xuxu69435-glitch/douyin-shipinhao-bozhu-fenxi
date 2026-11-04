import pytest

from app.links import InvalidDouyinLink, parse_douyin_input


@pytest.mark.parametrize("text,kind,platform_id", [
    ("https://www.douyin.com/video/7444000000000012345?aid=1", "video", "7444000000000012345"),
    ("https://www.douyin.com/note/7444000000000012345", "video", "7444000000000012345"),
    ("复制链接 8.22 https://www.douyin.com/user/MS4wLjABAAAA_TESTxyz123 复制", "profile", "MS4wLjABAAAA_TESTxyz123"),
    ("看作品 https://v.douyin.com/abcdef/。", "short", None),
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
