"""Synthetic prompt generation (lorem or code theme)."""

import json
import math
import os
import random
import warnings
from pathlib import Path
from typing import Tuple

os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "1"
warnings.filterwarnings("ignore", message=".*PyTorch.*")

from transformers import LlamaTokenizerFast

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


def sample_random_positive_int(mean: int, stddev: int) -> int:
    """Sample random numbers from a gaussian distribution until a positive number is sampled.

    Args:
        mean: The mean of the gaussian distribution to sample from.
        stddev: The standard deviation of the gaussian distribution to sample from.

    Returns:
        A random positive integer sampled from the gaussian distribution.
    """
    ret = -1
    while ret <= 0:
        ret = int(random.gauss(mean, stddev))
    return ret


def randomly_sample_lines_prompt(
    prompt_tokens_mean: int = 550,
    prompt_tokens_stddev: int = 250,
    expect_output_tokens: int = 150,
    source_file_path: Path | str | None = None,
    tokenizer = None
) -> Tuple[str, int]:
    """Generate a prompt that randomly samples lines from a source text file.

    Args:
        prompt_tokens_mean: The mean length of the prompt to generate.
        prompt_tokens_stddev: The standard deviation of the length of the prompt to generate.
        expect_output_tokens: The number of tokens to expect in the output. This is used to
        determine the length of the prompt. The prompt will be generated such that the output
        will be approximately this many tokens.
        source_file_path: Path to source text file. If None, defaults to a default text file in the same directory.
        tokenizer: Optional tokenizer instance. If None, will create LlamaTokenizerFast.

    Note:
        tokens will be counted from the source file using the Llama tokenizer. Using one tokenizer
        ensures a fairer comparison across different LLMs. For example, if gpt 3.5 tokenizes
        a prompt in less tokens than Llama2, then this will be reflected in the results since
        they will be fed identical prompts.

    Returns:
        A tuple of the prompt and the length of the prompt.
    """
    if tokenizer is None:
        tokenizer = LlamaTokenizerFast.from_pretrained(
            "hf-internal-testing/llama-tokenizer"
        )

    get_token_length = lambda text: len(tokenizer.encode(text))

    prompt = (
        "Randomly stream lines from the following text "
        f"with {expect_output_tokens} output tokens. "
        "Don't generate eos tokens:\n\n"
    )
    
    num_prompt_tokens = sample_random_positive_int(
        prompt_tokens_mean, prompt_tokens_stddev
    )
    while num_prompt_tokens < get_token_length(prompt):
        num_prompt_tokens = sample_random_positive_int(
            prompt_tokens_mean, prompt_tokens_stddev
        )
    remaining_prompt_tokens = num_prompt_tokens - get_token_length(prompt)

    if source_file_path is None:
        source_file_path = Path(__file__).parent.resolve() / "sonnet.txt"
    else:
        source_file_path = Path(source_file_path)
        if not source_file_path.is_absolute():
            source_file_path = source_file_path.resolve()
    
    if not source_file_path.exists():
        raise FileNotFoundError(f"Source file not found: {source_file_path}")
    
    with open(source_file_path, "r", encoding="utf-8") as f:
        source_lines = f.readlines()
    random.shuffle(source_lines)
    sampling_lines = True
    while sampling_lines:
        for line in source_lines:
            line_to_add = line
            if remaining_prompt_tokens - get_token_length(line_to_add) < 0:
                line_to_add = line_to_add[: int(math.ceil(remaining_prompt_tokens))]
                sampling_lines = False
                prompt += line_to_add
                break
            prompt += line_to_add
            remaining_prompt_tokens -= get_token_length(line_to_add)
    return (prompt, num_prompt_tokens)


def generate_prompts_from_file(
    count: int,
    mean_input_tokens: int = 550,
    stddev_input_tokens: int = 250,
    mean_output_tokens: int = 150,
    source_file_path: Path | str | None = None,
) -> list[str]:
    """Generate prompts by sampling from a source text file with exact token counts.

    Args:
        count: Number of prompts to generate.
        mean_input_tokens: Mean number of tokens in each prompt.
        stddev_input_tokens: Standard deviation of prompt token count.
        mean_output_tokens: Expected output tokens (used in prompt instruction).
        source_file_path: Path to source text file. If None, defaults to a default text file in the same directory.

    Returns:
        List of prompt strings.
    """
    tokenizer = LlamaTokenizerFast.from_pretrained(
        "hf-internal-testing/llama-tokenizer"
    )
    prompts = []
    for _ in range(count):
        prompt, _ = randomly_sample_lines_prompt(
            prompt_tokens_mean=mean_input_tokens,
            prompt_tokens_stddev=stddev_input_tokens,
            expect_output_tokens=mean_output_tokens,
            source_file_path=source_file_path,
            tokenizer=tokenizer,
        )
        prompts.append(prompt)
    return prompts
