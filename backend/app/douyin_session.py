"""Explicitly imported Douyin cookies; independent of all model credentials."""

import base64
import datetime as dt
from http.cookies import SimpleCookie, CookieError
import json
import os
from pathlib import Path

from .runtime_settings import _crypt_key

MAX_COOKIE_BYTES = 65_536
SESSION_FILENAME = "douyin-session.json"


class DouyinSessionError(ValueError):
    pass


def normalize_cookie(text: str) -> str:
    if not isinstance(text, str):
        raise DouyinSessionError("请粘贴 Cookie 请求头的值")
    text = text.lstrip("\ufeff").strip()
    if text.lower().startswith("cookie:"):
        text = text[7:].strip()
    if not text or len(text.encode("utf8")) > MAX_COOKIE_BYTES:
        raise DouyinSessionError("Cookie 不能为空，且不能超过 64 KiB")
    if any(ord(char) < 32 or ord(char) > 126 for char in text):
        raise DouyinSessionError("请复制单行 Cookie 请求头的值，不要包含换行或其他请求头")
    if text.startswith(("{", "[", "curl ", "#")):
        raise DouyinSessionError("请粘贴 Cookie 请求头的值，不要粘贴 JSON、导出表格或整段 cURL")
    parsed = SimpleCookie()
    try:
        parsed.load(text)
    except CookieError:
        raise DouyinSessionError("Cookie 格式无法识别，请重新复制 Cookie 请求头的值") from None
    if not parsed or any(part.strip() and "=" not in part for part in text.split(";")):
        raise DouyinSessionError("Cookie 应为 name=value; name2=value2 格式")
    return "; ".join(f"{key}={value.coded_value}" for key, value in parsed.items())


def cookie_metadata(cookie: str):
    parsed = SimpleCookie()
    parsed.load(cookie)
    return {"cookie_count": len(parsed),
            "login_marker_present": any(name in parsed for name in ("sessionid", "sessionid_ss", "sid_tt"))}


def session_status(data_dir: Path):
    path = data_dir / SESSION_FILENAME
    if not path.is_file():
        return {"configured": False, "cookie_count": 0, "login_marker_present": False, "saved_at": None}
    try:
        data = json.loads(path.read_text(encoding="utf8"))
        if data.get("version") != 1 or not isinstance(data.get("protected_cookie"), str):
            raise ValueError()
        return {"configured": True, "cookie_count": int(data.get("cookie_count", 0)),
                "login_marker_present": data.get("login_marker_present") is True, "saved_at": data.get("saved_at")}
    except (OSError, ValueError, TypeError):
        raise DouyinSessionError("已保存的抖音登录状态无法读取，请重新导入") from None


def save_session(data_dir: Path, text: str):
    cookie = normalize_cookie(text)
    if os.name != "nt":
        raise DouyinSessionError("加密保存抖音登录状态需要 Windows")
    try:
        protected = base64.b64encode(_crypt_key(cookie.encode("ascii"))).decode("ascii")
        data = {"version": 1, "protected_cookie": protected,
                "saved_at": dt.datetime.now(dt.timezone.utc).isoformat(), **cookie_metadata(cookie)}
        data_dir.mkdir(parents=True, exist_ok=True)
        path = data_dir / SESSION_FILENAME
        temporary = path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf8") as output:
            os.chmod(temporary, 0o600)
            json.dump(data, output, ensure_ascii=True)
        temporary.replace(path)
    except OSError:
        raise DouyinSessionError("Windows 无法加密保存抖音登录状态") from None
    return session_status(data_dir)


def read_cookie_file(cookie_file: str) -> str:
    try:
        path = Path(cookie_file)
        if path.stat().st_size > MAX_COOKIE_BYTES + 3:
            raise DouyinSessionError("Cookie 文件超过 64 KiB")
        return normalize_cookie(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError):
        raise DouyinSessionError("Cookie 文件无法读取，请检查文件路径和 UTF-8 编码") from None


def load_cookie(data_dir: Path, cookie_file: str = "") -> str | None:
    path = data_dir / SESSION_FILENAME
    if path.exists():
        try:
            session_status(data_dir)
            data = json.loads(path.read_text(encoding="utf8"))
            return normalize_cookie(_crypt_key(base64.b64decode(data["protected_cookie"], validate=True),
                                               decrypt=True).decode("ascii"))
        except (OSError, ValueError, KeyError, UnicodeError):
            raise DouyinSessionError("无法解密本机抖音登录状态，请在此 Windows 用户下重新导入") from None
    if cookie_file:
        return read_cookie_file(cookie_file)
    return None


def register_session_routes(api, data_dir: Path, any_running):
    from fastapi import HTTPException, Request

    @api.get("/douyin/session")
    def status():
        try:
            return session_status(data_dir)
        except DouyinSessionError as exc:
            raise HTTPException(409, str(exc))

    @api.post("/douyin/session")
    async def save(request: Request):
        if any_running():
            raise HTTPException(409, "请先暂停正在执行的任务，再更新抖音登录状态")
        # Parse here so validation errors cannot echo an entire credential-bearing body.
        content = bytearray()
        async for chunk in request.stream():
            content.extend(chunk)
            if len(content) > MAX_COOKIE_BYTES * 2:
                raise HTTPException(413, "导入内容过长，请只复制 Cookie 请求头的值")
        try:
            body = json.loads(content)
            if not isinstance(body, dict) or not isinstance(body.get("cookie"), str):
                raise DouyinSessionError("请粘贴 Cookie 请求头的值")
            return save_session(data_dir, body["cookie"])
        except (json.JSONDecodeError, UnicodeError):
            raise HTTPException(422, "导入格式无法识别") from None
        except DouyinSessionError as exc:
            raise HTTPException(422, str(exc))

    @api.post("/douyin/session/clear")
    def clear():
        if any_running():
            raise HTTPException(409, "请先暂停正在执行的任务，再清除抖音登录状态")
        (data_dir / SESSION_FILENAME).unlink(missing_ok=True)
        return session_status(data_dir)
