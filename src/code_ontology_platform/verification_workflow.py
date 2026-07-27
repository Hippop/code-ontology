from __future__ import annotations

import hashlib
import json
from collections import deque
from typing import Any

from .store import content_hash

RECONCILIATION_ENGINE_VERSION = "approved-actual-reconciliation-0.1.0"
IMPACT_ENGINE_VERSION = "relation-aware-impact-0.1.0"

_VOLATILE_NODE_FIELDS = frozenset(
    {"createdAt", "revision", "revisionId", "path", "workspacePath"}
)
_CHANGE_TYPE_NODE_TYPES: dict[str, frozenset[str]] = {
    "ProposedBehaviorChange": frozenset(
        {"Class", "Interface", "Method", "APIOperation"}
    ),
    "ProposedNodeModification": frozenset(
        {"Class", "Interface", "Method", "Field", "Parameter"}
    ),
    "ProposedNodeAddition": frozenset(
        {"Class", "Interface", "Method", "Field", "EventType"}
    ),
    "ProposedRelationAddition": frozenset(),
    "ProposedContractChange": frozenset(
        {
            "APIOperation",
            "Schema",
            "SchemaField",
            "Field",
            "Parameter",
            "EventType",
        }
    ),
    "ProposedDataMigration": frozenset({"Table", "Column"}),
    "ProposedConstraintChange": frozenset({"Table", "Column", "Method"}),
    "ProposedConfigurationChange": frozenset({"ConfigurationKey", "Field"}),
    "ProposedTestChange": frozenset({"UnitTest", "IntegrationTest", "ContractTest"}),
    "ProposedDeploymentChange": frozenset(
        {"DeployableUnit", "BuildArtifact", "Module", "ConfigurationKey"}
    ),
}
_RELATION_RISK: dict[str, tuple[float, str]] = {
    "call": (0.92, "both"),
    "implement": (0.88, "both"),
    "read": (0.82, "both"),
    "write": (0.86, "both"),
    "schema": (0.9, "both"),
    "contract": (0.9, "both"),
    "test": (0.75, "both"),
    "contain": (0.55, "both"),
    "depend": (0.8, "both"),
    "config": (0.78, "both"),
    "deploy": (0.72, "both"),
}


def stable_graph_item(item: dict[str, Any]) -> dict[str, Any]:
    value = {
        key: field_value
        for key, field_value in item.items()
        if key not in _VOLATILE_NODE_FIELDS
    }
    evidence = value.get("evidence")
    if isinstance(evidence, dict):
        value["evidence"] = {
            key: field_value
            for key, field_value in evidence.items()
            if key not in _VOLATILE_NODE_FIELDS | {"absolutePath"}
        }
    return value


def graph_delta(
    current_nodes: list[dict[str, Any]],
    current_edges: list[dict[str, Any]],
    actual_nodes: list[dict[str, Any]],
    actual_edges: list[dict[str, Any]],
) -> dict[str, Any]:
    current_by_id = {item["id"]: item for item in current_nodes}
    actual_by_id = {item["id"]: item for item in actual_nodes}
    added = sorted(set(actual_by_id) - set(current_by_id))
    removed = sorted(set(current_by_id) - set(actual_by_id))
    modified = sorted(
        entity_id
        for entity_id in set(current_by_id) & set(actual_by_id)
        if stable_graph_item(current_by_id[entity_id])
        != stable_graph_item(actual_by_id[entity_id])
    )

    def edge_key(edge: dict[str, Any]) -> tuple[str, str, str]:
        return (edge["source"], edge["relation"], edge["target"])

    current_edge_by_key = {edge_key(item): item for item in current_edges}
    actual_edge_by_key = {edge_key(item): item for item in actual_edges}
    added_edges = sorted(set(actual_edge_by_key) - set(current_edge_by_key))
    removed_edges = sorted(set(current_edge_by_key) - set(actual_edge_by_key))
    return {
        "addedEntityIds": added,
        "removedEntityIds": removed,
        "modifiedEntityIds": modified,
        "addedEdges": [actual_edge_by_key[key] for key in added_edges],
        "removedEdges": [current_edge_by_key[key] for key in removed_edges],
    }


