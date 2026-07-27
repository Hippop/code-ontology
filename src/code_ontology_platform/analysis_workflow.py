from __future__ import annotations

import hashlib
import re
from collections import deque
from typing import Any

from .planning import PlanningRules

ALIGNMENT_MODEL_VERSION = "deterministic-alignment-0.1.0"
DIFF_ENGINE_VERSION = "semantic-diff-0.1.0"

_TYPE_COMPATIBILITY: dict[str, frozenset[str]] = {
    "BusinessProcess": frozenset({"APIOperation", "Method", "Class", "Module"}),
    "BusinessProcessStep": frozenset({"APIOperation", "Method", "Class"}),
    "DesiredBusinessEntity": frozenset({"Class", "Method", "APIOperation", "Module"}),
    "BusinessRule": frozenset({"Class", "Method"}),
    "DesiredCodeRole": frozenset({"Class", "Interface", "Method"}),
    "DesiredAPIOperation": frozenset({"APIOperation", "Method"}),
    "DesiredSchema": frozenset({"Schema", "Class", "Interface"}),
    "DesiredSchemaField": frozenset({"SchemaField", "Field", "Parameter"}),
    "DesiredDatabaseObject": frozenset({"Table", "Column", "Class"}),
    "DesiredEventType": frozenset({"EventType", "MessageSchema", "Class"}),
    "DesiredConfigurationKey": frozenset({"ConfigurationKey", "Field"}),
    "DesiredTestObligation": frozenset(
        {"UnitTest", "IntegrationTest", "ContractTest", "Method"}
    ),
    "DesiredDeploymentAction": frozenset(
        {"DeployableUnit", "BuildArtifact", "Module", "ConfigurationKey"}
    ),
}


def _camel_tokens(value: str) -> set[str]:
    expanded = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    return {
        token.lower()
        for token in re.findall(
            r"[A-Za-z][A-Za-z0-9_-]{1,}|[\u4e00-\u9fff]{2,}", expanded
        )
    }


def _candidate_score(
    desired: dict[str, Any],
    current: dict[str, Any],
    suggestion_tokens: set[str],
) -> tuple[float, dict[str, float]]:
    desired_tokens = _camel_tokens(
        " ".join(
            [
                desired.get("label", ""),
                desired.get("canonicalId") or "",
                " ".join(desired.get("designTokens", [])),
            ]
        )
    )
    current_tokens = _camel_tokens(
        " ".join(
            [
                current.get("id", ""),
                current.get("label", ""),
                current.get("qualifiedName", ""),
                current.get("key", ""),
                current.get("path", ""),
                " ".join(current.get("roles", [])),
            ]
        )
    )
    desired_type = desired["entityType"]
    type_score = (
        1.0
        if current.get("type") in _TYPE_COMPATIBILITY.get(desired_type, frozenset())
        else 0.0
    )
    union = desired_tokens | current_tokens
    lexical = len(desired_tokens & current_tokens) / len(union) if union else 0.0
    suggestion = (
        len(suggestion_tokens & current_tokens)
        / len(suggestion_tokens | current_tokens)
        if suggestion_tokens and current_tokens
        else 0.0
    )
    exact = 0.0
    for token in desired.get("designTokens", []):
        if (
            token.lower()
            in (current.get("id", "") + " " + current.get("label", "")).lower()
        ):
            exact = 1.0
            break
    score = min(
        1.0,
        0.35 * type_score + 0.35 * lexical + 0.20 * exact + 0.10 * suggestion,
    )
    return score, {
        "type": round(type_score, 4),
        "lexical": round(lexical, 4),
        "explicitToken": round(exact, 4),
        "implementationSuggestion": round(suggestion, 4),
    }


