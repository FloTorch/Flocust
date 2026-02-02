# Flocust

Production-ready **LLM endpoint load testing** with [Locust](https://locust.io). Benchmark latency, time-to-first-token (TTFT), and token counts per request.

## Features

- **OpenAI-compatible API**: `POST /chat/completions` with streaming for TTFT.
- **Configurable load**: Concurrency, target RPS, duration, max tokens.
- **Prompts**: Load from `prompts.json` or `prompts.jsonl`.
- **Per-request results**: `result.jsonl` with `req_id`, `input_prompt`, `output_result`, `latency_ms`, `ttft_ms`, `input_tokens`, `output_tokens`.
- **Report card**: `report.json` with average latency, p50/p90/p95/p99, TTFT stats, total tokens, actual RPS.
- **Token counting**: Fast [tiktoken](https://github.com/openai/tiktoken) (cl100k_base, o200k_base, etc.).
- **CLI**: Interactive prompts for all inputs, then run and print report.
- **FastAPI server**: Same workflow via `POST /api/experiments/run`.

## Project structure

```
Flocust/
├── flocust/
│   ├── __init__.py
│   ├── cli.py           # CLI entry (flocust or python -m flocust.cli)
│   ├── config.py        # RunConfig (Pydantic)
│   ├── models.py        # RequestResult, ReportCard
│   ├── loader.py        # load_prompts (JSON/JSONL)
│   ├── tokenizer.py     # tiktoken count_tokens
│   ├── runner.py        # Locust LLM user, run_experiment(), result collection
│   ├── analyzer.py      # compute_report, write_report
│   └── api/
│       ├── __init__.py
│       ├── main.py      # FastAPI app
│       ├── routes.py    # POST /api/experiments/run
│       └── schemas.py   # RunExperimentRequest, RunExperimentResponse
├── prompts.jsonl        # Example prompts
├── pyproject.toml
├── requirements.txt
└── README.md
```

## Install

```bash
pip install -e .
# or
pip install -r requirements.txt
```

## CLI

Run the interactive CLI (prompts for base_url, api_key, model, concurrency, RPS, max_tokens, prompts path, output dir, duration, encoding):

```bash
flocust
# or
python -m flocust.cli
```

Outputs:

- `result.jsonl` in the chosen output directory (one JSON object per line per request).
- `report.json` with the report card (average_latency, p90, etc.).
- Report JSON printed to stdout.

## FastAPI server

### Run the server

From the project root (where `prompts.jsonl` lives if you use `prompts_path`):

```bash
uvicorn flocust.api.main:app --reload --host 0.0.0.0 --port 8000
```

- **GET /** — Health: returns `{"service": "flocust", "docs": "/docs", "openapi": "/openapi.json"}`.
- **GET /docs** — Swagger UI (with hints and examples) to run and test endpoints.
- **POST /api/experiments/run** — Run a load test with JSON body (`prompts` or `prompts_path`). Default `base_url`: `https://gateway.flotorch.cloud/openai/v1`.
- **POST /api/experiments/run/upload** — Run a load test by uploading a prompts file (`.json` or `.jsonl`) via multipart/form-data.
- **GET /api/experiments/result/{path}** — Download a result file by path (e.g. `artifacts/.../results.jsonl`).

### Test the API

**1. Health check**

```bash
curl http://localhost:8000/
```

**2. Run an experiment** (provide either `prompts` or `prompts_path`)

With inline prompts:

```bash
curl -X POST http://localhost:8000/api/experiments/run \
  -H "Content-Type: application/json" \
  -d "{
    \"base_url\": \"https://your-llm-api.com/v1\",
    \"api_key\": \"your-api-key\",
    \"model\": \"gpt-4o-mini\",
    \"concurrency\": 2,
    \"requests_per_second\": 1,
    \"num_requests\": 5,
    \"max_tokens\": 64,
    \"prompts\": [\"What is 2+2?\", \"Say hello.\"]
  }"
```

With a prompts file on the server (path relative to CWD when you started uvicorn):

```bash
curl -X POST http://localhost:8000/api/experiments/run \
  -H "Content-Type: application/json" \
  -d "{
    \"base_url\": \"https://your-llm-api.com/v1\",
    \"api_key\": \"your-api-key\",
    \"model\": \"gpt-4o-mini\",
    \"concurrency\": 2,
    \"requests_per_second\": 1,
    \"num_requests\": 5,
    \"max_tokens\": 64,
    \"prompts_path\": \"prompts.jsonl\"
  }"
```

**3. Run an experiment by uploading a prompts file** (multipart/form-data)

Upload a `prompts.json` or `prompts.jsonl` file. All other parameters are form fields. Default base URL is `https://gateway.flotorch.cloud/openai/v1`.

```bash
curl -X POST http://localhost:8000/api/experiments/run/upload \
  -F "prompts_file=@prompts.jsonl" \
  -F "api_key=your-api-key" \
  -F "model=flotorch/gemini-flash" \
  -F "concurrency=2" \
  -F "requests_per_second=1" \
  -F "num_requests=5" \
  -F "max_tokens=64"
```

Optional form fields: `base_url` (default: Flotorch gateway), `encoding`, `output_dir`.

Response: `report` (ReportCard with latency, TTFT, inter-token stats), `result_file`, `result_path`, `report_path`.

## Result and report format

**result.jsonl** (one line per request):

```json
{"req_id":"abc123_1","input_prompt":"What is 2+2?","output_result":"4","latency_ms":450.2,"ttft_ms":120.1,"input_tokens":8,"output_tokens":2,"success":true,"error":null}
```

**report.json** (report card):

```json
{
  "experiment_id": "experiment",
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
  "ttft_p90_ms": 180.0,
  "total_input_tokens": 1200,
  "total_output_tokens": 450,
  "total_tokens": 1650,
  "requests_per_second_actual": 4.8,
  "result_file": "result.jsonl",
  "notes": null
}
```

## Requirements

- Python 3.10+
- OpenAI-compatible chat completions endpoint (e.g. OpenAI, Azure OpenAI, local models with same API).
- For TTFT, the API must support `stream: true` and return SSE or JSON chunks.

## License

MIT.
