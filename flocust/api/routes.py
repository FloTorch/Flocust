"""API routes for running experiments and fetching results."""

import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from flocust.common.analyzer import compute_report, write_report
from flocust.common.config import RunConfig, artifact_output_dir
from flocust.common.models import ReportCard
from flocust.common.runner import run_experiment

from .constants import (
    ALLOWED_PROMPTS_EXTENSIONS,
    DEFAULT_BASE_URL,
    DIR_ARTIFACTS,
    DIR_EXPERIMENTS,
    PROMPTS_FILENAME,
    REPORT_FILENAME,
)
from .schemas import RunExperimentRequest, RunExperimentResponse

router = APIRouter(prefix="/api", tags=["experiments"])


def _experiments_dir() -> Path:
    """Return the experiments root directory (under CWD)."""
    return Path.cwd() / DIR_EXPERIMENTS


def _artifacts_dir() -> Path:
    """Return the artifacts root directory (under CWD)."""
    return Path.cwd() / DIR_ARTIFACTS


def _build_config(
    *,
    base_url: str,
    api_key: str,
    model: str,
    concurrency: int,
    requests_per_second: float,
    num_requests: int,
    max_tokens: int,
    prompts_path: Path,
    output_dir: Path,
    encoding: Literal["cl100k_base", "o200k_base", "p50k_base", "r50k_base"] = "cl100k_base",
) -> RunConfig:
    """Build RunConfig from common parameters."""
    return RunConfig(
        base_url=base_url,
        api_key=api_key,
        model=model,
        concurrency=concurrency,
        requests_per_second=requests_per_second,
        num_requests=num_requests,
        max_tokens=max_tokens,
        prompts_path=prompts_path,
        output_dir=output_dir,
        encoding=encoding,
    )


def _run_and_report(
    config: RunConfig,
    experiment_id: str,
) -> tuple[ReportCard, Path, Path]:
    """
    Run the experiment and write the report. Returns (report, result_path, report_path).
    """
    results, result_path, out_dir, duration_seconds = run_experiment(config)
    report = compute_report(
        results,
        experiment_id=experiment_id,
        duration_seconds=duration_seconds,
        result_file=result_path.name,
    )
    report_path = out_dir / REPORT_FILENAME
    write_report(report, report_path)
    return report, result_path, report_path


def _validate_prompts_source(
    prompts: list[str] | None,
    prompts_path: str | None,
) -> None:
    """Raise HTTP 400 if prompts source is ambiguous or missing."""
    if prompts and prompts_path:
        raise HTTPException(
            status_code=400,
            detail="Provide exactly one of: 'prompts' (inline list) or 'prompts_path' (server path).",
        )
    if not prompts and not prompts_path:
        raise HTTPException(
            status_code=400,
            detail="Provide either 'prompts' (inline list) or 'prompts_path' (server path). Or use POST /api/experiments/run/upload to upload a prompts file.",
        )


