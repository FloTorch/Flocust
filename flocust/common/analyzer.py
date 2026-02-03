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
            average_tokens_per_sec=None,
            requests_per_second_actual=0.0,
            result_file=result_file,
            total_cached_tokens=0,
            requests_with_cache_hit=0,
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
    tps_values = [r.tokens_per_sec for r in results if getattr(r, "tokens_per_sec", None) is not None]
    avg_tokens_per_sec = (sum(tps_values) / len(tps_values)) if tps_values else None

    # Per-request token stats for dashboard
    in_tok = [r.input_tokens for r in results]
    out_tok = [r.output_tokens for r in results]
    in_tok_sorted = sorted(in_tok) if in_tok else []
    out_tok_sorted = sorted(out_tok) if out_tok else []
    tps_sorted = sorted(tps_values) if tps_values else []

    input_tokens_min = min(in_tok) if in_tok else 0
    input_tokens_max = max(in_tok) if in_tok else 0
    input_tokens_avg = total_in / len(results) if results else 0.0
    input_tokens_std = _std([float(x) for x in in_tok]) if len(in_tok) >= 2 else 0.0
    input_tokens_p50 = percentile(in_tok_sorted, 50) if in_tok_sorted else 0.0
    input_tokens_p90 = percentile(in_tok_sorted, 90) if in_tok_sorted else 0.0
    input_tokens_p99 = percentile(in_tok_sorted, 99) if in_tok_sorted else 0.0

    output_tokens_min = min(out_tok) if out_tok else 0
    output_tokens_max = max(out_tok) if out_tok else 0
    output_tokens_avg = total_out / len(results) if results else 0.0
    output_tokens_std = _std([float(x) for x in out_tok]) if len(out_tok) >= 2 else 0.0
    output_tokens_p50 = percentile(out_tok_sorted, 50) if out_tok_sorted else 0.0
    output_tokens_p90 = percentile(out_tok_sorted, 90) if out_tok_sorted else 0.0
    output_tokens_p99 = percentile(out_tok_sorted, 99) if out_tok_sorted else 0.0

    tokens_per_sec_min = min(tps_values) if tps_values else None
    tokens_per_sec_max = max(tps_values) if tps_values else None
    tokens_per_sec_std = _std(tps_values) if len(tps_values) >= 2 else None
    tokens_per_sec_p50 = percentile(tps_sorted, 50) if tps_sorted else None
    tokens_per_sec_p90 = percentile(tps_sorted, 90) if tps_sorted else None
    tokens_per_sec_p99 = percentile(tps_sorted, 99) if tps_sorted else None

    cached_tokens_list = [r.cached_tokens for r in results if getattr(r, "cached_tokens", None) is not None]
    total_cached_tokens = sum(cached_tokens_list)
    requests_with_cache_hit = sum(1 for r in results if getattr(r, "cached_tokens", None) and r.cached_tokens > 0)

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
        input_tokens_min=input_tokens_min,
        input_tokens_max=input_tokens_max,
        input_tokens_avg=round(input_tokens_avg, 2),
        input_tokens_std=round(input_tokens_std, 2),
        input_tokens_p50=round(input_tokens_p50, 2),
        input_tokens_p90=round(input_tokens_p90, 2),
        input_tokens_p99=round(input_tokens_p99, 2),
        output_tokens_min=output_tokens_min,
        output_tokens_max=output_tokens_max,
        output_tokens_avg=round(output_tokens_avg, 2),
        output_tokens_std=round(output_tokens_std, 2),
        output_tokens_p50=round(output_tokens_p50, 2),
        output_tokens_p90=round(output_tokens_p90, 2),
        output_tokens_p99=round(output_tokens_p99, 2),
        average_tokens_per_sec=round(avg_tokens_per_sec, 2) if avg_tokens_per_sec is not None else None,
        tokens_per_sec_min=round(tokens_per_sec_min, 2) if tokens_per_sec_min is not None else None,
        tokens_per_sec_max=round(tokens_per_sec_max, 2) if tokens_per_sec_max is not None else None,
        tokens_per_sec_std=round(tokens_per_sec_std, 2) if tokens_per_sec_std is not None else None,
        tokens_per_sec_p50=round(tokens_per_sec_p50, 2) if tokens_per_sec_p50 is not None else None,
        tokens_per_sec_p90=round(tokens_per_sec_p90, 2) if tokens_per_sec_p90 is not None else None,
        tokens_per_sec_p99=round(tokens_per_sec_p99, 2) if tokens_per_sec_p99 is not None else None,
        requests_per_second_actual=round(rps, 2),
        result_file=result_file,
        notes=None,
        total_cached_tokens=total_cached_tokens,
        requests_with_cache_hit=requests_with_cache_hit,
    )


def write_report(report: ReportCard, output_path: Path) -> None:
    """Write report card as JSON to output_path."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
