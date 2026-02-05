"""
API routes: run load test, download report.

POST /api/run — multipart: prompts_file (upload) OR generate_prompts=true.
GET /api/report?report_id=... — download full report JSON.
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
    timeout_sec: int,
    duration_sec: float,
    ramp_up_sec: float,
    use_rps_throttle: bool,
    prompts_path: Path | None,
    output_dir: Path,
    encoding: Literal["cl100k_base", "o200k_base", "p50k_base", "r50k_base"],
    stream: bool,
    generate_prompts: bool,
    generate_prompts_count: int | None,
    generate_prompts_from_file: bool = False,
    prompt_mean_input_tokens: int | None = None,
    prompt_stddev_input_tokens: int | None = None,
    prompt_mean_output_tokens: int | None = None,
) -> RunConfig:
    """Build RunConfig from API form parameters."""
    return RunConfig(
        base_url=base_url,
        api_key=api_key,
        model=model,
        concurrency=concurrency,
        requests_per_second=requests_per_second,
        num_requests=num_requests,
        max_tokens=max_tokens,
        timeout_sec=timeout_sec,
        duration_sec=duration_sec,
        ramp_up_sec=ramp_up_sec,
        use_rps_throttle=use_rps_throttle,
        prompts_path=prompts_path,
        output_dir=output_dir,
        encoding=encoding,
        stream=stream,
        generate_prompts=generate_prompts,
        generate_prompts_count=generate_prompts_count,
        generate_prompts_from_file=generate_prompts_from_file,
        prompt_mean_input_tokens=prompt_mean_input_tokens,
        prompt_stddev_input_tokens=prompt_stddev_input_tokens,
        prompt_mean_output_tokens=prompt_mean_output_tokens,
    )


def _write_full_report_async(
    report_id: str,
    report: ReportCard,
    results: list[RequestResult],
) -> None:
    """Write full report to temp file and register path. Runs in background."""
    try:
        fd, path = tempfile.mkstemp(suffix=".json", prefix="flocust_report_")
        try:
            with open(fd, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "report": report.model_dump(mode="json"),
                        "results": [r.model_dump(mode="json") for r in results],
                    },
                    f,
                    indent=2,
                )
            register(report_id, Path(path))
        except Exception:
            try:
                Path(path).unlink(missing_ok=True)
            except OSError:
                pass
    except OSError:
        pass


def _cleanup_report_after_send(report_id: str) -> None:
    """Remove report from registry and delete temp file."""
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
    """Run experiment, compute report, schedule full-report write, return summary + report_id."""
    results, result_path, out_dir, duration_seconds = run_experiment(config)
    report = compute_report(
        results,
        experiment_id=experiment_id,
        duration_seconds=duration_seconds,
        result_file=result_path.name,
    )
    report_id = uuid.uuid4().hex
    background_tasks.add_task(_write_full_report_async, report_id, report, results)
    return RunExperimentResponse(
        report=report_to_summary(report),
        report_id=report_id,
    )


@router.post(
    "/run",
    response_model=RunExperimentResponse,
    summary="Run load test",
    response_description="Report summary + report_id. Use GET /api/report?report_id=... for full report.",
)
async def run_experiment_endpoint(
    background_tasks: BackgroundTasks,
    prompts_file: UploadFile | None = File(default=None, description="Prompts file (.json or .jsonl)"),
    base_url: str = Form(default=DEFAULT_BASE_URL, description="LLM API base URL"),
    api_key: str = Form(..., description="API key"),
    model: str = Form(..., description="Model name"),
    concurrency: int = Form(10, ge=1, le=10_000, description="Concurrent users"),
    requests_per_second: float = Form(5.0, ge=0.1, le=10_000.0, description="Target RPS (when use_rps_throttle)"),
    num_requests: int = Form(100, ge=1, le=1_000_000, description="Total requests"),
    duration_sec: float = Form(0, ge=0, description="Run duration in seconds (overrides num_requests when > 0)"),
    ramp_up_sec: float = Form(0, ge=0, description="Stagger worker start (seconds)"),
    use_rps_throttle: bool = Form(False, description="Throttle to RPS (false = max throughput)"),
    timeout_sec: int = Form(60, ge=1, le=300, description="Per-request timeout (seconds)"),
    max_tokens: int = Form(1024, ge=1, le=128_000, description="Max completion tokens"),
    encoding: str = Form("cl100k_base", description="Tiktoken encoding"),
    stream: bool = Form(True, description="Stream for TTFT/inter-token metrics"),
    generate_prompts: bool = Form(False, description="Generate prompts via LLM"),
    generate_prompts_count: int | None = Form(None, description="Number of prompts to generate"),
    generate_prompts_from_file: bool = Form(False, description="Generate prompts from source file (no LLM call). Defaults to default text file. Upload source_file to specify custom .txt file."),
    source_file: UploadFile | None = File(default=None, description="Source text file (.txt) for file-based prompt generation. If not provided, uses default sonnet.txt. Only used when generate_prompts_from_file=true."),
    prompt_mean_input_tokens: int | None = Form(None, ge=1, description="Mean input tokens for generated prompts"),
    prompt_stddev_input_tokens: int | None = Form(None, ge=0, description="Stddev input tokens for generated prompts"),
    prompt_mean_output_tokens: int | None = Form(None, ge=1, description="Mean output tokens for generated prompts"),
) -> RunExperimentResponse:
    """
    Run an LLM load test.

    Provide prompts in one way:
    - Upload a file: attach `prompts_file` (.json or .jsonl).
    - Or set `generate_prompts=true` (optionally `generate_prompts_count`).
    - Or set `generate_prompts_from_file=true` with token parameters. Upload `source_file` (.txt) for custom source, or leave blank to use default sonnet.txt.

    duration_sec > 0: run for N seconds; else run until num_requests.
    use_rps_throttle=true: throttle to requests_per_second; false: max throughput.

    Returns report summary and report_id. Full report (report + results) is written
    asynchronously; use GET /api/report?report_id={report_id} to download.
    """
    has_file = prompts_file is not None and (prompts_file.filename or "").strip() != ""
    if has_file and (generate_prompts or generate_prompts_from_file):
        raise HTTPException(
            status_code=400,
            detail="Provide either prompts_file, generate_prompts=true, or generate_prompts_from_file=true, not multiple.",
        )
    if not has_file and not generate_prompts and not generate_prompts_from_file:
        raise HTTPException(
            status_code=400,
            detail="Provide prompts_file (upload), set generate_prompts=true, or set generate_prompts_from_file=true.",
        )
    if generate_prompts and generate_prompts_from_file:
        raise HTTPException(
            status_code=400,
            detail="Cannot use both generate_prompts and generate_prompts_from_file.",
        )
    if generate_prompts_from_file:
        if prompt_mean_input_tokens is None or prompt_stddev_input_tokens is None or prompt_mean_output_tokens is None:
            raise HTTPException(
                status_code=400,
                detail="prompt_mean_input_tokens, prompt_stddev_input_tokens, and prompt_mean_output_tokens are required when generate_prompts_from_file=true.",
            )

    run_id = uuid.uuid4().hex[:8]
    temp_dir = Path(tempfile.mkdtemp(prefix="flocust_"))
    encoding_lit: Literal["cl100k_base", "o200k_base", "p50k_base", "r50k_base"] = (
        encoding if encoding in ("cl100k_base", "o200k_base", "p50k_base", "r50k_base")
        else "cl100k_base"
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
            prompts_path = temp_dir / (
                PROMPTS_FILENAME if suffix == ".jsonl" else "prompts.json"
            )
            prompts_path.write_bytes(content)
            config = _build_config(
                base_url=base_url,
                api_key=api_key,
                model=model,
                concurrency=concurrency,
                requests_per_second=requests_per_second,
                num_requests=num_requests,
                max_tokens=max_tokens,
                timeout_sec=timeout_sec,
                duration_sec=duration_sec,
                ramp_up_sec=ramp_up_sec,
                use_rps_throttle=use_rps_throttle,
                prompts_path=prompts_path,
                output_dir=temp_dir,
                encoding=encoding_lit,
                stream=stream,
                generate_prompts=False,
                generate_prompts_count=None,
                generate_prompts_from_file=False,
                prompt_mean_input_tokens=None,
                prompt_stddev_input_tokens=None,
                prompt_mean_output_tokens=None,
            )
        elif generate_prompts_from_file:
            # When generate_prompts_from_file=True, count must be None or 1–1000
            count = generate_prompts_count
            if count is None or count < 1:
                count = max(1, min(1000, num_requests // 10))
            # Handle source file upload
            source_path: Path | None = None
            if source_file and (source_file.filename or "").strip():
                suffix = Path(source_file.filename or "").suffix.lower()
                if suffix != ".txt":
                    raise HTTPException(
                        status_code=400,
                        detail=f"Source file must be a .txt file, got {suffix!r}.",
                    )
                content = await source_file.read()
                if not content or not content.strip():
                    raise HTTPException(status_code=400, detail="Source file is empty.")
                source_path = temp_dir / "source.txt"
                source_path.write_bytes(content)
            config = _build_config(
                base_url=base_url,
                api_key=api_key,
                model=model,
                concurrency=concurrency,
                requests_per_second=requests_per_second,
                num_requests=num_requests,
                max_tokens=max_tokens,
                timeout_sec=timeout_sec,
                duration_sec=duration_sec,
                ramp_up_sec=ramp_up_sec,
                use_rps_throttle=use_rps_throttle,
                prompts_path=source_path,  # Custom source file or None for default text file
                output_dir=temp_dir,
                encoding=encoding_lit,
                stream=stream,
                generate_prompts=False,
                generate_prompts_count=count,
                generate_prompts_from_file=True,
                prompt_mean_input_tokens=prompt_mean_input_tokens,
                prompt_stddev_input_tokens=prompt_stddev_input_tokens,
                prompt_mean_output_tokens=prompt_mean_output_tokens,
            )
        else:
            # When generate_prompts=True, count must be None or 1–1000 (RunConfig rejects 0)
            count = generate_prompts_count
            if count is None or count < 1:
                count = max(1, min(1000, num_requests // 10))
            config = _build_config(
                base_url=base_url,
                api_key=api_key,
                model=model,
                concurrency=concurrency,
                requests_per_second=requests_per_second,
                num_requests=num_requests,
                max_tokens=max_tokens,
                timeout_sec=timeout_sec,
                duration_sec=duration_sec,
                ramp_up_sec=ramp_up_sec,
                use_rps_throttle=use_rps_throttle,
                prompts_path=None,
                output_dir=temp_dir,
                encoding=encoding_lit,
                stream=stream,
                generate_prompts=True,
                generate_prompts_count=count,
                generate_prompts_from_file=False,
                prompt_mean_input_tokens=None,
                prompt_stddev_input_tokens=None,
                prompt_mean_output_tokens=None,
            )
        return _run_and_prepare_response(config, run_id, background_tasks)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@router.get(
    "/report",
    summary="Download full report",
    response_description="JSON file with report + results. Removed after send.",
)
def get_report(
    report_id: str,
    background_tasks: BackgroundTasks,
) -> FileResponse:
    """Download full report (report + results) as JSON. Use report_id from POST /api/run."""
    path = get_path(report_id)
    if path is None or not path.exists():
        raise HTTPException(
            status_code=404,
            detail="Report not found or expired. Run an experiment and use report_id within 1 hour.",
        )
    background_tasks.add_task(_cleanup_report_after_send, report_id)
    return FileResponse(
        path=path,
        filename=FULL_REPORT_FILENAME,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{FULL_REPORT_FILENAME}"'},
    )
