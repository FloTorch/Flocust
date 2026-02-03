"""Configuration models for LLM load test runs."""

import json
import os
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

_ENV_VAR_PATTERN = re.compile(r"^\$([A-Za-z_][A-Za-z0-9_]*)$")
_ENV_VAR_PATTERN_ALT = re.compile(r"^env:([A-Za-z_][A-Za-z0-9_]*)$")


def _resolve_env_string(s: str) -> str:
    """Resolve $VAR or env:VAR to os.environ value."""
    if not s or not isinstance(s, str):
        return s or ""
    s = s.strip()
    m = _ENV_VAR_PATTERN.match(s)
    if m:
        return os.environ.get(m.group(1), "")
    m = _ENV_VAR_PATTERN_ALT.match(s)
    if m:
        return os.environ.get(m.group(1), "")
    return s


class ProviderSettings(BaseModel):
    """Provider-specific settings from config file."""

    api_key: str = ""
    model: str = "gpt-4o-mini"
    base_url: str = "https://api.openai.com/v1"
    headers: dict[str, str] = Field(default_factory=dict)


class BenchSettings(BaseModel):
    """Benchmark run parameters."""

    concurrency: int = Field(default=10, ge=1, le=10_000)
    requests: int = Field(default=100, ge=1, le=1_000_000)
    requests_per_second: float = Field(default=0, ge=0, description="Target RPS (0 = max throughput)")
    duration_sec: float = Field(default=0, ge=0)
    ramp_up_sec: float = Field(default=0, ge=0)
    timeout_sec: int = Field(default=60, ge=1, le=300)
    max_tokens: int = Field(default=1024, ge=1, le=128_000)
    stream: bool = Field(default=True, description="Use streaming for TTFT/inter-token metrics")
    prompt_cache: bool = Field(
        default=False,
        description="Enable OpenAI-style prompt caching (default: disabled for reproducible load tests)",
    )
    generate_prompts: bool = Field(default=False, description="Generate prompts via LLM before run")
    generate_prompts_count: int | None = Field(default=None, ge=1, le=1000, description="Number of prompts to generate")


class ReportSettings(BaseModel):
    """Report output options."""

    format: Literal["console", "json"] = "console"


class ConfigFile(BaseModel):
    """Root structure of config JSON file."""

    provider: str = "openai"
    provider_settings: ProviderSettings = Field(default_factory=ProviderSettings)
    bench: BenchSettings = Field(default_factory=BenchSettings)
    input_file: str = "prompts.jsonl"
    report: ReportSettings = Field(default_factory=ReportSettings)


def artifact_output_dir(
    model: str,
    concurrency: int,
    requests_per_second: float,
    base: Path | None = None,
) -> Path:
    """Return artifacts/{model}-users{N}-rps{R} for standardized output."""
    base = base or Path(".")
    slug = re.sub(r"[^\w\-.]", "-", model.replace("/", "-").strip()) or "model"
    rps = int(round(requests_per_second))
    return base / "artifacts" / f"{slug}-users{concurrency}-rps{rps}"


