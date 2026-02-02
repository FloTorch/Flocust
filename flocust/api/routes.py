"""
API routes: one run endpoint (upload file or generate prompts), download report, health.

- POST /api/run — multipart: optional prompts_file OR generate_prompts=true.
- GET /api/report?report_id=... — download full report JSON.
- GET /health — health check.
"""

import json
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from flocust.common.analyzer import compute_report
from flocust.common.config import RunConfig
from flocust.common.models import ReportCard, RequestResult
from flocust.common.runner import run_experiment

from .constants import (
    ALLOWED_PROMPTS_EXTENSIONS,
    DEFAULT_BASE_URL,
    PROMPTS_FILENAME,
)
from .report_registry import get_path, register
from .schemas import RunExperimentResponse, report_to_summary

router = APIRouter(prefix="/api", tags=["experiments"])

FULL_REPORT_FILENAME = "flocust_full_report.json"


def _build_config(
    *,
    base_url: str,
    api_key: str,
    model: str,
    concurrency: int,
    requests_per_second: float,
    num_requests: int,
    max_tokens: int,
    prompts_path: Path | None,
    output_dir: Path,
    encoding: Literal["cl100k_base", "o200k_base", "p50k_base", "r50k_base"] = "cl100k_base",
    stream: bool = True,
    generate_prompts: bool = False,
    generate_prompts_count: int | None = None,
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
        stream=stream,
        generate_prompts=generate_prompts,
        generate_prompts_count=generate_prompts_count,
    )


def _write_full_report_async(report_id: str, report: ReportCard, results: list[RequestResult]) -> None:
    """
    Background task: write full report (report + results) to a temp file and register path.
    Runs outside request context; do not raise.
    """
    try:
        fd, path = tempfile.mkstemp(suffix=".json", prefix="flocust_report_")
        try:
            with open(fd, "w", encoding="utf-8") as f:
                payload = {
                    "report": report.model_dump(mode="json"),
                    "results": [r.model_dump(mode="json") for r in results],
                }
                json.dump(payload, f, indent=2)
            register(report_id, Path(path))
        except Exception:
            try:
                Path(path).unlink(missing_ok=True)
            except OSError:
                pass
    except OSError:
        pass


def _cleanup_report_after_send(report_id: str) -> None:
    """Background task: remove report from registry and delete temp file."""
    from .report_registry import pop_path

    path = pop_path(report_id)
    if path is not None and path.exists():
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def _run_and_prepare_response(
    config: RunConfig,
    experiment_id: str,
    background_tasks: BackgroundTasks,
) -> RunExperimentResponse:
    """
    Run experiment in temp dir, compute report, schedule async full-report write,
    return slim report + report_id. Caller must delete temp dir.
    """
    results, result_path, out_dir, duration_seconds = run_experiment(config)
    report = compute_report(
        results,
        experiment_id=experiment_id,
        duration_seconds=duration_seconds,
        result_file=result_path.name,
    )
    report_id = uuid.uuid4().hex
    background_tasks.add_task(_write_full_report_async, report_id, report, results)
    summary = report_to_summary(report)
    return RunExperimentResponse(report=summary, report_id=report_id)


