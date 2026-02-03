"""Colored terminal dashboard for displaying load test results (single table, AI Perf style)."""

import shutil

from flocust.common.models import ReportCard, RequestResult


class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"


def _c(text: str, color: str) -> str:
    """Colorize text."""
    return f"{color}{text}{Colors.RESET}"


def _fmt(num: float, precision: int = 2) -> str:
    """Format number with precision."""
    return f"{num:.{precision}f}"


def _cell_avg_min(val: float) -> str:
    """Green for avg/min (favorable)."""
    return _c(_fmt(val), Colors.GREEN)


def _cell_max(val: float) -> str:
    """Red for max (outlier)."""
    return _c(_fmt(val), Colors.RED)


def _cell_pct(val: float) -> str:
    """Yellow for percentiles."""
    return _c(_fmt(val), Colors.YELLOW)


def _cell_std(val: float) -> str:
    """Magenta for std."""
    return _c(_fmt(val), Colors.MAGENTA)


def _cell_metric(name: str) -> str:
    """Cyan/blue for metric row names."""
    return _c(name, Colors.CYAN)


def display_dashboard(report: ReportCard, results: list[RequestResult]) -> None:
    """Display a single-table dashboard (Flotorch LLM Benchmarking | LLM Metrics Summary style)."""
    try:
        tw = shutil.get_terminal_size().columns
    except (OSError, AttributeError):
        tw = 100

    metric_w = 32
    num_w = 10
    sep = " | "
    header = (
        _c("Metric", Colors.MAGENTA).ljust(metric_w + 9)
        + sep + _c("avg", Colors.MAGENTA).ljust(num_w + 9)
        + sep + _c("min", Colors.MAGENTA).ljust(num_w + 9)
        + sep + _c("max", Colors.MAGENTA).ljust(num_w + 9)
        + sep + _c("p99", Colors.MAGENTA).ljust(num_w + 9)
        + sep + _c("p90", Colors.MAGENTA).ljust(num_w + 9)
        + sep + _c("p50", Colors.MAGENTA).ljust(num_w + 9)
        + sep + _c("std", Colors.MAGENTA)
    )

    def row(
        metric_name: str,
        avg: float,
        min_v: float,
        max_v: float,
        p99: float,
        p90: float,
        p50: float,
        std: float,
    ) -> str:
        return (
            _cell_metric(metric_name).ljust(metric_w + 9)
            + sep + _cell_avg_min(avg).ljust(num_w + 9)
            + sep + _cell_avg_min(min_v).ljust(num_w + 9)
            + sep + _cell_max(max_v).ljust(num_w + 9)
            + sep + _cell_pct(p99).ljust(num_w + 9)
            + sep + _cell_pct(p90).ljust(num_w + 9)
            + sep + _cell_pct(p50).ljust(num_w + 9)
            + sep + _cell_std(std)
        )

    title = _c("Flocust LLM Benchmarking", Colors.CYAN) + " | " + _c("LLM Metrics Summary", Colors.WHITE)
    subtitle = _c("Latency (ms)", Colors.MAGENTA)
    print()
    print(title)
    print(subtitle)
    print("=" * min(tw, 95))
    print(header)
    print("-" * min(tw, 95))

    if report.ttft_available and report.average_ttft_ms is not None:
        ttft_avg = report.average_ttft_ms
        ttft_min = report.ttft_min_ms or ttft_avg
        ttft_max = report.ttft_max_ms or ttft_avg
        ttft_p99 = report.ttft_p99_ms or report.ttft_p90_ms or ttft_max
        ttft_p90 = report.ttft_p90_ms or ttft_avg
        ttft_p50 = report.ttft_p50_ms or ttft_avg
        ttft_std = report.ttft_std_ms or 0.0
        print(row("Time to First Token (TTFT)", ttft_avg, ttft_min, ttft_max, ttft_p99, ttft_p90, ttft_p50, ttft_std))
    else:
        print(row("Time to First Token (TTFT)", 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0))

    print(row(
        "Request Latency (Total)",
        report.average_latency_ms,
        report.latency_min_ms,
        report.latency_max_ms,
        report.latency_p99_ms,
        report.latency_p90_ms,
        report.latency_p50_ms,
        report.latency_std_ms,
    ))

    if report.inter_token_latency_available and report.average_inter_token_latency_ms is not None:
        itl_avg = report.average_inter_token_latency_ms
        itl_min = report.inter_token_latency_min_ms or itl_avg
        itl_max = report.inter_token_latency_max_ms or itl_avg
        itl_p99 = (report.inter_token_latency_p95_ms or itl_avg) * 1.05
        itl_p90 = report.inter_token_latency_p90_ms or itl_avg
        itl_p50 = report.inter_token_latency_p50_ms or itl_avg
        itl_std = report.inter_token_latency_std_ms or 0.0
        print(row("Inter Token Latency", itl_avg, itl_min, itl_max, itl_p99, itl_p90, itl_p50, itl_std))

    # Input tokens (per request)
    in_avg = getattr(report, "input_tokens_avg", 0.0) or 0.0
    in_min = float(getattr(report, "input_tokens_min", 0) or 0)
    in_max = float(getattr(report, "input_tokens_max", 0) or 0)
    in_p99 = getattr(report, "input_tokens_p99", 0.0) or in_avg
    in_p90 = getattr(report, "input_tokens_p90", 0.0) or in_avg
    in_p50 = getattr(report, "input_tokens_p50", 0.0) or in_avg
    in_std = getattr(report, "input_tokens_std", 0.0) or 0.0
    print(row("Input Tokens", in_avg, in_min, in_max, in_p99, in_p90, in_p50, in_std))

    # Output tokens (per request)
    out_avg = getattr(report, "output_tokens_avg", 0.0) or 0.0
    out_min = float(getattr(report, "output_tokens_min", 0) or 0)
    out_max = float(getattr(report, "output_tokens_max", 0) or 0)
    out_p99 = getattr(report, "output_tokens_p99", 0.0) or out_avg
    out_p90 = getattr(report, "output_tokens_p90", 0.0) or out_avg
    out_p50 = getattr(report, "output_tokens_p50", 0.0) or out_avg
    out_std = getattr(report, "output_tokens_std", 0.0) or 0.0
    print(row("Output Tokens", out_avg, out_min, out_max, out_p99, out_p90, out_p50, out_std))

    # Tokens per second (per request)
    tps_avg = getattr(report, "average_tokens_per_sec", None) or 0.0
    tps_min = getattr(report, "tokens_per_sec_min", None) or tps_avg
    tps_max = getattr(report, "tokens_per_sec_max", None) or tps_avg
    tps_p99 = getattr(report, "tokens_per_sec_p99", None) or tps_avg
    tps_p90 = getattr(report, "tokens_per_sec_p90", None) or tps_avg
    tps_p50 = getattr(report, "tokens_per_sec_p50", None) or tps_avg
    tps_std = getattr(report, "tokens_per_sec_std", None) or 0.0
    print(row("Tokens/sec", tps_avg, tps_min, tps_max, tps_p99, tps_p90, tps_p50, tps_std))

    print("-" * min(tw, 95))
    summary = f"Total Requests: {report.total_requests} | Successful: {report.successful_requests}"
    if report.failed_requests > 0:
        summary += f" | Failed: {_c(str(report.failed_requests), Colors.RED)}"
    summary += f" | Input tokens: {report.total_input_tokens} | Output tokens: {report.total_output_tokens} | Total tokens: {report.total_tokens}"
    if report.average_tokens_per_sec is not None:
        summary += f" | Avg tokens/s: {_c(_fmt(report.average_tokens_per_sec), Colors.GREEN)}"
    print(summary)
    print()
