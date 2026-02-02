#!/usr/bin/env python3
"""Quick test script for Flocust load testing."""

import pathlib
import time

from flocust.common.analyzer import compute_report, write_report
from flocust.common.config import RunConfig
from flocust.common.dashboard import display_dashboard
from flocust.common.runner import run_experiment

config = RunConfig(
    base_url="https://qa-gateway.flotorch.cloud/openai/v1",
    api_key="your-api-key",
    model="gpt-4o-mini",
    concurrency=5,
    requests_per_second=1.0,
    max_tokens=40,
    prompts_path=pathlib.Path("prompts.jsonl"),
    output_dir=pathlib.Path("."),
    num_requests=10,
    encoding="cl100k_base",
)

print("Starting Flocust load test...")
start_time = time.time()

try:
    results, result_path, output_dir, duration_seconds = run_experiment(config)
    end_time = time.time()

    print(f"\nCompleted in {end_time - start_time:.1f}s")

    if results:
        report = compute_report(
            results,
            experiment_id="test_run",
            duration_seconds=duration_seconds,
            result_file=result_path.name,
        )
        write_report(report, output_dir / "report.json")
        display_dashboard(report, results)
    else:
        print("No requests completed - check server status and credentials")

except Exception as e:
    end_time = time.time()
    print(f"Test failed after {end_time - start_time:.1f}s: {e}")
    import traceback
    traceback.print_exc()
