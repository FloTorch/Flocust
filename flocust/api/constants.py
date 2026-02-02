"""API constants: default URLs, allowed file types, and directory names."""

from pathlib import Path

__all__ = [
    "ALLOWED_PROMPTS_EXTENSIONS",
    "API_PREFIX",
    "API_VERSION",
    "DEFAULT_BASE_URL",
    "DIR_ARTIFACTS",
    "DIR_EXPERIMENTS",
    "DOCS_PATH",
    "OPENAPI_JSON_PATH",
    "PROMPTS_FILENAME",
    "REPORT_FILENAME",
    "RESULTS_FILENAME",
    "SERVICE_NAME",
    "artifacts_root",
    "experiments_root",
]

# Default LLM API base URL (OpenAI-compatible). No trailing slash.
DEFAULT_BASE_URL = "https://gateway.flotorch.cloud/openai/v1"

# Allowed extensions for prompts file upload.
ALLOWED_PROMPTS_EXTENSIONS = (".json", ".jsonl")

# Directory names used by the API (relative to CWD when server starts).
DIR_EXPERIMENTS = "experiments"
DIR_ARTIFACTS = "artifacts"

# Filename written when using inline prompts or upload.
PROMPTS_FILENAME = "prompts.jsonl"
REPORT_FILENAME = "report.json"
RESULTS_FILENAME = "results.jsonl"

# OpenAPI / service metadata.
SERVICE_NAME = "flocust"
API_VERSION = "0.1.0"
API_PREFIX = "/api"
DOCS_PATH = "/docs"
OPENAPI_JSON_PATH = "/openapi.json"


def experiments_root(base: Path | None = None) -> Path:
    """Return the experiments directory path."""
    return (base or Path.cwd()) / DIR_EXPERIMENTS


def artifacts_root(base: Path | None = None) -> Path:
    """Return the artifacts directory path."""
    return (base or Path.cwd()) / DIR_ARTIFACTS
