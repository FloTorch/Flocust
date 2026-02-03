"""Request/response schemas for the FastAPI server."""

from typing import Any, Literal

from pydantic import BaseModel, Field

from flocust.api.constants import DEFAULT_BASE_URL
from flocust.common.models import ReportCard

__all__ = [
    "ReportSummary",
    "RunExperimentRequest",
    "RunExperimentResponse",
    "RunExperimentResponseBody",
    "report_to_summary",
]


class ReportSummary(BaseModel):
    """Aggregated report summary (no result_file or notes)."""

    experiment_id: str = Field(..., description="Experiment identifier")
    total_requests: int = Field(..., ge=0)
    successful_requests: int = Field(..., ge=0)
    failed_requests: int = Field(..., ge=0)
    average_latency_ms: float = Field(..., ge=0)
    latency_min_ms: float = Field(..., ge=0)
    latency_max_ms: float = Field(..., ge=0)
    latency_p50_ms: float = Field(..., ge=0)
    latency_p90_ms: float = Field(..., ge=0)
    latency_p95_ms: float = Field(..., ge=0)
    latency_p99_ms: float = Field(..., ge=0)
    latency_std_ms: float = Field(default=0.0, ge=0)
    ttft_available: bool = Field(default=False)
    average_ttft_ms: float | None = Field(default=None, ge=0)
    ttft_min_ms: float | None = Field(default=None, ge=0)
    ttft_max_ms: float | None = Field(default=None, ge=0)
    ttft_p50_ms: float | None = Field(default=None, ge=0)
    ttft_p90_ms: float | None = Field(default=None, ge=0)
    ttft_p99_ms: float | None = Field(default=None, ge=0)
    ttft_std_ms: float | None = Field(default=None, ge=0)
    inter_token_latency_available: bool = Field(default=False)
    average_inter_token_latency_ms: float | None = Field(default=None, ge=0)
    inter_token_latency_min_ms: float | None = Field(default=None, ge=0)
    inter_token_latency_max_ms: float | None = Field(default=None, ge=0)
    inter_token_latency_p50_ms: float | None = Field(default=None, ge=0)
    inter_token_latency_p90_ms: float | None = Field(default=None, ge=0)
    inter_token_latency_p95_ms: float | None = Field(default=None, ge=0)
    inter_token_latency_std_ms: float | None = Field(default=None, ge=0)
    total_input_tokens: int = Field(..., ge=0)
    total_output_tokens: int = Field(..., ge=0)
    total_tokens: int = Field(..., ge=0)
    requests_per_second_actual: float = Field(..., ge=0)


def report_to_summary(report: ReportCard) -> ReportSummary:
    """Build slim summary from ReportCard."""
    return ReportSummary(
        experiment_id=report.experiment_id,
        total_requests=report.total_requests,
        successful_requests=report.successful_requests,
        failed_requests=report.failed_requests,
        average_latency_ms=report.average_latency_ms,
        latency_min_ms=report.latency_min_ms,
        latency_max_ms=report.latency_max_ms,
        latency_p50_ms=report.latency_p50_ms,
        latency_p90_ms=report.latency_p90_ms,
        latency_p95_ms=report.latency_p95_ms,
        latency_p99_ms=report.latency_p99_ms,
        latency_std_ms=report.latency_std_ms,
        ttft_available=report.ttft_available,
        average_ttft_ms=report.average_ttft_ms,
        ttft_min_ms=report.ttft_min_ms,
        ttft_max_ms=report.ttft_max_ms,
        ttft_p50_ms=report.ttft_p50_ms,
        ttft_p90_ms=report.ttft_p90_ms,
        ttft_p99_ms=report.ttft_p99_ms,
        ttft_std_ms=report.ttft_std_ms,
        inter_token_latency_available=report.inter_token_latency_available,
        average_inter_token_latency_ms=report.average_inter_token_latency_ms,
        inter_token_latency_min_ms=report.inter_token_latency_min_ms,
        inter_token_latency_max_ms=report.inter_token_latency_max_ms,
        inter_token_latency_p50_ms=report.inter_token_latency_p50_ms,
        inter_token_latency_p90_ms=report.inter_token_latency_p90_ms,
        inter_token_latency_p95_ms=report.inter_token_latency_p95_ms,
        inter_token_latency_std_ms=report.inter_token_latency_std_ms,
        total_input_tokens=report.total_input_tokens,
        total_output_tokens=report.total_output_tokens,
        total_tokens=report.total_tokens,
        requests_per_second_actual=report.requests_per_second_actual,
    )


class RunExperimentRequest(BaseModel):
    """Form parameters for POST /api/run. Prompts: upload file OR set generate_prompts=true."""

    base_url: str = Field(default=DEFAULT_BASE_URL, description="LLM API base URL")
    api_key: str = Field(..., min_length=1, description="API key")
    model: str = Field(..., description="Model name")
    concurrency: int = Field(default=10, ge=1, le=10_000, description="Concurrent users")
    requests_per_second: float = Field(
        default=5.0, ge=0.1, le=10_000.0,
        description="Target RPS; used only when use_rps_throttle=true",
    )
    num_requests: int = Field(
        default=100, ge=1, le=1_000_000,
        description="Total requests; ignored when duration_sec > 0",
    )
    duration_sec: float = Field(default=0, ge=0, description="Run for N seconds (overrides num_requests when > 0)")
    ramp_up_sec: float = Field(default=0, ge=0, description="Stagger worker start (seconds)")
    use_rps_throttle: bool = Field(
        default=False,
        description="True: throttle to requests_per_second. False: max throughput.",
    )
    timeout_sec: int = Field(default=60, ge=1, le=300, description="Per-request timeout (seconds)")
    max_tokens: int = Field(default=1024, ge=1, le=128_000, description="Max completion tokens")
    stream: bool = Field(default=True, description="Stream responses for TTFT/inter-token metrics")
    generate_prompts: bool = Field(default=False, description="Generate prompts via LLM (when no file uploaded)")
    generate_prompts_count: int | None = Field(default=None, ge=1, le=1000)
    encoding: Literal["cl100k_base", "o200k_base", "p50k_base", "r50k_base"] = Field(
        default="cl100k_base",
        description="Tiktoken encoding",
    )


class RunExperimentResponse(BaseModel):
    """Response: report summary and report_id for full download."""

    report: ReportSummary = Field(..., description="Aggregated metrics")
    report_id: str = Field(..., description="Use GET /api/report?report_id=... for full report")


class RunExperimentResponseBody(BaseModel):
    """Full response: report plus per-request results."""

    report: ReportCard = Field(..., description="Aggregated metrics")
    results: list[dict[str, Any]] = Field(default_factory=list, description="Per-request results")
    total_results: int = Field(..., ge=0, description="Total requests completed")
    results_truncated: bool = Field(default=False, description="True if results were capped")
