"""Locust-based LLM load test runner with isolated state management."""

import json
import math
import random
import shutil
import sys
import tempfile
import threading
import time
import uuid
from io import StringIO
from pathlib import Path
from typing import Any, Optional

import gevent
import httpx
from locust import HttpUser, constant, events, task
from locust.env import Environment
from locust.log import setup_logging

from flocust.common.config import RunConfig
from flocust.common.loader import load_prompts
from flocust.common.models import RequestResult
from flocust.common.utils import percentile

# Default count for LLM-generated prompts (10–20% of num_requests).
GENERATE_PROMPTS_DEFAULT_PERCENT = 0.15
GENERATE_PROMPTS_MIN = 1
GENERATE_PROMPTS_MAX = 500

RESULTS_FILENAME = "results.jsonl"
FLUSH_EVERY_LINES = 10
QUEUE_POLL_TIMEOUT = 0.1
STOP_POLL_INTERVAL = 0.1

def _usage_from_headers(headers) -> tuple[int, int]:
    """Extract input_tokens and output_tokens from response headers (e.g. x-input-tokens, x-completion-tokens)."""
    if headers is None:
        return 0, 0
    try:
        inp = headers.get("x-input-tokens") or headers.get("x-prompt-tokens")
        out = headers.get("x-completion-tokens") or headers.get("x-output-tokens")
        return (
            int(inp) if inp is not None else 0,
            int(out) if out is not None else 0,
        )
    except (TypeError, ValueError):
        return 0, 0


def _cached_tokens_from_usage(usage_or_data: dict) -> int | None:
    """Extract cached_tokens from OpenAI-style usage (prompt_tokens_details.cached_tokens)."""
    if not isinstance(usage_or_data, dict):
        return None
    usage = usage_or_data.get("usage") if isinstance(usage_or_data.get("usage"), dict) else usage_or_data
    if not isinstance(usage, dict):
        return None
    details = usage.get("prompt_tokens_details") or usage.get("promptTokensDetails")
    if not isinstance(details, dict):
        return None
    val = details.get("cached_tokens") or details.get("cachedTokens")
    return int(val) if val is not None else None


class RequestLimiter:
    """Strict limit: allow exactly N requests (no overshoot)."""

    def __init__(self):
        self._limit = 0
        self._remaining = 0
        self._lock = threading.Lock()

    def reset(self, limit: int) -> None:
        with self._lock:
            self._limit = max(0, limit)
            self._remaining = self._limit

    def can_make_request(self) -> bool:
        """Allow request only if remaining > 0; then decrement. Exactly N allowed."""
        with self._lock:
            if self._remaining <= 0:
                return False
            self._remaining -= 1
            return True

    @property
    def current_count(self) -> int:
        """Number of requests granted so far."""
        with self._lock:
            return self._limit - self._remaining


class LoadTestRunner:
    """Isolated load test execution with all state encapsulated."""

    def __init__(self):
        self.results: list[RequestResult] = []
        self.results_lock = threading.Lock()
        self.file_write_queue = gevent.queue.Queue()
        self.file_writer_greenlet: Optional[gevent.Greenlet] = None
        self.result_file_handle: Optional[sys.stdout] = None

        # Progress tracking (single bar, updated in place only)
        self.progress_current = 0
        self.progress_total = 0
        self.progress_start_time = 0.0
        self._progress_stop = False
        self.progress_greenlet: Optional[gevent.Greenlet] = None

        # Request limiting
        self.request_limiter = RequestLimiter()

        # Test configuration
        self.config: Optional[RunConfig] = None
        self.output_dir: Optional[Path] = None
        self.result_path: Optional[Path] = None



_PROGRESS_LINE_WIDTH = 80
_ANSI_CLEAR_LINE = "\033[2K\r"


