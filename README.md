# Flocust

**Flocust** is a production-ready LLM endpoint load testing tool built on [Locust](https://locust.io). It benchmarks OpenAI-compatible chat completion APIs with configurable concurrency and throughput, and reports latency, time-to-first-token (TTFT), inter-token latency, and token usage per request.

---

## Features

- **OpenAI-compatible API** — Targets `POST /chat/completions` with optional streaming for TTFT and inter-token metrics.
- **Configurable load** — Concurrency (virtual users), target requests per second, and total request count or duration.
- **Flexible prompts** — Load from a prompts file (JSON/JSONL) or generate prompts via a one-shot LLM call.
- **Streaming and non-streaming** — Default streaming for full metrics; optional non-streaming for latency-only measurement.
- **Per-request results** — `results.jsonl` with `req_id`, prompt, response, `latency_ms`, `ttft_ms`, `input_tokens`, `output_tokens`, `tokens_per_sec`, inter-token latencies, success/error.
- **Report card** — `report.json` with latency percentiles (p50/p90/p95/p99), TTFT stats, inter-token latency stats, total tokens, **input/output token and tokens/sec distributions** (avg, min, max, std, p50/p90/p99), and actual RPS.
- **Token counting** — [tiktoken](https://github.com/openai/tiktoken) with configurable encoding (e.g. `cl100k_base`, `o200k_base`). When the API does not return usage (e.g. streaming without usage in the stream), Flocust falls back to client-side token counts so you still get `input_tokens`, `output_tokens`, and `tokens_per_sec` for every request.
- **Console dashboard** — After each run, a table shows TTFT, Request Latency, Inter Token Latency, **Input Tokens**, **Output Tokens**, and **Tokens/sec** (each with avg, min, max, p99, p90, p50, std), plus a summary line with total tokens and avg tokens/s. When the API reports prompt cache usage, the dashboard also shows **Prompt cache:** requests with cache hit and total cached tokens.
- **Prompt caching** — Optional **prompt cache** mode: when **disabled** (default), each request gets a unique prefix so the API does not reuse cached prompts (reproducible load tests). When **enabled** (`--prompt-cache` or `prompt_cache: true` in config), prompts are sent as-is so the API can cache; results and report include `cached_tokens` and aggregated cache stats when the API reports them (e.g. OpenAI `prompt_tokens_details.cached_tokens`).
- **CLI** — Run with a config file or interactively (terminal prompts); run load test and view report/dashboard.
- **REST API** — FastAPI server with run endpoint (file upload or prompt generation), report download, and health check.

---

## Prerequisites

- **Python 3.10+**
- An **OpenAI-compatible** chat completions endpoint (e.g. OpenAI, Azure OpenAI, or any provider exposing the same API).
- For TTFT and inter-token metrics, the API must support **streaming** (`stream: true`) and return SSE or JSON chunks.

---

## Installation

From the project root:

```bash
pip install -e .
```

Or install dependencies only:

```bash
pip install -r requirements.txt
```

Verify the CLI:

```bash
flocust
# or
python -m flocust.cli.main
```

---

## Configuration

You can run Flocust in two ways:

1. **Config file** — Pass a JSON config with `-c`/`--config`. All settings are loaded from the file.
2. **Interactive (terminal)** — Run `flocust` without `-c`. The CLI prompts for every parameter in the terminal.

You **must** choose one: either provide a config file path or run interactively. The CLI does not auto-load `config.json` from the current directory when no option is given.

---

### Config file (`config.json`)

Use a JSON file to define provider settings, benchmark parameters, and input/report options. Paths in the file are relative to the config file’s directory.

#### Schema

| Section | Field | Type | Description |
|--------|--------|------|--------------|
| **provider** | — | string | Provider identifier (e.g. `"openai"`). Default: `"openai"`. |
| **provider_settings** | `api_key` | string | API key. Supports `$ENV_VAR` or `env:ENV_VAR` to read from environment. |
| | `model` | string | Model name (e.g. `gpt-4o-mini`, `flotorch/gemini-flash`). |
| | `base_url` | string | LLM API base URL without `/chat/completions` (e.g. `https://api.openai.com/v1`). |
| | `headers` | object | Optional extra HTTP headers. |
| **bench** | `concurrency` | int | Number of concurrent virtual users (1–10000). |
| | `requests` | int | Total requests to run when `duration_sec` is 0 (1–1000000). |
| | `requests_per_second` | float | Target RPS; `0` = max throughput. |
| | `duration_sec` | float | If &gt; 0, run for this many seconds (overrides `requests`). |
| | `ramp_up_sec` | float | Stagger worker start over this many seconds. |
| | `timeout_sec` | int | Per-request timeout in seconds. |
| | `max_tokens` | int | Max completion tokens per request. |
| | `stream` | bool | Use streaming for TTFT/inter-token metrics. |
| | `generate_prompts` | bool | If true, generate prompts via LLM; then `input_file` can be omitted. |
| | `generate_prompts_count` | int \| null | Number of prompts to generate (1–1000); used when `generate_prompts` is true. |
| | `prompt_cache` | bool | If true, send prompts as-is so the API can use prompt caching. If false (default), each request gets a unique prefix so no cache hits (reproducible load tests). |
| **input_file** | — | string | Path to prompts file (JSON or JSONL), relative to config file. Required if `generate_prompts` is false. |
| **report** | `format` | string | Output format: `"console"` or `"json"`. |

#### Environment variables in config

In `api_key`, `base_url`, or `headers` values you can use:

- `$VAR` — replaced by the value of environment variable `VAR`.
- `env:VAR` — same as `$VAR`.

Example: `"api_key": "$OPENAI_API_KEY"` or `"api_key": "env:OPENAI_API_KEY"`. If `provider` is `"openai"` and `api_key` is empty, `OPENAI_API_KEY` is used automatically.

#### Example `config.json`

```json
{
  "provider": "openai",
  "provider_settings": {
    "api_key": "$OPENAI_API_KEY",
    "model": "gpt-4o-mini",
    "base_url": "https://api.openai.com/v1",
    "headers": {}
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
    "generate_prompts_count": null,
    "prompt_cache": false
  },
  "input_file": "prompts.jsonl",
  "report": { "format": "console" }
}
```

- If `duration_sec` is `0`, the run stops after `requests` are completed.
- If `duration_sec` &gt; 0, the run lasts that many seconds and request count is derived from throughput.
- If `generate_prompts` is `true`, you can omit `input_file` or leave it empty; set `generate_prompts_count` (1–1000) to control how many prompts are generated.

---

## Running the CLI

### Option A: With a config file

Specify the config file explicitly. The CLI loads all settings from it and does not prompt.

```bash
flocust --config path/to/config.json
# or
flocust -c path/to/config.json
```

If the file is missing, the CLI exits with an error (e.g. `Config file not found`). To enable **prompt caching** (send prompts as-is so the API can cache), pass `--prompt-cache`:

```bash
flocust -c config.json --prompt-cache
```

### Option B: Interactive (no config file)

Run without `-c`/`--config`. The CLI prompts for every parameter in the terminal.

```bash
flocust
# or
python -m flocust.cli.main
```

You will be prompted for:

| Prompt | Description | Example |
|--------|-------------|---------|
| Base URL | LLM API base URL (without `/chat/completions`) | `https://api.openai.com/v1` |
| API key | Authentication key | (your key) |
| Model name | Model identifier | `gpt-4o-mini` |
| Concurrency (users) | Number of concurrent virtual users | `10` |
| Use duration mode? | `y` = run for N seconds; `n` = run until N requests | `n` |
| Run duration / Number of requests | Seconds or total requests | `100` |
| Ramp-up time (seconds) | Stagger worker start | `0` |
| Requests per second | Target RPS (0 = max throughput) | `5.0` |
| Request timeout (seconds) | Per-request timeout | `60` |
| Max tokens per completion | Cap per response | `1024` |
| Stream responses? | Use streaming (TTFT/inter-token) or not | `y` |
| Enable prompt caching? | `y` = send prompts as-is (API can cache); `n` = unique request per call (default) | `n` |
| Prompts: (f)ile or (l)lm-generated | File path vs generate via LLM | `f` |
| Prompts file path | Path to JSON/JSONL prompts (if file chosen) | `prompts.jsonl` |

Output is written under `artifacts/<model>-users<N>-rps<R>/` (e.g. `artifacts/gpt-4o-mini-users10-rps5/`), containing:

- `results.jsonl` — One JSON object per request: latency, TTFT, input_tokens, output_tokens, tokens_per_sec, inter-token latencies (and per-request percentiles), success/error.
- `report.json` — Aggregated report: latency percentiles, TTFT and inter-token latency stats, total tokens, **input/output token and tokens/sec distributions** (min, max, avg, std, p50/p90/p99), and actual RPS.

A summary and **console dashboard** are printed after the run: a table with TTFT, Request Latency, Inter Token Latency, Input Tokens, Output Tokens, and Tokens/sec (each row: avg, min, max, p99, p90, p50, std), plus a summary line.

---

## Running the FastAPI server

The API exposes a **run** endpoint (multipart form: upload a prompts file **or** set `generate_prompts=true`), a **report download** endpoint, and a **health** endpoint. All errors are handled so that invalid input returns 422 and unexpected failures return 500 with a safe message (details are logged server-side).

### Start the server

From the project root:

```bash
uvicorn flocust.api.main:app --host 0.0.0.0 --port 8000
```

With auto-reload (development):

```bash
uvicorn flocust.api.main:app --reload --host 0.0.0.0 --port 8000
```

- **Base URL:** `http://localhost:8000`
- **Interactive docs:** `http://localhost:8000/docs`
- **OpenAPI JSON:** `http://localhost:8000/openapi.json`

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check. Returns `{"status": "ok"}`. |
| GET | `/` | API info: service name, docs path, OpenAPI path. |
| POST | `/api/run` | Run a load test. **Multipart form:** either upload a prompts file or set `generate_prompts=true`. Returns summary + `report_id`. |
| GET | `/api/report?report_id=<id>` | Download the full report (report + all results) as JSON. File is removed after send; IDs expire after 1 hour. |

### POST `/api/run`

You must provide prompts in **exactly one** way:

- **Upload a prompts file** — Attach `prompts_file` (`.json` or `.jsonl`).
- **Generate prompts** — Set `generate_prompts=true` (optionally `generate_prompts_count`; if omitted or 0, a default is used).

**Required form fields:** `api_key`, `model`  
**Optional form fields (with defaults):** `base_url`, `concurrency`, `requests_per_second`, `num_requests`, `duration_sec`, `ramp_up_sec`, `use_rps_throttle`, `timeout_sec`, `max_tokens`, `encoding`, `stream`, `generate_prompts`, `generate_prompts_count`

**Example — run with prompts file:**

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

**Example — run with generated prompts:**

```bash
curl -X POST http://localhost:8000/api/run \
  -F "base_url=https://api.openai.com/v1" \
  -F "api_key=YOUR_API_KEY" \
  -F "model=gpt-4o-mini" \
  -F "concurrency=2" \
  -F "num_requests=10" \
  -F "max_tokens=1024" \
  -F "generate_prompts=true"
```

**Response:** JSON with a `report` (aggregate metrics) and `report_id`. The full report is written asynchronously; download it with GET `/api/report?report_id=<report_id>`.

### Error responses

- **400** — Bad request (e.g. both file and `generate_prompts` provided, or neither).
- **404** — Report not found or expired for GET `/api/report`.
- **422** — Validation failed (invalid form values or internal config validation); body includes `detail` with error list.
- **500** — Internal server error; body contains a safe message; details are logged on the server.

### Download the full report

```bash
curl -O -J "http://localhost:8000/api/report?report_id=YOUR_REPORT_ID"
```

---

## Project structure

```
Flocust/
├── flocust/
│   ├── __init__.py
│   ├── api/                    # FastAPI application
│   │   ├── constants.py        # API defaults, service name
│   │   ├── main.py             # FastAPI app, exception handlers, /health, /
│   │   ├── report_registry.py  # Temp report storage (TTL)
│   │   ├── routes.py           # POST /api/run, GET /api/report
│   │   └── schemas.py          # Request/response models
│   ├── cli/
│   │   ├── __init__.py
│   │   └── main.py             # CLI entry (flocust), interactive prompts
│   ├── common/                 # Shared logic
│   │   ├── analyzer.py        # compute_report, write_report (incl. token distributions)
│   │   ├── config.py          # RunConfig, ConfigFile, load_config_from_file
│   │   ├── dashboard.py       # Console table (TTFT, latency, inter-token, tokens, tokens/sec)
│   │   ├── generator.py       # Synthetic prompt generation (lorem/code)
│   │   ├── loader.py          # load_prompts (JSON/JSONL)
│   │   ├── models.py          # RequestResult, ReportCard (incl. token distribution fields)
│   │   ├── runner.py          # Locust user, run_experiment(), token fallback for streaming
│   │   ├── tokenizer.py       # tiktoken count_tokens, encoding cache
│   │   └── utils.py           # percentile, etc.
│   └── config.sample.json     # Example config
├── config.json                # Optional local config (git-ignored if desired)
├── prompts.jsonl              # Example prompts
├── pyproject.toml
├── requirements.txt
├── TECHNICAL_OVERVIEW.md      # Latency/token measurement, results writing, workflow
└── README.md
```

---

## Output formats

### `results.jsonl`

One JSON object per line, one line per request. Fields include:

- **req_id**, **input_prompt**, **output_result** — Request id, prompt, and model response.
- **latency_ms**, **ttft_ms** — Total latency and time to first token (TTFT; null when not streaming).
- **input_tokens**, **output_tokens**, **tokens_per_sec** — Token counts and throughput per request (from API usage when available; otherwise from tiktoken so streaming runs still get values).
- **cached_tokens** — Input tokens served from the API’s prompt cache (e.g. OpenAI `prompt_tokens_details.cached_tokens`); present when the API reports it.
- **inter_token_latencies**, **avg_inter_token_latency**, **p50/p90/p95_inter_token_latency** — Inter-token latency stats (when streaming).
- **success**, **error** — Request success and error message if failed.

Example (streaming):

```json
{"req_id":"abc123","input_prompt":"What is 2+2?","output_result":"4","latency_ms":450.2,"ttft_ms":120.1,"input_tokens":8,"output_tokens":2,"tokens_per_sec":22.5,"success":true,"error":null,"inter_token_latencies":[12.1,8.3],"avg_inter_token_latency":10.2,"p50_inter_token_latency":10.0,"p90_inter_token_latency":12.0,"p95_inter_token_latency":12.5}
```

### `report.json` (report card)

Aggregated metrics for the run. Includes:

- **Latency** — average, min, max, p50/p90/p95/p99, std.
- **TTFT** — average, min, max, p50/p90/p99, std (when streaming).
- **Inter-token latency** — average, min, max, p50/p90/p95, std (when streaming).
- **Total tokens** — total_input_tokens, total_output_tokens, total_tokens.
- **Token distributions (per request)** — input_tokens_avg/min/max/std/p50/p90/p99, output_tokens_*, average_tokens_per_sec, tokens_per_sec_min/max/std/p50/p90/p99.
- **Prompt cache** (when API reports cached tokens) — total_cached_tokens, requests_with_cache_hit.
- **requests_per_second_actual**, **result_file**, **notes**.

Example (abbreviated):

```json
{
  "experiment_id": "model-users10-rps5",
  "total_requests": 100,
  "successful_requests": 98,
  "failed_requests": 2,
  "average_latency_ms": 420.5,
  "latency_p50_ms": 380.0,
  "latency_p90_ms": 620.0,
  "latency_p95_ms": 710.0,
  "latency_p99_ms": 890.0,
  "ttft_available": true,
  "average_ttft_ms": 110.2,
  "inter_token_latency_available": true,
  "average_inter_token_latency_ms": 8.5,
  "total_input_tokens": 1200,
  "total_output_tokens": 450,
  "total_tokens": 1650,
  "input_tokens_avg": 12.0,
  "input_tokens_min": 8,
  "input_tokens_max": 22,
  "output_tokens_avg": 4.5,
  "output_tokens_min": 2,
  "output_tokens_max": 15,
  "average_tokens_per_sec": 25.3,
  "tokens_per_sec_min": 10.2,
  "tokens_per_sec_max": 45.0,
  "requests_per_second_actual": 4.8,
  "result_file": "results.jsonl",
  "notes": null
}
```

When `stream=false`, TTFT and inter-token fields may be omitted or null; only end-to-end latency is reported. Token counts and tokens_per_sec are still reported (from API usage or tiktoken fallback).

---

## Documentation

For implementation details (how latency, TTFT, and inter-token latency are measured; token counting and fallback when the API does not return usage; results writing and report aggregation; ramp-up and load control), see **[TECHNICAL_OVERVIEW.md](TECHNICAL_OVERVIEW.md)**.

---

## Requirements

- Python 3.10+
- OpenAI-compatible chat completions endpoint
- For TTFT and inter-token metrics: API must support `stream: true` and return SSE or JSON stream chunks

---

## License

MIT.
