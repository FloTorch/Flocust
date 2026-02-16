"""Fast token counting and prompt normalization using tiktoken (OpenAI-style encodings)."""

from functools import lru_cache
from typing import Literal

import tiktoken

EncodingName = Literal["cl100k_base", "o200k_base", "p50k_base", "r50k_base"]


@lru_cache(maxsize=4)
def get_encoding(name: EncodingName) -> tiktoken.Encoding:
    """Get tiktoken encoding by name (cached)."""
    return tiktoken.get_encoding(name)


def normalize_prompt_to_tokens(
    text: str,
    target_tokens: int,
    encoding_name: EncodingName = "cl100k_base",
) -> str:
    """
    Return a string that tokenizes to exactly target_tokens.
    Trims from the end if over; pads with spaces if under (for consistent benchmark input size).
    """
    if target_tokens <= 0:
        return ""
    enc = get_encoding(encoding_name)
    tokens = enc.encode(text)
    if len(tokens) >= target_tokens:
        return enc.decode(tokens[:target_tokens])
    # Pad with last token (or space if empty) so decoded length is exactly target_tokens
    pad_id = tokens[-1] if tokens else enc.encode(" ")[0]
    padded = tokens + [pad_id] * (target_tokens - len(tokens))
    return enc.decode(padded)


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