def _show_progress(runner: LoadTestRunner):
    """Single line, update in place (no newline)."""
    out = getattr(runner, "_real_stdout", None)
    if not out:
        return
    elapsed = time.time() - runner.progress_start_time
    rps = runner.progress_current / elapsed if elapsed > 0 else 0
    if runner.progress_total > 0:
        pct = min(runner.progress_current / runner.progress_total, 1.0)
        w = 30
        filled = int(w * pct)
        bar = "=" * filled + "-" * (w - filled)
        msg = f"[{bar}] {runner.progress_current}/{runner.progress_total} ({pct:.0%}) {rps:.1f} RPS"
    else:
        msg = f"{runner.progress_current} req | {elapsed:.1f}s | {rps:.1f} RPS"
    line = (msg + " " * _PROGRESS_LINE_WIDTH)[:_PROGRESS_LINE_WIDTH]
    out.write(_ANSI_CLEAR_LINE + line)
    out.flush()


def _update_progress(runner: LoadTestRunner):
    last = -1
    while not getattr(runner, "_progress_stop", False):
        if runner.progress_current != last:
            last = runner.progress_current
            _show_progress(runner)
        gevent.sleep(0.25)


def _start_progress(runner: LoadTestRunner, total_requests: int):
    runner.progress_current = 0
    runner.progress_total = total_requests
    runner.progress_start_time = time.time()
    runner._progress_stop = False
    runner.progress_greenlet = gevent.spawn(_update_progress, runner)


def _stop_progress(runner: LoadTestRunner):
    runner._progress_stop = True
    if runner.progress_greenlet:
        runner.progress_greenlet.join(timeout=1.0)
        runner.progress_greenlet = None


