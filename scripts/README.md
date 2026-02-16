# Standalone Prompt Generator

This directory contains standalone utilities that are independent of the main Flocust package.

## generate_prompts.py

Generates JSONL files with prompts for load testing, with configurable prompt count and **exact token counts** using tiktoken.

### Features

- **Accurate**: Uses tiktoken for exact token counting (matches Flocust's measurement)
- **Standalone**: No dependencies on Flocust internals (uses tiktoken directly)
- **Flexible**: Built-in paragraph or custom text file
- **Multi-encoder support**: Choose encoding for different model families (GPT-3.5, GPT-4, GPT-4o)
- **Variation**: Generates diverse prompts by varying the starting offset
- **Format compatible**: Outputs JSONL format compatible with Flocust's `input_file` config

### Usage

```bash
# Generate 100 prompts with exactly 128 tokens (GPT-3.5/4 encoding - default)
python scripts/generate_prompts.py --num-prompts 100 --tokens 128 --output prompts_128.jsonl

# Generate 50 prompts with exactly 2048 tokens for GPT-4o
python scripts/generate_prompts.py --num-prompts 50 --tokens 2048 --encoding o200k_base --output prompts_2048.jsonl

# Use custom paragraph from file
python scripts/generate_prompts.py -n 1000 -t 512 -p my_paragraph.txt -o custom_prompts.jsonl

# Short form with different encoding
python scripts/generate_prompts.py -n 100 -t 256 -e o200k_base -o prompts.jsonl

# Generate identical prompts (no variation)
python scripts/generate_prompts.py --num-prompts 10 --tokens 256 --no-vary --output identical.jsonl
```

### Arguments

- `--num-prompts, -n`: Number of prompts to generate (required)
- `--tokens, -t`: Target exact tokens per prompt (required)
- `--output, -o`: Output JSONL file path (default: `input_examples/prompts_generated.jsonl`)
- `--encoding, -e`: Tiktoken encoding (default: `cl100k_base`)
  - `cl100k_base`: GPT-3.5-turbo, GPT-4, GPT-4-turbo (default)
  - `o200k_base`: GPT-4o, GPT-4o-mini
  - `p50k_base`: GPT-3 (davinci, etc.)
  - `r50k_base`: GPT-3 (ada, babbage, curie)
- `--paragraph-file, -p`: Path to custom paragraph text file (optional)
- `--no-vary`: Generate identical prompts instead of varying start offset

### Output Format

Each line in the output file is a JSON object:

```json
{"text": "Your generated prompt text here..."}
```

This format is directly compatible with Flocust's load testing. Point your `config.json` `input_file` to the generated file:

```json
{
  "input_file": "./prompts_128.jsonl",
  ...
}
```

### Token Counting

The script uses **tiktoken** for accurate token counting, the same library used by OpenAI and Flocust internally. This ensures:

- **Exact token counts**: Generated prompts have exactly the specified number of tokens
- **Consistency**: Token counts match what Flocust measures during load tests
- **Model-specific**: Choose the right encoding for your target model family

The token counts are accurate within ±1 token of the target (due to word boundaries). The script builds text incrementally and uses tiktoken to count after each addition, stopping when the target is reached.

### Choosing the Right Encoding

| Encoding | Models | Use When |
|----------|--------|----------|
| `cl100k_base` (default) | GPT-3.5-turbo, GPT-4, GPT-4-turbo, text-embedding-ada-002 | Testing most OpenAI models |
| `o200k_base` | GPT-4o, GPT-4o-mini | Testing GPT-4o family |
| `p50k_base` | GPT-3 (davinci), Codex | Testing older GPT-3 models |
| `r50k_base` | GPT-3 (ada, babbage, curie) | Testing base GPT-3 models |

**Tip**: For non-OpenAI models, use `cl100k_base` as a reasonable default. Most modern LLM APIs use similar tokenization.