def reconcile_approved_actual(
    *,
    reconciliation_run_id: str,
    agent_run: dict[str, Any],
    plan: dict[str, Any],
    current_nodes: list[dict[str, Any]],
    current_edges: list[dict[str, Any]],
    actual_nodes: list[dict[str, Any]],
    actual_edges: list[dict[str, Any]],
    actual_revision: str,
    coverage: dict[str, Any],
) -> dict[str, Any]:
    delta = graph_delta(current_nodes, current_edges, actual_nodes, actual_edges)
    current_by_id = {item["id"]: item for item in current_nodes}
    actual_by_id = {item["id"]: item for item in actual_nodes}
    changed_ids = {
        *delta["addedEntityIds"],
        *delta["removedEntityIds"],
        *delta["modifiedEntityIds"],
    }
    changed_types = {
        entity_id: (
            actual_by_id.get(entity_id) or current_by_id.get(entity_id) or {}
        ).get("type")
        for entity_id in changed_ids
    }
    relation_changed = bool(delta["addedEdges"] or delta["removedEdges"])
    task_by_proposal = {
        item["proposalId"]: item for item in plan["implementationTasks"]
    }
    proposal_results = []
    claimed_entities: set[str] = set()
    for proposal in plan["proposals"]:
        target = proposal.get("targetCurrentEntityId")
        compatible_types = _CHANGE_TYPE_NODE_TYPES.get(
            proposal["changeType"], frozenset()
        )
        compatible_matches = [
            entity_id
            for entity_id in sorted(changed_ids)
            if not compatible_types or changed_types[entity_id] in compatible_types
        ]
        matched = []
        if (
            target
            and target in changed_ids
            and (not compatible_types or changed_types[target] in compatible_types)
        ):
            matched.append(target)
        suggested_files = set(
            task_by_proposal.get(proposal["proposalId"], {}).get("suggestedFiles", [])
        )
        for entity_id in compatible_matches:
            node = actual_by_id.get(entity_id) or current_by_id.get(entity_id) or {}
            source = (
                node.get("evidence", {}).get("source")
                if isinstance(node.get("evidence"), dict)
                else None
            )
            is_addition = entity_id in delta["addedEntityIds"]
            if entity_id not in matched and (
                (target is None and is_addition)
                or (source is not None and source in suggested_files)
            ):
                matched.append(entity_id)
        if proposal["changeType"] == "ProposedRelationAddition" and relation_changed:
            status = "Conformed"
        else:
            status = "Conformed" if matched else "Missing"
        claimed_entities.update(matched)
        proposal_results.append(
            {
                "proposalId": proposal["proposalId"],
                "changeType": proposal["changeType"],
                "role": proposal["role"],
                "status": status,
                "matchedActualEntityIds": matched,
                "evidenceRefs": proposal.get("evidenceRefs", []),
                "reason": (
                    "Actual Graph contains a compatible approved change."
                    if status == "Conformed"
                    else "No compatible structural change was found in Actual Graph."
                ),
            }
        )
    unexpected = sorted(changed_ids - claimed_entities)
    test_status = agent_run.get("testReport", {}).get("status")
    obligation_results = [
        {
            **obligation,
            "status": "Satisfied" if test_status == "Passed" else "Unsatisfied",
            "evidence": {
                "agentRunId": agent_run["runId"],
                "testReportStatus": test_status,
            },
        }
        for obligation in plan["verificationObligations"]
    ]
    deviations = []
    for result in proposal_results:
        if result["status"] == "Missing":
            deviations.append(
                {
                    "deviationType": "MissingApprovedChange",
                    "proposalId": result["proposalId"],
                    "severity": "High",
                }
            )
    for entity_id in unexpected:
        deviations.append(
            {
                "deviationType": "UnexpectedActualChange",
                "entityId": entity_id,
                "severity": "Medium",
            }
        )
    if agent_run["status"] != "Completed":
        deviations.append(
            {
                "deviationType": "AgentRunNotCompleted",
                "agentRunStatus": agent_run["status"],
                "severity": "Critical",
            }
        )
    if test_status != "Passed":
        deviations.append(
            {
                "deviationType": "VerificationFailed",
                "testReportStatus": test_status,
                "severity": "Critical",
            }
        )
    if coverage.get("failedJavaFiles", 0):
        deviations.append(
            {
                "deviationType": "ActualExtractionIncomplete",
                "failedJavaFiles": coverage["failedJavaFiles"],
                "severity": "Critical",
            }
        )
    status = "Conformed" if not deviations else "Deviated"
    result = {
        "runId": reconciliation_run_id,
        "agentRunId": agent_run["runId"],
        "changePlanId": plan["planId"],
        "requirementId": agent_run["requirementId"],
        "repositoryId": agent_run["repositoryId"],
        "baseRevision": plan["changeSet"]["currentRevision"],
        "approvedRevision": plan["planId"],
        "actualRevision": actual_revision,
        "engineVersion": RECONCILIATION_ENGINE_VERSION,
        "status": status,
        "coverage": coverage,
        "graphDelta": delta,
        "proposalResults": proposal_results,
        "verificationResults": obligation_results,
        "deviations": deviations,
    }
    result["resultHash"] = content_hash(result)
    return result


