"""Data models for experiment results and reports."""

from typing import Any

from pydantic import BaseModel, Field

__all__ = ["RequestResult", "ReportCard"]


class RequestResult(BaseModel):
    """Single request result for one experiment sample."""

    req_id: str = Field(..., description="Unique request identifier")
    input_prompt: str = Field(..., description="User prompt sent to the LLM")
    output_result: str = Field(default="", description="Model response content")
    latency_ms: float = Field(..., ge=0, description="Total request latency in milliseconds")
    ttft_ms: float | None = Field(default=None, description="Time to first token in milliseconds")
    input_tokens: int = Field(..., ge=0, description="Input token count (from LLM usage)")
    output_tokens: int = Field(..., ge=0, description="Output token count (from LLM usage)")
    tokens_per_sec: float | None = Field(default=None, ge=0, description="Total tokens per second for this request")
    success: bool = Field(default=True, description="Whether the request succeeded")
    error: str | None = Field(default=None, description="Error message if failed")

    # Inter-token latency metrics (added dynamically)
    inter_token_latencies: list[float] = Field(default_factory=list, description="List of inter-token latencies")
    avg_inter_token_latency: float | None = Field(default=None, description="Average inter-token latency")
    p50_inter_token_latency: float | None = Field(default=None, description="50th percentile inter-token latency")
    p90_inter_token_latency: float | None = Field(default=None, description="90th percentile inter-token latency")
    p95_inter_token_latency: float | None = Field(default=None, description="95th percentile inter-token latency")

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def to_result_line(self) -> dict[str, Any]:
        """Dict for writing one line of result.jsonl."""
        return self.model_dump(mode="json")


class ReportCard(BaseModel):
    """Aggregated report for an experiment (report card)."""

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
    # Input tokens distribution (per request)
    input_tokens_min: int = Field(default=0, ge=0)
    input_tokens_max: int = Field(default=0, ge=0)
    input_tokens_avg: float = Field(default=0.0, ge=0)
    input_tokens_std: float = Field(default=0.0, ge=0)
    input_tokens_p50: float = Field(default=0.0, ge=0)
    input_tokens_p90: float = Field(default=0.0, ge=0)
    input_tokens_p99: float = Field(default=0.0, ge=0)
    # Output tokens distribution (per request)
    output_tokens_min: int = Field(default=0, ge=0)
    output_tokens_max: int = Field(default=0, ge=0)
    output_tokens_avg: float = Field(default=0.0, ge=0)
    output_tokens_std: float = Field(default=0.0, ge=0)
    output_tokens_p50: float = Field(default=0.0, ge=0)
    output_tokens_p90: float = Field(default=0.0, ge=0)
    output_tokens_p99: float = Field(default=0.0, ge=0)
    # Tokens per second distribution (per request)
    average_tokens_per_sec: float | None = Field(default=None, ge=0)
    tokens_per_sec_min: float | None = Field(default=None, ge=0)
    tokens_per_sec_max: float | None = Field(default=None, ge=0)
    tokens_per_sec_std: float | None = Field(default=None, ge=0)
    tokens_per_sec_p50: float | None = Field(default=None, ge=0)
    tokens_per_sec_p90: float | None = Field(default=None, ge=0)
    tokens_per_sec_p99: float | None = Field(default=None, ge=0)
    requests_per_second_actual: float = Field(..., ge=0)
    result_file: str = Field(default="result.jsonl")
    notes: str | None = Field(default=None)
