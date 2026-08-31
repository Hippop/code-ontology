from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .models import JudgeResult, canonical_json


def _identity(value: Any) -> str:
    if isinstance(value, Mapping):
        for key in (
            "id",
            "changeId",
            "impactId",
            "requirementId",
            "proposalId",
            "alignmentId",
            "entityId",
            "targetEntityId",
        ):
            if value.get(key) is not None:
                return f"{key}:{value[key]}"
    return canonical_json(value)


def _as_collection(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, Mapping):
        for key in ("items", "changes", "impacts", "requirements", "results", "proposals"):
            candidate = value.get(key)
            if isinstance(candidate, list):
                return candidate
    return [value]


def _deep_contains(expected: Any, actual: Any) -> bool:
    if isinstance(expected, Mapping):
        if not isinstance(actual, Mapping):
            return False
        return all(
            key in actual and _deep_contains(value, actual[key])
            for key, value in expected.items()
        )
    if isinstance(expected, list):
        if not isinstance(actual, list):
            return False
        remaining = list(actual)
        for item in expected:
            match_index = next(
                (
                    index
                    for index, candidate in enumerate(remaining)
                    if _deep_contains(item, candidate)
                ),
                None,
            )
            if match_index is None:
                return False
            remaining.pop(match_index)
        return True
    return expected == actual


class ArtifactJudge:
    def judge(
        self,
        artifact_type: str,
        expected: Any,
        actual: Any,
        compare_mode: str,
        *,
        stage: str | None = None,
    ) -> JudgeResult:
        if compare_mode == "exact":
            passed = expected == actual
            return JudgeResult(
                judge="ArtifactJudge",
                artifact_type=artifact_type,
                status="Passed" if passed else "Failed",
                score=1.0 if passed else 0.0,
                details={} if passed else {"expected": expected, "actual": actual},
                stage=stage,
            )

        if compare_mode == "constraint":
            passed = _deep_contains(expected, actual)
            return JudgeResult(
                judge="ArtifactJudge",
                artifact_type=artifact_type,
                status="Passed" if passed else "Failed",
                score=1.0 if passed else 0.0,
                details={} if passed else {"expectedSubset": expected, "actual": actual},
                stage=stage,
            )

        if compare_mode in {"set", "ordered-set"}:
            expected_items = _as_collection(expected)
            actual_items = _as_collection(actual)
            if compare_mode == "ordered-set":
                expected_ids = [_identity(item) for item in expected_items]
                actual_ids = [_identity(item) for item in actual_items]
                passed = expected_ids == actual_ids
                overlap = sum(
                    1
                    for expected_id, actual_id in zip(expected_ids, actual_ids)
                    if expected_id == actual_id
                )
                score = overlap / max(len(expected_ids), len(actual_ids), 1)
                return JudgeResult(
                    judge="ArtifactJudge",
                    artifact_type=artifact_type,
                    status="Passed" if passed else "Failed",
                    score=score,
                    missing=[
                        item
                        for item in expected_items
                        if _identity(item) not in set(actual_ids)
                    ],
                    extra=[
                        item
                        for item in actual_items
                        if _identity(item) not in set(expected_ids)
                    ],
                    stage=stage,
                )

            expected_map = {_identity(item): item for item in expected_items}
            actual_map = {_identity(item): item for item in actual_items}
            missing_ids = expected_map.keys() - actual_map.keys()
            extra_ids = actual_map.keys() - expected_map.keys()
            intersection = expected_map.keys() & actual_map.keys()
            if not expected_map and not actual_map:
                precision = recall = score = 1.0
            else:
                precision = len(intersection) / len(actual_map) if actual_map else 0.0
                recall = len(intersection) / len(expected_map) if expected_map else 1.0
                score = (
                    2 * precision * recall / (precision + recall)
                    if precision + recall
                    else 0.0
                )
            passed = not missing_ids and not extra_ids
            return JudgeResult(
                judge="ArtifactJudge",
                artifact_type=artifact_type,
                status="Passed" if passed else "Failed",
                score=score,
                metrics={"precision": precision, "recall": recall},
                missing=[expected_map[item] for item in sorted(missing_ids)],
                extra=[actual_map[item] for item in sorted(extra_ids)],
                stage=stage,
            )

        if compare_mode == "semantic":
            return JudgeResult(
                judge="SemanticJudge",
                artifact_type=artifact_type,
                status="Skipped",
                score=0.0,
                details={"reason": "semantic judge disabled in deterministic v1"},
                stage=stage,
            )

        raise ValueError(f"Unsupported compare mode: {compare_mode}")


class GateJudge:
    def judge(
        self,
        expected_decision: str,
        actual_decision: str | None,
    ) -> JudgeResult:
        passed = actual_decision == expected_decision
        false_ready = (
            actual_decision in {"ReadyForImplementation", "ReadyToCommit"}
            and actual_decision != expected_decision
        )
        false_block = (
            expected_decision in {"ReadyForImplementation", "ReadyToCommit"}
            and actual_decision in {"BlockImplementation", "BlockCommit", "NeedsReview"}
        )
        return JudgeResult(
            judge="GateJudge",
            artifact_type="Decision",
            status="Passed" if passed else "Failed",
            score=1.0 if passed else 0.0,
            metrics={
                "falseReady": 1.0 if false_ready else 0.0,
                "falseBlock": 1.0 if false_block else 0.0,
            },
            details={
                "expectedDecision": expected_decision,
                "actualDecision": actual_decision,
            },
            stage="gate",
        )
