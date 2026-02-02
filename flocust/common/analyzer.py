"""Compute latency percentiles and report card from experiment results."""

from pathlib import Path

from flocust.common.models import ReportCard, RequestResult
from flocust.common.utils import percentile

DEFAULT_RESULT_FILENAME = "results.jsonl"


def _std(values: list[float]) -> float:
    """Return standard deviation."""
    if not values or len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
    return variance**0.5


def compute_report(
    results: list[RequestResult],
    experiment_id: str,
    duration_seconds: float,
    result_file: str = DEFAULT_RESULT_FILENAME,
) -> ReportCard:
    """
    Compute report card from list of RequestResults.

    Uses duration_seconds to compute actual RPS.
    """
    if not results:
        return ReportCard(
            experiment_id=experiment_id,
            total_requests=0,
            successful_requests=0,
            failed_requests=0,
            average_latency_ms=0.0,
            latency_min_ms=0.0,
            latency_max_ms=0.0,
            latency_p50_ms=0.0,
            latency_p90_ms=0.0,
            latency_p95_ms=0.0,
            latency_p99_ms=0.0,
            latency_std_ms=0.0,
            ttft_available=False,
            average_ttft_ms=None,
            ttft_min_ms=None,
            ttft_max_ms=None,
            ttft_p50_ms=None,
            ttft_p90_ms=None,
            ttft_p99_ms=None,
            ttft_std_ms=None,
            inter_token_latency_available=False,
            average_inter_token_latency_ms=None,
            inter_token_latency_min_ms=None,
            inter_token_latency_max_ms=None,
            inter_token_latency_p50_ms=None,
            inter_token_latency_p90_ms=None,
            inter_token_latency_p95_ms=None,
            inter_token_latency_std_ms=None,
            total_input_tokens=0,
            total_output_tokens=0,
            total_tokens=0,
            requests_per_second_actual=0.0,
            result_file=result_file,
        )

    successful = [r for r in results if r.success]
    failed = len(results) - len(successful)
    latencies = [r.latency_ms for r in results]
    latencies.sort()
    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
    latency_min = min(latencies) if latencies else 0.0
    latency_max = max(latencies) if latencies else 0.0
    latency_std = _std(latencies)

    ttft_values = [r.ttft_ms for r in results if r.ttft_ms is not None and r.ttft_ms >= 0]
    ttft_available = len(ttft_values) > 0
    avg_ttft = (sum(ttft_values) / len(ttft_values)) if ttft_values else None
    ttft_sorted = sorted(ttft_values) if ttft_values else []
    ttft_min = min(ttft_sorted) if ttft_sorted else None
    ttft_max = max(ttft_sorted) if ttft_sorted else None
    ttft_p50 = percentile(ttft_sorted, 50) if ttft_sorted else None
    ttft_p90 = percentile(ttft_sorted, 90) if ttft_sorted else None
    ttft_p99 = percentile(ttft_sorted, 99) if ttft_sorted else None
    ttft_std = _std(ttft_values) if ttft_values else None

    all_inter_latencies = []
    for r in results:
        if hasattr(r, "inter_token_latencies") and r.inter_token_latencies:
            all_inter_latencies.extend(r.inter_token_latencies)

    inter_token_available = len(all_inter_latencies) > 0
    avg_inter_token = (sum(all_inter_latencies) / len(all_inter_latencies)) if all_inter_latencies else None
    inter_token_sorted = sorted(all_inter_latencies) if all_inter_latencies else []
    inter_token_min = min(inter_token_sorted) if inter_token_sorted else None
    inter_token_max = max(inter_token_sorted) if inter_token_sorted else None
    inter_token_p50 = percentile(inter_token_sorted, 50) if inter_token_sorted else None
    inter_token_p90 = percentile(inter_token_sorted, 90) if inter_token_sorted else None
    inter_token_p95 = percentile(inter_token_sorted, 95) if inter_token_sorted else None
    inter_token_std = _std(all_inter_latencies) if all_inter_latencies else None

    total_in = sum(r.input_tokens for r in results)
    total_out = sum(r.output_tokens for r in results)
    rps = len(results) / duration_seconds if duration_seconds > 0 else 0.0

    return ReportCard(
        experiment_id=experiment_id,
        total_requests=len(results),
        successful_requests=len(successful),
        failed_requests=failed,
        average_latency_ms=round(avg_latency, 2),
        latency_min_ms=round(latency_min, 2),
        latency_max_ms=round(latency_max, 2),
        latency_p50_ms=round(percentile(latencies, 50), 2),
        latency_p90_ms=round(percentile(latencies, 90), 2),
        latency_p95_ms=round(percentile(latencies, 95), 2),
        latency_p99_ms=round(percentile(latencies, 99), 2),
        latency_std_ms=round(latency_std, 2),
        ttft_available=ttft_available,
        average_ttft_ms=round(avg_ttft, 2) if avg_ttft is not None else None,
        ttft_min_ms=round(ttft_min, 2) if ttft_min is not None else None,
        ttft_max_ms=round(ttft_max, 2) if ttft_max is not None else None,
        ttft_p50_ms=round(ttft_p50, 2) if ttft_p50 is not None else None,
        ttft_p90_ms=round(ttft_p90, 2) if ttft_p90 is not None else None,
        ttft_p99_ms=round(ttft_p99, 2) if ttft_p99 is not None else None,
        ttft_std_ms=round(ttft_std, 2) if ttft_std is not None else None,
        inter_token_latency_available=inter_token_available,
        average_inter_token_latency_ms=round(avg_inter_token, 2) if avg_inter_token is not None else None,
        inter_token_latency_min_ms=round(inter_token_min, 2) if inter_token_min is not None else None,
        inter_token_latency_max_ms=round(inter_token_max, 2) if inter_token_max is not None else None,
        inter_token_latency_p50_ms=round(inter_token_p50, 2) if inter_token_p50 is not None else None,
        inter_token_latency_p90_ms=round(inter_token_p90, 2) if inter_token_p90 is not None else None,
        inter_token_latency_p95_ms=round(inter_token_p95, 2) if inter_token_p95 is not None else None,
        inter_token_latency_std_ms=round(inter_token_std, 2) if inter_token_std is not None else None,
        total_input_tokens=total_in,
        total_output_tokens=total_out,
        total_tokens=total_in + total_out,
        requests_per_second_actual=round(rps, 2),
        result_file=result_file,
        notes=None,
    )


def write_report(report: ReportCard, output_path: Path) -> None:
    """Write report card as JSON to output_path."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
