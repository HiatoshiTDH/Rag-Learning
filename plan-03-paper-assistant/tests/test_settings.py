"""Test module settings: che secret, validate, ghi .env, giữ key cũ khi UI gửi bản che."""

import pytest

from src import config
from src.settings import _mask, apply_settings, get_settings


@pytest.fixture(autouse=True)
def restore_config(monkeypatch):
    """apply_settings mutate config + os.environ — đăng ký giá trị gốc để pytest tự trả lại."""
    for f in ["LLM_BACKEND", "ANSWER_MODEL", "EMBED_BACKEND", "RERANK_BACKEND",
              "ANSWER_LANGUAGE", "VOYAGE_API_KEY", "OPENAI_COMPAT_BASE_URL",
              "OPENAI_COMPAT_MODEL", "OPENAI_COMPAT_API_KEY"]:
        monkeypatch.setattr(config, f, getattr(config, f))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-original-key-000111")
    yield


def test_mask():
    assert _mask("") == ""
    assert _mask("short") == "•••••"
    assert _mask("sk-ant-api03-abcdefkey9xk2") == "sk-ant…9xk2"


def test_get_settings_masks_secrets():
    s = get_settings()
    assert s["ANTHROPIC_API_KEY"].startswith("sk-ant…")
    assert "original-key" not in s["ANTHROPIC_API_KEY"]     # không lộ key thật
    assert s["LLM_BACKEND"] in ("anthropic", "openai_compat")


def test_apply_settings_updates_config_and_env_file(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# comment giữ nguyên\nGROBID_URL=http://localhost:8070\nLLM_BACKEND=anthropic\n")

    out = apply_settings({"LLM_BACKEND": "openai_compat",
                          "OPENAI_COMPAT_MODEL": "qwen2.5:7b"}, env_path=env)
    assert out["ok"] and "LLM_BACKEND" in out["changed"]
    assert config.LLM_BACKEND == "openai_compat"
    content = env.read_text()
    assert "# comment giữ nguyên" in content                 # comment không mất
    assert "LLM_BACKEND=openai_compat" in content            # update tại chỗ
    assert "OPENAI_COMPAT_MODEL=qwen2.5:7b" in content       # key mới append


def test_apply_settings_invalid_enum_raises(tmp_path):
    with pytest.raises(ValueError):
        apply_settings({"LLM_BACKEND": "gpt4"}, env_path=tmp_path / ".env")


def test_masked_secret_sent_back_keeps_old_key(tmp_path, monkeypatch):
    """UI gửi lại đúng chuỗi che (user không sửa ô key) -> key cũ không bị ghi đè."""
    import os

    out = apply_settings({"ANTHROPIC_API_KEY": "sk-ant…0111", "ANSWER_MODEL": "claude-haiku-4-5"},
                         env_path=tmp_path / ".env")
    assert "ANTHROPIC_API_KEY" not in out["changed"]
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-ant-original-key-000111"
    assert config.ANSWER_MODEL == "claude-haiku-4-5"


def test_empty_secret_keeps_old_key(tmp_path):
    import os

    apply_settings({"ANTHROPIC_API_KEY": ""}, env_path=tmp_path / ".env")
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-ant-original-key-000111"


def test_new_secret_is_applied(tmp_path):
    import os

    apply_settings({"ANTHROPIC_API_KEY": "sk-ant-brand-new-key-xyz9"}, env_path=tmp_path / ".env")
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-ant-brand-new-key-xyz9"
    assert "sk-ant-brand-new-key-xyz9" in (tmp_path / ".env").read_text()


def test_embed_change_warns_reindex(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "EMBED_BACKEND", "voyage")
    out = apply_settings({"EMBED_BACKEND": "local"}, env_path=tmp_path / ".env")
    assert any("ingest lại" in w for w in out["warnings"])


def test_apply_resets_anthropic_client_cache(tmp_path):
    from src import llm

    llm._anthropic_client = object()   # giả lập client cũ đang cache
    apply_settings({"ANTHROPIC_API_KEY": "sk-ant-rotated-key-abc1"}, env_path=tmp_path / ".env")
    assert llm._anthropic_client is None
