"""Example runner to create and execute a pipeline job locally.

Usage: python tools/run_job_example.py
"""
from pathlib import Path
import time
import json
import os

from backend.pipeline import PipelineRunner


def main():
    repo = "https://github.com/keras-team/keras"
    runner = PipelineRunner()
    params = {"repo_url": repo, "model": None}
    job = runner.new_job(params)
    job_id = job["id"]
    print("Created job:", job_id)
    # Run synchronously for the example
    runner.run(job_id, params)
    # Print final status
    status_path = Path(os.getcwd()) / "processing" / "jobs" / f"{job_id}.json"
    if status_path.exists():
        print("Status file:", status_path)
        with open(status_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        print("Final status:", data.get("status"))
        print(json.dumps({"current_step": data.get("current_step"), "steps": data.get("steps")}, indent=2))
    else:
        print("Status file not found, job may have failed before writing status.")


if __name__ == "__main__":
    main()
