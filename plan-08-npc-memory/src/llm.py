"""Thin wrapper around the Claude API + ScriptedLLM (fake) for offline tests.

Every module receives `llm` as a parameter (injectable) — code that talks to
anthropic directly lives only here. The anthropic import is lazy inside
AnthropicLLM: offline tests need no install and no key.

The 3 surfaces Plan 8 needs:
- complete_json: importance scoring + reflection (structured output by schema)
- stream_dialogue: NPC dialogue — yields text chunks to the client, with any
  tool_use proposals at the end (the LLM NEVER decides gameplay — see dialogue.py)
"""

import json
from typing import Any, Iterator, Protocol

from src import config

# Events yielded by stream_dialogue: ("text", str) | ("tool_use", dict)
StreamEvent = tuple[str, Any]


class LLM(Protocol):
    def complete_json(self, prompt: str, *, model: str, schema: dict,
                      system: str | None = None, max_tokens: int = 1024) -> Any: ...

    def stream_dialogue(self, *, model: str, system_blocks: list[dict],
                        messages: list[dict], tools: list[dict] | None = None,
                        max_tokens: int = 500) -> Iterator[StreamEvent]: ...


class AnthropicLLM:
    """Real backend. Reads ANTHROPIC_API_KEY from the environment."""

    def __init__(self, timeout: float | None = None):
        import anthropic

        self.client = anthropic.Anthropic(timeout=timeout)

    def complete_json(self, prompt: str, *, model: str, schema: dict,
                      system: str | None = None, max_tokens: int = 1024) -> Any:
        kwargs: dict = dict(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
            output_config={"format": {"type": "json_schema", "schema": schema}},
        )
        if system:
            kwargs["system"] = system
        response = self.client.messages.create(**kwargs)
        text = next(b.text for b in response.content if b.type == "text")
        return json.loads(text)

    def stream_dialogue(self, *, model: str, system_blocks: list[dict],
                        messages: list[dict], tools: list[dict] | None = None,
                        max_tokens: int = 500) -> Iterator[StreamEvent]:
        kwargs: dict = dict(
            model=model,
            max_tokens=max_tokens,
            system=system_blocks,
            messages=messages,
        )
        if tools:
            kwargs["tools"] = tools
        with self.client.messages.stream(**kwargs) as stream:
            for text in stream.text_stream:
                yield ("text", text)
            final = stream.get_final_message()
        for block in final.content:
            if block.type == "tool_use":
                yield ("tool_use", {"name": block.name, "input": block.input})


class ScriptedLLM:
    """Fake for tests/offline dev — replies from a script, records every call.

    replies: a list; each element answers one call, in order:
      - complete_json pops the next element as its return value (dict/list)
      - stream_dialogue pops the next element: str (text only) or dict
        {"text": str, "tool_calls": [{"name":..., "input":...}]}
      - an Exception instance -> raised (simulates timeout/API failure)
    """

    def __init__(self, replies: list | None = None):
        self.replies = list(replies or [])
        self.calls: list[dict] = []  # lets tests assert the prompt contains expected memories

    def _next(self):
        if not self.replies:
            raise AssertionError("ScriptedLLM ran out of script — add elements to replies")
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    def complete_json(self, prompt: str, *, model: str, schema: dict,
                      system: str | None = None, max_tokens: int = 1024) -> Any:
        self.calls.append({"kind": "complete_json", "prompt": prompt,
                           "model": model, "system": system})
        return self._next()

    def stream_dialogue(self, *, model: str, system_blocks: list[dict],
                        messages: list[dict], tools: list[dict] | None = None,
                        max_tokens: int = 500) -> Iterator[StreamEvent]:
        self.calls.append({"kind": "stream_dialogue", "model": model,
                           "system_blocks": system_blocks, "messages": messages,
                           "tools": tools})
        reply = self._next()
        if isinstance(reply, str):
            reply = {"text": reply}
        # yield word by word to simulate real streaming
        text = reply.get("text", "")
        for i, word in enumerate(text.split(" ")):
            yield ("text", word if i == 0 else " " + word)
        for call in reply.get("tool_calls", []):
            yield ("tool_use", call)


def get_llm(timeout: float | None = None) -> LLM | None:
    """None when LLM_BACKEND=none — the server still serves memory read/write."""
    if config.LLM_BACKEND == "none":
        return None
    return AnthropicLLM(timeout=timeout)