def generate_alignment_run(
    *,
    run_id: str,
    requirement: dict[str, Any],
    current_revision: str,
    current_nodes: list[dict[str, Any]],
) -> dict[str, Any]:
    ir = requirement["ir"]
    suggestion_tokens: set[str] = set()
    for suggestion in ir.get("implementationSuggestions", []):
        suggestion_tokens |= _camel_tokens(suggestion.get("text", ""))
    alignments: list[dict[str, Any]] = []
    for desired in ir["desiredEntities"]:
        ranked: list[dict[str, Any]] = []
        for current in current_nodes:
            score, score_components = _candidate_score(
                desired, current, suggestion_tokens
            )
            if score < 0.18:
                continue
            if score >= 0.82:
                alignment_type = "ExactReuse"
            elif score >= 0.5:
                alignment_type = "ExtendExisting"
            else:
                alignment_type = "ModifyExisting"
            candidate_id = (
                "alignment-"
                + hashlib.sha256(
                    f"{run_id}|{desired['entityId']}|{current['id']}".encode()
                ).hexdigest()[:20]
            )
            evidence = current.get("evidence")
            ranked.append(
                {
                    "candidateId": candidate_id,
                    "desiredEntityId": desired["entityId"],
                    "currentEntityId": current["id"],
                    "currentEntityType": current.get("type"),
                    "alignmentType": alignment_type,
                    "confidence": round(score, 4),
                    "scoreComponents": score_components,
                    "evidenceRefs": [
                        *desired.get("evidenceRefs", []),
                        *([evidence] if evidence else []),
                    ],
                    "modelVersion": ALIGNMENT_MODEL_VERSION,
                    "reviewStatus": "Candidate",
                }
            )
        ranked.sort(key=lambda item: (-item["confidence"], item["currentEntityId"]))
        ranked = ranked[:5]
        if not ranked or ranked[0]["confidence"] < 0.3:
            candidate_id = (
                "alignment-"
                + hashlib.sha256(
                    f"{run_id}|{desired['entityId']}|NO_MATCH".encode()
                ).hexdigest()[:20]
            )
            ranked.insert(
                0,
                {
                    "candidateId": candidate_id,
                    "desiredEntityId": desired["entityId"],
                    "currentEntityId": None,
                    "currentEntityType": None,
                    "alignmentType": "NoMatch",
                    "confidence": round(
                        1.0 - (ranked[0]["confidence"] if ranked else 0.0), 4
                    ),
                    "scoreComponents": {
                        "type": 0.0,
                        "lexical": 0.0,
                        "explicitToken": 0.0,
                        "implementationSuggestion": 0.0,
                    },
                    "evidenceRefs": desired.get("evidenceRefs", []),
                    "modelVersion": ALIGNMENT_MODEL_VERSION,
                    "reviewStatus": "Candidate",
                },
            )
        alignments.append(
            {
                "desiredEntity": desired,
                "candidates": ranked,
                "selectedCandidateId": None,
                "reviewStatus": "Candidate",
            }
        )
    return {
        "runId": run_id,
        "requirementId": requirement["requirementId"],
        "designRevisionId": requirement["designRevisionId"],
        "currentRevision": current_revision,
        "desiredRevision": requirement["desiredGraphRevision"],
        "modelVersion": ALIGNMENT_MODEL_VERSION,
        "status": "Draft",
        "alignments": alignments,
    }


def _graph_neighborhood(
    start_id: str,
    nodes: dict[str, dict[str, Any]],
    edges: list[dict[str, Any]],
    depth: int = 3,
    limit: int = 80,
) -> dict[str, Any]:
    adjacency: dict[str, list[tuple[dict[str, Any], str]]] = {}
    for edge in edges:
        adjacency.setdefault(edge["source"], []).append((edge, edge["target"]))
        adjacency.setdefault(edge["target"], []).append((edge, edge["source"]))
    selected = {start_id}
    selected_edges: dict[tuple[str, str, str], dict[str, Any]] = {}
    queue = deque([(start_id, 0)])
    while queue and len(selected) < limit:
        current, level = queue.popleft()
        if level >= depth:
            continue
        for edge, neighbor in adjacency.get(current, []):
            if neighbor not in nodes:
                continue
            selected_edges[(edge["source"], edge["relation"], edge["target"])] = edge
            if neighbor not in selected:
                selected.add(neighbor)
                queue.append((neighbor, level + 1))
    return {
        "primaryEntry": start_id,
        "nodes": [nodes[item] for item in sorted(selected)],
        "edges": [selected_edges[item] for item in sorted(selected_edges)],
    }


