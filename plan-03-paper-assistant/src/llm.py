"""Thin wrapper around the Claude API — so every other module can inject a fake LLM in tests."""

import anthropic


_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the env
    return _client


def complete(prompt: str, model: str, max_tokens: int = 1024, system: str | None = None) -> str:
    """One simple text Q&A turn (used for query expansion, the map step...)."""
    kwargs: dict = dict(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    if system:
        kwargs["system"] = system
    response = _get_client().messages.create(**kwargs)
    return next((b.text for b in response.content if b.type == "text"), "")
