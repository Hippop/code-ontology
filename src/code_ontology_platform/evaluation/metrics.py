from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from .models import JudgeResult


def aggregate_metrics(results: Iterable[JudgeResult]) -> dict[str, float]:
    results = list(results)
    if not results:
        return {
            "passRate": 0.0,
            "averageScore": 0.0,
            "falseReadyRate": 0.0,
            "falseBlockRate": 0.0,
            "safetyWeightedScore": 0.0,
        }

    passed = sum(1 for result in results if result.status == "Passed")
    scored = [result.score for result in results if result.status != "Skipped"]
    metric_values: dict[str, list[float]] = defaultdict(list)
    for result in results:
        for key, value in result.metrics.items():
            metric_values[key].append(float(value))

    false_ready = sum(metric_values.get("falseReady", []))
    false_block = sum(metric_values.get("falseBlock", []))
    gate_count = max(len(metric_values.get("falseReady", [])), 1)

    named = {
        key: sum(values) / len(values)
        for key, values in metric_values.items()
        if values
    }

    impact_recall = named.get("nodeRecall", named.get("recall", 1.0))
    obligation_recall = named.get("obligationRecall", 1.0)
    test_recall = named.get("testObligationRecall", 1.0)
    gate_safety = 1.0 - false_ready / gate_count
    change_precision = named.get("changePrecision", named.get("precision", 1.0))
    change_recall = named.get("changeRecall", named.get("recall", 1.0))

    weighted = (
        0.10 * change_precision
        + 0.15 * change_recall
        + 0.20 * impact_recall
        + 0.20 * obligation_recall
        + 0.10 * test_recall
        + 0.25 * gate_safety
    )
    weighted = max(0.0, weighted - 0.10 * false_block - 1.0 * false_ready)

    return {
        "passRate": passed / len(results),
        "averageScore": sum(scored) / max(len(scored), 1),
        "falseReadyRate": false_ready / gate_count,
        "falseBlockRate": false_block / gate_count,
        "safetyWeightedScore": weighted,
        **named,
    }


def aggregate_runs(run_metrics: Iterable[dict[str, float]]) -> dict[str, float]:
    rows = list(run_metrics)
    if not rows:
        return {}
    keys = sorted({key for row in rows for key in row})
    return {
        key: sum(row.get(key, 0.0) for row in rows) / len(rows)
        for key in keys
    }
