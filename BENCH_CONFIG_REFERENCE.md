# Bench parameters reference (`config.json` → `bench`)

Detailed explanation of every field under `bench` in the config file, with allowed ranges and suggested values.

---

## Overview

| Parameter | Type | Range | Default | Purpose |
|-----------|------|--------|---------|---------|
| `concurrency` | int | 1–10,000 | 10 | Number of concurrent virtual users |
| `requests` | int | 1–1,000,000 | 100 | Total requests (when not using duration) |
| `requests_per_second` | float | ≥ 0 | 0 | Target RPS (0 = max throughput) |
| `duration_sec` | float | ≥ 0 | 0 | Run for N seconds (overrides requests when > 0) |
| `ramp_up_sec` | float | ≥ 0 | 0 | Stagger user start over N seconds |
| `timeout_sec` | int | 1–300 | 60 | Per-request HTTP timeout (seconds) |
| `max_output_tokens` | int | 1–128,000 | 1024 | Max output (completion) tokens per request |
| `stream` | bool | — | true | Use streaming (enables TTFT/inter-token metrics) |
| `generate_prompts` | bool | — | false | Generate prompts via LLM instead of file |
| `generate_prompts_count` | int \| null | 1–1000 | null | Number of prompts to generate (when generate_prompts is true) |

---

## 1. `concurrency` (int, 1–10,000)

**What it does:** Number of **virtual users** (Locust greenlets) running at the same time. Each user repeatedly calls the LLM `/chat/completions` endpoint until the run stops.

**Desired values:**
- **Light load / smoke test:** `1`–`5`
- **Typical load test:** `10`–`50`
- **Stress test:** `50`–`200` (watch API rate limits and errors)
- **Heavy stress:** up to `10,000` (only if your API and machine can handle it)

**Example:** `"concurrency": 10` → 10 users making requests concurrently.

---

## 2. `requests` (int, 1–1,000,000)

**What it does:** **Total number of requests** to complete before the run stops. Used only when `duration_sec` is `0`. The run ends when this many requests have finished (success or failure).

**Desired values:**
- **Quick check:** `10`–`20`
- **Short load test:** `50`–`100`
- **Standard benchmark:** `100`–`500`
- **Long run:** `1000`+ (or use `duration_sec` instead for time-based runs)

**Note:** If `duration_sec > 0`, this is ignored; the run is time-based.

**Example:** `"requests": 100` with `duration_sec: 0` → run until 100 requests are done.

---

## 3. `requests_per_second` (float, ≥ 0)

**What it does:** **Target throughput** for all users combined. Locust throttles so the aggregate request rate stays near this value.

- **`0`:** No throttle → **max throughput**. Users send requests as fast as they can (only limited by response time and concurrency).
- **`> 0`:** Throttle to this RPS. E.g. `5.0` → aim for 5 requests per second across all users.

**Desired values:**
- **Max throughput (find limit):** `0`
- **Sustained load (e.g. production-like):** `5.0`, `10.0`, `20.0`, etc., depending on what you want to simulate.

**Example:** `"requests_per_second": 5.0` → cap at ~5 requests/sec total; `"requests_per_second": 0` → no cap, push as hard as possible.

---

## 4. `duration_sec` (float, ≥ 0)

**What it does:** Run the test for this many **seconds**. When `duration_sec > 0`, the run is **time-based**: it stops after that many seconds, regardless of how many requests completed. When `0`, the run is **request-based** and stops after `requests` are done.

**Desired values:**
- **Request-based run (default):** `0` (use `requests` to decide when to stop)
- **Time-based run:** e.g. `60`, `300`, `600` (1, 5, 10 minutes) for “sustained load for N minutes”

**Example:** `"duration_sec": 60`, `"requests": 100` → run for 60 seconds; `requests` is ignored.

---

## 5. `ramp_up_sec` (float, ≥ 0)

**What it does:** **Stagger** the start of virtual users over this many seconds. Instead of all users starting at once, they are spawned gradually (e.g. 10 users over 10 seconds ≈ 1 user per second).

- **`0`:** All users start immediately (default).
- **`> 0`:** Users start spread over `ramp_up_sec` seconds.

**Desired values:**
- **No ramp (instant load):** `0`
- **Smooth ramp (e.g. avoid thundering herd):** e.g. `5`, `10`, `30` (seconds)

**Example:** `"concurrency": 20`, `"ramp_up_sec": 10` → 20 users started over 10 seconds (about 2 per second).

---

## 6. `timeout_sec` (int, 1–300)

