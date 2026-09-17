"""Generate deterministic, independently validated PS1 scenario deliverables."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.ps1_data import load_instance  # noqa: E402
from backend.ps1_solver import solve  # noqa: E402
from backend.ps1_validator import validate_submission  # noqa: E402


TABLES = {
    "SCHEDULE_ACCESS.csv": (
        "schedule_access", ["activity_id", "access_seq", "week", "eclo", "access_night"]),
    "SCHEDULE_OCCUPANCY.csv": (
        "schedule_occupancy", ["activity_id", "week", "location_id", "co_share_group"]),
    "RESULTS.csv": (
        "results", ["scenario", "contract_number", "simulated_completion_date", "overrun_days"]),
}

UPSTREAM_SOURCE_COMMIT = "16526c02579c7f37e54eaaa42a4cc6d4ceb19994"


def _write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: int(row[field]) if field == "eclo" else row[field]
                             for field in fields})


def _source_metadata(data_dir: Path) -> dict:
    files = {}
    combined = hashlib.sha256()
    for path in sorted(data_dir.glob("*.csv"), key=lambda item: item.name):
        content = path.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        files[path.name] = digest
        combined.update(path.name.encode("utf-8") + b"\0" + content + b"\0")
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        commit = None
    return {
        "dataset_sha256": combined.hexdigest(),
        "files_sha256": files,
        "is_repository_default_dataset": data_dir.resolve() == (ROOT / "data" / "ps1" / "01_data").resolve(),
        "upstream_source_commit": UPSTREAM_SOURCE_COMMIT,
        "application_base_commit": commit,
    }


def generate(data_dir: Path, output_dir: Path, time_limit: float) -> None:
    instance = load_instance(data_dir)
    source_metadata = _source_metadata(data_dir)
    reports_dir = output_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    for scenario in ("A", "B", "C"):
        result = solve(instance, scenario=scenario, time_limit_seconds=time_limit)
        report = validate_submission(instance, result, scenario)
        if result.get("status") != "success" or not report.get("feasible") or not report.get("complete"):
            raise RuntimeError(f"Scenario {scenario} has no complete locally validated result")
        scenario_dir = output_dir / scenario
        scenario_dir.mkdir(parents=True, exist_ok=True)
        for filename, (key, fields) in TABLES.items():
            _write_csv(scenario_dir / filename, fields, result[key])
        payload = {
            "scenario": scenario,
            "status": result["status"],
            "metrics": result["metrics"],
            "selection": result["selection"],
            "explanations": result.get("explanations", []),
            "physical_night_witness": result["physical_night_witness"],
            "source_metadata": source_metadata,
            "validation": report,
        }
        (reports_dir / f"{scenario}.validation.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data" / "ps1" / "01_data")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "submissions" / "ps1")
    parser.add_argument("--time-limit", type=float, default=20.0)
    args = parser.parse_args()
    generate(args.data_dir, args.output_dir, args.time_limit)


if __name__ == "__main__":
    main()
