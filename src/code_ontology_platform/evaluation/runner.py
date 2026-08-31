from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from ..errors import invalid
from .graph_judge import GraphJudge
from .judges import ArtifactJudge, GateJudge
from .lineage import diagnose_first_failure
from .loader import EvaluationLoader
from .metrics import aggregate_metrics, aggregate_runs
from .models import (
    EvaluationScenario,
    ExecutionConfig,
    JudgeResult,
    StageRun,
    WorkflowRun,
    content_hash,
)
from .mutations import MutationRegistry


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class BackendResult:
    artifacts: dict[str, Any]
    decision: str | None
    stages: list[StageRun] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class WorkflowBackend(Protocol):
    def execute(
        self,
        scenario: EvaluationScenario,
        config: ExecutionConfig,
    ) -> BackendResult:
        ...


class FileArtifactBackend:
    """Deterministic backend for stage/regression evaluation.

    The scenario points to already produced actual artifacts. Optional artifact
    mutations are applied after loading so downstream judges/gates can be
    regression-tested without executing the full workflow.
    """

    def __init__(self, loader: EvaluationLoader | None = None) -> None:
        self.loader = loader or EvaluationLoader()
        self.mutations = MutationRegistry()

    def execute(
        self,
        scenario: EvaluationScenario,
        config: ExecutionConfig,
    ) -> BackendResult:
        actual_refs = scenario.input.get("actualArtifacts")
        if not isinstance(actual_refs, dict) or not actual_refs:
            raise invalid(
                "FileArtifactBackend 需要 input.actualArtifacts",
                {"scenarioId": scenario.scenario_id},
            )
        base = (
            Path(scenario.source_path).parent
            if scenario.source_path is not None
            else Path.cwd()
        )
        artifacts: dict[str, Any] = {}
        stages: list[StageRun] = []
        for artifact_type, ref in actual_refs.items():
            if not isinstance(ref, str) or not ref.strip():
                raise invalid(f"actualArtifacts.{artifact_type} 必须是路径")
            path = Path(ref)
            if not path.is_absolute():
                path = base / path
            path = path.resolve()
            if not path.is_file():
                raise invalid(
                    "Actual Artifact 不存在",
                    {"artifactType": artifact_type, "path": str(path)},
                )
            artifacts[str(artifact_type)] = self.loader.load_artifact(path)
            stages.append(
                StageRun(
                    stage_id=f"stage-{artifact_type}",
                    stage_type=str(artifact_type),
                    status="Passed",
                    artifact_refs=[str(path)],
                )
            )

        mutation_metadata = None
        if scenario.mutation is not None:
            if scenario.mutation.path is None:
                raise invalid("FileArtifactBackend 的 mutation 必须提供 path")
            mutation = self.mutations.load(scenario.mutation.path)
            if mutation.mutation_id != scenario.mutation.mutation_id:
                raise invalid(
                    "Scenario mutation.id 与 Mutation 文件不一致",
                    {
                        "scenarioMutationId": scenario.mutation.mutation_id,
                        "fileMutationId": mutation.mutation_id,
                    },
                )
            if mutation.kind != "artifact":
                raise invalid("FileArtifactBackend 只允许 artifact mutation")
            artifact_type = mutation.target.get("artifactType")
            if artifact_type is None:
                if len(artifacts) != 1:
                    raise invalid(
                        "Artifact Mutation 必须指定 target.artifactType",
                        {"availableArtifacts": sorted(artifacts)},
                    )
                artifact_type = next(iter(artifacts))
            if not isinstance(artifact_type, str) or artifact_type not in artifacts:
                raise invalid(
                    "Artifact Mutation target.artifactType 不存在",
                    {"artifactType": artifact_type},
                )
            result = self.mutations.apply_artifact(
                mutation, artifacts[artifact_type]
            )
            artifacts[artifact_type] = result.details["artifact"]
            mutation_metadata = {
                "mutationId": result.mutation_id,
                "kind": mutation.kind,
                "operation": mutation.operation,
                "artifactType": artifact_type,
                "changed": result.changed,
            }

        decision = scenario.input.get("actualDecision")
        if decision is not None and not isinstance(decision, str):
            raise invalid("input.actualDecision 必须是字符串")
        return BackendResult(
            artifacts=artifacts,
            decision=decision,
            stages=stages,
            metadata={
                "backend": "file-artifact",
                "mutation": mutation_metadata,
            },
        )


_STAGE_BY_ARTIFACT = {
    "designIntent": "designIntent",
    "alignment": "alignment",
    "changeSet": "changeSet",
    "plannedImpactGraph": "plannedImpactGraph",
    "nodeRequirements": "nodeRequirements",
    "changePlanReview": "changePlanReview",
    "gitDiffSnapshot": "gitDiffSnapshot",
    "workingTreeGraphOverlay": "workingTreeGraphOverlay",
    "actualChangeSet": "actualChangeSet",
    "actualImpactGraph": "actualImpactGraph",
    "impactObligations": "impactObligations",
    "reconciliation": "reconciliation",
    "verificationCoverage": "verificationCoverage",
    "preCommitReview": "preCommitReview",
}


