"""Wrapper mỏng quanh Claude API + ScriptedLLM (fake) cho test offline.

Mọi module nhận `llm` qua tham số (inject được) — code gọi thẳng anthropic
chỉ nằm ở đây. Import anthropic để lazy trong AnthropicLLM: test offline
không cần cài/không cần key.

3 mặt cắt mà Plan 8 cần:
- complete_json: importance scoring + reflection (structured output theo schema)
- stream_dialogue: thoại NPC — yield từng mẩu text về client, kèm tool_use
  proposals ở cuối (LLM KHÔNG tự quyết gameplay — xem dialogue.py)
"""

import json
from typing import Any, Iterator, Protocol

from src import config

# Sự kiện stream_dialogue yield ra: ("text", str) | ("tool_use", dict)
StreamEvent = tuple[str, Any]


class LLM(Protocol):
    def complete_json(self, prompt: str, *, model: str, schema: dict,
                      system: str | None = None, max_tokens: int = 1024) -> Any: ...

    def stream_dialogue(self, *, model: str, system_blocks: list[dict],
                        messages: list[dict], tools: list[dict] | None = None,
                        max_tokens: int = 500) -> Iterator[StreamEvent]: ...


class AnthropicLLM:
    """Backend thật. Đọc ANTHROPIC_API_KEY từ env."""

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
    """Fake cho test/dev offline — trả lời theo kịch bản, ghi lại mọi call.

    replies: list, mỗi phần tử ứng với 1 call theo thứ tự:
      - complete_json lấy phần tử tiếp theo làm giá trị trả về (dict/list)
      - stream_dialogue lấy phần tử tiếp theo: str (chỉ text) hoặc dict
        {"text": str, "tool_calls": [{"name":..., "input":...}]}
      - một Exception instance -> raise (giả lập timeout/API lỗi)
    """

    def __init__(self, replies: list | None = None):
        self.replies = list(replies or [])
        self.calls: list[dict] = []  # để test assert prompt có chứa ký ức kỳ vọng

    def _next(self):
        if not self.replies:
            raise AssertionError("ScriptedLLM hết kịch bản — thêm phần tử vào replies")
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
        # yield từng "từ" một để giả lập streaming thật
        text = reply.get("text", "")
        for i, word in enumerate(text.split(" ")):
            yield ("text", word if i == 0 else " " + word)
        for call in reply.get("tool_calls", []):
            yield ("tool_use", call)


def get_llm(timeout: float | None = None) -> LLM | None:
    """None khi LLM_BACKEND=none — server vẫn chạy được phần ghi/đọc ký ức."""
    if config.LLM_BACKEND == "none":
        return None
    return AnthropicLLM(timeout=timeout)
