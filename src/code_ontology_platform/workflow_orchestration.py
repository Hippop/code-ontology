from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .errors import PlatformError, conflict, invalid, not_found
from .models import enum_value, list_value, object_value, string_value
from .store import content_hash, utc_now

WORKFLOW_ROLES = {
    "requirement-analyst": "extract-requirement-ir",
    "code-graph-analyst": "align-design-to-code-graph",
    "change-planner": "plan-code-graph-change",
    "architecture-reviewer": "review-change-architecture",
    "verification-agent": "verify-and-reconcile",
}


class RequirementWorkflowOrchestrator:
    """Durable state machine that binds role Agents to governed platform stages."""

    def __init__(self, platform: Any) -> None:
        self.platform = platform

    @property
    def store(self) -> Any:
        return self.platform.store

    def _step(
        self,
        workflow: dict[str, Any],
        *,
        stage: str,
        status: str,
        resource: Mapping[str, Any] | None = None,
        detail: Mapping[str, Any] | None = None,
    ) -> None:
        workflow.setdefault("steps", []).append(
            {
                "sequence": len(workflow.get("steps", [])) + 1,
                "stage": stage,
                "status": status,
                "resource": dict(resource or {}),
                "detail": dict(detail or {}),
                "timestamp": utc_now(),
            }
        )

    def _save(
        self,
        workflow: dict[str, Any],
        *,
        correlation_id: str | None,
        actor: str | None,
        event_type: str = "RequirementWorkflowStateChanged",
    ) -> dict[str, Any]:
        saved = self.store.put_workflow_run(workflow)
        self.store.append_audit_event(
            event_type,
            {
                "workflowId": workflow["workflowId"],
                "status": workflow["status"],
                "stage": workflow["stage"],
                "pendingGate": workflow.get("pendingGate"),
                "resourceIds": workflow.get("resourceIds", {}),
            },
            correlation_id=correlation_id,
            run_id=workflow["workflowId"],
            requirement_id=workflow.get("requirementId"),
            repository_id=workflow["repositoryId"],
            revision=workflow.get("currentRevision"),
            actor=actor,
        )
        return saved

    def _invoke_role(
        self,
        workflow: dict[str, Any],
        *,
        agent_name: str,
        payload: Mapping[str, Any],
        correlation_id: str | None,
        actor: str,
    ) -> bool:
        skill_name = WORKFLOW_ROLES[agent_name]
        if workflow["agentMode"] == "disabled":
            self._step(
                workflow,
                stage=agent_name,
                status="Skipped",
                detail={"reason": "agentMode=disabled", "skillName": skill_name},
            )
            return True
        repository = self.platform.get_repository(workflow["repositoryId"])
        agent_run_id = (
            f"{workflow['workflowId']}-{agent_name}-"
            f"{len(workflow.get('agentRuns', [])) + 1}"
        )
        prompt = (
            f"Load the `{skill_name}` skill and execute the governed "
            f"`{agent_name}` stage. This stage is read-only: do not edit files, "
            "commit, push, merge, deploy, or bypass a human gate. Validate the "
            "supplied platform context and return a concise JSON result with "
            "findings, evidence, assumptions, unresolved items, and the "
            "recommended next action.\n\n"
            + json.dumps(dict(payload), ensure_ascii=False, indent=2)
        )
        workflow.update(
            {
                "status": "Running",
                "stage": agent_name,
                "pendingGate": None,
                "nextActions": [],
            }
        )
        self._step(
            workflow,
            stage=agent_name,
            status="Running",
            resource={
                "runId": agent_run_id,
                "agentName": agent_name,
                "skillName": skill_name,
            },
        )
        self.store.put_workflow_run(workflow)
        self.store.append_audit_event(
            "WorkflowAgentStarted",
            {
                "workflowId": workflow["workflowId"],
                "agentRunId": agent_run_id,
                "agentName": agent_name,
                "skillName": skill_name,
                "contextHash": content_hash(payload),
            },
            correlation_id=correlation_id,
            run_id=workflow["workflowId"],
            requirement_id=workflow.get("requirementId"),
            repository_id=workflow["repositoryId"],
            revision=workflow.get("currentRevision"),
            actor=actor,
        )
        try:
            execution = self.platform.role_agent_adapter.execute(
                worktree=Path(repository["path"]),
                run_id=agent_run_id,
                prompt=prompt,
                agent_name=agent_name,
                allowed_files=[],
                forbidden_files=["**"],
                required_tests=[],
                skill_name=skill_name,
                read_only=True,
            )
            result = {
                "runId": agent_run_id,
                "agentName": agent_name,
                "skillName": skill_name,
                "status": "Completed",
                "runtime": execution.get("runtime"),
                "runtimeVersion": execution.get("runtimeVersion"),
                "sessionId": execution.get("sessionId"),
                "message": execution.get("message"),
                "contextHash": content_hash(payload),
                "completedAt": utc_now(),
            }
            workflow.setdefault("agentRuns", []).append(result)
            self._step(
                workflow,
                stage=agent_name,
                status="Completed",
                resource={
                    "runId": agent_run_id,
                    "agentName": agent_name,
                    "skillName": skill_name,
                },
                detail={"contextHash": result["contextHash"]},
            )
            self.store.append_audit_event(
                "WorkflowAgentCompleted",
                {key: value for key, value in result.items() if key != "message"},
                correlation_id=correlation_id,
                run_id=workflow["workflowId"],
                requirement_id=workflow.get("requirementId"),
                repository_id=workflow["repositoryId"],
                revision=workflow.get("currentRevision"),
                actor=actor,
            )
            self.store.put_workflow_run(workflow)
            return True
        except PlatformError as error:
            failure = {
                "runId": agent_run_id,
                "agentName": agent_name,
                "skillName": skill_name,
                "status": "Failed",
                "error": {
                    "code": error.code,
                    "message": error.message,
                    "details": error.details,
                },
                "contextHash": content_hash(payload),
                "completedAt": utc_now(),
            }
        except Exception as error:  # noqa: BLE001 - persist adapter boundary failures.
            failure = {
                "runId": agent_run_id,
                "agentName": agent_name,
                "skillName": skill_name,
                "status": "Failed",
                "error": {
                    "code": "WORKFLOW_AGENT_FAILED",
                    "message": str(error)[:1000],
                },
                "contextHash": content_hash(payload),
                "completedAt": utc_now(),
            }
        workflow.setdefault("agentRuns", []).append(failure)
        self._step(
            workflow,
            stage=agent_name,
            status="Failed",
            resource={"runId": agent_run_id, "agentName": agent_name},
            detail=failure["error"],
        )
        self.store.append_audit_event(
            "WorkflowAgentFailed",
            failure,
            correlation_id=correlation_id,
            run_id=workflow["workflowId"],
            requirement_id=workflow.get("requirementId"),
            repository_id=workflow["repositoryId"],
            revision=workflow.get("currentRevision"),
            actor=actor,
        )
        self.store.put_workflow_run(workflow)
        if workflow["agentMode"] == "required":
            workflow.update(
                {
                    "status": "Failed",
                    "stage": agent_name,
                    "pendingGate": None,
                    "error": failure["error"],
                    "nextActions": ["RetryFailedStage"],
                }
            )
            return False
        return True

    def _wait(
        self,
        workflow: dict[str, Any],
        *,
        gate: str,
        stage: str,
        next_actions: list[str],
        pending_items: list[dict[str, Any]] | None = None,
    ) -> None:
        workflow.update(
            {
                "status": "NeedsHumanReview",
                "stage": stage,
                "pendingGate": gate,
                "nextActions": next_actions,
                "pendingItems": pending_items or [],
            }
        )
        self._step(
            workflow,
            stage=stage,
            status="NeedsHumanReview",
            detail={"gate": gate, "nextActions": next_actions},
        )

    def create(
        self, body_value: Any, correlation_id: str | None = None
    ) -> dict[str, Any]:
        body = object_value(body_value, "request")
        repository_id = string_value(body.get("repositoryId"), "repositoryId")
        self.platform.get_repository(repository_id)
        actor = str(body.get("actor") or "requirement-orchestrator")
        agent_mode = enum_value(
            body.get("agentMode", "required"),
            "agentMode",
            frozenset({"required", "advisory", "disabled"}),
        )
        workflow_id_value = body.get("workflowId")
        workflow_id = (
            string_value(workflow_id_value, "workflowId")
            if workflow_id_value is not None
            else f"requirement-workflow-{uuid.uuid4()}"
        )
        existing = self.store.get_workflow_run(workflow_id)
        if existing is not None:
            return existing
        current_revision_value = body.get("currentRevision")
        if current_revision_value is None:
            revisions = self.store.list_repository_graph_revisions(repository_id)
            if revisions:
                current_revision = revisions[0]["revision"]
            else:
                scan = self.platform.scan_repository(
                    repository_id,
                    {"actor": actor},
                    correlation_id,
                )
                current_revision = scan["revision"]
        else:
            current_revision = string_value(current_revision_value, "currentRevision")
        current_nodes, _ = self.store.read_graph("current", current_revision)
        if not current_nodes:
            raise not_found(f"Current Graph Revision 不存在: {current_revision}")
        document_body = object_value(body.get("document"), "document")
        revision_body = object_value(body.get("revision"), "revision")
        workflow: dict[str, Any] = {
            "workflowId": workflow_id,
            "repositoryId": repository_id,
            "requirementId": None,
            "requestedRequirementId": body.get("requirementId"),
            "currentRevision": current_revision,
            "status": "Running",
            "stage": "Extract",
            "pendingGate": None,
            "agentMode": agent_mode,
            "orchestrator": {
                "agentName": "requirement-orchestrator",
                "skillName": "orchestrate-requirement-change",
                "version": "workflow-state-machine-1.0.0",
            },
            "resourceIds": {},
            "steps": [],
            "agentRuns": [],
            "nextActions": [],
        }
        self._step(
            workflow,
            stage="Workflow",
            status="Started",
            detail={"agentMode": agent_mode},
        )
        try:
            document = self.platform.create_design_document(
                {
                    **document_body,
                    "owner": document_body.get("owner") or actor,
                },
                correlation_id,
            )
            revision = self.platform.create_design_revision(
                document["documentId"],
                {**revision_body, "actor": actor},
                correlation_id,
            )
            workflow["resourceIds"].update(
                {
                    "documentId": document["documentId"],
                    "designRevisionId": revision["revisionId"],
                }
            )
            self._step(
                workflow,
                stage="DesignIngestion",
                status="Completed",
                resource=workflow["resourceIds"],
            )
            if not self._invoke_role(
                workflow,
                agent_name="requirement-analyst",
                payload={
                    "workflowId": workflow_id,
                    "document": document,
                    "designRevision": {
                        key: value
                        for key, value in revision.items()
                        if key != "content"
                    },
                    "designContent": revision["content"],
                },
                correlation_id=correlation_id,
                actor=actor,
            ):
                return self._save(workflow, correlation_id=correlation_id, actor=actor)
            extract_request: dict[str, Any] = {"actor": "requirement-analyst"}
            if body.get("requirementId") is not None:
                extract_request["requirementId"] = body["requirementId"]
            extracted = self.platform.extract_design_revision(
                revision["revisionId"],
                extract_request,
                correlation_id,
            )
            requirement_id = extracted["requirementId"]
            workflow["requirementId"] = requirement_id
            workflow["resourceIds"]["requirementId"] = requirement_id
            self._step(
                workflow,
                stage="RequirementIR",
                status="Completed",
                resource={
                    "requirementId": requirement_id,
                    "desiredRevision": extracted["desiredGraphRevision"],
                },
            )
            self._wait(
                workflow,
                gate="RequirementReview",
                stage="Requirement",
                next_actions=["Confirm", "NeedsRevision", "Reject"],
                pending_items=[
                    {
                        "requirementId": requirement_id,
                        "unresolvedQuestions": extracted["ir"].get(
                            "unresolvedQuestions", []
                        ),
                    }
                ],
            )
        except PlatformError as error:
            workflow.update(
                {
                    "status": "Failed",
                    "pendingGate": None,
                    "error": {
                        "code": error.code,
                        "message": error.message,
                        "details": error.details,
                    },
                    "nextActions": ["FixInputAndCreateNewWorkflow"],
                }
            )
            self._step(
                workflow,
                stage=workflow["stage"],
                status="Failed",
                detail=workflow["error"],
            )
        return self._save(
            workflow,
            correlation_id=correlation_id,
            actor=actor,
            event_type="RequirementWorkflowCreated",
        )

    def get(self, workflow_id: str) -> dict[str, Any]:
        workflow_id = string_value(workflow_id, "workflowId")
        workflow = self.store.get_workflow_run(workflow_id)
        if workflow is None:
            raise not_found(f"未找到 Requirement Workflow: {workflow_id}")
        return workflow

    def list(
        self,
        *,
        requirement_id: str | None = None,
        repository_id: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        if requirement_id is not None:
            requirement_id = string_value(requirement_id, "requirementId")
        if repository_id is not None:
            repository_id = string_value(repository_id, "repositoryId")
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 500
        ):
            raise invalid("limit 必须是 1 到 500 的整数")
        items = self.store.list_workflow_runs(
            requirement_id=requirement_id,
            repository_id=repository_id,
            limit=limit,
        )
        return {"items": items, "count": len(items)}

    def resume(
        self,
        workflow_id: str,
        body_value: Any,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        workflow = self.get(workflow_id)
        if workflow["status"] != "NeedsHumanReview":
            raise conflict(f"Workflow 当前状态不可恢复: {workflow['status']}")
        body = object_value(body_value, "request")
        gate = string_value(body.get("gate"), "gate")
        if gate != workflow.get("pendingGate"):
            raise conflict(
                f"Workflow 正在等待 {workflow.get('pendingGate')}，不能提交 {gate}"
            )
        actor = string_value(body.get("actor"), "actor")
        rationale = string_value(body.get("rationale"), "rationale")
        string_value(workflow.get("requirementId"), "requirementId")
        workflow.update(
            {
                "status": "Running",
                "pendingGate": None,
                "pendingItems": [],
                "nextActions": [],
            }
        )
        if gate == "RequirementReview":
            self._resume_requirement_review(
                workflow, body, actor, rationale, correlation_id
            )
        elif gate == "AlignmentReview":
            self._resume_alignment_review(
                workflow, body, actor, rationale, correlation_id
            )
        elif gate == "ArchitectureReview":
            self._resume_architecture_review(
                workflow, body, actor, rationale, correlation_id
            )
        elif gate == "ChangeApproval":
            self._resume_change_approval(
                workflow, body, actor, rationale, correlation_id
            )
        else:
            raise invalid(f"不支持的 Workflow Gate: {gate}")
        return self._save(workflow, correlation_id=correlation_id, actor=actor)

    def retry(
        self,
        workflow_id: str,
        body_value: Any,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        workflow = self.get(workflow_id)
        if workflow["status"] != "Failed":
            raise conflict(f"Workflow 当前状态不可重试: {workflow['status']}")
        body = object_value(body_value, "request")
        actor = string_value(body.get("actor"), "actor")
        rationale = string_value(body.get("rationale"), "rationale")
        failed_stage = workflow["stage"]
        workflow.update(
            {
                "status": "Running",
                "pendingGate": None,
                "pendingItems": [],
                "nextActions": [],
            }
        )
        workflow.pop("error", None)
        self._step(
            workflow,
            stage=failed_stage,
            status="Retrying",
            detail={"actor": actor, "rationale": rationale},
        )
        if failed_stage == "requirement-analyst":
            self._retry_requirement_analyst(workflow, correlation_id, actor)
        elif failed_stage == "code-graph-analyst":
            self._run_code_graph_analysis(workflow, correlation_id, actor)
        elif failed_stage == "change-planner":
            self._run_change_planning(workflow, correlation_id, actor)
        elif failed_stage == "architecture-reviewer":
            plan = self.platform.get_change_plan(
                workflow["resourceIds"]["changePlanId"]
            )
            self._run_architecture_review(workflow, plan, correlation_id, actor)
        elif failed_stage == "Implementation":
            self._run_implementation_and_verification(workflow, correlation_id, actor)
        elif failed_stage == "Reconciliation":
            self._run_reconciliation_and_verification(
                workflow, correlation_id, actor
            )
        elif failed_stage == "verification-agent":
            self._run_verification_agent(workflow, correlation_id, actor)
        else:
            raise conflict(f"Workflow 失败阶段不支持重试: {failed_stage}")
        return self._save(
            workflow,
            correlation_id=correlation_id,
            actor=actor,
            event_type="RequirementWorkflowRetried",
        )

    def _retry_requirement_analyst(
        self,
        workflow: dict[str, Any],
        correlation_id: str | None,
        actor: str,
    ) -> None:
        revision = self.store.get_design_revision(
            workflow["resourceIds"]["designRevisionId"]
        )
        document = self.store.get_design_document(workflow["resourceIds"]["documentId"])
        if revision is None or document is None:
            raise not_found("Workflow 对应设计文档或版本不存在")
        if not self._invoke_role(
            workflow,
            agent_name="requirement-analyst",
            payload={
                "workflowId": workflow["workflowId"],
                "document": document,
                "designRevision": {
                    key: value for key, value in revision.items() if key != "content"
                },
                "designContent": revision["content"],
            },
            correlation_id=correlation_id,
            actor=actor,
        ):
            return
        extract_request: dict[str, Any] = {"actor": "requirement-analyst"}
        if workflow.get("requestedRequirementId") is not None:
            extract_request["requirementId"] = workflow["requestedRequirementId"]
        extracted = self.platform.extract_design_revision(
            revision["revisionId"], extract_request, correlation_id
        )
        requirement_id = extracted["requirementId"]
        workflow["requirementId"] = requirement_id
        workflow["resourceIds"]["requirementId"] = requirement_id
        self._step(
            workflow,
            stage="RequirementIR",
            status="Completed",
            resource={
                "requirementId": requirement_id,
                "desiredRevision": extracted["desiredGraphRevision"],
            },
        )
        self._wait(
            workflow,
            gate="RequirementReview",
            stage="Requirement",
            next_actions=["Confirm", "NeedsRevision", "Reject"],
            pending_items=[
                {
                    "requirementId": requirement_id,
                    "unresolvedQuestions": extracted["ir"].get(
                        "unresolvedQuestions", []
                    ),
                }
            ],
        )

    def _resume_requirement_review(
        self,
        workflow: dict[str, Any],
        body: dict[str, Any],
        actor: str,
        rationale: str,
        correlation_id: str | None,
    ) -> None:
        requirement_id = workflow["requirementId"]
        decision = enum_value(
            body.get("decision"),
            "decision",
            frozenset({"Confirm", "Reject", "NeedsRevision"}),
        )
        review = self.platform.review_requirement(
            requirement_id,
            {
                "decision": decision,
                "actor": actor,
                "rationale": rationale,
                "acceptUnresolved": body.get("acceptUnresolved") is True,
            },
            correlation_id,
        )
        workflow["resourceIds"]["requirementReviewId"] = review["review"]["reviewId"]
        self._step(
            workflow,
            stage="RequirementReview",
            status=review["requirement"]["status"],
            resource={"reviewId": review["review"]["reviewId"]},
        )
        if decision != "Confirm":
            workflow.update(
                {
                    "status": ("Rejected" if decision == "Reject" else "NeedsRevision"),
                    "stage": "Requirement",
                    "pendingGate": None,
                    "nextActions": ["CreateRevisedDesignRevision"],
                }
            )
            return
        self._run_code_graph_analysis(workflow, correlation_id, actor)

    def _run_code_graph_analysis(
        self,
        workflow: dict[str, Any],
        correlation_id: str | None,
        actor: str,
    ) -> None:
        requirement_id = workflow["requirementId"]
        requirement = self.platform.get_requirement_ir(requirement_id)
        if not self._invoke_role(
            workflow,
            agent_name="code-graph-analyst",
            payload={
                "requirement": requirement,
                "currentRevision": workflow["currentRevision"],
                "repositoryId": workflow["repositoryId"],
            },
            correlation_id=correlation_id,
            actor=actor,
        ):
            return
        alignment = self.platform.create_alignment_run(
            {
                "requirementId": requirement_id,
                "currentRevision": workflow["currentRevision"],
                "repositoryId": workflow["repositoryId"],
                "actor": "code-graph-analyst",
            },
            correlation_id,
        )
        workflow["resourceIds"]["alignmentRunId"] = alignment["runId"]
        self._wait(
            workflow,
            gate="AlignmentReview",
            stage="Alignment",
            next_actions=["SubmitCandidateSelections"],
            pending_items=self._pending_alignments(alignment),
        )

    @staticmethod
    def _pending_alignments(alignment: Mapping[str, Any]) -> list[dict[str, Any]]:
        return [
            {
                "desiredEntityId": item["desiredEntity"]["entityId"],
                "candidates": item["candidates"],
            }
            for item in alignment["alignments"]
            if item.get("selectedCandidateId") is None
        ]

    def _resume_alignment_review(
        self,
        workflow: dict[str, Any],
        body: dict[str, Any],
        actor: str,
        rationale: str,
        correlation_id: str | None,
    ) -> None:
        selections = list_value(body.get("selections"), "selections", nonempty=True)
        alignment_run_id = workflow["resourceIds"]["alignmentRunId"]
        alignment = self.platform.get_alignment_run(alignment_run_id)
        for index, selection_value in enumerate(selections):
            selection = object_value(selection_value, f"selections[{index}]")
            candidate_id = string_value(
                selection.get("candidateId"),
                f"selections[{index}].candidateId",
            )
            alignment = self.platform.review_alignment(
                candidate_id,
                {
                    "decision": selection.get("decision", "Confirm"),
                    "actor": actor,
                    "rationale": selection.get("rationale") or rationale,
                },
                correlation_id,
            )
        if alignment["status"] != "Confirmed":
            self._wait(
                workflow,
                gate="AlignmentReview",
                stage="Alignment",
                next_actions=["SubmitRemainingCandidateSelections"],
                pending_items=self._pending_alignments(alignment),
            )
            return
        self._step(
            workflow,
            stage="AlignmentReview",
            status="Confirmed",
            resource={"alignmentRunId": alignment_run_id},
        )
        workflow["planningContext"] = object_value(
            body.get("planningContext", {}), "planningContext"
        )
        self._run_change_planning(workflow, correlation_id, actor)

    def _run_change_planning(
        self,
        workflow: dict[str, Any],
        correlation_id: str | None,
        actor: str,
    ) -> None:
        alignment_run_id = workflow["resourceIds"]["alignmentRunId"]
        alignment = self.platform.get_alignment_run(alignment_run_id)
        if not self._invoke_role(
            workflow,
            agent_name="change-planner",
            payload={
                "alignmentRun": alignment,
                "requirementId": workflow["requirementId"],
            },
            correlation_id=correlation_id,
            actor=actor,
        ):
            return
        plan = self.platform.create_change_plan(
            {
                "alignmentRunId": alignment_run_id,
                "actor": "change-planner",
                "context": {
                    "repositoryId": workflow["repositoryId"],
                    **workflow.get("planningContext", {}),
                },
            },
            correlation_id,
        )
        workflow["resourceIds"]["changePlanId"] = plan["planId"]
        self._run_architecture_review(workflow, plan, correlation_id, actor)

    def _run_architecture_review(
        self,
        workflow: dict[str, Any],
        plan: Mapping[str, Any],
        correlation_id: str | None,
        actor: str,
    ) -> None:
        if not self._invoke_role(
            workflow,
            agent_name="architecture-reviewer",
            payload={"changePlan": plan},
            correlation_id=correlation_id,
            actor=actor,
        ):
            return
        self._wait(
            workflow,
            gate="ArchitectureReview",
            stage="Plan",
            next_actions=["Accept", "NeedsRevision", "Reject"],
            pending_items=[
                {
                    "changePlanId": plan["planId"],
                    "governance": plan["governance"],
                    "reviewReasons": plan.get("reviewReasons", []),
                }
            ],
        )

    def _resume_architecture_review(
        self,
        workflow: dict[str, Any],
        body: dict[str, Any],
        actor: str,
        rationale: str,
        correlation_id: str | None,
    ) -> None:
        decision = enum_value(
            body.get("decision"),
            "decision",
            frozenset({"Accept", "Reject", "NeedsRevision"}),
        )
        plan_id = workflow["resourceIds"]["changePlanId"]
        plan = self.platform.review_change_plan(
            plan_id,
            {
                "decision": decision,
                "actor": actor,
                "rationale": rationale,
                "findings": body.get("findings", []),
            },
            correlation_id,
        )
        self._step(
            workflow,
            stage="ArchitectureReview",
            status=plan["status"],
            resource={"changePlanId": plan_id},
        )
        if decision != "Accept":
            workflow.update(
                {
                    "status": ("Rejected" if decision == "Reject" else "NeedsRevision"),
                    "stage": "Plan",
                    "pendingGate": None,
                    "nextActions": ["ReviseChangePlan"],
                }
            )
            return
        self._wait(
            workflow,
            gate="ChangeApproval",
            stage="Approval",
            next_actions=["ApproveWithExecutionPolicy"],
            pending_items=[
                {
                    "changePlanId": plan_id,
                    "requiresSecurityDataReview": plan["governance"][
                        "requiresSecurityDataReview"
                    ],
                }
            ],
        )

    def _resume_change_approval(
        self,
        workflow: dict[str, Any],
        body: dict[str, Any],
        actor: str,
        rationale: str,
        correlation_id: str | None,
    ) -> None:
        enum_value(body.get("decision"), "decision", frozenset({"Approve"}))
        plan_id = workflow["resourceIds"]["changePlanId"]
        self.platform.approve_change_plan(
            plan_id,
            {
                "actor": actor,
                "rationale": rationale,
                "allowedFiles": body.get("allowedFiles"),
                "forbiddenFiles": body.get("forbiddenFiles"),
                "requiredTests": body.get("requiredTests"),
                "securityDataApproved": body.get("securityDataApproved") is True,
            },
            correlation_id,
        )
        self._step(
            workflow,
            stage="ChangeApproval",
            status="Approved",
            resource={"changePlanId": plan_id},
        )
        self._run_implementation_and_verification(workflow, correlation_id, actor)

    def _run_implementation_and_verification(
        self,
        workflow: dict[str, Any],
        correlation_id: str | None,
        actor: str,
    ) -> None:
        plan_id = workflow["resourceIds"]["changePlanId"]
        workflow.update(
            {
                "status": "Running",
                "stage": "Implementation",
                "pendingGate": None,
                "nextActions": [],
            }
        )
        self._step(
            workflow,
            stage="Implementation",
            status="Running",
            resource={"changePlanId": plan_id},
        )
        self.store.put_workflow_run(workflow)
        agent_run = self.platform.create_agent_run(
            {
                "changePlanId": plan_id,
                "repositoryId": workflow["repositoryId"],
                "baseCommit": workflow["currentRevision"],
                "actor": "implementation-agent",
            },
            correlation_id,
        )
        workflow["resourceIds"]["agentRunId"] = agent_run["runId"]
        workflow.setdefault("agentRuns", []).append(
            {
                "runId": agent_run["runId"],
                "agentName": "implementation-agent",
                "skillName": "implement-approved-change",
                "status": agent_run["status"],
                "runtime": agent_run.get("runtime"),
                "runtimeVersion": agent_run.get("runtimeVersion"),
                "sessionId": agent_run.get("sessionId"),
            }
        )
        self._step(
            workflow,
            stage="Implementation",
            status=agent_run["status"],
            resource={"agentRunId": agent_run["runId"]},
        )
        self.store.put_workflow_run(workflow)
        if agent_run["status"] != "Completed":
            workflow.update(
                {
                    "status": "Failed",
                    "stage": "Implementation",
                    "pendingGate": None,
                    "error": agent_run.get("error")
                    or {
                        "code": "IMPLEMENTATION_NOT_COMPLETED",
                        "message": agent_run["status"],
                    },
                    "nextActions": ["InspectAgentRun", "RetryFailedStage"],
                }
            )
            return
        self._run_reconciliation_and_verification(
            workflow, correlation_id, actor
        )

    def _run_reconciliation_and_verification(
        self,
        workflow: dict[str, Any],
        correlation_id: str | None,
        actor: str,
    ) -> None:
        agent_run_id = workflow["resourceIds"]["agentRunId"]
        workflow.update(
            {
                "status": "Running",
                "stage": "Reconciliation",
                "pendingGate": None,
                "nextActions": [],
            }
        )
        self._step(
            workflow,
            stage="Reconciliation",
            status="Running",
            resource={"agentRunId": agent_run_id},
        )
        self.store.put_workflow_run(workflow)
        failure: dict[str, Any] | None = None
        try:
            reconciliation = self.platform.create_reconciliation_run(
                {
                    "agentRunId": agent_run_id,
                    "actor": "verification-agent",
                },
                correlation_id,
            )
            workflow["resourceIds"]["reconciliationRunId"] = reconciliation[
                "runId"
            ]
            impact = self.platform.create_impact_run(
                {
                    "reconciliationRunId": reconciliation["runId"],
                    "actor": "verification-agent",
                },
                correlation_id,
            )
            workflow["resourceIds"]["impactRunId"] = impact["runId"]
            self._step(
                workflow,
                stage="Reconciliation",
                status="Completed",
                resource={
                    "reconciliationRunId": reconciliation["runId"],
                    "impactRunId": impact["runId"],
                },
            )
            self.store.put_workflow_run(workflow)
            self._run_verification_agent(workflow, correlation_id, actor)
        except PlatformError as error:
            failure = {
                "code": error.code,
                "message": error.message,
                "details": error.details,
            }
        except Exception as error:  # noqa: BLE001 - persist orchestration boundary.
            failure = {
                "code": "RECONCILIATION_FAILED",
                "message": str(error)[:1000],
            }
        if failure is not None:
            workflow.update(
                {
                    "status": "Failed",
                    "stage": "Reconciliation",
                    "pendingGate": None,
                    "error": failure,
                    "nextActions": [
                        "InspectAgentRun",
                        "RetryFailedStage",
                    ],
                }
            )
            self._step(
                workflow,
                stage="Reconciliation",
                status="Failed",
                resource={"agentRunId": agent_run_id},
                detail=workflow["error"],
            )

    def _run_verification_agent(
        self,
        workflow: dict[str, Any],
        correlation_id: str | None,
        actor: str,
    ) -> None:
        agent_run = self.platform.get_agent_run(workflow["resourceIds"]["agentRunId"])
        reconciliation = self.platform.get_reconciliation_run(
            workflow["resourceIds"]["reconciliationRunId"]
        )
        impact = self.platform.get_impact_run(workflow["resourceIds"]["impactRunId"])
        if not self._invoke_role(
            workflow,
            agent_name="verification-agent",
            payload={
                "agentRun": {
                    key: value
                    for key, value in agent_run.items()
                    if key not in {"diff", "execution"}
                },
                "reconciliation": reconciliation,
                "impact": impact,
            },
            correlation_id=correlation_id,
            actor=actor,
        ):
            return
        workflow.update(
            {
                "status": "Completed",
                "stage": "Impact",
                "pendingGate": None,
                "pendingItems": [],
                "nextActions": ["ReviewReleaseAdvice"],
                "result": {
                    "reconciliationStatus": reconciliation["status"],
                    "releaseDecision": impact["releasePlan"]["decision"],
                    "releaseHumanGateRequired": impact["releasePlan"][
                        "requiresHumanReleaseGate"
                    ],
                },
            }
        )
        self._step(
            workflow,
            stage="Workflow",
            status="Completed",
            resource=workflow["resourceIds"],
            detail=workflow["result"],
        )
