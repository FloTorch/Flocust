# Flocust Demo Guide

Quick reference for giving a demo: where to start and how Locust is used to achieve concurrency.

---

## Where to Start

### Option 1: CLI with config file (recommended for demo)

1. **Edit `config.json`** for your demo:
   - Set `bench.concurrency` (e.g. `5` or `10`) — number of concurrent virtual users.
   - Set `bench.requests` (e.g. `20` or `50`) — total requests to run.
   - Set `bench.requests_per_second` (e.g. `5.0`) — target RPS; use `0` for max throughput.
   - Ensure `input_file` points to `prompts.jsonl` (or your prompts file).

2. **Run the load test:**
   ```bash
   flocust -c config.json
   ```
   Or from project root:
   ```bash
   python -m flocust.cli.main -c config.json
   ```

3. **What you’ll see:** Progress bar, then a **console dashboard** with TTFT, latency, inter-token latency, input/output tokens, tokens/sec (avg, min, max, p99, p90, p50, std), and a summary.

4. **Output:** Under `artifacts/<model>-users<N>-rps<R>/` you get `results.jsonl` and `report.json`.

### Option 2: Interactive CLI (no config)

```bash
flocust
```
You’ll be prompted for base URL, API key, model, concurrency, requests, RPS, etc. Good for showing “prompted” mode.

### Option 3: REST API (for API-first demo)

1. **Start the server:**
   ```bash
   uvicorn flocust.api.main:app --host 0.0.0.0 --port 8000
   ```

2. **Open docs:** `http://localhost:8000/docs`

3. **Run a test via API:**
   ```bash
   curl -X POST http://localhost:8000/api/run \
     -F "prompts_file=@prompts.jsonl" \
     -F "base_url=https://api.openai.com/v1" \
     -F "api_key=YOUR_KEY" \
     -F "model=gpt-4o-mini" \
     -F "concurrency=5" \
     -F "num_requests=20" \
     -F "max_tokens=1024"
   ```

---

## How We Use Locust

| Component | Role |
|-----------|------|
| **Locust** | Load-testing framework; we use its **programmatic API** (no web UI). |
| **`HttpUser`** | Base class for “virtual users” that make HTTP requests. |
| **`LLMUser`** | Our subclass in `flocust/common/runner.py`: one “user” = one concurrent worker that repeatedly calls the LLM `/chat/completions` endpoint. |
| **`@task`** | The `chat_completion` method is the single task; each user runs it in a loop. |
| **`Environment`** | We create a Locust `Environment` with `user_classes=[LLMUser]`, set `host` to the LLM base URL, then create a **local runner** (no master/worker). |
| **`runner.start(concurrency, spawn_rate=...)`** | This is where **concurrency** is applied: Locust spawns `concurrency` greenlets, each running an `LLMUser` that executes the task. |

So: **concurrency = number of concurrent Locust users (greenlets)** each hammering the LLM API with the same task.

---

## How We Achieve the Desired Concurrency

### 1. **Concurrency (virtual users)**

- **Config:** `bench.concurrency` in `config.json` (or “Concurrency (users)” in interactive CLI).
- **Code:** `runner.start(config.concurrency, spawn_rate=spawn_rate)` in `_run_experiment_programmatic()` (`runner.py`).
- **Effect:** Locust spawns exactly `concurrency` users. Each user runs in a greenlet and keeps calling `chat_completion()` until the run is stopped.

### 2. **Ramp-up (optional)**

- **Config:** `bench.ramp_up_sec`.
- **Code:** If `ramp_up_sec > 0`, we set `spawn_rate = max(1, concurrency / ramp_up_sec)` so users are staggered over that period; otherwise `spawn_rate = concurrency` (all users start at once).
- **Effect:** Avoids a sudden spike; load increases gradually.

### 3. **Throughput: max vs target RPS**

- **Max throughput:** `requests_per_second` is `0` → we set `LLMUser.wait_time = constant(0)`. Users run the task as fast as they can (no wait between requests).
- **Target RPS:** `requests_per_second > 0` → we set `LLMUser.wait_time = constant_throughput(requests_per_second)`. Locust throttles so that *across all users* the total rate is about `requests_per_second`.

So:
- **Concurrency** = *how many* concurrent users.
- **RPS** = *how fast* they collectively send requests (0 = as fast as possible).

### 4. **Stopping condition: request count or duration**

- **Fixed number of requests:** `duration_sec` is 0. We use a `RequestLimiter` so that *exactly* `num_requests` are allowed. The main loop stops when `len(results) >= num_requests`.
- **Fixed duration:** `duration_sec > 0`. The loop runs until `elapsed >= duration_sec`, then we stop the runner.

### 5. **Key code locations**

| What | File | Symbol / line |
|------|------|----------------|
| Locust user class | `flocust/common/runner.py` | `class LLMUser(HttpUser)` |
| Single task (one LLM call) | `flocust/common/runner.py` | `def chat_completion(self)` (decorated with `@task`) |
| Concurrency + spawn rate | `flocust/common/runner.py` | `runner.start(config.concurrency, spawn_rate=spawn_rate)` |
| RPS throttle vs max | `flocust/common/runner.py` | `constant_throughput(...)` vs `constant(0)` |
| Request limit (exact N) | `flocust/common/runner.py` | `RequestLimiter`, `can_make_request()` in `chat_completion` |
| Config → RunConfig | `flocust/common/config.py` | `load_config_from_file()`, `RunConfig.concurrency`, `num_requests`, `use_rps_throttle` |

---

## Demo Talking Points

1. **“We use Locust as the load engine.”**  
   We use its programmatic API: `Environment`, local runner, and our `LLMUser` (subclass of `HttpUser`) so we don’t need the Locust web UI.

2. **“Concurrency is the number of simultaneous virtual users.”**  
   That’s `bench.concurrency`. Each user is a greenlet that repeatedly calls the LLM `/chat/completions` endpoint (streaming or non-streaming).

3. **“We can cap throughput with target RPS.”**  
   When `requests_per_second > 0`, we use Locust’s `constant_throughput` so the *aggregate* request rate stays at the configured RPS.

4. **“We run exactly N requests or for N seconds.”**  
   Implemented with `RequestLimiter` plus a loop that stops when we have enough results or when duration is reached.

5. **“Metrics are LLM-specific.”**  
   We collect latency, TTFT, inter-token latency, and token usage (from API or tiktoken), then report them in the console dashboard and in `report.json` / `results.jsonl`.

---

## Suggested Demo Flow

1. Show `config.json`: point out `concurrency`, `requests`, `requests_per_second`.
2. Run: `flocust -c config.json`.
3. Point at the progress bar and then the **console dashboard** (TTFT, latency, tokens, etc.).
4. Open `artifacts/.../report.json` and optionally `results.jsonl`.
5. (Optional) Show `runner.py`: `LLMUser`, `@task`, and `runner.start(config.concurrency, ...)` to tie config to “how many users” and “how we achieve concurrency.”

This gives a clear path from “where do I start” to “how we use Locust and achieve the desired concurrency.”
