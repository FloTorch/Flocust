"""Request/response schemas for the FastAPI server."""

from typing import Any, Literal

__all__ = [
    "ReportSummary",
    "RunExperimentRequest",
    "RunExperimentResponse",
    "RunExperimentResponseBody",
    "report_to_summary",
]

from pydantic import BaseModel, Field

from flocust.api.constants import DEFAULT_BASE_URL
from flocust.common.models import ReportCard


class ReportSummary(BaseModel):
    """Slim report for default API response (no result_file, notes)."""

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
    """Build slim summary from ReportCard (exclude result_file, notes)."""
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
    """
    Request body for POST /api/experiments/run (JSON).

    Provide prompts in exactly one way: `prompts` (inline list), `prompts_path` (path on server),
    or use POST /api/experiments/run/upload to upload a prompts file.
    """

    base_url: str = Field(
        default=DEFAULT_BASE_URL,
        description="LLM API base URL (OpenAI-compatible). No trailing slash.",
        examples=[DEFAULT_BASE_URL, "https://api.openai.com/v1"],
    )
    api_key: str = Field(
        ...,
        description="API key for the LLM provider.",
        min_length=1,
    )
    model: str = Field(
        ...,
        description="Model name (e.g. gpt-4o-mini, flotorch/gemini-flash).",
        examples=["gpt-4o-mini", "flotorch/gemini-flash"],
    )
    concurrency: int = Field(
        default=10,
        ge=1,
        le=10_000,
        description="Number of concurrent virtual users.",
    )
    requests_per_second: float = Field(
        default=5.0,
        ge=0.1,
        le=10_000.0,
        description="Target global throughput (requests per second).",
    )
    num_requests: int = Field(
        default=100,
        ge=1,
        le=1_000_000,
        description="Total number of requests to run; test stops when this is reached.",
    )
    max_tokens: int = Field(
        default=1024,
        ge=1,
        le=128_000,
        description="Max tokens per completion.",
    )
    prompts: list[str] | None = Field(
        default=None,
        description="Inline list of prompt strings. Use this OR prompts_path, not both.",
        examples=[["What is 2+2?", "Say hello."]],
    )
    prompts_path: str | None = Field(
        default=None,
        description="Path to prompts.json or prompts.jsonl on the server (relative to CWD). Use this OR prompts.",
        examples=["prompts.jsonl", "data/prompts.json"],
    )
    stream: bool = Field(
        default=True,
        description="Use streaming; if False, only latency is measured (no TTFT/inter-token).",
    )
    generate_prompts: bool = Field(
        default=False,
        description="Generate prompts via one LLM call (10–20% of num_requests) and use for load test.",
    )
    generate_prompts_count: int | None = Field(
        default=None,
        ge=1,
        le=1000,
        description="Number of prompts to generate. Default: ~15% of num_requests.",
    )
    encoding: Literal["cl100k_base", "o200k_base", "p50k_base", "r50k_base"] = Field(
        default="cl100k_base",
        description="Tiktoken encoding for input token counting.",
    )
    output_dir: str | None = Field(
        default=None,
        description="Output directory for results (default: auto-generated under artifacts/).",
    )


class RunExperimentResponse(BaseModel):
    """
    Default API response: slim report + report_id.

    Use GET /api/report?report_id={report_id} to download the full report (report + results) as JSON.
    """

    report: ReportSummary = Field(
        ...,
        description="Aggregated metrics (slim; no result_file/notes).",
    )
    report_id: str = Field(
        ...,
        description="ID to download full report via GET /api/report?report_id=...",
    )


class RunExperimentResponseBody(BaseModel):
    """
    API response: report + results in one JSON. No files written to CWD.

    Use include_results=false or max_results to limit payload size for large runs.
    """

    report: ReportCard = Field(
        ...,
        description="Aggregated metrics: latency, TTFT, inter-token latency, RPS.",
    )
    results: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Per-request results (same as results.jsonl rows). Empty if include_results=false.",
    )
    total_results: int = Field(
        ...,
        ge=0,
        description="Total number of requests completed (len(results) or more if truncated).",
    )
    results_truncated: bool = Field(
        default=False,
        description="True if results were capped by max_results; total_results > len(results).",
    )
