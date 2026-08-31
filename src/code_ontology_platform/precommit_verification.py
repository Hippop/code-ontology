from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

from .store import content_hash
from .verification_workflow import build_impact_analysis, graph_delta


def build_git_diff_snapshot(diff: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize collect_worktree_diff output into an immutable pre-commit artifact."""
    patch = str(diff.get("patch") or "")
    changed_files = sorted({str(item) for item in diff.get("changedFiles", [])})
    snapshot = {
        "baseRevision": str(diff.get("baseCommit") or ""),
        "headRevision": str(diff.get("headCommit") or ""),
        "headUnchanged": bool(diff.get("headUnchanged")),
        "changedFiles": changed_files,
        "patchHash": str(diff.get("patchHash") or content_hash({"patch": patch})),
        "patch": patch,
        "source": "git-working-tree",
    }
    snapshot["snapshotHash"] = content_hash(
        {key: value for key, value in snapshot.items() if key != "patch"}
    )
    return snapshot


def build_worktree_graph_overlay(
    *,
    base_revision: str,
    actual_revision: str,
    current_nodes: list[dict[str, Any]],
    current_edges: list[dict[str, Any]],
    actual_nodes: list[dict[str, Any]],
    actual_edges: list[dict[str, Any]],
    working_tree_hash: str,
) -> dict[str, Any]:
    delta = graph_delta(current_nodes, current_edges, actual_nodes, actual_edges)
    current_by_id = {item["id"]: item for item in current_nodes}
    actual_by_id = {item["id"]: item for item in actual_nodes}
    overlay = {
        "baseRevision": base_revision,
        "actualRevision": actual_revision,
        "workingTreeHash": working_tree_hash,
        "addedNodes": [actual_by_id[item] for item in delta["addedEntityIds"]],
        "removedNodes": [current_by_id[item] for item in delta["removedEntityIds"]],
        "modifiedNodes": [
            {
                "entityId": entity_id,
                "before": current_by_id[entity_id],
                "after": actual_by_id[entity_id],
            }
            for entity_id in delta["modifiedEntityIds"]
        ],
        "addedEdges": delta["addedEdges"],
        "removedEdges": delta["removedEdges"],
        "graphDelta": delta,
    }
    overlay["overlayId"] = "overlay-" + hashlib.sha256(
        content_hash(overlay).encode("utf-8")
    ).hexdigest()[:20]
    return overlay


def build_actual_change_set(
    *,
    base_revision: str,
    actual_revision: str,
    graph_overlay: Mapping[str, Any],
    working_tree_hash: str,
) -> dict[str, Any]:
    delta = dict(graph_overlay.get("graphDelta") or {})
    changes: list[dict[str, Any]] = []

    def add_entity_change(operation: str, entity_id: str) -> None:
        change_id = "actual-change-" + hashlib.sha256(
            f"{base_revision}|{actual_revision}|{operation}|{entity_id}".encode()
        ).hexdigest()[:20]
        changes.append(
            {
                "changeId": change_id,
                "operation": operation,
                "aspect": "Structure",
                "entityId": entity_id,
                "evidence": {"workingTreeHash": working_tree_hash},
            }
        )

    for entity_id in delta.get("addedEntityIds", []):
        add_entity_change("Add", str(entity_id))
    for entity_id in delta.get("removedEntityIds", []):
        add_entity_change("Remove", str(entity_id))
    for entity_id in delta.get("modifiedEntityIds", []):
        add_entity_change("Modify", str(entity_id))

    for operation, field in (("AddRelation", "addedEdges"), ("RemoveRelation", "removedEdges")):
        for edge in delta.get(field, []):
            edge_key = "|".join(
                str(edge.get(key) or "") for key in ("source", "relation", "target")
            )
            change_id = "actual-change-" + hashlib.sha256(
                f"{base_revision}|{actual_revision}|{operation}|{edge_key}".encode()
            ).hexdigest()[:20]
            changes.append(
                {
                    "changeId": change_id,
                    "operation": operation,
                    "aspect": "Relation",
                    "edge": dict(edge),
                    "evidence": {"workingTreeHash": working_tree_hash},
                }
            )

    result = {
        "baseRevision": base_revision,
        "actualRevision": actual_revision,
        "workingTreeHash": working_tree_hash,
        "changes": sorted(changes, key=lambda item: item["changeId"]),
        "graphDelta": delta,
    }
    result["changeSetId"] = "actual-change-set-" + hashlib.sha256(
        content_hash(result).encode("utf-8")
    ).hexdigest()[:20]
    result["changeSetHash"] = content_hash(result)
    return result


def build_actual_impact_graph(
    *,
    actual_change_set: Mapping[str, Any],
    actual_nodes: list[dict[str, Any]],
    actual_edges: list[dict[str, Any]],
    requirement_id: str = "precommit-evaluation",
    depth: int = 5,
    limit: int = 500,
) -> dict[str, Any]:
    change_set_id = str(actual_change_set.get("changeSetId") or "actual-change-set")
    actual_revision = str(actual_change_set.get("actualRevision") or "actual")
    reconciliation = {
        "runId": f"synthetic-reconciliation:{change_set_id}",
        "requirementId": requirement_id,
        "actualRevision": actual_revision,
        "status": "Conformed",
        "graphDelta": dict(actual_change_set.get("graphDelta") or {}),
        "proposalResults": [],
    }
    plan = {
        "planId": f"synthetic-plan:{change_set_id}",
        "proposals": [],
        "implementationTasks": [],
        "approval": {"payload": {"requiredTests": []}},
    }
    impact_run_id = "precommit-impact-" + hashlib.sha256(
        f"{change_set_id}|{depth}|{limit}".encode()
    ).hexdigest()[:20]
    impact = build_impact_analysis(
        impact_run_id=impact_run_id,
        reconciliation=reconciliation,
        plan=plan,
        actual_nodes=actual_nodes,
        actual_edges=actual_edges,
        depth=depth,
        limit=limit,
    )
    impact["actualChangeSetId"] = change_set_id
    return impact


def build_impact_obligations(
    impact: Mapping[str, Any],
    actual_nodes: list[dict[str, Any]],
    actual_change_set: Mapping[str, Any],
    *,
    test_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    nodes = {item["id"]: item for item in actual_nodes}
    changed_ids = {
        str(item.get("entityId"))
        for item in actual_change_set.get("changes", [])
        if item.get("entityId") is not None
    }
    test_passed = isinstance(test_report, Mapping) and test_report.get("status") == "Passed"
    obligations: list[dict[str, Any]] = []
    for item in impact.get("impacts", []):
        if not isinstance(item, Mapping):
            continue
        entity_id = str(item.get("entityId") or "")
        if not entity_id:
            continue
        node = nodes.get(entity_id, {})
        node_type = str(node.get("type") or "")
        label = str(node.get("label") or "")
        is_test = node_type.endswith("Test") or label.endswith("Test")
        state = str(item.get("state") or "Unresolved")
        if is_test:
            obligation_type = "RequiredTest"
            status = "Satisfied" if test_passed else "Unsatisfied"
        elif state == "Direct":
            obligation_type = "DirectChangeVerification"
            status = "Satisfied" if entity_id in changed_ids else "Unverified"
        elif state == "Propagated":
            obligation_type = "RequiredModification"
            status = "Satisfied" if entity_id in changed_ids else "Unsatisfied"
        elif state == "Contained":
            obligation_type = "CompatibilityVerification"
            status = "Contained"
        else:
            obligation_type = "RequiredReview"
            status = "Unverified"
        obligation_id = "impact-obligation-" + hashlib.sha256(
            f"{impact.get('runId')}|{entity_id}|{obligation_type}".encode()
        ).hexdigest()[:20]
        obligations.append(
            {
                "obligationId": obligation_id,
                "entityId": entity_id,
                "obligationType": obligation_type,
                "status": status,
                "impactState": state,
                "confidence": item.get("confidence"),
                "path": item.get("path", []),
                "reason": item.get("reason"),
            }
        )
    return {
        "impactRunId": impact.get("runId"),
        "actualChangeSetId": actual_change_set.get("changeSetId"),
        "obligations": sorted(obligations, key=lambda item: item["obligationId"]),
    }


def build_simple_reconciliation(
    *,
    planned_artifact: Mapping[str, Any] | None,
    actual_change_set: Mapping[str, Any],
    impact_obligations: Mapping[str, Any],
) -> dict[str, Any]:
    planned = planned_artifact or {}
    actual_entity_ids = {
        str(item.get("entityId"))
        for item in actual_change_set.get("changes", [])
        if item.get("entityId") is not None
    }
    planned_items = []
    for key in ("changes", "proposals", "requirements", "items"):
        value = planned.get(key)
        if isinstance(value, list):
            planned_items = value
            break
    planned_results: list[dict[str, Any]] = []
    for index, item in enumerate(planned_items):
        if not isinstance(item, Mapping):
            continue
        planned_id = str(
            item.get("changeId")
            or item.get("proposalId")
            or item.get("requirementId")
            or f"planned-{index}"
        )
        target = item.get("targetCurrentEntityId") or item.get("entityId") or item.get("targetEntityId")
        matched = isinstance(target, str) and target in actual_entity_ids
        planned_results.append(
            {
                "plannedId": planned_id,
                "targetEntityId": target,
                "status": "Conformed" if matched else "MissingPlannedImplementation",
            }
        )

    obligation_results = [
        dict(item)
        for item in impact_obligations.get("obligations", [])
        if isinstance(item, Mapping)
    ]
    missing_propagation = [
        item
        for item in obligation_results
        if item.get("obligationType") == "RequiredModification"
        and item.get("status") != "Satisfied"
    ]
    deviations: list[dict[str, Any]] = []
    for item in planned_results:
        if item["status"] != "Conformed":
            deviations.append(
                {
                    "deviationType": "MissingPlannedImplementation",
                    "plannedId": item["plannedId"],
                    "targetEntityId": item.get("targetEntityId"),
                    "severity": "High",
                }
            )
    for item in missing_propagation:
        deviations.append(
            {
                "deviationType": "MissingPropagationImplementation",
                "obligationId": item.get("obligationId"),
                "entityId": item.get("entityId"),
                "severity": "High",
            }
        )
    return {
        "status": "Conformed" if not deviations else "Deviated",
        "plannedResults": planned_results,
        "obligationResults": obligation_results,
        "deviations": deviations,
    }


def build_verification_coverage(
    *,
    impact_obligations: Mapping[str, Any],
    test_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    obligations = [
        item
        for item in impact_obligations.get("obligations", [])
        if isinstance(item, Mapping)
    ]
    required = [
        item
        for item in obligations
        if item.get("obligationType")
        in {"RequiredModification", "RequiredTest", "DirectChangeVerification"}
    ]
    satisfied = [item for item in required if item.get("status") == "Satisfied"]
    missing = [item for item in required if item.get("status") != "Satisfied"]
    coverage = len(satisfied) / len(required) if required else 1.0
    return {
        "requiredObligationCount": len(required),
        "satisfiedObligationCount": len(satisfied),
        "coverage": round(coverage, 6),
        "missingObligationIds": [item.get("obligationId") for item in missing],
        "testReportStatus": (
            test_report.get("status") if isinstance(test_report, Mapping) else "NotRun"
        ),
        "complete": not missing,
    }


def build_precommit_review(
    *,
    working_tree_hash: str,
    reconciliation: Mapping[str, Any],
    verification_coverage: Mapping[str, Any],
    impact_obligations: Mapping[str, Any],
) -> dict[str, Any]:
    blocking_issues: list[dict[str, Any]] = []
    for deviation in reconciliation.get("deviations", []):
        if isinstance(deviation, Mapping):
            blocking_issues.append(dict(deviation))
    if verification_coverage.get("complete") is not True:
        blocking_issues.append(
            {
                "deviationType": "VerificationCoverageIncomplete",
                "missingObligationIds": verification_coverage.get(
                    "missingObligationIds", []
                ),
                "severity": "High",
            }
        )
    unresolved = [
        dict(item)
        for item in impact_obligations.get("obligations", [])
        if isinstance(item, Mapping) and item.get("status") == "Unverified"
    ]
    if unresolved:
        blocking_issues.append(
            {
                "deviationType": "UnverifiedImpactObligation",
                "obligationIds": [item.get("obligationId") for item in unresolved],
                "severity": "High",
            }
        )
    decision = "ReadyToCommit" if not blocking_issues else "BlockCommit"
    result = {
        "workingTreeHash": working_tree_hash,
        "planReconciliation": reconciliation.get("status"),
        "impactClosure": "Complete" if not unresolved else "Incomplete",
        "verificationCoverage": verification_coverage.get("coverage"),
        "blockingIssues": blocking_issues,
        "decision": decision,
    }
    result["reviewHash"] = content_hash(result)
    return result
