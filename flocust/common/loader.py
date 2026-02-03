"""Load prompts from JSON or JSONL files."""

import json
from pathlib import Path

PROMPT_KEYS = ("prompt", "text", "content", "input", "message")


def _messages_to_prompt(messages: list[dict]) -> str:
    """Convert messages array to single prompt string (role: content per line)."""
    parts = []
    for m in messages:
        role = m.get("role") or ""
        content = m.get("content") or ""
        parts.append(f"{role}: {content}".strip())
    return "\n".join(p for p in parts if p)


def load_prompts(path: Path) -> list[str]:
    """
    Load prompts from JSON or JSONL file.

    Supports: JSON array of strings; array of {messages: [{role, content}, ...]};
    object with prompt/text/content; JSONL (one JSON per line or raw line);
    plain text (one prompt per line).
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Prompts file not found: {path}")

    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []

    if path.suffix.lower() == ".json":
        return _parse_json_prompts(text)
    if path.suffix.lower() == ".jsonl":
        return _parse_jsonl_prompts(text)
    try:
        return _parse_json_prompts(text)
    except (json.JSONDecodeError, TypeError):
        return _parse_jsonl_prompts(text)


def _parse_json_prompts(text: str) -> list[str]:
    data = json.loads(text)
    if isinstance(data, list):
        return [_extract_prompt(item) for item in data]
    if isinstance(data, dict):
        if "prompts" in data:
            return [_extract_prompt(p) for p in data["prompts"]]
        return [_extract_prompt(data)]
    raise ValueError("JSON must be a list of prompts or an object with 'prompts' key")


def _parse_jsonl_prompts(text: str) -> list[str]:
    prompts = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            prompts.append(_extract_prompt(json.loads(line)))
        except json.JSONDecodeError:
            prompts.append(line)
    return prompts


def _extract_prompt(item: str | dict) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        if "messages" in item and isinstance(item["messages"], list):
            return _messages_to_prompt(item["messages"])
        for key in PROMPT_KEYS:
            if key in item and isinstance(item[key], str):
                return item[key]
        for v in item.values():
            if isinstance(v, str):
                return v
    raise ValueError(f"Cannot extract prompt from: {type(item).__name__}")
