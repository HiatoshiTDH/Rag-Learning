"""LLM dispatch: anthropic | openai_compat | fake. Mọi module nhận llm inject được khi test.

- anthropic:     model do caller truyền (DIALOGUE_MODEL / REFLECTION_MODEL / IMPORTANCE_MODEL)
- openai_compat: Ollama/LM Studio/Groq/Gemini — bỏ qua model caller, dùng OPENAI_COMPAT_MODEL
- fake:          trả text canned deterministic — cho CI/test chạy server end-to-end không cần LLM
"""

import requests

from src import config

_anthropic_client = None


def _anthropic_complete(prompt: str, model: str, max_tokens: int, system: str | None) -> str:
    global _anthropic_client
    if _anthropic_client is None:
        import anthropic

        _anthropic_client = anthropic.Anthropic()
    kwargs: dict = dict(model=model, max_tokens=max_tokens,
                        messages=[{"role": "user", "content": prompt}])
    if system:
        kwargs["system"] = system
    response = _anthropic_client.messages.create(**kwargs)
    return next((b.text for b in response.content if b.type == "text"), "")


def _openai_compat_complete(prompt: str, max_tokens: int, system: str | None) -> str:
    messages = ([{"role": "system", "content": system}] if system else []) + [
        {"role": "user", "content": prompt}
    ]
    r = requests.post(
        f"{config.OPENAI_COMPAT_BASE_URL.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {config.OPENAI_COMPAT_API_KEY}"},
        json={"model": config.OPENAI_COMPAT_MODEL, "max_tokens": max_tokens, "messages": messages},
        timeout=300,
    )
    if r.status_code != 200:
        raise RuntimeError(
            f"LLM endpoint lỗi {r.status_code}: {r.text[:300]} "
            f"(base_url={config.OPENAI_COMPAT_BASE_URL} — Ollama đã chạy chưa?)"
        )
    return r.json()["choices"][0]["message"]["content"] or ""


def complete(prompt: str, model: str, max_tokens: int = 1024, system: str | None = None) -> str:
    if config.LLM_BACKEND == "fake":
        return f"[fake-llm] {prompt[:80]}"
    if config.LLM_BACKEND == "openai_compat":
        return _openai_compat_complete(prompt, max_tokens, system)
    return _anthropic_complete(prompt, model, max_tokens, system)
