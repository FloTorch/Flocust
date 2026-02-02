"""
CLI for Flocust: interactive prompts for inputs, run load test, output to artifacts/.

Prompts for: base_url, api_key, model, max_tokens, concurrency, RPS, num_requests.
Runs at target RPS until num_requests are completed (no duration).
"""

import sys
from pathlib import Path

__all__ = ["main", "collect_config_from_cli"]

from flocust.common.analyzer import compute_report, write_report
from flocust.common.config import RunConfig, artifact_output_dir
from flocust.common.dashboard import display_dashboard
from flocust.common.runner import run_experiment

DEFAULT_PROMPTS_PATH = Path("prompts.jsonl")
DEFAULT_ENCODING = "cl100k_base"


def _prompt(text: str, default: str | None = None) -> str:
    if default is not None:
        p = f"{text} [{default}]: "
    else:
        p = f"{text}: "
    try:
        value = input(p).strip()
    except (EOFError, KeyboardInterrupt):
        sys.exit(0)
    return value if value else (default or "")


def _prompt_int(text: str, default: int, min_val: int = 1, max_val: int = 10_000) -> int:
    while True:
        raw = _prompt(text, str(default))
        try:
            v = int(raw)
            if min_val <= v <= max_val:
                return v
        except ValueError:
            pass
        print(f"  Enter an integer between {min_val} and {max_val}.")


def _prompt_float(text: str, default: float, min_val: float = 0.1, max_val: float = 10_000.0) -> float:
    while True:
        raw = _prompt(text, str(default))
        try:
            v = float(raw)
            if min_val <= v <= max_val:
                return v
        except ValueError:
            pass
        print(f"  Enter a number between {min_val} and {max_val}.")


def _prompt_bool(text: str, default: bool = True) -> bool:
    """Prompt for y/n; default True -> 'y', False -> 'n'."""
    default_str = "y" if default else "n"
    raw = _prompt(text, default_str).lower().strip()
    if not raw:
        return default
    return raw in ("y", "yes", "1", "true")


def _normalize_base_url(url: str) -> str:
    url = (url or "").strip().rstrip("/")
    if not url:
        return url
    lower = url.lower()
    if lower.startswith("htttps://"):
        url = "https://" + url[9:]
    elif lower.startswith("htttp://"):
        url = "http://" + url[8:]
    elif lower.startswith("htps://"):
        url = "https://" + url[7:]
    elif not (lower.startswith("http://") or lower.startswith("https://")):
        if "://" not in url:
            url = "https://" + url
    return url


def _prompt_base_url(text: str, default: str | None = None) -> str:
    raw = _prompt(text, default)
    normalized = _normalize_base_url(raw)
    if normalized and normalized != raw:
        print(f"  -> Using base URL: {normalized}")
    return normalized or raw


def collect_config_from_cli() -> RunConfig:
    """Interactively collect: base_url, api_key, model, max_tokens, concurrency, rps, num_requests, stream, generate_prompts."""
    print("Flocust — LLM endpoint load test\n")
    base_url = _prompt_base_url(
        "Base URL (without /chat/completions)",
        "https://qa-gateway.flotorch.cloud/openai/v1",
    )
    api_key = _prompt("API key", "")
    if not api_key:
        print("API key is required.")
        sys.exit(1)
    model = _prompt("Model name", "gpt-4o-mini")
    max_tokens = _prompt_int("Max tokens per completion", 1024, 1, 128_000)
    concurrency = _prompt_int("Concurrency (users)", 10, 1, 10_000)
    rps = _prompt_float("Requests per second", 5.0, 0.1, 10_000.0)
    num_requests = _prompt_int("Number of requests to run", 100, 1, 1_000_000)
    stream = _prompt_bool("Stream responses (TTFT/inter-token metrics)? (y/n)", default=True)
    generate_prompts = _prompt_bool("Generate prompts via LLM? (y/n)", default=False)

    prompts_path: Path | None = None
    generate_prompts_count: int | None = None
    if generate_prompts:
        auto_count = max(1, num_requests // 10)
        raw_count = _prompt("Number of prompts to generate (blank = auto)", str(auto_count)).strip()
        if raw_count:
            try:
                generate_prompts_count = int(raw_count)
                if generate_prompts_count < 1 or generate_prompts_count > 1000:
                    generate_prompts_count = min(1000, max(1, generate_prompts_count))
            except ValueError:
                generate_prompts_count = auto_count
    else:
        prompts_path = DEFAULT_PROMPTS_PATH.resolve()
        if not prompts_path.exists():
            print(f"  Prompts file not found: {prompts_path}")
            print("  Create prompts.jsonl in the current directory or run from project root.")
            sys.exit(1)

    output_dir = artifact_output_dir(model, concurrency, rps)

    return RunConfig(
        base_url=base_url,
        api_key=api_key,
        model=model,
        concurrency=concurrency,
        requests_per_second=rps,
        max_tokens=max_tokens,
        prompts_path=prompts_path,
        output_dir=output_dir,
        num_requests=num_requests,
        encoding=DEFAULT_ENCODING,  # type: ignore[arg-type]
        stream=stream,
        generate_prompts=generate_prompts,
        generate_prompts_count=generate_prompts_count,
    )


def main() -> None:
    """Entry point: collect config, run experiment until num_requests done, write to artifacts/."""
    config = collect_config_from_cli()
    print("\nRunning load test...")
    results, result_path, out_dir, duration_seconds = run_experiment(config)
    print(f"Requests completed: {len(results)}")

    report = compute_report(
        results,
        experiment_id=out_dir.name,
        duration_seconds=duration_seconds,
        result_file=result_path.name,
    )
    report_path = out_dir / "report.json"
    write_report(report, report_path)

    print(f"Artifacts: {out_dir}")
    print(f"  {result_path.name}")
    print(f"  {report_path.name}")

    display_dashboard(report, results)


if __name__ == "__main__":
    main()
