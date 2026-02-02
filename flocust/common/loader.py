"""Load prompts from JSON or JSONL files."""

import json
from pathlib import Path

# Keys to try when extracting prompt text from a JSON object.
PROMPT_KEYS = ("prompt", "text", "content", "input", "message")


def load_prompts(path: Path) -> list[str]:
    """
    Load prompts from a JSON or JSONL file.

    - JSON: expects a list of strings or a list of objects with a 'prompt' or 'text' key.
    - JSONL: one JSON object per line with optional 'prompt' or 'text' key, or raw string per line.

    Returns:
        List of prompt strings.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Prompts file not found: {path}")

    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []

    # Try JSON first (array or single object)
    if path.suffix.lower() == ".json":
        return _parse_json_prompts(text)
    if path.suffix.lower() == ".jsonl":
        return _parse_jsonl_prompts(text)
    # Default: try JSON then JSONL
    try:
        return _parse_json_prompts(text)
    except (json.JSONDecodeError, TypeError):
        return _parse_jsonl_prompts(text)


def _parse_json_prompts(text: str) -> list[str]:
    data = json.loads(text)
    if isinstance(data, list):
        return [_extract_prompt(item) for item in data]
    if isinstance(data, dict):
        # Single object or {"prompts": [...]}
        if "prompts" in data:
            return [_extract_prompt(p) for p in data["prompts"]]
        return [_extract_prompt(data)]
    raise ValueError("JSON must be a list of prompts or an object with 'prompts' key")


def _parse_jsonl_prompts(text: str) -> list[str]:
    prompts: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            prompts.append(_extract_prompt(obj))
        except json.JSONDecodeError:
            # Treat line as raw prompt
            prompts.append(line)
    return prompts


def _extract_prompt(item: str | dict) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        for key in PROMPT_KEYS:
            if key in item and isinstance(item[key], str):
                return item[key]
        for v in item.values():
            if isinstance(v, str):
                return v
    raise ValueError(f"Cannot extract prompt from: {type(item).__name__}")
