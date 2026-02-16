<p align="center">
  <img src="assets/flotorch_logo.png" alt="FlotorchEval Logo" width="200" />
</p>

<h2 align="center">FlotorchEval</h2>
<p align="center"><strong>Load testing and evaluation for any OpenAI-compatible chat completions API</strong></p>

<p align="center">
  <a href="https://pypi.org/project/flocust/"><img src="https://img.shields.io/badge/PyPI-0.1.0-3776AB?logo=pypi&logoColor=white" alt="PyPI version" /></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-3776AB?logo=python&logoColor=white" alt="Python versions" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License" /></a>

  <a href="https://flotorch.cloud"><img src="https://img.shields.io/badge/Website-flotorch.cloud-blue" alt="Website" /></a>
</p>

<p align="center">
  <a href="#installation">Installation</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#prompt-generation">Prompt Generation</a> •
  <a href="#examples">Examples</a> •
  <a href="#documentation">Documentation</a> •
  <a href="#contributing">Contributing</a>
</p>

---

## About

**FlotorchEval** (CLI: `flocust`) is a load-testing and evaluation tool for **any** service that exposes an OpenAI-style **chat completions** endpoint (`POST /chat/completions`). It is not limited to the Flotorch ecosystem—use it with **OpenAI**, **Azure OpenAI**, **Flotorch**, or any gateway/proxy that speaks the same API.

- **Load test** — Run many concurrent requests with configurable RPS and concurrency; measure latency, throughput, and token usage.
- **Streaming & non-streaming** — Supports both; when streaming is enabled, reports time-to-first-token (TTFT) and inter-token latency.
- **Token metrics** — Input/output tokens and tokens-per-second from response headers (e.g. `x-input-tokens`, `x-completion-tokens`) or from the response body `usage` when the API provides it.
- **CLI and REST API** — Run from the command line (config file or interactive prompts) or via a FastAPI server for automated pipelines.

Outputs: per-request `results.jsonl`, aggregated `report.json`, and a console dashboard with latency and token statistics.

**Works with:** OpenAI, Azure OpenAI, Flotorch, and any other service that exposes an OpenAI-compatible `POST /chat/completions` endpoint.

---

## Installation

**Requirements:** Python 3.10+. Any HTTP endpoint that implements the OpenAI chat completions API (e.g. OpenAI, Azure OpenAI, Flotorch, or a custom proxy).

```bash
pip install -e .
# or
pip install -r requirements.txt
```

Verify:

```bash
flocust
# or
python -m flocust.cli.main
```

---

## Quick Start

**Option 1 — Config file**