def build_implementation_slices(
    alignment_run: dict[str, Any],
    current_nodes: list[dict[str, Any]],
    current_edges: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    nodes = {item["id"]: item for item in current_nodes}
    slices = []
    for item in alignment_run["alignments"]:
        selected = next(
            (
                candidate
                for candidate in item["candidates"]
                if candidate["candidateId"] == item.get("selectedCandidateId")
            ),
            None,
        )
        if not selected or selected["currentEntityId"] is None:
            continue
        neighborhood = _graph_neighborhood(
            selected["currentEntityId"], nodes, current_edges
        )
        slice_id = (
            "slice-"
            + hashlib.sha256(
                (
                    alignment_run["runId"] + "|" + item["desiredEntity"]["entityId"]
                ).encode()
            ).hexdigest()[:16]
        )
        slices.append(
            {
                "sliceId": slice_id,
                "desiredEntityId": item["desiredEntity"]["entityId"],
                "alignmentId": selected["candidateId"],
                "primaryEntry": selected["currentEntityId"],
                "supportingEntityIds": [
                    node["id"]
                    for node in neighborhood["nodes"]
                    if node["id"] != selected["currentEntityId"]
                ],
                "evidenceRefs": selected["evidenceRefs"],
                "currentRevision": alignment_run["currentRevision"],
            }
        )
    return slices


def compute_semantic_diff(alignment_run: dict[str, Any]) -> dict[str, Any]:
    differences: list[dict[str, Any]] = []
    for item in alignment_run["alignments"]:
        selected = next(
            (
                candidate
                for candidate in item["candidates"]
                if candidate["candidateId"] == item.get("selectedCandidateId")
            ),
            None,
        )
        if selected is None:
            continue
        desired = item["desiredEntity"]
        alignment_type = selected["alignmentType"]
        if alignment_type == "ExactReuse":
            continue
        difference_type = (
            "AddEntityDifference"
            if alignment_type == "NoMatch"
            else "ModifyEntityDifference"
        )
        difference_id = (
            "diff-"
            + hashlib.sha256(
                (
                    alignment_run["runId"]
                    + "|"
                    + desired["entityId"]
                    + "|"
                    + difference_type
                ).encode()
            ).hexdigest()[:20]
        )
        differences.append(
            {
                "differenceId": difference_id,
                "differenceType": difference_type,
                "desiredEntityId": desired["entityId"],
                "desiredEntityType": desired["entityType"],
                "currentEntityId": selected["currentEntityId"],
                "alignmentId": selected["candidateId"],
                "alignmentType": alignment_type,
                "confidence": selected["confidence"],
                "evidenceRefs": desired.get("evidenceRefs", []),
            }
        )
    return {
        "diffId": f"semantic-diff:{alignment_run['runId']}",
        "engineVersion": DIFF_ENGINE_VERSION,
        "currentRevision": alignment_run["currentRevision"],
        "desiredRevision": alignment_run["desiredRevision"],
        "differences": differences,
    }


def _fallback_proposal(difference: dict[str, Any], rule_version: str) -> dict[str, Any]:
    desired_type = difference["desiredEntityType"]
    change_type = {
        "BusinessProcess": "ProposedBehaviorChange",
        "BusinessProcessStep": "ProposedBehaviorChange",
        "BusinessRule": "ProposedBehaviorChange",
        "DesiredBusinessEntity": "ProposedBehaviorChange",
        "DesiredCodeRole": "ProposedNodeModification",
        "DesiredAPIOperation": "ProposedContractChange",
        "DesiredSchema": "ProposedContractChange",
        "DesiredSchemaField": "ProposedContractChange",
        "DesiredDatabaseObject": "ProposedDataMigration",
        "DesiredEventType": "ProposedContractChange",
        "DesiredConfigurationKey": "ProposedConfigurationChange",
        "DesiredTestObligation": "ProposedTestChange",
        "DesiredDeploymentAction": "ProposedDeploymentChange",
    }.get(desired_type, "ProposedNodeModification")
    proposal_id = (
        "proposal-"
        + hashlib.sha256(
            (
                rule_version
                + "|FALLBACK|"
                + difference["differenceId"]
                + "|"
                + change_type
            ).encode()
        ).hexdigest()[:16]
    )
    return {
        "proposalId": proposal_id,
        "category": "Required",
        "changeType": change_type,
        "role": f"Implement{desired_type}",
        "targetCurrentEntityId": difference.get("currentEntityId"),
        "desiredEntityId": difference["desiredEntityId"],
        "reason": "Semantic Diff 需要实现，但当前规则集没有更具体的展开模板。",
        "evidenceRefs": difference.get("evidenceRefs", []),
        "derivedByRule": "GENERIC-SEMANTIC-DIFFERENCE",
        "dependsOn": [],
        "humanGate": "ArchitectureReview",
    }


def build_change_plan(
    *,
    plan_id: str,
    requirement: dict[str, Any],
    alignment_run: dict[str, Any],
    semantic_diff: dict[str, Any],
    implementation_slices: list[dict[str, Any]],
    planning_rules: PlanningRules,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = context or {}
    proposals: list[dict[str, Any]] = []
    assessments: list[dict[str, Any]] = []
    unresolved_questions: list[dict[str, Any]] = []
    matched_rules: set[str] = set()
    for difference in semantic_diff["differences"]:
        expansion = planning_rules.expand(difference, context)
        matched_rules.update(expansion["matchedRules"])
        expanded = expansion["proposals"] or [
            _fallback_proposal(difference, planning_rules.version)
        ]
        proposals.extend(expanded)
        for assessment in expansion["assessments"]:
            assessments.append(
                {
                    "assessmentType": assessment,
                    "differenceId": difference["differenceId"],
                    "status": "Required",
                }
            )
        unresolved_questions.extend(expansion["unresolvedQuestions"])

    proposal_by_id = {item["proposalId"]: item for item in proposals}
    proposals = [proposal_by_id[item] for item in sorted(proposal_by_id)]
    acceptance = [
        item
        for item in requirement["ir"]["desiredEntities"]
        if item["entityType"] == "DesiredTestObligation"
    ]
    obligations = [
        {
            "obligationId": (
                "verify-"
                + hashlib.sha256(f"{plan_id}|{item['entityId']}".encode()).hexdigest()[
                    :16
                ]
            ),
            "desiredEntityId": item["entityId"],
            "description": item["label"],
            "evidenceRefs": item["evidenceRefs"],
            "status": "Required",
        }
        for item in acceptance
    ]
    slice_by_desired = {item["desiredEntityId"]: item for item in implementation_slices}
    tasks: list[dict[str, Any]] = []
    non_test_task_ids: list[str] = []
    for proposal in proposals:
        task_id = f"task:{proposal['proposalId']}"
        desired_id = proposal.get("desiredEntityId")
        implementation_slice = slice_by_desired.get(desired_id, {})
        suggested_files: list[str] = []
        for evidence in implementation_slice.get("evidenceRefs", []):
            if isinstance(evidence, dict) and evidence.get("source"):
                suggested_files.append(evidence["source"])
        task_type = {
            "ProposedContractChange": "ModifyContract",
            "ProposedDataMigration": "AddMigration",
            "ProposedConfigurationChange": "ModifyConfiguration",
            "ProposedTestChange": "AddTest",
            "ProposedDeploymentChange": "ModifyDeployment",
        }.get(proposal["changeType"], "ModifyCode")
        task = {
            "taskId": task_id,
            "proposalId": proposal["proposalId"],
            "taskType": task_type,
            "repository": context.get("repositoryId"),
            "module": context.get("module"),
            "suggestedFiles": sorted(set(suggested_files)),
            "allowedFiles": [],
            "forbiddenFiles": [],
            "dependsOn": [],
            "acceptanceCriteria": [item["description"] for item in obligations],
            "requiredTests": [item["obligationId"] for item in obligations],
            "owner": None,
            "status": "Draft",
        }
        if task_type == "AddTest":
            task["dependsOn"] = list(non_test_task_ids)
        else:
            non_test_task_ids.append(task_id)
        tasks.append(task)
    return {
        "planId": plan_id,
        "status": "Draft",
        "changeSet": {
            "requirementId": requirement["requirementId"],
            "currentRevision": semantic_diff["currentRevision"],
            "desiredRevision": semantic_diff["desiredRevision"],
            "ruleSetVersion": planning_rules.version,
            "alignmentRunId": alignment_run["runId"],
            "semanticDiffId": semantic_diff["diffId"],
        },
        "semanticDiff": semantic_diff,
        "matchedRules": sorted(matched_rules),
        "proposals": proposals,
        "compatibilityAssessments": assessments,
        "verificationObligations": obligations,
        "implementationTasks": tasks,
        "unresolvedQuestions": unresolved_questions,
        "architectureReview": None,
        "approval": None,
    }
