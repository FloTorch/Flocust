"""Configuration models for LLM load test runs."""

import json
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class ProviderSettings(BaseModel):
    """Provider-specific settings from config.json."""

    api_key: str = ""
    model: str = "gpt-4o-mini"
    base_url: str = "https://api.openai.com/v1"
    headers: dict[str, str] = Field(default_factory=dict)


class BenchSettings(BaseModel):
    """Benchmark settings from config.json."""

    concurrency: int = Field(default=10, ge=1, le=10_000)
    requests: int = Field(default=100, ge=1, le=1_000_000)
    duration_sec: float = Field(default=0, ge=0)
    ramp_up_sec: float = Field(default=0, ge=0)
    timeout_sec: int = Field(default=60, ge=1, le=300)
    max_tokens: int = Field(default=1024, ge=1, le=128_000)


class ReportSettings(BaseModel):
    """Report settings from config.json."""

    format: Literal["console", "json"] = "console"


class ConfigFile(BaseModel):
    """Root structure of config.json."""

    provider: str = "openai"
    provider_settings: ProviderSettings = Field(default_factory=ProviderSettings)
    bench: BenchSettings = Field(default_factory=BenchSettings)
    input_file: str = "prompts.jsonl"
    generate: dict[str, Any] = Field(default_factory=dict)
    report: ReportSettings = Field(default_factory=ReportSettings)


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


def normalize_base_url(url: str) -> str:
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
    prompts_path: Path | None = Field(
        default=None,
        description="Path to prompts.json or prompts.jsonl. Required unless generate_prompts=True.",
    )
    output_dir: Path = Field(default_factory=lambda: Path("."), description="Directory for result.jsonl and report")
    num_requests: int = Field(ge=1, le=1_000_000, default=100, description="Total number of requests to run (stop when reached)")
    timeout_sec: int = Field(default=60, ge=1, le=300, description="Request timeout in seconds")
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
        description="Number of prompts to generate. Default: max(1, num_requests // 10).",
    )
    encoding: Literal["cl100k_base", "o200k_base", "p50k_base", "r50k_base"] = Field(
        default="cl100k_base",
        description="Tiktoken encoding for token counting",
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_base_url(cls, data: Any) -> Any:
        if isinstance(data, dict) and "base_url" in data and data["base_url"]:
            data = {**data, "base_url": normalize_base_url(data["base_url"])}
        return data

    @model_validator(mode="after")
    def require_prompts_path_unless_generate(self) -> "RunConfig":
        if not self.generate_prompts and self.prompts_path is None:
            raise ValueError("prompts_path is required when generate_prompts is False")
        return self

    @property
    def chat_completions_url(self) -> str:
        """URL for OpenAI-compatible chat completions endpoint."""
        base = self.base_url.rstrip("/")
        return f"{base}/chat/completions"

    class Config:
        arbitrary_types_allowed = True


def load_config_from_file(path: Path) -> RunConfig:
    """
    Load configuration from a config.json file and convert to RunConfig.

    Expects JSON with: provider, provider_settings (api_key, model, base_url, headers),
    bench (concurrency, requests, duration_sec, timeout_sec, max_tokens), input_file.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))
    cfg = ConfigFile.model_validate(raw)

    ps = cfg.provider_settings
    bench = cfg.bench

    # Resolve prompts path relative to config file
    input_path = Path(cfg.input_file)
    if not input_path.is_absolute():
        input_path = (path.parent / input_path).resolve()

    # RPS: if duration_sec > 0 use requests/duration, else use concurrency as target throughput
    if bench.duration_sec > 0:
        rps = bench.requests / bench.duration_sec
    else:
        rps = float(bench.concurrency)

    out_dir = artifact_output_dir(ps.model, bench.concurrency, rps)

    return RunConfig(
        base_url=normalize_base_url(ps.base_url),
        api_key=ps.api_key,
        model=ps.model,
        concurrency=bench.concurrency,
        requests_per_second=rps,
        max_tokens=bench.max_tokens,
        prompts_path=input_path,
        output_dir=out_dir,
        num_requests=bench.requests,
        timeout_sec=bench.timeout_sec,
        encoding="cl100k_base",
    )
