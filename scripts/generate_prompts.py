#!/usr/bin/env python3
"""
Standalone prompt generator for Flocust load testing.

Generates a JSONL file with a given number of prompts, each with exactly
the specified number of tokens using tiktoken for accurate counting.

Usage:
    python scripts/generate_prompts.py --num-prompts 100 --tokens 128 --output prompts.jsonl
    python scripts/generate_prompts.py --num-prompts 50 --tokens 2048 --encoding o200k_base --output prompts.jsonl
"""

import argparse
import json
import sys
from functools import lru_cache
from pathlib import Path
from typing import List

import tiktoken


# Built-in paragraph (public domain / generic prose)
DEFAULT_PARAGRAPH = """
The quick brown fox jumps over the lazy dog near the riverbank on a sunny afternoon.
Birds chirp melodiously in the tall oak trees while gentle breezes rustle through the leaves.
Children play in the meadow, their laughter echoing across the green fields.
An old stone bridge spans the crystal-clear stream where fish swim lazily beneath the surface.
The village clock tower chimes the hour as people go about their daily routines.
Markets bustle with activity as vendors sell fresh produce and handmade crafts.
The aroma of freshly baked bread wafts from the bakery down the cobblestone street.
Horses pull wooden carts loaded with hay and supplies for the neighboring farms.
As evening approaches, lanterns begin to glow in cottage windows throughout the countryside.
Stars emerge one by one in the darkening sky, painting a celestial canvas overhead.
Crickets sing their nocturnal symphony while owls hoot softly from distant trees.
The world settles into peaceful slumber as another day comes to a gentle close.
""".strip()


@lru_cache(maxsize=4)
def get_encoding(name: str) -> tiktoken.Encoding:
    """Get tiktoken encoding by name (cached)."""
    return tiktoken.get_encoding(name)


def count_tokens(text: str, encoding: str = "cl100k_base") -> int:
    """
    Count tokens using tiktoken for accurate token counting.
    
    Args:
        text: Input text string
        encoding: Tiktoken encoding name
            - cl100k_base: GPT-3.5-turbo, GPT-4, GPT-4-turbo (default)
            - o200k_base: GPT-4o, GPT-4o-mini
            - p50k_base: GPT-3 models (davinci, etc.)
            - r50k_base: GPT-3 models (ada, babbage, curie)
        
    Returns:
        Exact token count
    """
    if not text:
        return 0
    enc = get_encoding(encoding)
    return len(enc.encode(text))


def generate_prompt_text(source_text: str, target_tokens: int, encoding: str, offset: int = 0) -> str:
    """
    Generate a single prompt with exactly target_tokens tokens.
    
    Repeats and trims the source text to reach the exact target token count.
    Uses an offset to vary the starting position for diversity.
    
    Args:
        source_text: Base paragraph to repeat
        target_tokens: Target exact token count
        encoding: Tiktoken encoding name for token counting
        offset: Word offset for starting position (for variation)
        
    Returns:
        Generated prompt text with exactly target_tokens tokens
    """
    words = source_text.split()
    if not words:
        raise ValueError("Source text is empty")
    
    # Handle very small target
    if target_tokens < 1:
        return words[0] if words else ""
    
    # Create a large pool of words by repeating the source
    # We'll build incrementally and check token count
    start_idx = offset % len(words)
    
    # Build text incrementally until we reach or exceed target
    current_words = []
    word_idx = start_idx
    current_text = ""
    current_tokens = 0
    
    # Keep adding words until we're close to target
    # We'll repeat the word list as needed
    max_iterations = target_tokens * 3  # Safety limit
    iteration = 0
    
    while current_tokens < target_tokens and iteration < max_iterations:
        current_words.append(words[word_idx % len(words)])
        current_text = " ".join(current_words)
        current_tokens = count_tokens(current_text, encoding)
        word_idx += 1
        iteration += 1
    
    # If we overshot, try removing words one by one until we hit target or go under
    while current_tokens > target_tokens and len(current_words) > 1:
        current_words.pop()
        current_text = " ".join(current_words)
        current_tokens = count_tokens(current_text, encoding)
    
    return current_text


