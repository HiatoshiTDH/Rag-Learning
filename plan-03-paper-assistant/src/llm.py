"""Wrapper mỏng quanh Claude API — để mọi module khác inject fake LLM khi test."""

import anthropic


_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()  # đọc ANTHROPIC_API_KEY từ env
    return _client


def complete(prompt: str, model: str, max_tokens: int = 1024, system: str | None = None) -> str:
    """Một lượt hỏi-đáp text đơn giản (dùng cho query expansion, map step...)."""
    kwargs: dict = dict(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    if system:
        kwargs["system"] = system
    response = _get_client().messages.create(**kwargs)
    return next((b.text for b in response.content if b.type == "text"), "")
