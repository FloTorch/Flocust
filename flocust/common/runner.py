"""
Locust-based LLM load test runner.

Uses programmatic Locust API for accurate metrics and comprehensive load testing.
"""

import json
import random
import shutil
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

import gevent
import httpx
from locust import HttpUser, constant_throughput, task, events
from locust.env import Environment
from locust.log import setup_logging

from flocust.common.config import RunConfig
from flocust.common.loader import load_prompts
from flocust.common.models import RequestResult
from flocust.common.tokenizer import count_tokens
from flocust.common.utils import percentile

# Default count for LLM-generated prompts (10–20% of num_requests).
GENERATE_PROMPTS_DEFAULT_PERCENT = 0.15
GENERATE_PROMPTS_MIN = 1
GENERATE_PROMPTS_MAX = 500

RESULTS_FILENAME = "results.jsonl"
FLUSH_EVERY_LINES = 10
QUEUE_POLL_TIMEOUT = 0.1
STOP_POLL_INTERVAL = 0.2

_results: list[RequestResult] = []
_results_lock = threading.Lock()
_file_write_queue = gevent.queue.Queue()
_file_writer_greenlet = None
_result_file_handle = None

# Progress tracking
_progress_current = 0
_progress_total = 0
_progress_start_time = 0.0

# Input token cache (prompt -> count) to avoid repeated tiktoken calls; cleared each run
_input_token_cache: dict[str, int] = {}
_INPUT_TOKEN_CACHE_MAX = 256


def _cached_input_tokens(prompt: str, encoding: str) -> int:
    """Return input token count, using cache for repeated prompts."""
    if prompt in _input_token_cache:
        return _input_token_cache[prompt]
    n = count_tokens(prompt, encoding)
    if len(_input_token_cache) >= _INPUT_TOKEN_CACHE_MAX:
        _input_token_cache.clear()
    _input_token_cache[prompt] = n
    return n


def _show_progress():
    """Display progress bar during test execution."""
    if _progress_total == 0:
        return

    elapsed = time.time() - _progress_start_time
    progress = min(_progress_current / _progress_total, 1.0)
    bar_width = 40
    filled = int(bar_width * progress)
    bar = "=" * filled + "-" * (bar_width - filled)

    rps = _progress_current / elapsed if elapsed > 0 else 0
    msg = (
        f"\rProgress: [{bar}] {_progress_current}/{_progress_total} "
        f"requests ({progress:.1%}) | {rps:.1f} RPS"
    )
    sys.stdout.write(msg)
    sys.stdout.flush()


def _update_progress():
    """Update progress bar in a loop."""
    while True:
        _show_progress()
        gevent.sleep(0.5)


def _start_progress(total_requests: int):
    """Start progress tracking."""
    global _progress_current, _progress_total, _progress_start_time
    _progress_current = 0
    _progress_total = total_requests
    _progress_start_time = time.time()

    gevent.spawn(_update_progress)


def _increment_progress():
    """Increment progress counter."""
    global _progress_current
    _progress_current += 1


def _generate_prompts_via_llm(config: RunConfig, count: int) -> list[str]:
    """
    Call the LLM once (non-streaming) to generate `count` short prompts.
    Returns list of prompt strings (one per line from response).
    """
    url = f"{config.base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": config.model,
        "messages": [
            {
                "role": "user",
                "content": (
                    f"Generate exactly {count} short prompts for testing an LLM API. "
                    "Each prompt should be one line, 1-2 sentences, varied topics (questions, tasks, summaries). "
                    "Output only the prompts, one per line, no numbering or bullets."
                ),
            }
        ],
        "max_tokens": min(4096, count * 80),
        "temperature": 0.7,
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    content = ""
    choices = data.get("choices") or []
    if choices and isinstance(choices[0], dict):
        msg = choices[0].get("message") or {}
        if isinstance(msg, dict):
            content = (msg.get("content") or "").strip()
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    # Trim to count; if fewer, duplicate to reach at least count
    if len(lines) < count:
        while len(lines) < count:
            lines.extend(lines[: count - len(lines)])
    return lines[:count]


