from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def compare_run_sets(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    baseline_runs = {
        item["scenario_id"]: item
        for item in baseline.get("runs", [])
        if isinstance(item, dict) and "scenario_id" in item
    }
    candidate_runs = {
        item["scenario_id"]: item
        for item in candidate.get("runs", [])
        if isinstance(item, dict) and "scenario_id" in item
    }
    scenario_ids = sorted(baseline_runs.keys() | candidate_runs.keys())
    regressions: list[dict[str, Any]] = []
    improvements: list[dict[str, Any]] = []
    comparisons: list[dict[str, Any]] = []

    for scenario_id in scenario_ids:
        before = baseline_runs.get(scenario_id)
        after = candidate_runs.get(scenario_id)
        row = {
            "scenarioId": scenario_id,
            "baselineStatus": before.get("status") if before else None,
            "candidateStatus": after.get("status") if after else None,
            "metricDelta": {},
        }
        if before and after:
            keys = sorted(set(before.get("metrics", {})) | set(after.get("metrics", {})))
            row["metricDelta"] = {
                key: float(after.get("metrics", {}).get(key, 0.0))
                - float(before.get("metrics", {}).get(key, 0.0))
                for key in keys
            }
            if before.get("status") == "Passed" and after.get("status") != "Passed":
                regressions.append(row)
            elif before.get("status") != "Passed" and after.get("status") == "Passed":
                improvements.append(row)
        comparisons.append(row)

    return {
        "schemaVersion": "evaluation-comparison/v1",
        "scenarioCount": len(scenario_ids),
        "regressionCount": len(regressions),
        "improvementCount": len(improvements),
        "regressions": regressions,
        "improvements": improvements,
        "comparisons": comparisons,
    }


def load_run_set(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError("run set must be a JSON object")
    return value
