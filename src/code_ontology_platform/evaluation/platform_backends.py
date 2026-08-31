from __future__ import annotations

import copy
import shutil
import subprocess
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ..agent_runtime import collect_worktree_diff
from ..errors import conflict, invalid
from ..precommit_verification import (
    build_actual_change_set,
    build_actual_impact_graph,
    build_git_diff_snapshot,
    build_impact_obligations,
    build_precommit_review,
    build_simple_reconciliation,
    build_verification_coverage,
    build_worktree_graph_overlay,
)
from ..repository_scan import RepositoryScanner
from ..service import PlatformService
from ..store import SQLiteStore, content_hash
from ..verification_workflow import reconcile_approved_actual
from .loader import EvaluationLoader
from .models import EvaluationScenario, ExecutionConfig, StageRun
from .runner import BackendResult, utc_now


def _project_rules_path() -> Path:
    return Path(__file__).resolve().parents[3] / "rules" / "requirement-change-planning-rules.yaml"


def _scenario_base(scenario: EvaluationScenario) -> Path:
    return Path(scenario.source_path).parent if scenario.source_path else Path.cwd()


def _resolve_scenario_path(scenario: EvaluationScenario, value: Any) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise invalid("Scenario 路径必须是非空字符串")
    path = Path(value)
    if not path.is_absolute():
        path = _scenario_base(scenario) / path
    return path.resolve()


def _fixture_repository(source: Path) -> Path:
    if (source / "repo").is_dir():
        return source / "repo"
    return source


def _copy_fixture_repository(scenario: EvaluationScenario, workspace: Path) -> Path:
    source = _fixture_repository(Path(scenario.fixture.source_path).resolve())
    if not source.is_dir():
        raise invalid("Fixture repository 不存在", {"path": str(source)})
    target = workspace / "repo"
    shutil.copytree(source, target, symlinks=False)
    return target