def _relation_policy(relation: str) -> tuple[float, str]:
    name = relation.lower()
    for token, policy in _RELATION_RISK.items():
        if token in name:
            return policy
    return 0.45, "both"


def build_impact_analysis(
    *,
    impact_run_id: str,
    reconciliation: dict[str, Any],
    plan: dict[str, Any],
    actual_nodes: list[dict[str, Any]],
    actual_edges: list[dict[str, Any]],
    depth: int = 5,
    limit: int = 500,
) -> dict[str, Any]:
    nodes = {item["id"]: item for item in actual_nodes}
    starts = sorted(
        {
            *reconciliation["graphDelta"]["addedEntityIds"],
            *reconciliation["graphDelta"]["modifiedEntityIds"],
            *reconciliation["graphDelta"]["removedEntityIds"],
        }
    )
    adjacency: dict[str, list[tuple[dict[str, Any], str, float]]] = {}
    for edge in actual_edges:
        risk, direction = _relation_policy(edge["relation"])
        if direction in {"both", "forward"}:
            adjacency.setdefault(edge["source"], []).append(
                (edge, edge["target"], risk)
            )
        if direction in {"both", "reverse"}:
            adjacency.setdefault(edge["target"], []).append(
                (edge, edge["source"], risk)
            )
    impacts: dict[str, dict[str, Any]] = {}
    impact_edges: dict[tuple[str, str, str], dict[str, Any]] = {}
    queue = deque()
    for entity_id in starts:
        state = "Direct" if entity_id in nodes else "Unresolved"
        impacts[entity_id] = {
            "entityId": entity_id,
            "state": state,
            "depth": 0,
            "confidence": 1.0,
            "path": [entity_id],
            "reason": "Changed by the implementation patch.",
        }
        if entity_id in nodes:
            queue.append((entity_id, 0, 1.0, [entity_id]))
    while queue and len(impacts) < limit:
        current, level, confidence, path = queue.popleft()
        if level >= depth:
            continue
        for edge, neighbor, edge_risk in adjacency.get(current, []):
            if neighbor not in nodes:
                continue
            next_confidence = round(confidence * edge_risk, 4)
            state = "Propagated" if next_confidence >= 0.5 else "Contained"
            previous = impacts.get(neighbor)
            if previous and previous["confidence"] >= next_confidence:
                continue
            impacts[neighbor] = {
                "entityId": neighbor,
                "state": state,
                "depth": level + 1,
                "confidence": next_confidence,
                "path": [*path, neighbor],
                "viaRelation": edge["relation"],
                "reason": (
                    "Impact propagated through a typed graph relation."
                    if state == "Propagated"
                    else "Relation attenuation contains the likely impact."
                ),
            }
            impact_edges[(edge["source"], edge["relation"], edge["target"])] = edge
            if state == "Propagated":
                queue.append((neighbor, level + 1, next_confidence, [*path, neighbor]))
    impacted_tests = [
        {
            "entityId": entity_id,
            "type": nodes[entity_id].get("type"),
            "confidence": impact["confidence"],
            "reason": impact["path"],
        }
        for entity_id, impact in impacts.items()
        if entity_id in nodes
        and (
            str(nodes[entity_id].get("type", "")).endswith("Test")
            or str(nodes[entity_id].get("label", "")).endswith("Test")
        )
    ]
    required_commands = sorted(
        {
            command
            for task in plan["implementationTasks"]
            for command in task.get("requiredTests", [])
            if command
            in plan.get("approval", {}).get("payload", {}).get("requiredTests", [])
        }
    )
    if not required_commands:
        required_commands = sorted(
            {
                command
                for task in plan["implementationTasks"]
                for command in task.get("requiredTests", [])
                if command.startswith(("./mvnw", "mvn ", "./gradlew", "gradle "))
            }
        )
    change_types = {item["changeType"] for item in plan["proposals"]}
    high_risk = bool(
        change_types
        & {
            "ProposedContractChange",
            "ProposedDataMigration",
            "ProposedConstraintChange",
            "ProposedDeploymentChange",
        }
    )
    unresolved = [item for item in impacts.values() if item["state"] == "Unresolved"]
    release_decision = (
        "Blocked"
        if reconciliation["status"] != "Conformed" or unresolved
        else ("Canary" if high_risk else "Standard")
    )
    release_plan = {
        "decision": release_decision,
        "riskLevel": (
            "Critical"
            if release_decision == "Blocked"
            else ("High" if high_risk else "Medium")
        ),
        "preconditions": [
            "Reconciliation status is Conformed",
            "All selected tests pass",
            "Release reviewer confirms rollback and observability",
        ],
        "rollout": (
            [
                "Deploy to non-production",
                "Run contract and migration verification",
                "Canary rollout",
                "Observe business and technical metrics",
                "Progressive rollout",
            ]
            if high_risk
            else [
                "Deploy to non-production",
                "Run selected regression tests",
                "Standard rollout with monitoring",
            ]
        ),
        "rollbackTriggers": [
            "Acceptance metric regression",
            "Contract error increase",
            "Data reconciliation failure",
        ],
        "requiresHumanReleaseGate": True,
    }
    impact_nodes = [
        {
            "id": f"impact:{impact_run_id}:{entity_id}",
            "type": "ImpactAssessment",
            **impact,
            "targetEntity": nodes.get(entity_id),
        }
        for entity_id, impact in sorted(impacts.items())
    ]
    impact_graph_edges = [
        {
            "source": f"impact:{impact_run_id}:{source}",
            "relation": "impact:propagatesVia",
            "target": f"impact:{impact_run_id}:{target}",
            "sourceRelation": relation,
        }
        for source, relation, target in sorted(impact_edges)
        if source in impacts and target in impacts
    ]
    result = {
        "runId": impact_run_id,
        "reconciliationRunId": reconciliation["runId"],
        "requirementId": reconciliation["requirementId"],
        "actualRevision": reconciliation["actualRevision"],
        "engineVersion": IMPACT_ENGINE_VERSION,
        "status": "Completed",
        "impactSummary": {
            state: sum(1 for item in impacts.values() if item["state"] == state)
            for state in ("Direct", "Propagated", "Contained", "Rejected", "Unresolved")
        },
        "impacts": [impacts[item] for item in sorted(impacts)],
        "selectedTests": impacted_tests,
        "requiredTestCommands": required_commands,
        "releasePlan": release_plan,
        "graph": {
            "nodes": impact_nodes,
            "edges": impact_graph_edges,
        },
    }
    result["resultHash"] = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(result, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
    )
    return result