Create a JSON config (see [Configuration](#configuration)) and run:

```bash
flocust --config path/to/config.json
```

**Option 2 — Interactive**

Run without a config; the CLI will prompt for base URL, API key, model, concurrency, requests, prompts file, etc.:

```bash
flocust
```

Output is written under `artifacts/<model>-users<N>-rps<R>/` with `results.jsonl`, `report.json`, and a console dashboard.

---

## Prompt generation

Generate JSONL prompt files with **exact token counts** using the standalone script (uses tiktoken; no Flocust imports). Output goes to `input_examples/` by default and is compatible with `input_file` in your config.

| Command | Description |
|--------|-------------|
| `python scripts/generate_prompts.py -n 100 -t 128` | 100 prompts, 128 tokens each (default encoding; writes to `input_examples/prompts_generated.jsonl`) |
| `python scripts/generate_prompts.py -n 1000 -t 1024 -o input_examples/prompts_1024.jsonl` | 1000 prompts, 1024 tokens each, custom path |
| `python scripts/generate_prompts.py -n 50 -t 2048 -e o200k_base` | 50 prompts, 2048 tokens, GPT-4o encoding |
| `python scripts/generate_prompts.py -n 100 -t 512 -p my_text.txt -o custom.jsonl` | Custom paragraph from file |

**Options:** `-n` / `--num-prompts`, `-t` / `--tokens`, `-o` / `--output` (default: `input_examples/prompts_generated.jsonl`), `-e` / `--encoding` (`cl100k_base` \| `o200k_base` \| `p50k_base` \| `r50k_base`), `-p` / `--paragraph-file`, `--no-vary` (identical prompts).

Then point your config at the generated file:

```json
"input_file": "./input_examples/prompts_generated.jsonl"
```

See [scripts/README.md](scripts/README.md) for full details and encoding guide.

---

## Examples

- **Config-based run:** `flocust -c config.json` — point `base_url` in the config to your endpoint (OpenAI, Azure, Flotorch, or any OpenAI-compatible API).
- **Interactive run:** `flocust` — you’ll be prompted for base URL, API key, model, concurrency, requests, and prompts file.
- **API run:** `POST /api/run` with `prompts_file` or `generate_prompts=true` (see [REST API](#rest-api)) — useful for CI or remote runs against any chat completions endpoint.

---

## Configuration

Use a JSON config file when running with `--config`. Set `base_url` to your provider (e.g. `https://api.openai.com/v1`, `https://your-gateway.com/openai/v1`). Paths in the config are relative to the config file directory.

| Section | Key fields |
|--------|-------------|
| **provider_settings** | `api_key`, `model`, `base_url` (supports `$ENV_VAR`) |
| **bench** | `concurrency`, `requests`, `duration_sec`, `requests_per_second`, `timeout_sec`, `max_tokens`, `stream`, `generate_prompts`, `generate_prompts_count` |
| **input_file** | Path to prompts file (JSON/JSONL). Required if `generate_prompts` is false. |
| **report** | `format`: `"console"` or `"json"` |

**Example `config.json`**

```json
{
  "provider": "openai",
  "provider_settings": {
    "api_key": "$OPENAI_API_KEY",
    "model": "gpt-4o-mini",
    "base_url": "https://api.openai.com/v1"
  },
  "bench": {
    "concurrency": 10,
    "requests": 100,
    "requests_per_second": 5.0,
    "duration_sec": 0,
    "ramp_up_sec": 0,
    "timeout_sec": 60,
    "max_tokens": 1024,
    "stream": true,
    "generate_prompts": false,
    "generate_prompts_count": null
  },
  "input_file": "prompts.jsonl",
  "report": { "format": "console" }
}
```

- `duration_sec > 0`: run for that many seconds; otherwise the run stops after `requests` are completed.
- `generate_prompts: true`: prompts are generated via a one-shot LLM call; you can omit `input_file` and set `generate_prompts_count` (1–1000).

---

## Running the CLI

| Mode | Command |
|------|--------|
| With config | `flocust -c config.json` |
| Interactive | `flocust` (no `-c`) |

Interactive prompts include: base URL, API key, model, concurrency, duration vs request count, RPS, timeout, max tokens, streaming, prompts source (file or LLM-generated), and prompts file path when using a file.

---

## REST API

Start the server:

```bash
uvicorn flocust.api.main:app --host 0.0.0.0 --port 8000
```

- **Docs:** `http://localhost:8000/docs`
- **Health:** `GET /health`
- **Run load test:** `POST /api/run` (multipart: upload `prompts_file` **or** set `generate_prompts=true`; required: `api_key`, `model`)
- **Download report:** `GET /api/report?report_id=<id>`

**Example**

```bash
curl -X POST http://localhost:8000/api/run \
  -F "prompts_file=@prompts.jsonl" \
  -F "base_url=https://api.openai.com/v1" \
  -F "api_key=YOUR_API_KEY" \
  -F "model=gpt-4o-mini" \
  -F "concurrency=2" \
  -F "num_requests=10" \
  -F "max_tokens=1024"
```

---

## Output

After each run you get:

- **results.jsonl** — One JSON line per request: `req_id`, `input_prompt`, `output_result`, `latency_ms`, `ttft_ms`, `input_tokens`, `output_tokens`, `tokens_per_sec`, inter-token latencies, `success`, `error`. Token counts are read from response headers (e.g. `x-input-tokens`, `x-completion-tokens`) or from the body `usage` object when the API provides it.
- **report.json** — Aggregated metrics: latency/TTFT/inter-token percentiles (p50/p90/p95/p99), total and per-request token stats, actual RPS.
- **Console** — A dashboard table (TTFT, request latency, inter-token latency, input/output tokens, tokens/sec with avg/min/max/percentiles) and a one-line summary.

Artifacts are written under `artifacts/<model-slug>-users<N>-rps<R>/`.

---

## Project structure

```
Flocust/
├── flocust/
│   ├── api/          # FastAPI: /health, POST /api/run, GET /api/report
│   ├── cli/          # CLI entry (flocust), interactive prompts
│   ├── common/       # config, loader, runner, analyzer, dashboard, models
│   └── config.sample.json
├── scripts/
│   ├── generate_prompts.py   # Standalone prompt generator (tiktoken, exact token counts)
│   └── README.md
├── input_examples/    # Example and generated prompt files (.jsonl)
├── prompts.jsonl
├── pyproject.toml
├── requirements.txt
├── TECHNICAL_OVERVIEW.md
└── README.md
```

---

## Contributing

Contributions are welcome. Open an issue or submit a pull request.

---

## License

MIT.