def _git(repository: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["git", "-C", str(repository), *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    if check and completed.returncode != 0:
        raise conflict(
            "Evaluation Git 操作失败: "
            + (completed.stderr or completed.stdout or "unknown error")[-500:]
        )
    return completed


def _prepare_git_base(repository: Path, requested_revision: str) -> str:
    probe = _git(repository, "rev-parse", "--is-inside-work-tree", check=False)
    if probe.returncode != 0 or probe.stdout.strip() != "true":
        raise invalid("Platform workflow evaluation 需要 Git fixture")
    resolved = _git(repository, "rev-parse", f"{requested_revision}^{{commit}}", check=False)
    if resolved.returncode != 0:
        resolved = _git(repository, "rev-parse", "HEAD")
    commit = resolved.stdout.strip()
    _git(repository, "reset", "--hard", commit)
    _git(repository, "clean", "-fd")
    return commit


def _stage(stage_type: str, artifact_ref: str | None = None) -> StageRun:
    now = utc_now()
    return StageRun(
        stage_id=f"stage-{stage_type}",
        stage_type=stage_type,
        status="Passed",
        artifact_refs=[artifact_ref] if artifact_ref else [],
        started_at=now,
        finished_at=now,
    )


def _planned_change_set(plan: Mapping[str, Any]) -> dict[str, Any]:
    metadata = dict(plan.get("changeSet") or {})
    changes = []
    for proposal in plan.get("proposals", []):
        if not isinstance(proposal, Mapping):
            continue
        target = proposal.get("targetCurrentEntityId")
        changes.append(
            {
                "changeId": proposal.get("proposalId"),
                "targetEntityId": target,
                "desiredEntityId": proposal.get("desiredEntityId"),
                "operation": "Add" if target is None else "Modify",
                "aspect": proposal.get("changeType"),
                "role": proposal.get("role"),
                "evidenceRefs": proposal.get("evidenceRefs", []),
                "derivedByRule": proposal.get("derivedByRule"),
            }
        )
    result = {
        "changeSetId": plan.get("planId"),
        **metadata,
        "changes": changes,
    }
    result["changeSetHash"] = content_hash(result)
    return result


def _planning_impact(
    plan: Mapping[str, Any],
    current_nodes: list[dict[str, Any]],
    current_edges: list[dict[str, Any]],
) -> dict[str, Any]:
    current_ids = {item["id"] for item in current_nodes}
    modified = sorted(
        {
            str(item.get("targetCurrentEntityId"))
            for item in plan.get("proposals", [])
            if item.get("targetCurrentEntityId") in current_ids
        }
    )
    synthetic_change_set = {
        "changeSetId": f"planned:{plan.get('planId')}",
        "actualRevision": plan.get("changeSet", {}).get("currentRevision"),
        "graphDelta": {
            "addedEntityIds": [],
            "removedEntityIds": [],
            "modifiedEntityIds": modified,
            "addedEdges": [],
            "removedEdges": [],
        },
    }
    impact = build_actual_impact_graph(
        actual_change_set=synthetic_change_set,
        actual_nodes=current_nodes,
        actual_edges=current_edges,
        requirement_id=str(plan.get("changeSet", {}).get("requirementId") or "planning"),
    )
    impact["planningChangePlanId"] = plan.get("planId")
    impact["status"] = "Completed"
    return impact


def _node_requirements(
    plan: Mapping[str, Any],
    impact: Mapping[str, Any],
    current_nodes: list[dict[str, Any]],
) -> dict[str, Any]:
    proposal_by_id = {
        item["proposalId"]: item
        for item in plan.get("proposals", [])
        if isinstance(item, Mapping) and item.get("proposalId")
    }
    requirements: list[dict[str, Any]] = []
    covered_entities: set[str] = set()
    for task in plan.get("implementationTasks", []):
        if not isinstance(task, Mapping):
            continue
        proposal = proposal_by_id.get(task.get("proposalId"), {})
        target = proposal.get("targetCurrentEntityId")
        if isinstance(target, str):
            covered_entities.add(target)
        requirements.append(
            {
                "requirementId": task.get("taskId"),
                "sourceChange": task.get("proposalId"),
                "targetEntityId": target,
                "requirementType": task.get("taskType"),
                "suggestedFiles": task.get("suggestedFiles", []),
                "acceptanceCriteria": task.get("acceptanceCriteria", []),
                "requiredTests": task.get("requiredTests", []),
                "status": "Required",
            }
        )

    synthetic_change_set = {
        "changeSetId": f"planned:{plan.get('planId')}",
        "changes": [{"entityId": item} for item in sorted(covered_entities)],
    }
    obligations = build_impact_obligations(
        impact,
        current_nodes,
        synthetic_change_set,
        test_report={"status": "NotRun"},
    )
    for obligation in obligations["obligations"]:
        entity_id = obligation.get("entityId")
        if entity_id in covered_entities or obligation.get("impactState") == "Direct":
            continue
        requirements.append(
            {
                "requirementId": f"planned:{obligation['obligationId']}",
                "sourceImpact": obligation["obligationId"],
                "targetEntityId": entity_id,
                "requirementType": obligation["obligationType"],
                "path": obligation.get("path", []),
                "status": "Required",
            }
        )
    return {
        "planId": plan.get("planId"),
        "requirements": sorted(
            requirements, key=lambda item: str(item.get("requirementId") or "")
        ),
    }


class PlanningWorkflowBackend:
    def __init__(self, *, rules_path: str | Path | None = None) -> None:
        self.rules_path = Path(rules_path) if rules_path else _project_rules_path()

    def execute(
        self,
        scenario: EvaluationScenario,
        config: ExecutionConfig,
    ) -> BackendResult:
        if scenario.workflow not in {"planning", "paired"}:
            raise invalid("PlanningWorkflowBackend 只支持 planning / paired")
        temporary = tempfile.TemporaryDirectory(prefix="code-ontology-eval-plan-")
        workspace = Path(temporary.name).resolve()
        try:
            repository = _copy_fixture_repository(scenario, workspace)
            base_commit = _prepare_git_base(repository, scenario.fixture.revision)
            rules_path = Path(config.rule_set_path) if config.rule_set_path else self.rules_path
            service = PlatformService(
                SQLiteStore(workspace / "evaluation.db"),
                rules_path,
                repository_roots=[workspace],
                worktree_root=workspace / "agent-worktrees",
            )
            repository_id = str(
                scenario.input.get("repositoryId") or f"eval-{scenario.fixture.fixture_id}"
            )
            service.register_repository(
                {
                    "path": str(repository),
                    "repositoryId": repository_id,
                    "name": repository.name,
                }
            )
            service.scan_repository(
                repository_id, {"includeGraph": True, "actor": "evaluation"}
            )
            revisions = service.repository_graph_revisions(repository_id)["revisions"]
            if not revisions:
                raise invalid("Evaluation scan 未生成 Current Graph")
            current_revision = revisions[0]["revision"]
            current_nodes, current_edges = service.store.read_graph(
                "current", current_revision
            )

            design_content = scenario.input.get("designContent")
            if design_content is None:
                design_path = _resolve_scenario_path(
                    scenario, scenario.input.get("designDocument")
                )
                design_content = design_path.read_text(encoding="utf-8")
            if not isinstance(design_content, str) or not design_content.strip():
                raise invalid("Planning Scenario 需要 designDocument 或 designContent")
            requirement_id = str(
                scenario.input.get("requirementId") or scenario.scenario_id
            )
            document = service.create_design_document(
                {
                    "title": scenario.input.get("designTitle")
                    or scenario.scenario_id,
                    "owner": "evaluation",
                }
            )
            revision = service.create_design_revision(
                document["documentId"],
                {"content": design_content, "actor": "evaluation"},
            )
            requirement = service.extract_design_revision(
                revision["revisionId"],
                {"requirementId": requirement_id, "actor": "evaluation"},
            )
            artifacts: dict[str, Any] = {"designIntent": requirement["ir"]}
            stages = [_stage("designIntent", f"requirement:{requirement_id}")]

            review = service.review_requirement(
                requirement_id,
                {
                    "decision": "Confirm",
                    "actor": "evaluation",
                    "rationale": "evaluation gate",
                    "acceptUnresolved": bool(
                        scenario.input.get("acceptUnresolved", False)
                    ),
                },
            )
            if review["requirement"]["status"] != "Confirmed":
                return BackendResult(
                    artifacts=artifacts,
                    decision="NeedsReview",
                    stages=stages,
                    metadata={
                        "backend": "platform-planning",
                        "workspace": str(workspace),
                    },
                )

            alignment_draft = service.create_alignment_run(
                {
                    "requirementId": requirement_id,
                    "currentRevision": current_revision,
                    "repositoryId": repository_id,
                    "actor": "evaluation",
                }
            )
            selections = scenario.input.get("alignmentSelections")
            auto_top = scenario.input.get("autoConfirmTopCandidate") is True
            if not isinstance(selections, Mapping) and not auto_top:
                artifacts["alignment"] = alignment_draft
                stages.append(_stage("alignment", alignment_draft["runId"]))
                return BackendResult(
                    artifacts=artifacts,
                    decision="NeedsReview",
                    stages=stages,
                    metadata={
                        "backend": "platform-planning",
                        "workspace": str(workspace),
                    },
                )
            for item in alignment_draft["alignments"]:
                desired_id = item["desiredEntity"]["entityId"]
                selected = None
                requested = (
                    selections.get(desired_id)
                    if isinstance(selections, Mapping)
                    else None
                )
                if requested is not None:
                    selected = next(
                        (
                            candidate
                            for candidate in item["candidates"]
                            if candidate["candidateId"] == requested
                            or candidate.get("currentEntityId") == requested
                        ),
                        None,
                    )
                    if selected is None:
                        raise invalid(
                            "alignmentSelections 未匹配 Candidate",
                            {
                                "desiredEntityId": desired_id,
                                "selection": requested,
                            },
                        )
                elif auto_top and item["candidates"]:
                    selected = item["candidates"][0]
                if selected is None:
                    artifacts["alignment"] = alignment_draft
                    stages.append(_stage("alignment", alignment_draft["runId"]))
                    return BackendResult(
                        artifacts=artifacts,
                        decision="NeedsReview",
                        stages=stages,
                        metadata={
                            "backend": "platform-planning",
                            "workspace": str(workspace),
                        },
                    )
                service.review_alignment(
                    selected["candidateId"],
                    {
                        "decision": "Confirm",
                        "actor": "evaluation",
                        "rationale": "evaluation selection",
                    },
                )
            alignment = service.get_alignment_run(alignment_draft["runId"])
            artifacts["alignment"] = alignment
            stages.append(_stage("alignment", alignment["runId"]))

            plan = service.create_change_plan(
                {
                    "alignmentRunId": alignment["runId"],
                    "actor": "evaluation",
                    "context": {"repositoryId": repository_id},
                }
            )
            artifacts["changeSet"] = _planned_change_set(plan)
            stages.append(_stage("changeSet", plan["planId"]))
            planned_impact = _planning_impact(plan, current_nodes, current_edges)
            artifacts["plannedImpactGraph"] = planned_impact
            stages.append(_stage("plannedImpactGraph", planned_impact["runId"]))
            artifacts["nodeRequirements"] = _node_requirements(
                plan, planned_impact, current_nodes
            )
            stages.append(_stage("nodeRequirements", plan["planId"]))

            decision = "NeedsReview"
            plan_review = {
                "planId": plan["planId"],
                "completeness": "Partial",
                "blockingIssues": list(plan.get("unresolvedQuestions", [])),
                "decision": decision,
            }
            if (
                scenario.input.get("autoAcceptArchitecture") is True
                and not plan.get("unresolvedQuestions")
            ):
                plan = service.review_change_plan(
                    plan["planId"],
                    {
                        "decision": "Accept",
                        "actor": "evaluation",
                        "rationale": "evaluation architecture gate",
                        "findings": [],
                    },
                )
                decision = "ReadyForImplementation"
                plan_review = {
                    "planId": plan["planId"],
                    "completeness": "Complete",
                    "blockingIssues": [],
                    "architectureReview": plan.get("architectureReview"),
                    "decision": decision,
                }
            artifacts["changePlanReview"] = plan_review
            stages.append(_stage("changePlanReview", plan["planId"]))
            return BackendResult(
                artifacts=artifacts,
                decision=decision,
                stages=stages,
                metadata={
                    "backend": "platform-planning",
                    "workspace": str(workspace),
                    "baseCommit": base_commit,
                    "currentRevision": current_revision,
                    "changePlan": copy.deepcopy(plan),
                },
            )
        finally:
            temporary.cleanup()


class PreCommitWorkflowBackend:
    def __init__(self, loader: EvaluationLoader | None = None) -> None:
        self.loader = loader or EvaluationLoader()

    def _load_input_document(
        self, scenario: EvaluationScenario, value: Any
    ) -> dict[str, Any]:
        if isinstance(value, Mapping):
            return dict(value)
        path = _resolve_scenario_path(scenario, value)
        document = self.loader.load_artifact(path)
        if not isinstance(document, Mapping):
            raise invalid("PreCommit 输入文档必须是 object")
        return dict(document)

    def _planned_plan(self, scenario: EvaluationScenario) -> dict[str, Any] | None:
        planned = scenario.planned_artifacts or {}
        value = planned.get("changePlan")
        if value is None:
            return None
        if isinstance(value, Mapping) and "path" in value:
            value = value["path"]
        return self._load_input_document(scenario, value)

    def _simple_planned(
        self, scenario: EvaluationScenario
    ) -> dict[str, Any] | None:
        planned = scenario.planned_artifacts or {}
        for key in ("nodeRequirements", "changeSet"):
            value = planned.get(key)
            if value is None:
                continue
            if isinstance(value, Mapping) and "path" in value:
                value = value["path"]
            return self._load_input_document(scenario, value)
        return None

    def execute_with_plan(
        self,
        scenario: EvaluationScenario,
        config: ExecutionConfig,
        planned_plan: dict[str, Any] | None,
    ) -> BackendResult:
        temporary = tempfile.TemporaryDirectory(prefix="code-ontology-eval-precommit-")
        workspace = Path(temporary.name).resolve()
        try:
            repository = _copy_fixture_repository(scenario, workspace)
            base_commit = _prepare_git_base(repository, scenario.fixture.revision)
            base_scan = RepositoryScanner().scan(
                repository, f"eval-{scenario.fixture.fixture_id}"
            )
            current_graph = base_scan["graph"]

            patch_value = scenario.input.get("workingTreePatch")
            if patch_value is not None:
                patch_path = _resolve_scenario_path(scenario, patch_value)
                completed = subprocess.run(
                    [
                        "git",
                        "-C",
                        str(repository),
                        "apply",
                        "--whitespace=nowarn",
                        str(patch_path),
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=60,
                )
                if completed.returncode != 0:
                    raise conflict(
                        "无法应用 Evaluation workingTreePatch: "
                        + completed.stderr[-500:]
                    )

            diff = collect_worktree_diff(repository, base_commit)
            git_snapshot = build_git_diff_snapshot(diff)
            actual_scan = RepositoryScanner().scan(
                repository, f"eval-{scenario.fixture.fixture_id}"
            )
            actual_graph = actual_scan["graph"]
            overlay = build_worktree_graph_overlay(
                base_revision=current_graph["revision"],
                actual_revision=actual_graph["revision"],
                current_nodes=current_graph["nodes"],
                current_edges=current_graph["edges"],
                actual_nodes=actual_graph["nodes"],
                actual_edges=actual_graph["edges"],
                working_tree_hash=git_snapshot["snapshotHash"],
            )
            actual_change_set = build_actual_change_set(
                base_revision=current_graph["revision"],
                actual_revision=actual_graph["revision"],
                graph_overlay=overlay,
                working_tree_hash=git_snapshot["snapshotHash"],
            )
            impact = build_actual_impact_graph(
                actual_change_set=actual_change_set,
                actual_nodes=actual_graph["nodes"],
                actual_edges=actual_graph["edges"],
                requirement_id=str(
                    (planned_plan or {}).get("changeSet", {}).get("requirementId")
                    or scenario.input.get("requirementId")
                    or scenario.scenario_id
                ),
            )
            test_report_value = scenario.input.get("testReport")
            test_report = (
                self._load_input_document(scenario, test_report_value)
                if test_report_value is not None
                else {"status": "NotRun", "executions": []}
            )
            obligations = build_impact_obligations(
                impact,
                actual_graph["nodes"],
                actual_change_set,
                test_report=test_report,
            )

            plan = planned_plan or self._planned_plan(scenario)
            if plan is not None and isinstance(plan.get("proposals"), list):
                normalized_plan = copy.deepcopy(plan)
                normalized_plan.setdefault(
                    "planId", f"eval-plan:{scenario.scenario_id}"
                )
                normalized_plan.setdefault("implementationTasks", [])
                normalized_plan.setdefault("verificationObligations", [])
                normalized_plan.setdefault("changeSet", {})
                normalized_plan["changeSet"].setdefault(
                    "currentRevision", current_graph["revision"]
                )
                normalized_plan["changeSet"].setdefault(
                    "requirementId",
                    str(
                        scenario.input.get("requirementId")
                        or scenario.scenario_id
                    ),
                )
                agent_run = {
                    "runId": f"eval-agent:{scenario.scenario_id}",
                    "requirementId": normalized_plan["changeSet"]["requirementId"],
                    "repositoryId": f"eval-{scenario.fixture.fixture_id}",
                    "status": "Completed",
                    "testReport": test_report,
                }
                reconciliation = reconcile_approved_actual(
                    reconciliation_run_id=f"eval-reconciliation:{scenario.scenario_id}",
                    agent_run=agent_run,
                    plan=normalized_plan,
                    current_nodes=current_graph["nodes"],
                    current_edges=current_graph["edges"],
                    actual_nodes=actual_graph["nodes"],
                    actual_edges=actual_graph["edges"],
                    actual_revision=actual_graph["revision"],
                    coverage=actual_scan["coverage"],
                )
            else:
                reconciliation = build_simple_reconciliation(
                    planned_artifact=self._simple_planned(scenario),
                    actual_change_set=actual_change_set,
                    impact_obligations=obligations,
                )

            coverage = build_verification_coverage(
                impact_obligations=obligations,
                test_report=test_report,
            )
            review = build_precommit_review(
                working_tree_hash=git_snapshot["snapshotHash"],
                reconciliation=reconciliation,
                verification_coverage=coverage,
                impact_obligations=obligations,
            )
            artifacts = {
                "gitDiffSnapshot": git_snapshot,
                "workingTreeGraphOverlay": overlay,
                "actualChangeSet": actual_change_set,
                "actualImpactGraph": impact,
                "impactObligations": obligations,
                "reconciliation": reconciliation,
                "verificationCoverage": coverage,
                "preCommitReview": review,
            }
            stages = [
                _stage(
                    name,
                    str(
                        artifacts[name].get("runId")
                        or artifacts[name].get("changeSetId")
                        or name
                    ),
                )
                for name in (
                    "gitDiffSnapshot",
                    "workingTreeGraphOverlay",
                    "actualChangeSet",
                    "actualImpactGraph",
                    "impactObligations",
                    "reconciliation",
                    "verificationCoverage",
                    "preCommitReview",
                )
            ]
            return BackendResult(
                artifacts=artifacts,
                decision=review["decision"],
                stages=stages,
                metadata={
                    "backend": "platform-precommit",
                    "workspace": str(workspace),
                    "baseCommit": base_commit,
                    "workingTreeHash": git_snapshot["snapshotHash"],
                },
            )
        finally:
            temporary.cleanup()

    def execute(
        self, scenario: EvaluationScenario, config: ExecutionConfig
    ) -> BackendResult:
        if scenario.workflow not in {"precommit", "paired"}:
            raise invalid("PreCommitWorkflowBackend 只支持 precommit / paired")
        return self.execute_with_plan(
            scenario, config, self._planned_plan(scenario)
        )


class PairedWorkflowBackend:
    def __init__(
        self,
        planning: PlanningWorkflowBackend | None = None,
        precommit: PreCommitWorkflowBackend | None = None,
    ) -> None:
        self.planning = planning or PlanningWorkflowBackend()
        self.precommit = precommit or PreCommitWorkflowBackend()

    def execute(
        self, scenario: EvaluationScenario, config: ExecutionConfig
    ) -> BackendResult:
        planning_result = self.planning.execute(scenario, config)
        plan = planning_result.metadata.get("changePlan")
        if not isinstance(plan, dict):
            return planning_result
        precommit_result = self.precommit.execute_with_plan(
            scenario, config, plan
        )
        return BackendResult(
            artifacts={**planning_result.artifacts, **precommit_result.artifacts},
            decision=precommit_result.decision,
            stages=[*planning_result.stages, *precommit_result.stages],
            metadata={
                "backend": "platform-paired",
                "planning": planning_result.metadata,
                "precommit": precommit_result.metadata,
            },
        )


class PlatformWorkflowBackend:
    def __init__(
        self,
        *,
        rules_path: str | Path | None = None,
        loader: EvaluationLoader | None = None,
    ) -> None:
        self.planning = PlanningWorkflowBackend(rules_path=rules_path)
        self.precommit = PreCommitWorkflowBackend(loader=loader)
        self.paired = PairedWorkflowBackend(self.planning, self.precommit)

    def execute(
        self, scenario: EvaluationScenario, config: ExecutionConfig
    ) -> BackendResult:
        if scenario.workflow == "planning":
            return self.planning.execute(scenario, config)
        if scenario.workflow == "precommit":
            return self.precommit.execute(scenario, config)
        if scenario.workflow == "paired":
            return self.paired.execute(scenario, config)
        raise invalid(
            "Unsupported evaluation workflow", {"workflow": scenario.workflow}
        )
