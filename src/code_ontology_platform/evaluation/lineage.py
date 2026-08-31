from __future__ import annotations

from .models import FailureDiagnosis, JudgeResult

PLANNING_STAGES = (
    "designIntent",
    "alignment",
    "changeSet",
    "plannedImpactGraph",
    "nodeRequirements",
    "changePlanReview",
    "gate",
)
PRECOMMIT_STAGES = (
    "gitDiffSnapshot",
    "workingTreeGraphOverlay",
    "actualChangeSet",
    "actualImpactGraph",
    "impactObligations",
    "reconciliation",
    "verificationCoverage",
    "preCommitReview",
    "gate",
)


def diagnose_first_failure(
    workflow: str,
    results: list[JudgeResult],
) -> FailureDiagnosis | None:
    failures = [result for result in results if result.status == "Failed"]
    if not failures:
        return None
    order = (
        PLANNING_STAGES
        if workflow == "planning"
        else PRECOMMIT_STAGES
        if workflow == "precommit"
        else PLANNING_STAGES + PRECOMMIT_STAGES
    )
    ranks = {stage: index for index, stage in enumerate(order)}
    first = min(
        failures,
        key=lambda result: ranks.get(result.stage or "", len(ranks) + 1),
    )
    return FailureDiagnosis(
        first_failed_stage=first.stage,
        failed_artifact=first.artifact_type,
        summary=f"{first.judge} 在 {first.artifact_type} 首次发现偏差",
        details={
            "missing": first.missing,
            "extra": first.extra,
            "metrics": first.metrics,
            "judgeDetails": first.details,
        },
    )