@router.post(
    "/run",
    response_model=RunExperimentResponse,
    summary="Run load test",
    response_description="Slim report + report_id. Use GET /api/report?report_id=... to download full report.",
)
async def run_experiment_endpoint(
    background_tasks: BackgroundTasks,
    prompts_file: UploadFile | None = File(
        default=None,
        description="Prompts file (.json or .jsonl). Provide this OR set generate_prompts=true.",
    ),
    base_url: str = Form(default=DEFAULT_BASE_URL),
    api_key: str = Form(...),
    model: str = Form(...),
    concurrency: int = Form(default=10, ge=1, le=10_000),
    requests_per_second: float = Form(default=5.0, ge=0.1, le=10_000.0),
    num_requests: int = Form(default=100, ge=1, le=1_000_000),
    max_tokens: int = Form(default=1024, ge=1, le=128_000),
    encoding: str = Form(default="cl100k_base"),
    stream: bool = Form(default=True, description="Stream responses; if False, only latency is measured."),
    generate_prompts: bool = Form(
        default=False,
        description="Generate prompts via LLM (use when not uploading a file).",
    ),
    generate_prompts_count: int | None = Form(
        default=None,
        description="Number of prompts to generate (default ~15%% of num_requests).",
    ),
) -> RunExperimentResponse:
    """
    Run an LLM load test.

    **Provide prompts in exactly one way:**
    - **Upload a file**: attach `prompts_file` (.json or .jsonl).
    - **Generate prompts**: set `generate_prompts=true` (optionally set `generate_prompts_count`).

    **Response:** `{ "report": { ... }, "report_id": "..." }`. Full report (report + results) is written
    asynchronously; use **GET /api/report?report_id={report_id}** to download the JSON file.
    """
    has_file = prompts_file is not None and (prompts_file.filename or "").strip() != ""
    if has_file and generate_prompts:
        raise HTTPException(
            status_code=400,
            detail="Provide either prompts_file (upload) or generate_prompts=true, not both.",
        )
    if not has_file and not generate_prompts:
        raise HTTPException(
            status_code=400,
            detail="Provide prompts_file (upload) or set generate_prompts=true.",
        )

    run_id = uuid.uuid4().hex[:8]
    temp_dir = Path(tempfile.mkdtemp(prefix="flocust_"))
    encoding_lit: Literal["cl100k_base", "o200k_base", "p50k_base", "r50k_base"] = (
        encoding if encoding in ("cl100k_base", "o200k_base", "p50k_base", "r50k_base") else "cl100k_base"
    )
    try:
        if has_file and prompts_file:
            suffix = Path(prompts_file.filename or "").suffix.lower()
            if suffix not in ALLOWED_PROMPTS_EXTENSIONS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Prompts file must be .json or .jsonl; got {suffix!r}.",
                )
            content = await prompts_file.read()
            if not content or not content.strip():
                raise HTTPException(status_code=400, detail="Prompts file is empty.")
            prompts_path = temp_dir / (PROMPTS_FILENAME if suffix == ".jsonl" else "prompts.json")
            prompts_path.write_bytes(content)
            config = _build_config(
                base_url=base_url,
                api_key=api_key,
                model=model,
                concurrency=concurrency,
                requests_per_second=requests_per_second,
                num_requests=num_requests,
                max_tokens=max_tokens,
                prompts_path=prompts_path,
                output_dir=temp_dir,
                encoding=encoding_lit,
                stream=stream,
                generate_prompts=False,
                generate_prompts_count=None,
            )
        else:
            config = _build_config(
                base_url=base_url,
                api_key=api_key,
                model=model,
                concurrency=concurrency,
                requests_per_second=requests_per_second,
                num_requests=num_requests,
                max_tokens=max_tokens,
                prompts_path=None,
                output_dir=temp_dir,
                encoding=encoding_lit,
                stream=stream,
                generate_prompts=True,
                generate_prompts_count=generate_prompts_count,
            )
        return _run_and_prepare_response(config, run_id, background_tasks)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@router.get(
    "/report",
    summary="Download full report",
    response_description="JSON file with report + results. File is removed after send.",
)
def get_report(
    report_id: str,
    background_tasks: BackgroundTasks,
) -> FileResponse:
    """
    Download the full report (report + results) as a JSON file.

    Use the **report_id** returned from POST /api/run. Reports expire after 1 hour.
    The file is deleted after the response is sent.
    """
    path = get_path(report_id)
    if path is None or not path.exists():
        raise HTTPException(
            status_code=404,
            detail="Report not found or expired. Run an experiment first and use the returned report_id within 1 hour.",
        )
    background_tasks.add_task(_cleanup_report_after_send, report_id)
    return FileResponse(
        path=path,
        filename=FULL_REPORT_FILENAME,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{FULL_REPORT_FILENAME}"'},
    )
