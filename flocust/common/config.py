"""Configuration models for LLM load test runs."""

import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


def artifact_output_dir(
    model: str,
    concurrency: int,
    requests_per_second: float,
    base: Path | None = None,
) -> Path:
    """Return artifacts/{modelname}-users{N}-rps{R} for standardized output (no user prompt)."""
    base = base or Path(".")
    # Safe dir name: replace / and strip invalid chars
    slug = re.sub(r"[^\w\-.]", "-", model.replace("/", "-").strip()) or "model"
    rps = int(round(requests_per_second))
    return base / "artifacts" / f"{slug}-users{concurrency}-rps{rps}"


def _normalize_base_url(url: str) -> str:
    """Fix common base URL typos (e.g. htttps -> https) so the endpoint is hit correctly."""
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


class RunConfig(BaseModel):
    """Configuration for a single load test experiment."""

    base_url: str = Field(..., description="LLM API base URL (e.g. https://api.openai.com/v1)")
    api_key: str = Field(..., description="API key for authentication")
    model: str = Field(..., description="Model name (e.g. gpt-4, claude-3)")
    concurrency: int = Field(ge=1, le=10_000, description="Number of concurrent users")
    requests_per_second: float = Field(ge=0.1, le=10_000.0, description="Target requests per second")
    max_tokens: int = Field(ge=1, le=128_000, default=1024, description="Max tokens per completion")
    prompts_path: Path = Field(..., description="Path to prompts.json or prompts.jsonl")
    output_dir: Path = Field(default_factory=lambda: Path("."), description="Directory for result.jsonl and report")
    num_requests: int = Field(ge=1, le=1_000_000, default=100, description="Total number of requests to run (stop when reached)")
    encoding: Literal["cl100k_base", "o200k_base", "p50k_base", "r50k_base"] = Field(
        default="cl100k_base",
        description="Tiktoken encoding for token counting",
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_base_url(cls, data: Any) -> Any:
        if isinstance(data, dict) and "base_url" in data and data["base_url"]:
            data = {**data, "base_url": _normalize_base_url(data["base_url"])}
        return data

    @property
    def chat_completions_url(self) -> str:
        """URL for OpenAI-compatible chat completions endpoint."""
        base = self.base_url.rstrip("/")
        return f"{base}/chat/completions"

    class Config:
        arbitrary_types_allowed = True
