"""Fast token counting using tiktoken (OpenAI-style encodings)."""

from functools import lru_cache
from typing import Literal

import tiktoken

EncodingName = Literal["cl100k_base", "o200k_base", "p50k_base", "r50k_base"]


@lru_cache(maxsize=4)
def get_encoding(name: EncodingName) -> tiktoken.Encoding:
    """Get tiktoken encoding by name (cached)."""
    return tiktoken.get_encoding(name)


def count_tokens(text: str, encoding_name: EncodingName = "cl100k_base") -> int:
    """
    Count tokens in text using tiktoken. Fast and suitable for production.

    Args:
        text: Input string.
        encoding_name: Tiktoken encoding (cl100k_base for GPT-4/3.5, o200k_base for GPT-4o).

    Returns:
        Token count.
    """
    if not text:
        return 0
    enc = get_encoding(encoding_name)
    return len(enc.encode(text))


def count_tokens_batch(texts: list[str], encoding_name: EncodingName = "cl100k_base") -> list[int]:
    """Count tokens for multiple texts (efficient batch)."""
    enc = get_encoding(encoding_name)
    return [len(enc.encode(t)) for t in texts]
