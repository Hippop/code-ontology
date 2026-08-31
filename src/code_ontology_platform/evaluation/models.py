from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any

from ..errors import invalid

WORKFLOWS = frozenset({"planning", "precommit", "paired"})
FIXTURE_LEVELS = frozenset({"micro", "feature", "architecture", "real"})
ORACLE_TYPES = frozenset({"deterministic", "rule-derived", "human-reviewed"})
COMPARE_MODES = frozenset({"exact", "set", "ordered-set", "graph", "semantic", "constraint"})
RUN_STATUSES = frozenset({"Pending", "Running", "Passed", "Failed", "Error", "Skipped"})
JUDGE_STATUSES = frozenset({"Passed", "Failed", "Skipped"})
DECISIONS = frozenset(
    {
        "ReadyForImplementation",
        "NeedsReview",
        "BlockImplementation",
        "ReadyToCommit",
        "BlockCommit",
    }
)


def _enum(value: Any, name: str, allowed: frozenset[str]) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise invalid(
            f"{name} 不受支持",
            {"allowed": sorted(allowed), "actual": value},
        )
    return value


def canonical_json(value: Any) -> str:
    if is_dataclass(value):
        value = asdict(value)
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def content_hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RepositoryFixtureRef:
    fixture_id: str
    source_path: str
    revision: str
    graph_baseline: str | None = None
    fixture_level: str = "micro"

    def __post_init__(self) -> None:
        if not self.fixture_id:
            raise invalid("fixture.id 不能为空")
        if not self.source_path:
            raise invalid("fixture.path 不能为空")
        if not self.revision:
            raise invalid("fixture.revision 不能为空")
        _enum(self.fixture_level, "fixture.level", FIXTURE_LEVELS)


@dataclass(frozen=True)
class ExpectedArtifactRef:
    artifact_type: str
    path: str
    oracle_type: str = "deterministic"
    compare_mode: str = "exact"

    def __post_init__(self) -> None:
        if not self.artifact_type:
            raise invalid("expected.artifactType 不能为空")
        if not self.path:
            raise invalid("expected.path 不能为空")
        _enum(self.oracle_type, "expected.oracle", ORACLE_TYPES)
        _enum(self.compare_mode, "expected.compare", COMPARE_MODES)


@dataclass(frozen=True)
class MutationRef:
    mutation_id: str
    path: str | None = None

    def __post_init__(self) -> None:
        if not self.mutation_id:
            raise invalid("mutation.id 不能为空")


@dataclass(frozen=True)
class EvaluationScenario:
    scenario_id: str
    workflow: str
    fixture: RepositoryFixtureRef
    input: dict[str, Any]
    expected: dict[str, ExpectedArtifactRef]
    expected_decision: str
    planned_artifacts: dict[str, Any] | None = None
    mutation: MutationRef | None = None
    tags: tuple[str, ...] = ()
    oracle: dict[str, str] = field(default_factory=dict)
    schema_version: str = "evaluation-scenario/v1"
    source_path: str | None = None

    def __post_init__(self) -> None:
        if self.schema_version != "evaluation-scenario/v1":
            raise invalid(
                "scenario.schemaVersion 不受支持",
                {"actual": self.schema_version},
            )
        if not self.scenario_id:
            raise invalid("scenarioId 不能为空")
        _enum(self.workflow, "workflow", WORKFLOWS)
        _enum(self.expected_decision, "expectedDecision", DECISIONS)
        if not self.expected:
            raise invalid("expected 至少包含一个 Artifact")
        if self.workflow == "planning" and "workingTreePatch" in self.input:
            raise invalid("Planning Scenario 不允许 workingTreePatch")
        if self.workflow == "precommit" and not any(
            key in self.input for key in ("workingTreePatch", "actualArtifacts")
        ):
            raise invalid("PreCommit Scenario 必须提供 workingTreePatch 或 actualArtifacts")


@dataclass(frozen=True)
class ExecutionConfig:
    config_id: str = "default"
    agent_versions: dict[str, str] = field(default_factory=dict)
    skill_versions: dict[str, str] = field(default_factory=dict)
    subagent_versions: dict[str, str] = field(default_factory=dict)
    rule_set_path: str | None = None
    rule_set_hash: str | None = None
    model: str | None = None
    mcp_version: str | None = None
    semantic_judge: bool = False
    environment: dict[str, str] = field(default_factory=dict)

    def manifest(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StageRun:
    stage_id: str
    stage_type: str
    status: str = "Pending"
    input_refs: list[str] = field(default_factory=list)
    artifact_refs: list[str] = field(default_factory=list)
    started_at: str | None = None
    finished_at: str | None = None
    tool_calls: int = 0
    token_usage: dict[str, int] = field(default_factory=dict)
    error: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        _enum(self.status, "stage.status", RUN_STATUSES)


@dataclass
class JudgeResult:
    judge: str
    artifact_type: str
    status: str
    score: float
    metrics: dict[str, float] = field(default_factory=dict)
    missing: list[Any] = field(default_factory=list)
    extra: list[Any] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    stage: str | None = None

    def __post_init__(self) -> None:
        _enum(self.status, "judge.status", JUDGE_STATUSES)
        if not 0 <= self.score <= 1:
            raise invalid("judge.score 必须位于 0 到 1")


@dataclass
class FailureDiagnosis:
    first_failed_stage: str | None
    failed_artifact: str | None
    summary: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowRun:
    run_id: str
    scenario_id: str
    execution_config_id: str
    started_at: str
    finished_at: str | None = None
    status: str = "Running"
    workspace: str | None = None
    input_hash: str | None = None
    stages: list[StageRun] = field(default_factory=list)
    judge_results: list[JudgeResult] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)
    final_decision: str | None = None
    expected_decision: str | None = None
    diagnosis: FailureDiagnosis | None = None
    manifest: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _enum(self.status, "run.status", RUN_STATUSES)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