class LLMUser(HttpUser):
    """High-performance Locust user for LLM API load testing."""

    def __init__(self, environment):
        super().__init__(environment)
        if not hasattr(environment, "_prompts_loaded"):
            path = Path(self.environment.parsed_options.prompts_path)
            environment._prompts_loaded = load_prompts(path)
            if not environment._prompts_loaded:
                raise ValueError(f"No prompts loaded from {path}")
        self.prompts = environment._prompts_loaded

    def on_start(self):
        """Set up authentication headers."""
        self.client.headers.update({
            "Authorization": f"Bearer {self.environment.parsed_options.api_key}",
            "Content-Type": "application/json",
        })

    def _next_prompt(self):
        """Pick a random prompt (shuffled) with short UUID."""
        prompt = random.choice(self.prompts)
        req_id = str(uuid.uuid4())[:8]
        return req_id, prompt

    @task
    def chat_completion(self):
        """Make a chat completion request (stream or non-stream)."""
        req_id, prompt = self._next_prompt()
        stream = self.environment.parsed_options.stream
        payload = {
            "model": self.environment.parsed_options.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": self.environment.parsed_options.max_tokens,
            "temperature": 0.0,
            "stream": stream,
        }

        start_time = time.perf_counter_ns()
        content = ""
        status_code = 0
        error_msg = None
        ttft_ms = None
        inter_token_latencies: list[float] = []
        output_tokens = 0

        if stream:
            ttft_start = None
            last_token_time = None
            token_count = 0
            try:
                timeout = self.environment.parsed_options.timeout
                with self.client.post(
                    "/chat/completions",
                    json=payload,
                    stream=True,
                    timeout=timeout,
                    catch_response=True,
                ) as response:
                    status_code = response.status_code
                    ttft_start = time.perf_counter_ns()
                    buffer = b""
                    seen_done = False
                    for chunk in response.iter_content(chunk_size=8192, decode_unicode=False):
                        if not chunk:
                            continue
                        chunk_time = time.perf_counter_ns()
                        buffer += chunk
                        while b"\n" in buffer:
                            line, buffer = buffer.split(b"\n", 1)
                            try:
                                line_str = line.decode("utf-8", errors="ignore").strip()
                            except Exception:
                                continue
                            if not line_str.startswith("data: "):
                                continue
                            data_str = line_str[6:].strip()
                            if data_str == "[DONE]":
                                seen_done = True
                                buffer = b""
                                break
                            content_piece = self._parse_one_sse_line(data_str)
                            if content_piece:
                                if ttft_start is None:
                                    ttft_start = chunk_time
                                content += content_piece
                                token_count += 1
                                if last_token_time is not None:
                                    inter_token_latencies.append((chunk_time - last_token_time) / 1e6)
                                last_token_time = chunk_time
                                if len(content) > 1000:
                                    break
                            if seen_done or len(content) > 1000:
                                break
                    if status_code == 200:
                        response.success()
                    else:
                        response.failure(f"HTTP {status_code}")
            except Exception as e:
                status_code = 0
                error_msg = str(e)[:200]
            end_time = time.perf_counter_ns()
            latency_ms = (end_time - start_time) / 1e6
            ttft_ms = ((ttft_start - start_time) / 1e6) if ttft_start and ttft_start >= start_time else None
            output_tokens = token_count
        else:
            try:
                timeout = self.environment.parsed_options.timeout
                with self.client.post(
                    "/chat/completions",
                    json=payload,
                    stream=False,
                    timeout=timeout,
                    catch_response=True,
                ) as response:
                    status_code = response.status_code
                    if status_code == 200:
                        try:
                            data = response.json()
                            choices = data.get("choices") or []
                            if choices and isinstance(choices[0], dict):
                                msg = choices[0].get("message") or {}
                                if isinstance(msg, dict):
                                    content = (msg.get("content") or "").strip()
                            usage = data.get("usage") or {}
                            if isinstance(usage, dict) and "completion_tokens" in usage:
                                output_tokens = int(usage["completion_tokens"])
                            else:
                                output_tokens = count_tokens(content, self.environment.parsed_options.encoding)
                            response.success()
                        except Exception:
                            response.failure("Invalid JSON response")
                            status_code = 0
                            error_msg = "Invalid JSON response"
                    else:
                        response.failure(f"HTTP {status_code}")
            except Exception as e:
                status_code = 0
                error_msg = str(e)[:200]
            end_time = time.perf_counter_ns()
            latency_ms = (end_time - start_time) / 1e6

        input_tokens = _cached_input_tokens(prompt, self.environment.parsed_options.encoding)
        success = status_code == 200
        result = RequestResult(
            req_id=req_id,
            input_prompt=prompt,
            output_result=content,
            latency_ms=round(latency_ms, 2),
            ttft_ms=round(ttft_ms, 2) if ttft_ms else None,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            success=success,
            error=None if success else (error_msg or f"HTTP {status_code}"),
        )
        result.inter_token_latencies = inter_token_latencies

        _file_write_queue.put(result)
        with _results_lock:
            _results.append(result)
        _increment_progress()

    def _parse_one_sse_line(self, data_str: str) -> str:
        """Parse one SSE payload (after 'data: ') and return content from choices[0].delta.content."""
        if not data_str or data_str == "[DONE]":
            return ""
        try:
            j = json.loads(data_str)
            choices = j.get("choices") or []
            if not choices or not isinstance(choices[0], dict):
                return ""
            delta = choices[0].get("delta") or {}
            if not isinstance(delta, dict):
                return ""
            c = delta.get("content")
            return c if isinstance(c, str) else ""
        except (json.JSONDecodeError, TypeError, KeyError):
            return ""


