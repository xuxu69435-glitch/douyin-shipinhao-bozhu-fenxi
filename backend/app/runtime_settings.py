"""User-owned runtime settings, stored outside the application installation."""

import base64
import ctypes
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class RuntimeSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())
    OPENAI_BASE_URL: str = Field(default="", max_length=2048)
    OPENAI_MODEL: str = Field(default="", max_length=200)
    OPENAI_API_KEY: SecretStr | None = None
    model_provider: Literal["api", "chatgpt"] = "api"
    CHATGPT_MODEL: str = Field(default="", max_length=200)
    enable_live: bool = False
    collector_provider: Literal["f2", "browser"] = "f2"
    cookie_file: str = Field(default="", max_length=2048)
    whisper_model: str = Field(default="small", min_length=1, max_length=2048)

    @field_validator("OPENAI_BASE_URL")
    @classmethod
    def validate_base_url(cls, value: str):
        value = value.strip().rstrip("/")
        if not value:
            return value
        parsed = urlsplit(value)
        if (not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment
                or (parsed.scheme != "https" and not
                    (parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}))):
            raise ValueError("API 地址须为 HTTPS 或本机 HTTP，不包含密钥、查询参数或片段")
        if parsed.path.endswith("/chat/completions"):
            raise ValueError("请填写基础地址（通常以 /v1 结尾），不要包含 /chat/completions")
        return value

    @field_validator("OPENAI_MODEL", "CHATGPT_MODEL", "cookie_file", "whisper_model")
    @classmethod
    def strip_value(cls, value: str, info):
        value = value.strip()
        if not value and info.field_name == "whisper_model":
            raise ValueError("语音模型名称或目录不能为空")
        return value

    @field_validator("OPENAI_API_KEY")
    @classmethod
    def strip_key(cls, value):
        return SecretStr(value.get_secret_value().strip()) if value is not None else None

    def public_view(self, data_dir: Path):
        return {**self.model_dump(exclude={"OPENAI_API_KEY"}),
                "api_key_configured": bool(self.OPENAI_API_KEY and self.OPENAI_API_KEY.get_secret_value()),
                "data_dir": str(data_dir), "api_key_encrypted": os.name == "nt"}


def _crypt_key(value: bytes, decrypt=False) -> bytes:
    """Windows DPAPI binds the saved key to the current Windows account."""
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    buffer = ctypes.create_string_buffer(value)
    source = Blob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    destination = Blob()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    operation = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
    operation.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    operation.restype = wintypes.BOOL
    if not operation(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(destination)):
        raise OSError("Windows 无法读取或保存本机 API 密钥")
    try:
        return ctypes.string_at(destination.data, destination.size)
    finally:
        kernel32.LocalFree(ctypes.cast(destination.data, ctypes.c_void_p))


def load_runtime_settings(data_dir: Path, *, include_api_key: bool | None = None) -> RuntimeSettings:
    values = {
        "OPENAI_BASE_URL": os.getenv("OPENAI_BASE_URL", ""),
        "OPENAI_MODEL": os.getenv("OPENAI_MODEL", ""),
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", ""),
        "enable_live": os.getenv("ANALYST_ENABLE_LIVE") == "1",
        "cookie_file": os.getenv("ANALYST_DOUYIN_COOKIE_FILE", ""),
    }
    path = data_dir / "model-settings.json"
    if path.exists():
        saved = json.loads(path.read_text(encoding="utf8"))
        saved.pop("api_key_present", None)
        encrypted = saved.pop("protected_api_key", None)
        use_key = include_api_key if include_api_key is not None else saved.get("model_provider", "api") == "api"
        if encrypted is not None and use_key:
            if os.name != "nt":
                raise ValueError("此配置中的密钥绑定于 Windows 用户，请重新配置")
            saved["OPENAI_API_KEY"] = _crypt_key(base64.b64decode(encrypted), decrypt=True).decode("utf8")
        values.update(saved)
        if not use_key:
            values["OPENAI_API_KEY"] = None
    if include_api_key is False:
        values["OPENAI_API_KEY"] = None
    return RuntimeSettings.model_validate(values)


def save_runtime_settings(data_dir: Path, settings: RuntimeSettings, *, preserve_key=False):
    data_dir.mkdir(parents=True, exist_ok=True)
    values = settings.model_dump(exclude={"OPENAI_API_KEY"})
    key = settings.OPENAI_API_KEY.get_secret_value() if settings.OPENAI_API_KEY else ""
    path = data_dir / "model-settings.json"
    if preserve_key and path.exists():
        saved = json.loads(path.read_text(encoding="utf8"))
        for field in ("protected_api_key", "OPENAI_API_KEY"):
            if field in saved:
                values[field] = saved[field]
        values["api_key_present"] = saved.get("api_key_present", bool(saved.get("protected_api_key") or saved.get("OPENAI_API_KEY")))
    elif os.name == "nt":
        values["protected_api_key"] = base64.b64encode(_crypt_key(key.encode("utf8"))).decode("ascii")
    else:
        values["OPENAI_API_KEY"] = key
    if not preserve_key or not path.exists():
        values["api_key_present"] = bool(key)
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf8") as stream:
        os.chmod(temporary, 0o600)
        json.dump(values, stream, ensure_ascii=False, indent=2)
    temporary.replace(path)
