"""Đọc/ghi cấu hình từ UI Settings — áp dụng ngay trong process + lưu bền vào .env.

Nguyên tắc:
- API key KHÔNG BAO GIỜ trả về nguyên văn cho UI — chỉ dạng che (sk-ant…abcd).
- UI gửi lại giá trị che hoặc rỗng -> hiểu là "giữ nguyên key cũ".
- Đổi backend có hệ quả (embedding đổi số chiều vector) -> trả warning rõ ràng.
"""

import os
from pathlib import Path

from src import config

# Các field UI được phép đổi. ANTHROPIC_API_KEY sống trong env (SDK tự đọc),
# còn lại là attr của config — apply cập nhật cả hai nơi.
FIELDS = [
    "LLM_BACKEND", "ANSWER_MODEL", "ANTHROPIC_API_KEY",
    "OPENAI_COMPAT_BASE_URL", "OPENAI_COMPAT_MODEL", "OPENAI_COMPAT_API_KEY",
    "EMBED_BACKEND", "VOYAGE_API_KEY", "RERANK_BACKEND", "ANSWER_LANGUAGE",
]
_SECRET_FIELDS = {"ANTHROPIC_API_KEY", "VOYAGE_API_KEY", "OPENAI_COMPAT_API_KEY"}

_ALLOWED = {
    "LLM_BACKEND": {"anthropic", "openai_compat"},
    "EMBED_BACKEND": {"voyage", "local", "fake"},
    "RERANK_BACKEND": {"voyage", "local", "fake", "none"},
    "ANSWER_LANGUAGE": {"auto", "en", "vi"},
    "ANSWER_MODEL": {"claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5"},
}


def _mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 10:
        return "•" * len(value)
    return f"{value[:6]}…{value[-4:]}"


def _current(field: str) -> str:
    if field == "ANTHROPIC_API_KEY":
        return os.getenv("ANTHROPIC_API_KEY", "")
    return str(getattr(config, field, "") or "")


def get_settings() -> dict:
    """Trạng thái hiện tại cho UI — secret đã che."""
    return {
        f: (_mask(_current(f)) if f in _SECRET_FIELDS else _current(f))
        for f in FIELDS
    }


def _write_env(updates: dict, env_path: Path | None = None) -> None:
    """Cập nhật .env giữ nguyên comment/thứ tự; key chưa có thì append cuối."""
    env_path = env_path or (config.ROOT / ".env")
    lines = env_path.read_text().splitlines() if env_path.exists() else []
    remaining = dict(updates)
    out = []
    for line in lines:
        stripped = line.strip()
        key = stripped.split("=", 1)[0].strip() if "=" in stripped and not stripped.startswith("#") else None
        if key in remaining:
            out.append(f"{key}={remaining.pop(key)}")
        else:
            out.append(line)
    for key, value in remaining.items():
        out.append(f"{key}={value}")
    env_path.write_text("\n".join(out) + "\n")


def apply_settings(updates: dict, env_path: Path | None = None) -> dict:
    """Áp dụng cấu hình mới: validate -> os.environ + config attr -> .env -> reset cache.

    Trả {"ok": True, "warnings": [...]}. Giá trị không hợp lệ -> ValueError (webapp trả 400).
    """
    clean: dict[str, str] = {}
    for key, value in updates.items():
        if key not in FIELDS or not isinstance(value, str):
            continue
        value = value.strip()
        # Secret: rỗng hoặc còn nguyên dạng che -> user không đổi, giữ key cũ
        if key in _SECRET_FIELDS and (not value or "…" in value or set(value) == {"•"}):
            continue
        if key in _ALLOWED and value and value not in _ALLOWED[key]:
            raise ValueError(f"{key} không nhận giá trị {value!r} (cho phép: {sorted(_ALLOWED[key])})")
        clean[key] = value

    warnings = []
    if clean.get("EMBED_BACKEND") and clean["EMBED_BACKEND"] != config.EMBED_BACKEND:
        warnings.append(
            "Đổi embedding backend làm vector cũ lệch số chiều — xóa index "
            "(data/qdrant/ hoặc volume docker) rồi chạy ingest lại trước khi hỏi."
        )
    if clean.get("LLM_BACKEND") == "openai_compat":
        warnings.append(
            "Local LLM: nhớ chạy endpoint trước khi hỏi (VD Ollama: "
            "OLLAMA_CONTEXT_LENGTH=16384 ollama serve)."
        )

    for key, value in clean.items():
        os.environ[key] = value
        if hasattr(config, key):
            setattr(config, key, value)

    _write_env(clean, env_path)

    # Client Anthropic cache trong llm.py gắn với key cũ -> vô hiệu hóa
    from src import llm
    llm._anthropic_client = None

    return {"ok": True, "warnings": warnings, "changed": sorted(clean)}


def test_connection() -> dict:
    """Kiểm tra nhanh cấu hình hiện tại — không tốn phí (không gọi generation)."""
    if config.LLM_BACKEND == "openai_compat":
        import requests

        try:
            r = requests.get(f"{config.OPENAI_COMPAT_BASE_URL.rstrip('/')}/models",
                             headers={"Authorization": f"Bearer {config.OPENAI_COMPAT_API_KEY}"},
                             timeout=4)
            if r.status_code == 200:
                return {"ok": True, "message": f"Endpoint local OK ({config.OPENAI_COMPAT_MODEL})"}
            return {"ok": False, "message": f"Endpoint trả {r.status_code} — model đã pull chưa?"}
        except Exception as e:
            return {"ok": False,
                    "message": f"Không nối được {config.OPENAI_COMPAT_BASE_URL} — Ollama đã chạy chưa? ({type(e).__name__})"}
    if os.getenv("ANTHROPIC_API_KEY", "").startswith("sk-ant"):
        return {"ok": True, "message": f"Đã có Anthropic API key ({config.ANSWER_MODEL}) — xác thực thật sẽ diễn ra ở câu hỏi đầu tiên"}
    return {"ok": False, "message": "Chưa có ANTHROPIC_API_KEY (dạng sk-ant-...)"}
