"""Request/response schemas for the FastAPI server."""

from typing import Literal

__all__ = ["RunExperimentRequest", "RunExperimentResponse"]

from pydantic import BaseModel, Field

from flocust.api.constants import DEFAULT_BASE_URL
from flocust.common.models import ReportCard


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
    encoding: Literal["cl100k_base", "o200k_base", "p50k_base", "r50k_base"] = Field(
        default="cl100k_base",
        description="Tiktoken encoding for input token counting.",
    )
    output_dir: str | None = Field(
        default=None,
        description="Output directory for results (default: auto-generated under artifacts/).",
    )


class RunExperimentResponse(BaseModel):
    """Response for POST /api/experiments/run and POST /api/experiments/run/upload."""

    report: ReportCard = Field(
        ...,
        description="Aggregated metrics: latency, TTFT, inter-token latency, RPS.",
    )
    result_file: str = Field(
        ...,
        description="Filename of the results file (e.g. results.jsonl).",
    )
    result_path: str = Field(
        ...,
        description="Absolute path to the results file on the server.",
    )
    report_path: str = Field(
        ...,
        description="Absolute path to the report JSON file on the server.",
    )