class BatchEvaluationRunner:
    def __init__(
        self,
        backend: WorkflowBackend,
        loader: EvaluationLoader | None = None,
    ) -> None:
        self.backend = backend
        self.loader = loader or EvaluationLoader()
        self.artifact_judge = ArtifactJudge()
        self.graph_judge = GraphJudge()
        self.gate_judge = GateJudge()

    def run_scenario(
        self,
        scenario: EvaluationScenario,
        config: ExecutionConfig | None = None,
    ) -> WorkflowRun:
        config = config or ExecutionConfig()
        run = WorkflowRun(
            run_id=f"eval-{uuid.uuid4()}",
            scenario_id=scenario.scenario_id,
            execution_config_id=config.config_id,
            started_at=utc_now(),
            status="Running",
            input_hash=content_hash(
                {
                    "scenario": scenario.scenario_id,
                    "workflow": scenario.workflow,
                    "input": scenario.input,
                    "fixture": scenario.fixture.fixture_id,
                    "revision": scenario.fixture.revision,
                    "mutation": (
                        scenario.mutation.mutation_id
                        if scenario.mutation is not None
                        else None
                    ),
                }
            ),
            expected_decision=scenario.expected_decision,
            manifest={
                "executionConfig": config.manifest(),
                "scenarioSource": scenario.source_path,
                "mutation": (
                    {
                        "mutationId": scenario.mutation.mutation_id,
                        "path": scenario.mutation.path,
                    }
                    if scenario.mutation is not None
                    else None
                ),
            },
        )
        try:
            backend_result = self.backend.execute(scenario, config)
            run.stages.extend(backend_result.stages)
            run.final_decision = backend_result.decision
            run.manifest["backend"] = backend_result.metadata

            results: list[JudgeResult] = []
            for artifact_type, expected_ref in scenario.expected.items():
                expected = self.loader.load_artifact(expected_ref.path)
                if artifact_type not in backend_result.artifacts:
                    results.append(
                        JudgeResult(
                            judge="ArtifactPresenceJudge",
                            artifact_type=artifact_type,
                            status="Failed",
                            score=0.0,
                            missing=[artifact_type],
                            details={"reason": "actual artifact missing"},
                            stage=_STAGE_BY_ARTIFACT.get(artifact_type, artifact_type),
                        )
                    )
                    continue
                actual = backend_result.artifacts[artifact_type]
                stage = _STAGE_BY_ARTIFACT.get(artifact_type, artifact_type)
                if expected_ref.compare_mode == "graph":
                    result = self.graph_judge.judge(
                        artifact_type,
                        expected,
                        actual,
                        stage=stage,
                    )
                else:
                    result = self.artifact_judge.judge(
                        artifact_type,
                        expected,
                        actual,
                        expected_ref.compare_mode,
                        stage=stage,
                    )
                results.append(result)

            results.append(
                self.gate_judge.judge(
                    scenario.expected_decision,
                    backend_result.decision,
                )
            )
            run.judge_results = results
            run.metrics = aggregate_metrics(results)
            run.diagnosis = diagnose_first_failure(scenario.workflow, results)
            run.status = (
                "Passed"
                if all(result.status in {"Passed", "Skipped"} for result in results)
                else "Failed"
            )
        except Exception as error:
            run.status = "Error"
            run.diagnosis = diagnose_first_failure(
                scenario.workflow,
                [
                    JudgeResult(
                        judge="Runner",
                        artifact_type="WorkflowRun",
                        status="Failed",
                        score=0.0,
                        details={"errorType": type(error).__name__, "message": str(error)},
                        stage="runner",
                    )
                ],
            )
            run.manifest["error"] = {
                "type": type(error).__name__,
                "message": str(error),
            }
        finally:
            run.finished_at = utc_now()
        return run

    def run_many(
        self,
        scenarios: list[EvaluationScenario],
        config: ExecutionConfig | None = None,
    ) -> dict[str, Any]:
        runs = [self.run_scenario(scenario, config) for scenario in scenarios]
        return {
            "schemaVersion": "evaluation-run-set/v1",
            "executionConfig": (config or ExecutionConfig()).manifest(),
            "runs": [run.to_dict() for run in runs],
            "summary": {
                "count": len(runs),
                "passed": sum(run.status == "Passed" for run in runs),
                "failed": sum(run.status == "Failed" for run in runs),
                "errors": sum(run.status == "Error" for run in runs),
                "metrics": aggregate_runs(run.metrics for run in runs),
            },
        }


def write_run_set(document: dict[str, Any], output: str | Path) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path