def _async_file_writer():
    """Background greenlet that writes results to file asynchronously."""
    global _result_file_handle
    lines_since_flush = 0
    while True:
        try:
            result = _file_write_queue.get(timeout=QUEUE_POLL_TIMEOUT)
            if result is None:
                break
            if _result_file_handle:
                # Fill per-request inter-token stats here (off hot path)
                if result.inter_token_latencies:
                    sorted_itt = sorted(result.inter_token_latencies)
                    result.avg_inter_token_latency = round(
                        sum(result.inter_token_latencies) / len(result.inter_token_latencies), 4
                    )
                    result.p50_inter_token_latency = round(percentile(sorted_itt, 50), 4)
                    result.p90_inter_token_latency = round(percentile(sorted_itt, 90), 4)
                    result.p95_inter_token_latency = round(percentile(sorted_itt, 95), 4)
                _result_file_handle.write(result.model_dump_json() + "\n")
                lines_since_flush += 1
                if lines_since_flush >= FLUSH_EVERY_LINES:
                    _result_file_handle.flush()
                    lines_since_flush = 0
        except gevent.queue.Empty:
            continue
        except Exception:
            continue


def _start_async_writer(result_path: Path):
    """Start the async file writer greenlet."""
    global _file_writer_greenlet, _result_file_handle
    _result_file_handle = open(
        result_path, "w", encoding="utf-8", buffering=65536
    )
    _file_writer_greenlet = gevent.spawn(_async_file_writer)


def _stop_async_writer():
    """Stop the async file writer and close file handle."""
    global _file_writer_greenlet, _result_file_handle
    if _file_writer_greenlet:
        _file_write_queue.put(None)
        _file_writer_greenlet.join(timeout=2.0)
    if _result_file_handle:
        _result_file_handle.flush()
        _result_file_handle.close()
        _result_file_handle = None


def _on_request(request_type, name, response_time, response_length, exception, **kwargs):
    """Locust request event listener (no-op; required for event registration)."""


def _run_experiment_programmatic(
    config: RunConfig,
) -> tuple[list[RequestResult], float]:
    """Run load test using programmatic Locust API."""
    global _results, _input_token_cache
    with _results_lock:
        _results.clear()
    _input_token_cache.clear()

    setup_logging("INFO", None)

    env = Environment(user_classes=[LLMUser])

    env.parsed_options = type("Options", (), {
        "api_key": config.api_key,
        "model": config.model,
        "max_tokens": config.max_tokens,
        "prompts_path": str(config.prompts_path),
        "encoding": config.encoding,
        "timeout": config.timeout_sec,
        "stream": config.stream,
    })()

    env.host = config.base_url.rstrip("/")

    # Throttle to target RPS (global throughput)
    LLMUser.wait_time = constant_throughput(config.requests_per_second)

    events.request.add_listener(_on_request)

    runner = env.create_local_runner()

    spawn_rate = min(config.concurrency, 10)
    runner.start(config.concurrency, spawn_rate=spawn_rate)

    start_time = time.perf_counter()
    num_requests = config.num_requests
    while True:
        gevent.sleep(STOP_POLL_INTERVAL)
        with _results_lock:
            n = len(_results)
        if n >= num_requests:
            break
    runner.stop()
    runner.quit()
    end_time = time.perf_counter()
    duration_seconds = end_time - start_time

    with _results_lock:
        return list(_results), duration_seconds


def run_experiment(
    config: RunConfig,
) -> tuple[list[RequestResult], Path, Path, float]:
    """
    Run a single load test experiment using programmatic Locust API.
    Runs at target RPS with given concurrency until num_requests are completed.
    When generate_prompts=True, generates prompts via one LLM call first.
    Writes result.jsonl and returns (results, result_path, output_dir, duration_seconds).
    """
    generated_prompts_temp_dir: Path | None = None
    if config.generate_prompts:
        count = config.generate_prompts_count
        if count is None:
            count = max(
                GENERATE_PROMPTS_MIN,
                min(GENERATE_PROMPTS_MAX, int(config.num_requests * GENERATE_PROMPTS_DEFAULT_PERCENT)),
            )
        count = max(GENERATE_PROMPTS_MIN, min(GENERATE_PROMPTS_MAX, count))
        prompts_list = _generate_prompts_via_llm(config, count)
        generated_prompts_temp_dir = Path(tempfile.mkdtemp(prefix="flocust_prompts_"))
        prompts_path = generated_prompts_temp_dir / "prompts.jsonl"
        prompts_path.write_text("\n".join(prompts_list), encoding="utf-8")
        config = config.model_copy(update={"prompts_path": prompts_path})

    prompts_path = Path(config.prompts_path)
    if not prompts_path.exists():
        raise FileNotFoundError(f"Prompts file not found: {prompts_path}")

    out_dir = Path(config.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    result_path = out_dir / RESULTS_FILENAME

    _start_progress(config.num_requests)
    _start_async_writer(result_path)

    try:
        results, duration_seconds = _run_experiment_programmatic(config)
    finally:
        _stop_async_writer()
        _show_progress()
        print()
        if generated_prompts_temp_dir is not None and generated_prompts_temp_dir.exists():
            try:
                shutil.rmtree(generated_prompts_temp_dir, ignore_errors=True)
            except OSError:
                pass

    return results, result_path, out_dir, duration_seconds