def generate_prompts(
    num_prompts: int,
    tokens_per_prompt: int,
    source_text: str,
    encoding: str,
    vary_prompts: bool = True
) -> List[str]:
    """
    Generate multiple prompts with exact token counts.
    
    Args:
        num_prompts: Number of prompts to generate
        tokens_per_prompt: Target exact tokens per prompt
        source_text: Base text to use for generation
        encoding: Tiktoken encoding name
        vary_prompts: If True, vary starting offset for each prompt
        
    Returns:
        List of generated prompt texts
    """
    prompts = []
    source_words = source_text.split()
    step = max(1, len(source_words) // max(1, num_prompts)) if vary_prompts else 0
    
    for i in range(num_prompts):
        offset = (i * step) if vary_prompts else 0
        prompt_text = generate_prompt_text(source_text, tokens_per_prompt, encoding, offset)
        prompts.append(prompt_text)
    
    return prompts


def write_jsonl(prompts: List[str], output_path: Path) -> None:
    """
    Write prompts to JSONL file.
    
    Each line is a JSON object: {"text": "prompt content"}
    
    Args:
        prompts: List of prompt texts
        output_path: Output file path
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        for prompt in prompts:
            json_line = json.dumps({"text": prompt}, ensure_ascii=False)
            f.write(json_line + '\n')


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate prompts for Flocust load testing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --num-prompts 100 --tokens 128 --output prompts_128.jsonl
  %(prog)s --num-prompts 50 --tokens 2048 --encoding o200k_base --output prompts_2048.jsonl
  %(prog)s -n 1000 -t 512 -e cl100k_base -o test_prompts.jsonl
  %(prog)s -n 100 -t 256 -p custom.txt -o custom_prompts.jsonl
        """
    )
    
    parser.add_argument(
        '--num-prompts', '-n',
        type=int,
        required=True,
        help='Number of prompts to generate'
    )
    
    parser.add_argument(
        '--tokens', '-t',
        type=int,
        required=True,
        help='Target exact tokens per prompt (uses tiktoken for accurate counting)'
    )
    
    parser.add_argument(
        '--output', '-o',
        type=str,
        default='input_examples/prompts_generated.jsonl',
        help='Output JSONL file path (default: input_examples/prompts_generated.jsonl)'
    )
    
    parser.add_argument(
        '--encoding', '-e',
        type=str,
        default='cl100k_base',
        choices=['cl100k_base', 'o200k_base', 'p50k_base', 'r50k_base'],
        help='Tiktoken encoding: cl100k_base (GPT-3.5/4, default), o200k_base (GPT-4o), p50k_base/r50k_base (GPT-3)'
    )
    
    parser.add_argument(
        '--paragraph-file', '-p',
        type=str,
        default=None,
        help='Optional: path to text file with custom paragraph (default: use built-in)'
    )
    
    parser.add_argument(
        '--no-vary',
        action='store_true',
        help='Generate identical prompts instead of varying start offset'
    )
    
    args = parser.parse_args()
    
    # Validate arguments
    if args.num_prompts <= 0:
        print("Error: --num-prompts must be positive", file=sys.stderr)
        return 1
    
    if args.tokens <= 0:
        print("Error: --tokens must be positive", file=sys.stderr)
        return 1
    
    # Load source text
    if args.paragraph_file:
        paragraph_path = Path(args.paragraph_file)
        if not paragraph_path.exists():
            print(f"Error: Paragraph file not found: {paragraph_path}", file=sys.stderr)
            return 1
        try:
            source_text = paragraph_path.read_text(encoding='utf-8').strip()
        except Exception as e:
            print(f"Error reading paragraph file: {e}", file=sys.stderr)
            return 1
    else:
        source_text = DEFAULT_PARAGRAPH
    
    if not source_text:
        print("Error: Source text is empty", file=sys.stderr)
        return 1
    
    # Generate prompts
    print(f"Generating {args.num_prompts} prompts with exactly {args.tokens} tokens each...")
    print(f"Using {'custom' if args.paragraph_file else 'built-in'} paragraph")
    print(f"Encoding: {args.encoding}")
    print(f"Output: {args.output}")
    
    try:
        prompts = generate_prompts(
            num_prompts=args.num_prompts,
            tokens_per_prompt=args.tokens,
            source_text=source_text,
            encoding=args.encoding,
            vary_prompts=not args.no_vary
        )
        
        # Verify token counts (sample first prompt)
        if prompts:
            sample_tokens = count_tokens(prompts[0], args.encoding)
            print(f"Sample: First prompt has {sample_tokens} tokens (target: {args.tokens})")
        
        # Write output
        output_path = Path(args.output)
        write_jsonl(prompts, output_path)
        
        print(f"[OK] Successfully generated {len(prompts)} prompts")
        print(f"[OK] Written to: {output_path.absolute()}")
        
        # Stats
        actual_tokens = [count_tokens(p, args.encoding) for p in prompts[:min(10, len(prompts))]]
        if actual_tokens:
            avg = sum(actual_tokens) / len(actual_tokens)
            min_tok = min(actual_tokens)
            max_tok = max(actual_tokens)
            print(f"[OK] Token stats (first {len(actual_tokens)} prompts): min={min_tok}, max={max_tok}, avg={avg:.1f}")
        
        return 0
        
    except Exception as e:
        print(f"Error generating prompts: {e}", file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
