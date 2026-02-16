"""Synthetic prompt generation (AIPerf-style corpus-based or code theme)."""

import json
import random
from pathlib import Path
from typing import Literal

EncodingName = Literal["cl100k_base", "o200k_base", "p50k_base", "r50k_base"]
CHARS_PER_TOKEN = 4

# Bundled corpus path (sonnet.txt next to this module, like AIPerf's assets/shakespeare.txt)
_CORPUS_DIR = Path(__file__).resolve().parent
DEFAULT_CORPUS_FILE = _CORPUS_DIR / "sonnet.txt"

_CODE_FUNCS = (
    "Foo", "Bar", "Baz", "Quux", "Handler", "Process", "Run",
    "Execute", "Parse", "Validate",
)

# Cache corpus words by path (lazy-loaded, AIPerf-style)
_corpus_cache: dict[Path, list[str]] = {}


def _load_corpus_words(corpus_path: Path | None = None) -> list[str]:
    """Load corpus file and return list of words (AIPerf-style: one text corpus, sample from it)."""
    path = (corpus_path or DEFAULT_CORPUS_FILE).resolve()
    if path in _corpus_cache:
        return _corpus_cache[path]
    if not path.exists():
        raise FileNotFoundError(
            f"Corpus file not found: {path}. "
            "Synthetic prompt generation requires sonnet.txt (or another corpus) in flocust/common."
        )
    text = path.read_text(encoding="utf-8")
    # Split on whitespace and filter empty; preserves natural phrasing when we sample contiguous runs
    words = [w for line in text.splitlines() for w in line.split() if w]
    if not words:
        raise ValueError(f"Corpus file is empty: {path}")
    _corpus_cache[path] = words
    return words


def _build_from_corpus(target_chars: int, corpus_path: Path | None = None) -> str:
    """Build a prompt by sampling contiguous words from the corpus (AIPerf-style)."""
    words = _load_corpus_words(corpus_path)
    corpus_size = len(words)
    if corpus_size == 0:
        raise ValueError("Corpus has no words")
    parts = []
    # Start at a random position and take contiguous words (with wrap) to reach target_chars
    start = random.randrange(corpus_size)
    idx = start
    while sum(len(p) for p in parts) + (len(parts) - 1 if parts else 0) < target_chars:
        word = words[idx % corpus_size]
        parts.append(" " + word if parts else word)
        idx += 1
    s = "".join(parts)
    return s[:target_chars] if len(s) > target_chars else s


def _build_code(target_chars: int) -> str:
    parts = []
    while len("".join(parts)) < target_chars:
        f = random.choice(_CODE_FUNCS)
        parts.append(f"func {f}() {{\n  // placeholder logic\n}}\n\n")
    s = "".join(parts)
    return s[:target_chars] if len(s) > target_chars else s


def build_prompt(
    target_chars: int,
    theme: str,
    corpus_path: Path | None = None,
) -> str:
    """Build one prompt of approximately target_chars.
    Theme: 'sonnet' or 'lorem' (corpus-based, uses sonnet.txt) or 'code'.
    """
    if theme == "code":
        return _build_code(target_chars)
    return _build_from_corpus(target_chars, corpus_path=corpus_path)


def generate_prompts(
    count: int,
    input_tokens: int = 500,
    theme: str = "sonnet",
    format: str = "json",
    corpus_path: Path | None = None,
    encoding: EncodingName = "cl100k_base",
) -> list[str]:
    """Generate synthetic prompts from corpus (AIPerf-style) or code theme.
    Target length by character heuristic (~ input_tokens * 4 chars). No normalization.
    Theme: 'sonnet', 'lorem' (both use sonnet.txt corpus), or 'code'.
    """
    target_chars = max(100, input_tokens * CHARS_PER_TOKEN)
    count = max(1, count)
    theme = (theme or "sonnet").lower()
    if theme not in ("sonnet", "lorem", "code"):
        theme = "sonnet"
    return [build_prompt(target_chars, theme, corpus_path=corpus_path) for _ in range(count)]


def generate_to_file(
    path: Path,
    count: int,
    input_tokens: int = 500,
    theme: str = "sonnet",
    format: str = "json",
    corpus_path: Path | None = None,
    encoding: EncodingName = "cl100k_base",
) -> None:
    """Write generated prompts to path. Format: 'json' (array) or 'text' (one per line)."""
    prompts = generate_prompts(
        count=count,
        input_tokens=input_tokens,
        theme=theme,
        format=format,
        corpus_path=corpus_path,
        encoding=encoding,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    if format == "json":
        path.write_text(json.dumps(prompts, indent=2), encoding="utf-8")
    else:
        path.write_text("\n".join(prompts), encoding="utf-8")
