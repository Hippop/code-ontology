from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .errors import invalid

STAGES = frozenset(
    {"extract", "align", "plan", "generate", "implement", "verify", "precommit", "impact"}
)
GRAPH_SPACES = frozenset(
    {"current", "business", "desired", "proposed", "approved", "actual", "impact"}
)
QUERY_TYPES = frozenset(
    {
        "GRAPH_OVERVIEW",
        "ENTITY_NEIGHBORHOOD",
        "IMPLEMENTATION_SLICE",
        "BUSINESS_TRACE",
        "CALL_PATH",
        "CONTRACT_CONSUMERS",
        "DATA_DEPENDENCIES",
        "CHANGE_CONTEXT",
        "IMPACT_PATHS",
    }
)
ARTIFACT_TYPES = frozenset(
    {
        "RequirementIRDraft",
        "DesiredGraphDraft",
        "CandidateAlignmentDraft",
        "ImplementationSliceDraft",
        "ProposedChangeDraft",
        "ArchitectureReview",
        "ImplementationPatch",
        "TestExecutionReport",
        "ReconciliationReport",
        "ImpactExplanation",
        "EngineeringSemanticGraph",
        "EngineeringCoverage",
        "CodeGenerationPlan",
        "CodeGenerationArtifact",
        "GitDiffSnapshot",
        "WorkingTreeGraphOverlay",
        "ActualChangeSet",
        "ActualImpactGraph",
        "ImpactObligationArtifact",
        "ImplementationReconciliationArtifact",
        "VerificationCoverageArtifact",
        "PreCommitReview",
    }
)
ALIGNMENT_TYPES = frozenset(
    {
        "ExactReuse",
        "ExtendExisting",
        "ModifyExisting",
        "SemanticAlias",
        "ReplaceExisting",
        "NoMatch",
        "Ambiguous",
    }
)
RECONCILIATION_STATUSES = frozenset(
    {
        "ImplementedAsDesigned",
        "MissingImplementation",
        "UnexpectedImplementation",
        "ChangedDesign",
        "PartiallyImplemented",
        "Unverified",
    }
)


def object_value(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise invalid(f"{name} 必须是 JSON object")
    return dict(value)


def string_value(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise invalid(f"{name} 必须是非空字符串")
    return value.strip()


def list_value(value: Any, name: str, *, nonempty: bool = False) -> list[Any]:
    if not isinstance(value, list):
        raise invalid(f"{name} 必须是数组")
    if nonempty and not value:
        raise invalid(f"{name} 至少包含一项")
    return value


def enum_value(value: Any, name: str, allowed: frozenset[str]) -> str:
    result = string_value(value, name)
    if result not in allowed:
        raise invalid(
            f"{name} 不受支持", {"allowed": sorted(allowed), "actual": result}
        )
    return result


def validate_artifact_payload(artifact_type: str, payload: Any) -> dict[str, Any]:
    enum_value(artifact_type, "artifactType", ARTIFACT_TYPES)
    result = object_value(payload, "payload")
    if not result:
        raise invalid("payload 不能为空")

    if artifact_type == "RequirementIRDraft":
        string_value(result.get("requirementId"), "payload.requirementId")
        string_value(result.get("designRevisionId"), "payload.designRevisionId")
        list_value(
            result.get("desiredEntities"), "payload.desiredEntities", nonempty=True
        )

    elif artifact_type == "CandidateAlignmentDraft":
        candidates = list_value(
            result.get("candidates"), "payload.candidates", nonempty=True
        )
        for index, candidate_value in enumerate(candidates):
            candidate = object_value(candidate_value, f"payload.candidates[{index}]")
            string_value(
                candidate.get("desiredEntityId"),
                f"payload.candidates[{index}].desiredEntityId",
            )
            current_id = candidate.get("currentEntityId")
            alignment_type = enum_value(
                candidate.get("alignmentType"),
                f"payload.candidates[{index}].alignmentType",
                ALIGNMENT_TYPES,
            )
            if alignment_type != "NoMatch":
                string_value(current_id, f"payload.candidates[{index}].currentEntityId")
            confidence = candidate.get("confidence")
            if (
                isinstance(confidence, bool)
                or not isinstance(confidence, (int, float))
                or not 0 <= confidence <= 1
            ):
                raise invalid(f"payload.candidates[{index}].confidence 必须位于 0 到 1")
            list_value(
                candidate.get("evidenceRefs"),
                f"payload.candidates[{index}].evidenceRefs",
                nonempty=True,
            )

    elif artifact_type == "ProposedChangeDraft":
        proposals = list_value(
            result.get("proposals"), "payload.proposals", nonempty=True
        )
        for index, proposal_value in enumerate(proposals):
            proposal = object_value(proposal_value, f"payload.proposals[{index}]")
            string_value(
                proposal.get("proposalId"),
                f"payload.proposals[{index}].proposalId",
            )
            string_value(
                proposal.get("changeType"),
                f"payload.proposals[{index}].changeType",
            )
            list_value(
                proposal.get("evidenceRefs"),
                f"payload.proposals[{index}].evidenceRefs",
                nonempty=True,
            )

    elif artifact_type == "ReconciliationReport":
        results = list_value(result.get("results"), "payload.results", nonempty=True)
        for index, item_value in enumerate(results):
            item = object_value(item_value, f"payload.results[{index}]")
            string_value(item.get("proposalId"), f"payload.results[{index}].proposalId")
            enum_value(
                item.get("status"),
                f"payload.results[{index}].status",
                RECONCILIATION_STATUSES,
            )
            list_value(
                item.get("evidenceRefs"), f"payload.results[{index}].evidenceRefs"
            )
        enum_value(
            result.get("releaseRecommendation"),
            "payload.releaseRecommendation",
            frozenset({"Pass", "Block", "NeedsHumanReview"}),
        )

    return result
