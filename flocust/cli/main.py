"""
CLI for Flocust: load config from file or interactive prompts, run load test.

Usage:
  flocust                    # uses config.json if present, else interactive
  flocust config.json        # load given config file
  flocust -c config.json     # same via -c/--config
"""

import argparse
import sys
import traceback
from pathlib import Path

from flocust.common.analyzer import compute_report, write_report
from flocust.common.config import (
    RunConfig,
    artifact_output_dir,
    load_config_from_file,
    normalize_base_url,
)
from flocust.common.dashboard import display_dashboard
from flocust.common.runner import run_experiment

DEFAULT_ENCODING = "cl100k_base"
DEFAULT_PROMPTS_PATH = Path("prompts.jsonl")
DEFAULT_CONFIG_PATH = Path("config.json")

__all__ = ["main", "collect_config", "collect_config_from_cli"]


def _prompt(text: str, default: str | None = None) -> str:
    """Read a string from stdin with optional default."""
    suffix = f" [{default}]" if default is not None else ""
    try:
        value = input(f"{text}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        sys.exit(0)
    return value if value else (default or "")


def _prompt_int(
    text: str, default: int, min_val: int = 1, max_val: int = 10_000
) -> int:
    """Read an integer in range from stdin."""
    while True:
        raw = _prompt(text, str(default))
        try:
            val = int(raw)
            if min_val <= val <= max_val:
                return val
        except ValueError:
            pass
        print(f"  Enter an integer between {min_val} and {max_val}.")


def _prompt_float(
    text: str,
    default: float,
    min_val: float = 0.1,
    max_val: float = 10_000.0,
) -> float:
    """Read a float in range from stdin."""
    while True:
        raw = _prompt(text, str(default))
        try:
            val = float(raw)
            if min_val <= val <= max_val:
                return val
        except ValueError:
            pass
        print(f"  Enter a number between {min_val} and {max_val}.")


def _prompt_bool(text: str, default: bool = True) -> bool:
    """Read y/n from stdin."""
    default_str = "y" if default else "n"
    raw = _prompt(text, default_str).lower().strip()
    if not raw:
        return default
    return raw in ("y", "yes", "1", "true")


def _prompt_base_url(text: str, default: str | None = None) -> str:
    """Read and normalize base URL from stdin."""
    raw = _prompt(text, default)
    normalized = normalize_base_url(raw)
    if normalized and normalized != raw:
        print(f"  -> Using base URL: {normalized}")
    return normalized or raw


def collect_config(config_path: Path | None = None) -> RunConfig:
    """
    Load config from file or collect interactively.

    If config_path is given, load from that file (raise if missing).
    If config_path is None (no -c/--config passed), always prompt for
    parameters in the terminal (interactive mode).
    """
    if config_path is not None:
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")
        return load_config_from_file(config_path)
    return collect_config_from_cli()


def collect_config_from_cli() -> RunConfig:
    """Collect run parameters interactively via terminal prompts."""
    print("Flocust — LLM endpoint load test\n")
    base_url = _prompt_base_url(
        "Base URL (without /chat/completions)",
        "https://api.openai.com/v1",
    )
    api_key = _prompt("API key", "")
    if not api_key:
        print("API key is required.")
        sys.exit(1)
    model = _prompt("Model name", "gpt-4o-mini")
    concurrency = _prompt_int("Concurrency (users)", 10, 1, 10_000)

    use_duration = _prompt_bool(
        "Use duration mode (y/n)? (n = fixed request count)", default=False
    )
    if use_duration:
        duration_sec = _prompt_float("Run duration (seconds)", 30.0, 0.1, 3600.0)
        num_requests = 100  # Ignored in duration mode
    else:
        duration_sec = 0.0
        num_requests = _prompt_int("Number of requests", 100, 1, 1_000_000)

    ramp_up_sec = _prompt_float("Ramp-up time (seconds)", 0.0, 0.0, 300.0)
    rps = _prompt_float("Requests per second (0 = max throughput)", 5.0, 0, 10_000.0)
    use_rps_throttle = rps > 0

    timeout_sec = _prompt_int("Request timeout (seconds)", 60, 1, 300)
    max_tokens = _prompt_int("Max tokens per completion", 1024, 1, 128_000)
    stream = _prompt_bool("Stream responses (TTFT/inter-token)? (y/n)", default=True)
    prompt_cache = _prompt_bool("Enable prompt caching (y/n)? (n = unique request per call)", default=False)

    generate_type = _prompt("Prompts: (f)ile, (l)lm-generated, (s)ource-file", "f").lower().strip()
    prompts_path: Path | None = None
    generate_prompts = False
    generate_prompts_count: int | None = None
    generate_prompts_from_file = False
    prompt_mean_input_tokens: int | None = None
    prompt_stddev_input_tokens: int | None = None
    prompt_mean_output_tokens: int | None = None

    if generate_type in ("l", "llm-generated"):
        generate_prompts = True
        auto_count = max(1, num_requests // 10)
        raw = _prompt(
            "Number of prompts to generate (blank = auto)", str(auto_count)
        ).strip()
        if raw:
            try:
                generate_prompts_count = min(1000, max(1, int(raw)))
            except ValueError:
                generate_prompts_count = auto_count
        else:
            generate_prompts_count = auto_count
    elif generate_type in ("s", "source-file", "sonnet"):
        generate_prompts_from_file = True
        source_file_input = _prompt(
            "Source text file path (.txt) (blank = use default sonnet.txt)", ""
        ).strip()
        if source_file_input:
            source_file_path = Path(source_file_input).resolve()
            if not source_file_path.exists():
                print(f"  Error: Source file not found: {source_file_path}")
                print("  Please provide a valid .txt file path.")
                sys.exit(1)
            if source_file_path.suffix.lower() != ".txt":
                print(f"  Error: Source file must be a .txt file, got: {source_file_path.suffix}")
                sys.exit(1)
            prompts_path = source_file_path
        else:
            prompts_path = None
        auto_count = max(1, num_requests // 10)
        raw = _prompt(
            "Number of prompts to generate (blank = auto)", str(auto_count)
        ).strip()
        if raw:
            try:
                generate_prompts_count = min(1000, max(1, int(raw)))
            except ValueError:
                generate_prompts_count = auto_count
        else:
            generate_prompts_count = auto_count
        prompt_mean_input_tokens = _prompt_int("Mean input tokens", 550, 1, 10000)
        prompt_stddev_input_tokens = _prompt_int("Stddev input tokens", 250, 0, 5000)
        prompt_mean_output_tokens = _prompt_int("Mean output tokens", 150, 1, 10000)
    else:
        prompts_path = Path(
            _prompt("Prompts file path", str(DEFAULT_PROMPTS_PATH))
        ).resolve()
        if not prompts_path.exists():
            print(f"  Error: Prompts file not found: {prompts_path}")
            print("  Please provide a valid prompts file (JSON or JSONL).")
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
        timeout_sec=timeout_sec,
        duration_sec=duration_sec,
        ramp_up_sec=ramp_up_sec,
        use_rps_throttle=use_rps_throttle,
        encoding=DEFAULT_ENCODING,  # type: ignore[arg-type]
        stream=stream,
        prompt_cache=prompt_cache,
        generate_prompts=generate_prompts,
        generate_prompts_count=generate_prompts_count,
        generate_prompts_from_file=generate_prompts_from_file,
        prompt_mean_input_tokens=prompt_mean_input_tokens,
        prompt_stddev_input_tokens=prompt_stddev_input_tokens,
        prompt_mean_output_tokens=prompt_mean_output_tokens,
    )


def _parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Flocust — LLM endpoint load testing",
        prog="flocust",
        epilog="""
Supported usage:
  flocust                 Run load test: use config.json if present, else interactive
  flocust CONFIG          Run load test with CONFIG (e.g. config.json)
  flocust -c PATH         Run load test with config file at PATH
  flocust --prompt-cache  Enable prompt caching (default: disabled)
  flocust -h, --help      Show this help and exit
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=None,
        metavar="PATH",
        help="Path to config JSON file.",
    )
    parser.add_argument(
        "config_path",
        nargs="?",
        type=Path,
        default=None,
        metavar="CONFIG",
        help="Config JSON file. If omitted and config.json exists, it is used; else interactive mode.",
    )
    parser.add_argument(
        "--prompt-cache",
        action="store_true",
        dest="prompt_cache",
        help="Enable prompt caching (default: disabled so each request avoids cache for reproducible load tests).",
    )
    return parser.parse_args()


def main() -> None:
    """Entry point: load config, run experiment, write report and display dashboard."""
    args = _parse_args()
    # Prefer -c/--config, then positional CONFIG, then default config.json if it exists
    config_path: Path | None = args.config or args.config_path
    if config_path is None and DEFAULT_CONFIG_PATH.exists():
        config_path = DEFAULT_CONFIG_PATH

    if config_path is not None:
        print(f"Loading config from: {config_path}")
    else:
        print("No config file specified, using interactive mode")

    try:
        config = collect_config(config_path)
        if getattr(args, "prompt_cache", False):
            config = config.model_copy(update={"prompt_cache": True})
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except ValueError as e:
        print(f"Config error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Config loading failed: {e}")
        traceback.print_exc()
        sys.exit(1)

    print(
        f"Config loaded: output_dir={config.output_dir}, "
        f"generate_prompts={config.generate_prompts}, prompt_cache={config.prompt_cache}"
    )
    print("\nRunning load test...")

    try:
        results, result_path, out_dir, duration_seconds = run_experiment(config)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Load test failed: {e}")
        traceback.print_exc()
        sys.exit(1)

    print(f"Requests completed: {len(results)}")

    report = compute_report(
        results,
        experiment_id=out_dir.name,
        duration_seconds=duration_seconds,
        result_file=result_path.name,
    )
    report_path = out_dir / "report.json"
    try:
        write_report(report, report_path)
        print(f"Output: {out_dir}")
        print(f"  {result_path.name}")
        print(f"  {report_path.name}")
    except OSError as e:
        print(f"Warning: Could not write report: {e}")

    try:
        display_dashboard(report, results)
    except Exception as e:
        print(f"Warning: Could not display dashboard: {e}")


if __name__ == "__main__":
    main()