@router.post(
    "/experiments/run",
    response_model=RunExperimentResponse,
    summary="Run experiment (JSON body)",
    response_description="Report card and paths to result and report files.",
)
def run_experiment_endpoint(body: RunExperimentRequest) -> RunExperimentResponse:
    """
    Run an LLM load test experiment using a JSON body.

    **Prompts:** Provide exactly one of:

    - **prompts**: list of strings (e.g. `["What is 2+2?", "Say hello."]`)
    - **prompts_path**: path to a prompts file on the server (e.g. `prompts.jsonl`)

    For file upload (prompts.jsonl or prompts.json), use **POST /api/experiments/run/upload** instead.

    Writes `results.jsonl` and `report.json` under the output directory and returns the report plus paths.
    """
    _validate_prompts_source(body.prompts, body.prompts_path)

    if body.prompts:
        run_id = uuid.uuid4().hex[:8]
        output_dir = _experiments_dir() / run_id
        output_dir.mkdir(parents=True, exist_ok=True)
        prompts_path = output_dir / PROMPTS_FILENAME
        prompts_path.write_text("\n".join(body.prompts), encoding="utf-8")
        config = _build_config(
            base_url=body.base_url,
            api_key=body.api_key,
            model=body.model,
            concurrency=body.concurrency,
            requests_per_second=body.requests_per_second,
            num_requests=body.num_requests,
            max_tokens=body.max_tokens,
            prompts_path=prompts_path,
            output_dir=output_dir,
            encoding=body.encoding,
        )
        experiment_id = run_id
    else:
        path = Path(body.prompts_path)
        if not path.is_absolute():
            path = Path.cwd().resolve() / path
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"Prompts file not found: {path}")
        output_dir = (
            Path(body.output_dir)
            if body.output_dir
            else artifact_output_dir(body.model, body.concurrency, body.requests_per_second)
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        config = _build_config(
            base_url=body.base_url,
            api_key=body.api_key,
            model=body.model,
            concurrency=body.concurrency,
            requests_per_second=body.requests_per_second,
            num_requests=body.num_requests,
            max_tokens=body.max_tokens,
            prompts_path=path,
            output_dir=output_dir,
            encoding=body.encoding,
        )
        experiment_id = output_dir.name

    report, result_path, report_path = _run_and_report(config, experiment_id)

    return RunExperimentResponse(
        report=report,
        result_file=result_path.name,
        result_path=str(result_path.resolve()),
        report_path=str(report_path.resolve()),
    )


@router.post(
    "/experiments/run/upload",
    response_model=RunExperimentResponse,
    summary="Run experiment (upload prompts file)",
    response_description="Report card and paths to result and report files.",
)
async def run_experiment_upload_endpoint(
    prompts_file: UploadFile = File(
        ...,
        description="Prompts file: .json or .jsonl. JSON: list of strings or object with 'prompts' key. JSONL: one prompt per line or one JSON object per line with 'prompt'/'text' key.",
    ),
    base_url: str = Form(
        default=DEFAULT_BASE_URL,
        description="LLM API base URL (OpenAI-compatible).",
    ),
    api_key: str = Form(..., description="API key for the LLM provider."),
    model: str = Form(..., description="Model name (e.g. flotorch/gemini-flash)."),
    concurrency: int = Form(default=10, ge=1, le=10_000),
    requests_per_second: float = Form(default=5.0, ge=0.1, le=10_000.0),
    num_requests: int = Form(default=100, ge=1, le=1_000_000),
    max_tokens: int = Form(default=1024, ge=1, le=128_000),
    encoding: str = Form(default="cl100k_base"),
    output_dir: str | None = Form(default=None),
) -> RunExperimentResponse:
    """
    Run an LLM load test experiment by uploading a prompts file.

    **Upload:** Send `prompts_file` as multipart/form-data. File must be **.json** or **.jsonl**.

    - **.json**: array of strings, or object with `"prompts": [...]`
    - **.jsonl**: one prompt per line (plain text) or one JSON object per line with `prompt`/`text`/`content` key

    All other parameters are form fields. Default base URL is the Flotorch gateway.
    """
    suffix = Path(prompts_file.filename or "").suffix.lower()
    if suffix not in ALLOWED_PROMPTS_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Prompts file must have extension .json or .jsonl; got {suffix!r}. Upload a prompts.json or prompts.jsonl file.",
        )

    content = await prompts_file.read()
    if not content or not content.strip():
        raise HTTPException(status_code=400, detail="Prompts file is empty.")

    run_id = uuid.uuid4().hex[:8]
    out_dir = _experiments_dir() / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    # Keep original extension so loader can choose JSON vs JSONL.
    prompts_path = out_dir / (PROMPTS_FILENAME if suffix == ".jsonl" else "prompts.json")
    prompts_path.write_bytes(content)

    encoding_lit: Literal["cl100k_base", "o200k_base", "p50k_base", "r50k_base"] = (
        encoding if encoding in ("cl100k_base", "o200k_base", "p50k_base", "r50k_base") else "cl100k_base"
    )
    config = _build_config(
        base_url=base_url,
        api_key=api_key,
        model=model,
        concurrency=concurrency,
        requests_per_second=requests_per_second,
        num_requests=num_requests,
        max_tokens=max_tokens,
        prompts_path=prompts_path,
        output_dir=out_dir,
        encoding=encoding_lit,
    )

    report, result_path, report_path = _run_and_report(config, run_id)

    return RunExperimentResponse(
        report=report,
        result_file=result_path.name,
        result_path=str(result_path.resolve()),
        report_path=str(report_path.resolve()),
    )


def _is_safe_path(file_path: Path, *allowed_roots: Path) -> bool:
    """Return True if file_path is under one of the allowed roots (no path traversal)."""
    resolved = file_path.resolve()
    for root in allowed_roots:
        try:
            resolved.relative_to(root.resolve())
            return True
        except ValueError:
            continue
    return False


@router.get(
    "/experiments/result/{path:path}",
    summary="Download a result or report file",
    response_description="File content (e.g. results.jsonl or report.json).",
)
def get_result_file(path: str) -> FileResponse:
    """
    Serve a result file by path. Path must be under `experiments/`, `artifacts/`, or the server CWD.

    Example paths: `artifacts/model-users10-rps5/results.jsonl`, `experiments/abc123/report.json`.
    """
    p = Path(path).resolve()
    experiments = _experiments_dir()
    artifacts = _artifacts_dir()
    cwd = Path.cwd()
    if not _is_safe_path(p, experiments, artifacts, cwd):
        raise HTTPException(
            status_code=403,
            detail="Path must be under experiments/, artifacts/, or current working directory.",
        )
    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail="File not found.")
    return FileResponse(p, filename=p.name, media_type="application/x-ndjson")