def normalize_base_url(url: str) -> str:
    """Normalize base URL (fix typos, ensure scheme)."""
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

    base_url: str = Field(..., description="LLM API base URL")
    api_key: str = Field(..., description="API key for authentication")
    model: str = Field(..., description="Model name")
    concurrency: int = Field(ge=1, le=10_000, description="Number of concurrent users")
    requests_per_second: float = Field(
        ge=0.1, le=10_000.0,
        description="Target RPS when use_rps_throttle is True",
    )
    max_tokens: int = Field(ge=1, le=128_000, default=1024, description="Max tokens per completion")
    prompts_path: Path | None = Field(
        default=None,
        description="Path to prompts file. Required unless generate_prompts is True.",
    )
    output_dir: Path = Field(default_factory=lambda: Path("."), description="Output directory")
    num_requests: int = Field(
        ge=1, le=1_000_000, default=100,
        description="Total requests; ignored when duration_sec > 0",
    )
    timeout_sec: int = Field(default=60, ge=1, le=300, description="Request timeout (seconds)")
    duration_sec: float = Field(default=0, ge=0, description="Run for N seconds (overrides num_requests when > 0)")
    ramp_up_sec: float = Field(default=0, ge=0, description="Stagger worker start over N seconds")
    use_rps_throttle: bool = Field(
        default=False,
        description="When False, max throughput; when True, throttle to requests_per_second",
    )
    stream: bool = Field(default=True, description="Use streaming for TTFT/inter-token metrics")
    prompt_cache: bool = Field(
        default=False,
        description="Enable prompt caching; when False, each request is made unique to avoid cache hits",
    )
    generate_prompts: bool = Field(default=False, description="Generate prompts via LLM before run")
    generate_prompts_count: int | None = Field(default=None, ge=1, le=1000)
    encoding: Literal["cl100k_base", "o200k_base", "p50k_base", "r50k_base"] = Field(
        default="cl100k_base",
        description="Tiktoken encoding for token counting",
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_base_url(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get("base_url"):
            data = {**data, "base_url": normalize_base_url(data["base_url"])}
        return data

    @model_validator(mode="after")
    def _require_prompts_path_unless_generate(self) -> "RunConfig":
        if not self.generate_prompts and self.prompts_path is None:
            raise ValueError("prompts_path is required when generate_prompts is False")
        return self

    @property
    def chat_completions_url(self) -> str:
        """OpenAI-compatible chat completions URL."""
        return f"{self.base_url.rstrip('/')}/chat/completions"

    class Config:
        arbitrary_types_allowed = True


def _resolve_provider_env(cfg: ConfigFile) -> None:
    """Resolve env var references in config."""
    ps = cfg.provider_settings
    ps.api_key = _resolve_env_string(ps.api_key)
    if cfg.provider == "openai" and not ps.api_key:
        ps.api_key = os.environ.get("OPENAI_API_KEY", "")
    ps.base_url = _resolve_env_string(ps.base_url)
    cfg.input_file = _resolve_env_string(cfg.input_file)
    cfg.report.format = _resolve_env_string(cfg.report.format) or cfg.report.format
    if ps.headers:
        ps.headers = {k: _resolve_env_string(v) for k, v in ps.headers.items()}


def load_config_from_file(path: Path) -> RunConfig:
    """Load config from JSON file and return RunConfig. Resolves env vars ($VAR, env:VAR)."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))
    cfg = ConfigFile.model_validate(raw)
    _resolve_provider_env(cfg)

    ps = cfg.provider_settings
    bench = cfg.bench
    base = path.parent
    slug = re.sub(r"[^\w\-.]", "-", ps.model.replace("/", "-").strip()) or "model"
    rps = bench.requests_per_second if bench.requests_per_second > 0 else bench.concurrency
    out_dir = base / "artifacts" / f"{slug}_{bench.concurrency}_{bench.requests}_{int(rps)}"

    # Resolve prompts path
    input_file_resolved = cfg.input_file.strip()
    if not input_file_resolved and not bench.generate_prompts:
        raise ValueError("input_file is required when generate_prompts is false")

    if input_file_resolved:
        input_path = Path(input_file_resolved)
        if not input_path.is_absolute():
            input_path = (path.parent / input_path).resolve()
    else:
        # When generate_prompts is true and no input_file, we'll generate to output_dir
        input_path = out_dir / "generated_prompts.json"

    # Use RPS throttle if requests_per_second > 0, otherwise max throughput
    use_rps_throttle = bench.requests_per_second > 0
    rps = bench.requests_per_second if use_rps_throttle else float(bench.concurrency)

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
        duration_sec=bench.duration_sec,
        ramp_up_sec=bench.ramp_up_sec,
        use_rps_throttle=use_rps_throttle,
        stream=bench.stream,
        prompt_cache=bench.prompt_cache,
        generate_prompts=bench.generate_prompts,
        generate_prompts_count=bench.generate_prompts_count,
        encoding="cl100k_base",
    )