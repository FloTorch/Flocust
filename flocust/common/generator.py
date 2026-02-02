"""Synthetic prompt generation (lorem or code theme)."""

import json
import random
from pathlib import Path

CHARS_PER_TOKEN = 4
LOREM = (
    "Lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod tempor "
    "incididunt ut labore et dolore magna aliqua Ut enim ad minim veniam quis nostrud "
    "exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat Duis aute "
    "irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat "
    "nulla pariatur Excepteur sint occaecat cupidatat non proident sunt in culpa "
    "qui officia deserunt mollit anim id est laborum"
).split()
CODE_FUNCS = (
    "Foo", "Bar", "Baz", "Quux", "Handler", "Process", "Run",
    "Execute", "Parse", "Validate",
)


def _build_lorem(target_chars: int) -> str:
    parts = []
    while sum(len(p) for p in parts) + (len(parts) - 1 if parts else 0) < target_chars:
        word = random.choice(LOREM)
        parts.append(" " + word if parts else word)
    s = "".join(parts)
    return s[:target_chars] if len(s) > target_chars else s


def _build_code(target_chars: int) -> str:
    parts = []
    while len("".join(parts)) < target_chars:
        f = random.choice(CODE_FUNCS)
        parts.append(f"func {f}() {{\n  // placeholder logic\n}}\n\n")
    s = "".join(parts)
    return s[:target_chars] if len(s) > target_chars else s


def build_prompt(target_chars: int, theme: str) -> str:
    """Build one prompt of approximately target_chars. Theme: 'lorem' or 'code'."""
    return _build_code(target_chars) if theme == "code" else _build_lorem(target_chars)


def generate_prompts(
    count: int,
    input_tokens: int = 500,
    theme: str = "lorem",
    format: str = "json",
) -> list[str]:
    """Generate synthetic prompts. Target length ~ input_tokens * 4 chars per prompt."""
    target_chars = max(100, input_tokens * CHARS_PER_TOKEN)
    count = max(1, count)
    theme = (theme or "lorem").lower()
    theme = theme if theme in ("lorem", "code") else "lorem"
    return [build_prompt(target_chars, theme) for _ in range(count)]


def generate_to_file(
    path: Path,
    count: int,
    input_tokens: int = 500,
    theme: str = "lorem",
    format: str = "json",
) -> None:
    """Write generated prompts to path. Format: 'json' (array) or 'text' (one per line)."""
    prompts = generate_prompts(
        count=count, input_tokens=input_tokens, theme=theme, format=format
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    if format == "json":
        path.write_text(json.dumps(prompts, indent=2), encoding="utf-8")
    else:
        path.write_text("\n".join(prompts), encoding="utf-8")
