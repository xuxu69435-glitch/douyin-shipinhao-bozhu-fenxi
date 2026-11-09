import asyncio
import json
import os
from types import SimpleNamespace

import pytest

from app.chatgpt_plan import ChatGPTPlanBridge, ChatGPTPlanError, make_generator, private_environment
from app.runtime_settings import RuntimeSettings, load_runtime_settings, save_runtime_settings


def test_plan_settings_never_decrypt_or_replace_existing_api_key(tmp_path, monkeypatch):
    from app import runtime_settings
    save_runtime_settings(tmp_path, RuntimeSettings(OPENAI_API_KEY="fixture-only-secret"))
    original = json.loads((tmp_path / "model-settings.json").read_text())
    def forbidden(*args, **kwargs):
        raise AssertionError("must not decrypt a separate API key")
    monkeypatch.setattr(runtime_settings, "_crypt_key", forbidden)
    save_runtime_settings(tmp_path, RuntimeSettings(model_provider="chatgpt", CHATGPT_MODEL="fixture-model"), preserve_key=True)
    configuration = load_runtime_settings(tmp_path)
    assert configuration.OPENAI_API_KEY is None
    saved = json.loads((tmp_path / "model-settings.json").read_text())
    field = "protected_api_key" if os.name == "nt" else "OPENAI_API_KEY"
    assert saved[field] == original[field]
    assert make_generator(configuration, tmp_path).cache_identity.startswith("chatgpt-plan-responses-v1|")


def test_child_environment_does_not_inherit_keys_or_node_hooks(monkeypatch):
    for name in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "NODE_OPTIONS", "NODE_PATH", "ANALYST_BACKEND_TOKEN"):
        monkeypatch.setenv(name, "fixture-sensitive")
    env = private_environment()
    assert not any(key.startswith(("OPENAI_", "NODE_", "ANALYST_")) for key in env)


@pytest.mark.skipif(os.name != "nt", reason="actual Windows DPAPI integration")
def test_official_bridge_reads_only_its_own_disconnected_store(tmp_path):
    bridge = ChatGPTPlanBridge(tmp_path)
    assert bridge.call("status") == {"status": "disconnected", "sharing": False}
    with pytest.raises(ChatGPTPlanError, match="sign_in_required"):
        bridge.call("generate", {"model": "fixture-model", "content": "fixture-text"})
    assert not list(tmp_path.rglob("*token*"))


@pytest.mark.skipif(os.name != "nt", reason="actual Windows DPAPI integration")
def test_official_bridge_encrypts_and_decrypts_synthetic_credentials_across_processes(tmp_path):
    # SDK migration exercises the real private-pipe DPAPI adapter without network/OAuth.
    profile = {"version": 1, "id": "fixture-profile", "label": "Synthetic account", "clientId": "fixture_client",
               "status": "connected", "scopes": ["openid", "chatgpt.tokens.use.direct"],
               "savedAt": "2026-11-09T00:00:00.000Z", "subject": "fixture-subject",
               "identity": {"email": "fixture@example.invalid"}, "profileIdToken": "fixture-id-token",
               "credentials": {"accessToken": "fixture-access-token", "refreshToken": "fixture-refresh-token", "expiresAt": 9_999_999_999_999}}
    directory = tmp_path / "chatgpt"
    directory.mkdir()
    path = directory / "chatgpt-auth.json"
    path.write_text(json.dumps({"version": 2, "activeProfileId": profile["id"], "profiles": [profile], "pendingRegistrations": []}))
    first = ChatGPTPlanBridge(tmp_path).call("status")
    assert first["sharing"] is True
    assert "fixture-access-token" not in json.dumps(first)
    encrypted = path.read_text()
    assert "fixture-access-token" not in encrypted and "fixture@example.invalid" not in encrypted
    assert json.loads(encrypted)["provider"] == "windows-dpapi-v1"
    assert ChatGPTPlanBridge(tmp_path).call("status") == first


def test_plan_contract_keeps_real_evidence_and_has_no_api_fallback(tmp_path, monkeypatch):
    from test_m1_pipeline import FakeLLM
    generator = make_generator(RuntimeSettings(model_provider="chatgpt", CHATGPT_MODEL="fixture"), tmp_path)
    segments = [SimpleNamespace(segment_id=0, start_ms=0, end_ms=1000, text="fixture")]
    draft = asyncio.run(FakeLLM().generate(segments))
    draft["summary_segment_ids"] = [0]
    draft["explicitly_stated_preferences"] = []
    def generate(op, args, timeout):
        assert op == "generate" and "instructions" in args
        return {"text": json.dumps(draft)}
    monkeypatch.setattr(generator.bridge, "call", generate)
    assert asyncio.run(generator.generate(segments))["summary_segment_ids"] == [0]
    assert generator.last_run["max_output_tokens"] is None
    assert generator.last_run["requests"] == 1
    draft["summary_segment_ids"] = [999]
    with pytest.raises(ValueError, match="不存在"):
        asyncio.run(generator.generate(segments))
    def denied(*args):
        raise ChatGPTPlanError("subscription_sharing_usage_limit_exceeded")
    monkeypatch.setattr(generator.bridge, "call", denied)
    with pytest.raises(ChatGPTPlanError):
        asyncio.run(generator.generate(segments))
    assert generator.last_run["requests"] == 1


def test_login_routes_require_desktop_token_and_do_not_infer(client, auth, monkeypatch):
    monkeypatch.setattr(ChatGPTPlanBridge, "status", lambda self: {"status": "disconnected", "sharing": False})
    assert client.get("/api/chatgpt/status").status_code == 401
    assert client.post("/api/chatgpt/sign-in").status_code == 401
    assert client.get("/api/chatgpt/status", headers=auth).json()["sharing"] is False


def test_insufficient_domain_evidence_is_explicitly_uncategorized():
    from app.insights import InsightDraft
    draft = {"summary": "连接测试字幕", "summary_segment_ids": [0], "primary_domain": " ",
             "secondary_topics": [], "content_format": "测试", "key_claims": [],
             "explicitly_stated_preferences": [], "discussed_entities": []}
    assert InsightDraft.model_validate(draft).primary_domain == "未分类"
    draft["primary_domain"] = None
    with pytest.raises(ValueError):
        InsightDraft.model_validate(draft)