**What it does:** **Per-request HTTP timeout** in seconds. If the LLM API does not respond within this time, the request is marked as failed.

**Desired values:**
- **Fast models / short answers:** `30`–`60`
- **Slow or long-generation models:** `60`–`120`
- **Very long outputs:** up to `300` (5 minutes)

**Example:** `"timeout_sec": 60` → each request times out after 60 seconds.

---

## 7. `max_output_tokens` (int, 1–128,000)

**What it does:** **Maximum output (completion) tokens** per request (sent as `max_tokens` in the chat completion payload). Caps how long each response can be. Name aligns with LLMPerf’s `mean_output_tokens` / `stddev_output_tokens`.

**Desired values:**
- **Short answers (e.g. classification, one-liners):** `64`–`256`
- **Normal chat/summaries:** `512`–`1024`
- **Long outputs:** `2048`–`4096` or higher (check model limits)

**Example:** `"max_output_tokens": 1024` → API will not generate more than 1024 tokens per reply.

**Backward compatibility:** Config files can still use the key `max_tokens`; it is accepted as an alias for `max_output_tokens`.

---

## 8. `stream` (bool)

**What it does:** Whether to call the API with **streaming** (`stream: true`) or non-streaming.

- **`true`:** Streaming; you get **TTFT** (time to first token) and **inter-token latency** metrics in the report and dashboard.
- **`false`:** Single response; you only get **end-to-end latency** (no TTFT/inter-token).

**Desired values:**
- **Full metrics (TTFT, inter-token):** `true`
- **Latency-only, simpler:** `false`

**Example:** `"stream": true` → use streaming and collect TTFT + inter-token stats.

---

## 9. `generate_prompts` (bool)

**What it does:** If `true`, prompts are **generated by the LLM** (one initial non-streaming call) instead of being read from `input_file`. You can omit or leave `input_file` empty when this is true.

**Desired values:**
- **Use a prompts file (default):** `false`
- **No file, generate prompts:** `true` (set `generate_prompts_count` or rely on default)

**Example:** `"generate_prompts": true` → prompts are created by the LLM; `input_file` not required.

---

## 10. `generate_prompts_count` (int | null, 1–1000)

**What it does:** **Number of prompts** to generate when `generate_prompts` is `true`. If `null`, a default is used (e.g. a percentage of `requests`).

**Desired values:**
- **Not generating prompts:** leave `null` (ignored when `generate_prompts` is false)
- **Generate N prompts:** e.g. `50`, `100`, `200` (1–1000)

**Example:** `"generate_prompts": true`, `"generate_prompts_count": 100` → generate 100 prompts for the run.

---

## Example configs

**Quick smoke test (few requests, low concurrency):**
```json
"bench": {
  "concurrency": 2,
  "requests": 10,
  "requests_per_second": 0,
  "duration_sec": 0,
  "ramp_up_sec": 0,
  "timeout_sec": 60,
  "max_output_tokens": 256,
  "stream": true,
  "generate_prompts": false,
  "generate_prompts_count": null
}
```

**Standard load test (request-based, capped RPS):**
```json
"bench": {
  "concurrency": 10,
  "requests": 100,
  "requests_per_second": 5.0,
  "duration_sec": 0,
  "ramp_up_sec": 5,
  "timeout_sec": 60,
  "max_output_tokens": 1024,
  "stream": true,
  "generate_prompts": false,
  "generate_prompts_count": null
}
```

**Time-based stress test (max throughput for 2 minutes):**
```json
"bench": {
  "concurrency": 20,
  "requests": 10000,
  "requests_per_second": 0,
  "duration_sec": 120,
  "ramp_up_sec": 10,
  "timeout_sec": 90,
  "max_output_tokens": 512,
  "stream": true,
  "generate_prompts": false,
  "generate_prompts_count": null
}
```

---

## Interaction summary

| If you want… | Set |
|--------------|-----|
| Run until N requests | `duration_sec: 0`, `requests: N` |
| Run for N seconds | `duration_sec: N` (requests ignored) |
| Max throughput | `requests_per_second: 0` |
| Cap throughput at R RPS | `requests_per_second: R` |
| All users start at once | `ramp_up_sec: 0` |
| Stagger user start | `ramp_up_sec: T` (e.g. 5 or 10) |
| TTFT + inter-token metrics | `stream: true` |
| Use your own prompts | `generate_prompts: false`, set `input_file` |
| No file, LLM-generated prompts | `generate_prompts: true`, optional `generate_prompts_count` |