def _generate_prompts_via_llm(config: RunConfig, count: int) -> list[str]:
    """Call the LLM once (non-streaming) to generate count short prompts."""
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
        # Check if we've reached the request limit
        if not LLMUser.test_runner_instance.request_limiter.can_make_request():
            return
        req_id, prompt = self._next_prompt()
        stream = self.environment.parsed_options.stream
        prompt_cache = getattr(self.environment.parsed_options, "prompt_cache", False)
        # When prompt_cache is False (default), prepend a unique nonce so each request
        # has a different prefix → no OpenAI prompt cache hits (reproducible load tests).
        user_content = prompt if prompt_cache else f"[req:{req_id}]\n{prompt}"
        payload = {
            "model": self.environment.parsed_options.model,
            "messages": [{"role": "user", "content": user_content}],
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
        input_tokens = 0
        output_tokens = 0
        stream_usage: dict = {}
        response_data: dict = {}  # full response for non-stream (for cached_tokens)

        if stream:
            ttft_start = None
            last_token_time = None
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
                    content_done = False  # stop appending to content after 1000 chars, but keep reading for usage
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
                                # Continue processing buffer; usage is often in the same chunk after [DONE]
                                continue
                            parsed = self._parse_one_sse_line_with_usage(data_str)
                            if parsed.get("usage"):
                                stream_usage = parsed["usage"]
                            content_piece = parsed.get("content", "")
                            if content_piece and not content_done:
                                if ttft_start is None:
                                    ttft_start = chunk_time
                                content += content_piece
                                if last_token_time is not None:
                                    inter_token_latencies.append((chunk_time - last_token_time) / 1e6)
                                last_token_time = chunk_time
                                if len(content) > 1000:
                                    content_done = True
                            if seen_done:
                                break
                    input_tokens, output_tokens = _usage_from_headers(response.headers)
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
                            response_data = response.json()
                            choices = response_data.get("choices") or []
                            if choices and isinstance(choices[0], dict):
                                msg = choices[0].get("message") or {}
                                if isinstance(msg, dict):
                                    content = (msg.get("content") or "").strip()
                            input_tokens, output_tokens = _usage_from_headers(response.headers)
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

        cached_tokens = (
            _cached_tokens_from_usage(stream_usage) if stream else _cached_tokens_from_usage(response_data)
        )

        success = status_code == 200
        total_tokens = input_tokens + output_tokens
        tokens_per_sec = round((total_tokens / (latency_ms / 1000)), 2) if latency_ms > 0 and total_tokens > 0 else None
        result = RequestResult(
            req_id=req_id,
            input_prompt=prompt,
            output_result=content,
            latency_ms=round(latency_ms, 2),
            ttft_ms=round(ttft_ms, 2) if ttft_ms else None,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
            tokens_per_sec=tokens_per_sec,
            success=success,
            error=None if success else (error_msg or f"HTTP {status_code}"),
        )
        result.inter_token_latencies = inter_token_latencies

        LLMUser.test_runner_instance.file_write_queue.put(result)
        with LLMUser.test_runner_instance.results_lock:
            LLMUser.test_runner_instance.results.append(result)
        LLMUser.test_runner_instance.progress_current += 1

    def _parse_one_sse_line_with_usage(self, data_str: str) -> dict:
        """Parse one SSE payload (after 'data: '); return dict with 'content' and 'usage'.
        'usage' is used for cached_tokens extraction only; token counts come from headers.
        """
        out: dict = {"content": "", "usage": {}}
        if not data_str or data_str == "[DONE]":
            return out
        try:
            j = json.loads(data_str)
            # Only store as usage when this chunk has usage-like keys (so we keep last real usage)
            usage_keys = ("usage", "prompt_tokens", "completion_tokens", "input_tokens", "output_tokens")
            if any(k in j for k in usage_keys) or (isinstance(j.get("usage"), dict) and j["usage"]):
                out["usage"] = j
            choices = j.get("choices") or []
            if not choices or not isinstance(choices[0], dict):
                return out
            delta = choices[0].get("delta") or {}
            if not isinstance(delta, dict):
                return out
            c = delta.get("content")
            out["content"] = c if isinstance(c, str) else ""
            return out
        except (json.JSONDecodeError, TypeError, KeyError):
            return out

    @property
    def prompts(self):
        """Get prompts from environment."""
        return self.environment._prompts_loaded


def _async_file_writer(runner: LoadTestRunner):
    """Background greenlet that writes results to file asynchronously."""
    lines_since_flush = 0
    while True:
        try:
            result = runner.file_write_queue.get(timeout=QUEUE_POLL_TIMEOUT)
            if result is None:
                break
            if runner.result_file_handle:
                # Fill per-request inter-token stats here (off hot path)
                if result.inter_token_latencies:
                    sorted_itt = sorted(result.inter_token_latencies)
                    result.avg_inter_token_latency = round(
                        sum(result.inter_token_latencies) / len(result.inter_token_latencies), 4
                    )
                    result.p50_inter_token_latency = round(percentile(sorted_itt, 50), 4)
                    result.p90_inter_token_latency = round(percentile(sorted_itt, 90), 4)
                    result.p95_inter_token_latency = round(percentile(sorted_itt, 95), 4)
                runner.result_file_handle.write(result.model_dump_json() + "\n")
                lines_since_flush += 1
                if lines_since_flush >= FLUSH_EVERY_LINES:
                    runner.result_file_handle.flush()
                    lines_since_flush = 0
        except gevent.queue.Empty:
            continue
        except Exception:
            continue


def _start_async_writer(runner: LoadTestRunner, result_path: Path):
    """Start the async file writer greenlet."""
    runner.result_file_handle = open(
        result_path, "w", encoding="utf-8", buffering=65536
    )
    runner.file_writer_greenlet = gevent.spawn(_async_file_writer, runner)


def _stop_async_writer(runner: LoadTestRunner):
    """Stop the async file writer and close file handle."""
    if runner.file_writer_greenlet:
        runner.file_write_queue.put(None)
        runner.file_writer_greenlet.join(timeout=2.0)
    if runner.result_file_handle:
        runner.result_file_handle.flush()
        runner.result_file_handle.close()
        runner.result_file_handle = None

    # Logging was disabled at environment level, no need to restore


def _on_request(request_type, name, response_time, response_length, exception, **kwargs):
    """Locust request event listener (no-op; required for event registration)."""


def _run_experiment_programmatic(
    config: RunConfig,
    test_runner: LoadTestRunner,
) -> float:
    """Run load test using programmatic Locust API."""
    test_runner.config = config
    test_runner.request_limiter.reset(config.num_requests)

    # Max throughput: use all configured users; no throttle so we run at system limit.
    effective_concurrency = config.concurrency

    # Suppress Locust logging so only our single progress bar is visible
    setup_logging(loglevel="CRITICAL")
    env = Environment(user_classes=[LLMUser])

    # Timeout: (connect_sec, read_sec) so long LLM responses are not cut off
    timeout_tuple = (10, config.timeout_sec) if config.timeout_sec > 0 else (10, 120)
    env.parsed_options = type("Options", (), {
        "api_key": config.api_key,
        "model": config.model,
        "max_tokens": config.max_tokens,
        "prompts_path": str(config.prompts_path),
        "encoding": config.encoding,
        "timeout": timeout_tuple,
        "stream": config.stream,
        "prompt_cache": getattr(config, "prompt_cache", False),
    })()

    # Pass test runner instance to users
    LLMUser.test_runner_instance = test_runner

    env.host = config.base_url.rstrip("/")

    # No wait between tasks: max req/s (each user runs again as soon as request completes)
    LLMUser.wait_time = constant(0)

    events.request.add_listener(_on_request)

    runner = env.create_local_runner()

    # Spawn all users as fast as possible so we hit target throughput from the first second.
    if getattr(config, "ramp_up_sec", 0) and config.ramp_up_sec > 0:
        spawn_rate = max(1, int(effective_concurrency / config.ramp_up_sec))
    else:
        spawn_rate = min(15000, max(effective_concurrency, 1000))
    runner.start(effective_concurrency, spawn_rate=spawn_rate)

    start_time = time.perf_counter()
    use_duration = getattr(config, "duration_sec", 0) and config.duration_sec > 0
    num_requests = config.num_requests
    duration_sec = getattr(config, "duration_sec", 0) or 0
    while True:
        gevent.sleep(STOP_POLL_INTERVAL)
        elapsed = time.perf_counter() - start_time
        if use_duration:
            if elapsed >= duration_sec:
                break
        else:
            # Stop as soon as we have exactly num_requests completed (strict, no overshoot)
            with test_runner.results_lock:
                n_done = len(test_runner.results)
            if n_done >= num_requests:
                break
    runner.stop()
    runner.quit()
    end_time = time.perf_counter()
    duration_seconds = end_time - start_time

    return duration_seconds


def run_experiment(
    config: RunConfig,
) -> tuple[list[RequestResult], Path, Path, float]:
    """
    Run a single load test experiment using programmatic Locust API.
    Runs at target RPS with given concurrency until num_requests are completed.
    When generate_prompts=True, generates prompts via one LLM call first.
    Writes result.jsonl and returns (results, result_path, output_dir, duration_seconds).
    """
    # Create isolated runner instance
    runner = LoadTestRunner()

    generated_prompts_temp_dir: Path | None = None
    if config.generate_prompts:
        count = config.generate_prompts_count
        if count is None:
            count = max(
                GENERATE_PROMPTS_MIN,
                min(GENERATE_PROMPTS_MAX, int(config.num_requests * GENERATE_PROMPTS_DEFAULT_PERCENT)),
            )
        count = max(GENERATE_PROMPTS_MIN, min(GENERATE_PROMPTS_MAX, count))
        sys.stdout.write("Generating prompts via LLM...\n")
        sys.stdout.flush()
        prompts_list = _generate_prompts_via_llm(config, count)
        sys.stdout.write(f"Prompts generated: {len(prompts_list)}\n")
        sys.stdout.flush()
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

    # Single-process path (multiprocessing removed for reliability)
    # Redirect stdout/stderr so only progress line is visible
    real_stdout = sys.stdout
    real_stderr = sys.stderr
    runner._real_stdout = real_stdout
    sys.stdout = StringIO()
    sys.stderr = StringIO()

    total_for_progress = (
        0 if (getattr(config, "duration_sec", 0) and config.duration_sec > 0)
        else config.num_requests
    )
    _start_progress(runner, total_for_progress)
    _start_async_writer(runner, result_path)

    try:
        duration_seconds = _run_experiment_programmatic(config, runner)
    finally:
        _stop_progress(runner)
        _stop_async_writer(runner)
        sys.stdout = real_stdout
        sys.stderr = real_stderr
        real_stdout.write(_ANSI_CLEAR_LINE + " " * _PROGRESS_LINE_WIDTH + "\n")
        real_stdout.flush()
        if generated_prompts_temp_dir is not None and generated_prompts_temp_dir.exists():
            try:
                shutil.rmtree(generated_prompts_temp_dir, ignore_errors=True)
            except OSError:
                pass

    # Strict: return exactly num_requests results
    with runner.results_lock:
        results = runner.results[: config.num_requests]
    return results, result_path, out_dir, duration_seconds
