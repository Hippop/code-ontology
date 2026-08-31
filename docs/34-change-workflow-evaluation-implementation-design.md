# 代码变更工作流批量评测框架实现设计

## 1. 文档目标

本文给出 `33-change-workflow-batch-evaluation-framework.md` 的第一版实现设计，重点回答：

1. 在现有 `code-ontology-platform` Python 代码结构中新增哪些模块；
2. Scenario、Mutation、Golden、Run、Judge、Metric 等核心对象如何定义；
3. Planning、PreCommit、Paired E2E 三种 Runner 如何调用现有平台能力；
4. 如何保证评测结果可重复、可定位、可比较；
5. 第一版如何用最少新增基础设施形成可运行的批量回归框架。

实现优先复用仓库现有能力：Python 3.11、PyYAML、SQLiteStore、PlatformService、现有 Graph / Workflow / Agent Runtime、语义验证和 CLI。第一版不引入新的数据库、任务队列或独立 Web 服务。

## 2. 实现边界

第一版 Evaluation Harness 是现有平台的外部测试编排层，不改变 Planning Workflow 与 PreCommit Workflow 的业务语义。

```text
Evaluation Harness
      │
      ├── 准备 Fixture / Scenario / Mutation
      ├── 创建隔离工作目录
      ├── 调用现有 Workflow / Service / CLI 能力
      ├── 收集中间 Artifact
      ├── 与 Expected Artifact 比较
      └── 生成 Metric / Diagnosis / Comparison
```

明确禁止：

- Judge 修改被测试 Workflow 的结果；
- Evaluation Runner 自动修正失败 Artifact；
- Semantic Judge 替代确定性 Schema / Graph Judge；
- Golden 使用当前被测试 Agent 运行时动态生成；
- Paired E2E 直接在开发者真实 Worktree 上执行 Fault Mutation；
- Evaluation 结果写入正式 Current / Desired / Actual / Impact 图空间。

## 3. 与现有仓库结构的集成

当前包采用 `src/code_ontology_platform/`，CLI 通过 `argparse` 暴露命令，数据和 Artifact 主要使用 Python dict / JSON 结构并由现有 validation helper 校验。

第一版建议新增：

```text
src/code_ontology_platform/evaluation/
  __init__.py
  models.py
  loader.py
  fixtures.py
  mutations.py
  runner.py
  planning_runner.py
  precommit_runner.py
  paired_runner.py
  artifact_collector.py
  judges.py
  graph_judge.py
  semantic_judge.py
  lineage.py
  metrics.py
  reports.py
  comparison.py

scripts/
  generate_evaluation_scenarios.py

evaluation/
  scenarios/
  scenario-families/
  fixtures/
  mutations/
  goldens/
  configs/
  reports/

tests/
  test_evaluation_models.py
  test_evaluation_loader.py
  test_evaluation_mutations.py
  test_evaluation_judges.py
  test_evaluation_metrics.py
  test_evaluation_runner.py
```

第一版不拆独立 Python package，直接作为 `code_ontology_platform.evaluation` 子模块，便于复用 `PlatformService`、`SQLiteStore`、图模型和错误模型。

## 4. 顶层执行入口

CLI 增加：

```text
code-ontology-platform eval validate <scenario-or-directory>
code-ontology-platform eval run <scenario-or-directory>
code-ontology-platform eval compare <baseline-run> <candidate-run>
code-ontology-platform eval report <run-id-or-json>
```

建议参数：

```text
--mode stage|workflow|paired
--config evaluation/configs/default.yaml
--jobs N
--filter tag-expression
--output evaluation/reports/<run-id>
--fail-on-false-ready
--keep-workspaces
--semantic-judge on|off
```

第一版默认：

```text
jobs = 1
semantic-judge = off
keep-workspaces = false
fail-on-false-ready = true
```

先保证确定性与可诊断性，再增加并发和 LLM Judge。

## 5. 核心数据模型

建议在 `evaluation/models.py` 使用 `dataclasses` + 现有 validation helper，避免第一版增加 Pydantic 依赖。

### 5.1 EvaluationScenario

逻辑结构：

```python
@dataclass(frozen=True)
class EvaluationScenario:
    scenario_id: str
    workflow: str
    fixture: RepositoryFixtureRef
    input: dict[str, Any]
    expected: dict[str, ExpectedArtifactRef]
    expected_decision: str
    planned_artifacts: dict[str, Any] | None
    mutation: MutationRef | None
    tags: tuple[str, ...]
    oracle: dict[str, str]
```

`workflow` 第一版只允许：

```text
planning
precommit
paired
```

### 5.2 RepositoryFixtureRef

```python
@dataclass(frozen=True)
class RepositoryFixtureRef:
    fixture_id: str
    source_path: str
    revision: str
    graph_baseline: str | None
    fixture_level: str
```

`fixture_level`：

```text
micro
feature
architecture
real
```

### 5.3 ExpectedArtifactRef

```python
@dataclass(frozen=True)
class ExpectedArtifactRef:
    artifact_type: str
    path: str
    oracle_type: str
    compare_mode: str
```

`oracle_type`：

```text
deterministic
rule-derived
human-reviewed
```

`compare_mode`：

```text
exact
set
ordered-set
graph
semantic
constraint
```

### 5.4 ExecutionConfig

```python
@dataclass(frozen=True)
class ExecutionConfig:
    config_id: str
    agent_versions: dict[str, str]
    skill_versions: dict[str, str]
    subagent_versions: dict[str, str]
    rule_set_path: str
    rule_set_hash: str
    model: str | None
    mcp_version: str | None
    semantic_judge: bool
    environment: dict[str, str]
```

所有 Version 信息进入 Run Manifest，禁止只保存在日志文本中。

### 5.5 WorkflowRun

```python
@dataclass
class WorkflowRun:
    run_id: str
    scenario_id: str
    execution_config_id: str
    started_at: str
    finished_at: str | None
    status: str
    workspace: str
    input_hash: str
    stages: list[StageRun]
    metrics: dict[str, float]
    final_decision: str | None
```

### 5.6 StageRun

```python
@dataclass
class StageRun:
    stage_id: str
    stage_type: str
    status: str
    input_refs: list[str]
    artifact_refs: list[str]
    started_at: str
    finished_at: str | None
    tool_calls: int
    token_usage: dict[str, int]
    error: dict[str, Any] | None
```

Stage 是 Failure Attribution 的最小定位单元。

## 6. Scenario YAML Schema

第一版 Scenario 文件使用 YAML。

推荐结构：

```yaml
schemaVersion: evaluation-scenario/v1
scenarioId: PRECOMMIT-ADD-PARAM-001
workflow: precommit

tags:
  - micro
  - signature-change
  - negative

fixture:
  id: retry-service
  path: evaluation/fixtures/micro/retry-service
  revision: base-v1
  graphBaseline: expected/base.graph.json
  level: micro

input:
  workingTreePatch: patches/missing-caller.diff

plannedArtifacts:
  changeSet: plan/planned-change-set.json
  nodeRequirements: plan/node-change-requirements.json

expected:
  actualChangeSet:
    path: expected/actual-change-set.json
    oracle: deterministic
    compare: set

  actualImpactGraph:
    path: expected/actual-impact.json
    oracle: rule-derived
    compare: graph

  reconciliation:
    path: expected/reconciliation.json
    oracle: human-reviewed
    compare: set

expectedDecision: BlockCommit

mutation:
  id: missing-caller
```

### 6.1 Scenario Validation

`eval validate` 在执行前必须检查：

- `schemaVersion`；
- Scenario ID 唯一；
- Fixture 路径存在；
- Revision 与 Fixture Manifest 一致；
- 所有 Expected Artifact 文件存在；
- oracle / compare 枚举合法；
- Planning Scenario 不允许 workingTreePatch；
- PreCommit Scenario 必须存在 working tree 输入；
- Paired Scenario 必须同时存在 design input 和 implementation variant；
- Golden 文件不能位于运行输出目录；
- Mutation 与 Scenario Workflow 兼容。

校验失败时 Scenario 不进入执行队列。

## 7. Fixture Manifest

每个 Fixture 目录建议包含：

```text
retry-service/
  fixture.yaml
  repo/
  baselines/
  designs/
  patches/
  expected/
```

`fixture.yaml`：

```yaml
schemaVersion: evaluation-fixture/v1
fixtureId: retry-service
level: micro
language: java
repositoryId: eval-retry-service
baseRevision: base-v1
sourceRoot: repo

graphBaseline:
  current: baselines/current.graph.json

features:
  - calls
  - tests
  - configuration
```

Fixture 在 Evaluation 中必须复制到临时 workspace，不允许直接修改 `evaluation/fixtures/*/repo`。

## 8. Workspace Manager

新增 `fixtures.py` 中的 `EvaluationWorkspaceManager`。

职责：

```text
Scenario
→ 创建 /tmp/code-ontology-eval/<run-id>/<scenario-id>/
→ 复制 Fixture repo
→ 校验 base revision / fixture hash
→ 应用 Patch / Mutation
→ 创建独立 evaluation SQLite DB
→ 返回 WorkspaceContext
```

建议结构：

```text
<workspace>/
  repo/
  data/eval.db
  input/
  artifacts/
  logs/
  report/
```

每个 Scenario 一个独立 DB 和 repo 副本，避免不同 Case 污染。

第一版使用普通目录复制即可；后续规模扩大后再优化为 Git worktree / copy-on-write。

## 9. Mutation DSL 实现

Mutation 分成两类：

```text
Source Mutation
Artifact Mutation
```

### 9.1 Source Mutation

直接修改 Fixture 中的源码或 patch，用于 Paired / PreCommit 场景。

例如：

```yaml
schemaVersion: evaluation-mutation/v1
mutationId: missing-caller
kind: source
operation: DropChange

target:
  file: src/main/java/example/BatchDeployJob.java
  symbol: BatchDeployJob.execute

selector:
  marker: "EVAL:retry-policy-adaptation"

expectedFailure:
  type: MissingPropagationImplementation
```

第一版不要做通用 AST Rewrite DSL。为了保证 Fixture 稳定和 Mutation 可预测，推荐优先使用 fixture 内显式 marker 或预先准备 Patch Variant。

例如：

```java
// EVAL-BEGIN:retry-policy-adaptation
service.deployPolicy(policy, retryPolicy);
// EVAL-END:retry-policy-adaptation
```

Fault Injector 删除这一段即可。

### 9.2 Artifact Mutation

用于 Stage Evaluation，直接修改某一级输入 Artifact，例如删除 Impact Edge、改变 alignment status、删除 test obligation。

```yaml
mutationId: drop-impact-node
kind: artifact
artifactType: ActualImpactGraph
operation: RemoveItem
selector:
  id: impact:BatchDeployJob.execute
```

Artifact Mutation 可以非常快速地验证下游 Reviewer / Gate 是否具备防漏能力。

### 9.3 MutationRegistry

```python
class MutationRegistry:
    def apply(
        self,
        mutation: MutationDefinition,
        context: EvaluationWorkspaceContext,
    ) -> MutationResult:
        ...
```

第一版内建：

```text
DropFileChange
DropMarkedBlock
ReplaceMarkedValue
AddUnexpectedPatch
RemoveArtifactItem
ReplaceArtifactField
```

这些底层操作足够支持首批五类 Fault Mutation。

## 10. Golden Artifact Loader

`loader.py` 负责：

- YAML Scenario；
- Fixture Manifest；
- Mutation Definition；
- Expected JSON / YAML Artifact；
- ExecutionConfig。

所有加载结果进入 canonical representation。

Canonical JSON 规则：

```text
UTF-8
object key stable sort
统一换行
禁止 NaN / Infinity
set-like collections 按 stable identity 排序
```

生成：

```text
contentHash = sha256(canonical_json)
```

Run Manifest 保存 Expected Artifact Hash，以防评测过程中 Golden 被修改。

## 11. Runner 总接口

```python
class EvaluationRunner(Protocol):
    def run(
        self,
        scenario: EvaluationScenario,
        config: ExecutionConfig,
        workspace: EvaluationWorkspaceContext,
    ) -> WorkflowRun:
        ...
```

实现三个 Runner：

```text
PlanningEvaluationRunner
PreCommitEvaluationRunner
PairedEvaluationRunner
```

## 12. PlanningEvaluationRunner

运行阶段建议映射为：

```text
P1 design-intent
P2 alignment
P3 change-set
P4 planned-impact
P5 node-requirements
P6 plan-review
```

Runner 不复制业务逻辑，应优先调用正式 PlatformService / Workflow Service。

伪代码：

```python
def run(...):
    context = seed_fixture(...)

    stage("design-intent", lambda: workflow.extract_design_intent(...))
    stage("alignment", lambda: workflow.align_entities(...))
    stage("change-set", lambda: workflow.build_change_set(...))
    stage("planned-impact", lambda: workflow.analyze_planning_impact(...))
    stage("node-requirements", lambda: workflow.build_node_requirements(...))
    stage("plan-review", lambda: workflow.review_change_plan(...))

    return collect_run(...)
```

如果正式平台目前仍以较粗的 `RequirementIRDraft` / `ProposedChangeDraft` 表示部分阶段，Evaluation Harness 应通过 Adapter 读取正式 Artifact，不应复制一套平行 Planning 实现。

## 13. PreCommitEvaluationRunner

阶段：

```text
C1 git-diff-snapshot
C2 worktree-overlay
C3 actual-change-set
C4 actual-impact
C5 impact-obligations
C6 reconciliation
C7 verification-coverage
C8 precommit-review
```

伪代码：

```python
def run(...):
    apply_implementation_variant(...)

    diff = precommit.get_git_diff_snapshot(...)
    overlay = precommit.build_worktree_graph_overlay(...)
    changes = precommit.extract_actual_change_set(...)
    impacts = precommit.analyze_actual_impacts(...)
    obligations = precommit.build_impact_obligations(...)
    reconciliation = precommit.reconcile(...)
    coverage = precommit.verify_coverage(...)
    review = precommit.review(...)

    return collect_run(...)
```

实际平台尚未实现的接口，在实现 Evaluation Harness 前应先以正式 Service Interface 定义，不建议在 evaluation 包里做临时业务算法。

## 14. PairedEvaluationRunner

Paired Runner 不是重新实现两条 Workflow，而是组合：

```text
PlanningEvaluationRunner
        ↓
保存 Planned Artifacts
        ↓
Apply Correct / Faulty Implementation
        ↓
PreCommitEvaluationRunner
```

关键点：PreCommit 阶段必须消费该次 Planning Run 的实际 Artifact，而不是直接读取预先准备的 Expected Planning Golden。否则无法测出“Planning 自己错了导致 PreCommit 是否能兜底”。

同时支持两种模式：

```text
paired-real-output
paired-golden-plan
```

`paired-real-output`：Planning 输出直接进入 PreCommit，用于真实 E2E。

`paired-golden-plan`：Expected Planning Artifact 进入 PreCommit，用于隔离测试 PreCommit 流程。

## 15. Artifact Collector

新增 `artifact_collector.py`。

职责：

```text
Stage 完成
→ 从正式 Store / Workflow Run 中解析 Artifact
→ canonicalize
→ 写入 <workspace>/artifacts/<stage>/actual.json
→ 保存 hash / source IDs
→ 注册到 StageRun
```

Collector 不解析自然语言日志作为正式 Artifact。如果某阶段只有 Markdown，应优先增加结构化输出契约，再由 Evaluation 消费。

Artifact Metadata：

```json
{
  "artifactType": "ActualChangeSet",
  "artifactId": "...",
  "stage": "actual-change-set",
  "contentHash": "sha256:...",
  "sourceRunId": "...",
  "createdAt": "..."
}
```

## 16. Judge 总体接口

```python
class Judge(Protocol):
    def judge(
        self,
        expected: Any,
        actual: Any,
        context: JudgeContext,
    ) -> JudgeResult:
        ...
```

统一返回：

```python
@dataclass
class JudgeResult:
    judge_type: str
    passed: bool
    score: float
    missing: list[Any]
    unexpected: list[Any]
    mismatches: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
```

## 17. ArtifactJudge

负责 exact / constraint / schema 类型检查。

第一版包含：

```text
ExactJsonJudge
RequiredFieldJudge
EnumJudge
CrossReferenceJudge
RevisionConsistencyJudge
EvidenceReferenceJudge
```

其中 CrossReferenceJudge 应覆盖：

```text
Change.sourceIntent → DesignIntent.intentId
Impact.changeId → ChangeSet.changeId
Requirement.sourceImpact → Impact.impactId
Reconciliation.requirementId → NodeRequirement.requirementId
```

跨 Artifact 引用断裂应作为确定性失败，而不是 Warning。

## 18. GraphJudge

输入 expected / actual graph canonical model：

```python
GraphView(
    nodes: dict[str, CanonicalNode],
    edges: dict[str, CanonicalEdge],
    paths: list[CanonicalPath],
)
```

Identity 规则必须可配置，默认：

```text
Node = stableEntityId / impactId
Edge = source + relation + target + ruleId
```

输出：

```text
nodePrecision
nodeRecall
edgePrecision
edgeRecall
pathRecall
ruleAccuracy
```

同时保留 Missing / Unexpected 明细。

不能因为最终 target node 存在，就忽略传播路径或 Rule 错误。

## 19. SemanticJudge

第一版建议作为可选插件，默认关闭。

接口：

```python
class SemanticJudgeProvider(Protocol):
    def compare(self, expected: str, actual: str, context: dict[str, Any]) -> dict:
        ...
```

必须先进行 canonical structure comparison，只有无法确定时才调用模型。

输出必须限制为：

```json
{
  "equivalent": true,
  "confidence": 0.94,
  "differences": [],
  "judgeVersion": "..."
}
```

Semantic Judge 不能直接产生 Ready / Block。

## 20. GateJudge

Gate Judge 是最高安全级 Judge。

输入：

```text
Expected Decision
Actual Decision
Blocking Issues Expected
Blocking Issues Actual
```

分类：

```text
TrueReady
TrueBlock
FalseReady
FalseBlock
WrongBlockReason
```

其中：

```text
FalseReady severity = critical
FalseBlock severity = medium
```

如果 Expected 为 Block，而 Actual 虽然 Block 但完全因为错误原因阻塞，应记录 `WrongBlockReason`，不能简单判满分。

## 21. Metric Engine

`metrics.py` 不直接读取原始 Artifact，只消费 JudgeResult 和 StageRun。

第一版 Metric：

```text
intent_precision
intent_recall
alignment_accuracy
change_precision
change_recall
impact_node_precision
impact_node_recall
impact_edge_precision
impact_edge_recall
impact_path_recall
obligation_precision
obligation_recall
requirement_coverage
reconciliation_accuracy
test_obligation_recall
evidence_completeness
gate_accuracy
false_ready_rate
false_block_rate
determinism_rate
tool_calls
latency_ms
```

聚合必须同时支持：

```text
scenario
scenario family
mutation type
fixture level
workflow
execution config
全量 dataset
```

## 22. Safety Score

实现为独立函数：

```python
def safety_weighted_score(metrics: Mapping[str, float]) -> float:
    ...
```

建议初始权重：

```text
0.10 change_precision
0.15 change_recall
0.20 impact_node_recall
0.20 obligation_recall
0.10 test_obligation_recall
0.25 gate_safety
```

`gate_safety` 不等于普通 accuracy，应将 False Ready 权重大幅放大。

除分数外，Regression Gate 必须有硬约束：

```text
critical_false_ready == 0
impact_node_recall >= configured threshold
obligation_recall >= configured threshold
```

即综合分不能抵消安全错误。

## 23. Artifact Lineage Comparator

新增 `lineage.py`。

核心输入：

```text
Expected Artifact Chain
Actual Artifact Chain
Per-stage Judge Results
```

输出：

```python
@dataclass
class FailureDiagnosis:
    first_failed_stage: str
    category: str
    expected_ref: str | None
    actual_ref: str | None
    missing_entities: list[str]
    unexpected_entities: list[str]
    likely_causes: list[str]
    upstream_status: dict[str, str]
```

诊断规则第一版以确定性规则为主，例如：

```text
ChangeSet pass + Graph baseline pass + Impact fail
→ IMPACT_RULE_OR_ENGINE

Alignment fail
→ ALIGNMENT

ActualChangeSet fail but GitDiffSnapshot pass
→ SEMANTIC_CHANGE_EXTRACTION

Obligation pass + Reconciliation fail
→ IMPLEMENTATION_CLOSURE

All stages pass + Gate fail
→ REVIEW_GATE
```

不要第一版就让 LLM 自由分析失败根因。

## 24. Run Manifest 与可重复性

每次批量运行生成 `run-manifest.json`：

```json
{
  "runId": "eval-20260831-001",
  "datasetHash": "sha256:...",
  "executionConfigHash": "sha256:...",
  "ruleSetHash": "sha256:...",
  "scenarioCount": 180,
  "platformVersion": "0.3.0",
  "pythonVersion": "3.11.x",
  "startedAt": "..."
}
```

每个 Scenario Run 再保存：

```text
fixture hash
scenario hash
mutation hash
golden hashes
working tree hash
所有 Stage Artifact hashes
Agent / Skill / Model version
```

同一 Manifest 在环境允许的情况下应可重新运行。

## 25. Determinism Evaluation

增加 `--repeat N`。

同一个 Scenario 重跑 N 次，比较：

```text
Artifact Hash
Graph Set
Final Decision
Semantic Judge Result
```

定义：

```text
Strict Determinism
= 所有 deterministic Artifact Hash 完全相同

Decision Determinism
= 所有最终 Gate Decision 相同
```

LLM 参与阶段允许 Artifact 文本不完全相同，但结构结果应尽量稳定。

## 26. 批量执行器

`runner.py` 负责 dataset expansion 和任务调度。

第一版串行：

```python
for scenario in scenarios:
    run_one(scenario)
```

第二版可使用标准库 `concurrent.futures.ProcessPoolExecutor`，但需要确保：

- 每个 Scenario 独立 SQLite DB；
- 每个 Scenario 独立 Repository Workspace；
- 输出目录独立；
- Agent Runtime 不共享可写 Session；
- 并发不会改变 Golden。

因此第一版不建议为了速度提前引入并行复杂度。

## 27. Comparison Engine

`comparison.py` 比较两个 Run Manifest。

匹配键：

```text
scenarioId
```

每个 Scenario 输出：

```text
Improved
Regressed
Unchanged
NewFailure
FixedFailure
```

Regression 优先级：

```text
FalseReady regression
>
Impact Recall regression
>
Obligation Recall regression
>
Test Recall regression
>
Cost regression
```

最终报告必须能回答：

```text
哪些 Scenario 从 Pass 变 Fail？
哪些 False Ready 新出现？
哪些 Failure 被修复？
哪个 Stage 的回归最多？
Token / Tool Call 成本变化多少？
```

## 28. 报告结构

第一版输出 JSON + Markdown，不先做 Web Dashboard。

```text
reports/<run-id>/
  run-manifest.json
  summary.json
  summary.md
  scenarios/
    <scenario-id>/
      result.json
      diagnosis.json
      actual/
      judge-results/
```

`summary.md` 重点展示：

```text
总 Scenario 数
Pass / Fail
False Ready
False Block
Impact Recall
Obligation Recall
Test Obligation Recall
各 Stage Failure 数量
Top Regression Scenarios
Top Failure Categories
```

## 29. 第一版 Scenario 生成策略

第一版不要尝试完全自动从任意仓库生成 Golden。

采用：

```text
人工设计 Base Scenario
+
确定性 Mutation Expansion
```

每个 Scenario Family 包含：

```text
1 个 Happy Path
5 个 Fault Variants
```

首批 30 个 Base Scenario：

```text
10 Parameter / Signature
5 Return Type
5 Behavior
5 Configuration
5 DTO / API Contract
```

每个扩展：

```text
HappyPath
MissingPlannedChange
MissingCallerAdaptation
MissingRequiredTest
UnexpectedImplementation
WrongSemanticImplementation
```

目标约 180 Cases。

## 30. 第一版 Fixture 设计

建议先做 5 个 Micro Fixture，而不是 30 个完全不同仓库：

```text
micro-call-chain
micro-adapter-boundary
micro-api-dto
micro-config
micro-behavior-test
```

通过不同 Scenario 使用同一个 Fixture 的不同目标节点和 mutation，降低维护成本。

然后增加 2～3 个 Feature Fixture 做组合测试。

## 31. 第一版 Mutation 与预期错误映射

| Mutation | 主要预期发现 |
|---|---|
| MissingPlannedChange | MissingPlannedImplementation |
| MissingCallerAdaptation | MissingPropagationImplementation |
| MissingRequiredTest | MissingTest / VerificationIncomplete |
| UnexpectedImplementation | UnexpectedImplementation |
| WrongSemanticImplementation | SemanticMismatch |

每个 Fault Scenario 必须声明 expectedFailureType，Gate Judge 不只比较 `BlockCommit`，还要比较至少一个主要 Blocking Reason。

## 32. 现有模型的扩展建议

当前 `models.py` 中 `ARTIFACT_TYPES` 主要覆盖现有 Requirement / Proposed Change / Reconciliation 等 Artifact。若正式 Workflow 要输出本文的结构化中间产物，建议逐步加入：

```text
DesignIntentIR
AlignmentArtifact
PlannedChangeSet
PlannedImpactGraph
NodeChangeRequirementArtifact
ChangePlanReview
GitDiffSnapshot
WorkingTreeGraphOverlay
ActualChangeSet
ActualImpactGraph
ImpactObligationArtifact
ImplementationReconciliationArtifact
VerificationCoverageArtifact
PreCommitReview
```

但 Evaluation Harness 自己的 `JudgeResult`、`MetricSet`、`FailureDiagnosis` 不建议混入业务 Artifact Type；它们属于 evaluation domain。

## 33. Store 设计

第一版 Evaluation 结果优先写文件，不要求全部进入 `SQLiteStore`。

原因：

```text
Scenario / Golden 是版本库资产
Actual Artifact 已在正式 Store 中存在
Evaluation Result 更适合可移植 JSON
大量批量结果写数据库会增加 schema 复杂度
```

只在需要跨运行查询时，再增加：

```text
evaluation_runs
evaluation_scenarios
evaluation_metrics
```

第一版先保证报告 JSON Schema 稳定。

## 34. 错误处理

Scenario 状态建议：

```text
PASS
FAIL
ERROR
SKIPPED
INVALID
```

含义：

```text
FAIL = Workflow 正常执行，但结果不符合 Expected
ERROR = Workflow / Agent / MCP 自身执行失败
INVALID = Scenario / Golden / Fixture 不合法
SKIPPED = 不满足环境前置条件
```

不能把 ERROR 计为普通 FAIL，否则无法区分产品能力错误和测试基础设施错误。

## 35. 测试策略

Evaluation Harness 本身也必须测试。

### 35.1 Unit Tests

覆盖：

```text
Scenario schema validation
Canonical JSON / hash
Mutation operations
Graph set comparison
Metric calculation
Safety score
Failure attribution
```

### 35.2 Self-test Fixtures

准备极小固定 Artifact，不调用 Agent：

```text
expected graph A/B/C
actual graph A/B
```

精确验证 Recall / Precision。

准备：

```text
Expected BlockCommit
Actual ReadyToCommit
```

精确验证 False Ready 分类。

### 35.3 Integration Tests

使用 Micro Fixture 跑真实 PlatformService，但禁用 Agent，验证：

```text
Fixture → Scan → Artifact → Judge → Report
```

### 35.4 E2E Tests

选 2～3 个 Paired Scenario 进入正常仓库回归。

不要把全部 180 Cases 放进普通单元测试；完整 dataset 可以作为独立 regression command。

## 36. CLI 返回码

建议：

```text
0 = 全部满足 Gate
1 = 存在 Evaluation Failure
2 = Scenario / Config Invalid
3 = Infrastructure / Runtime Error
4 = 存在 False Ready
```

`4` 单独保留，便于 CI 对最高严重性错误快速阻塞。

## 37. CI 集成

第一版定义三个集合：

```text
smoke
critical
full
```

例如：

```bash
code-ontology-platform eval run evaluation/scenarios \
  --filter smoke
```

PR 默认：

```text
smoke + critical
```

夜间或手工：

```text
full
```

涉及以下文件变更时应强制跑 critical：

```text
.opencode/skills/**
.opencode/agents/**
rules/**
ontology/**
shapes/**
src/code_ontology_platform/*impact*
src/code_ontology_platform/*workflow*
src/code_ontology_platform/evaluation/**
```

## 38. 实现阶段划分

### Phase 1：Evaluation Core

实现：

```text
models
loader
scenario validation
workspace manager
artifact collector
ArtifactJudge
GraphJudge
MetricEngine
report
CLI eval validate/run
```

目标：可以执行人工编写的 Stage / Workflow Scenario。

### Phase 2：Fault Mutation

实现：

```text
MutationRegistry
DropMarkedBlock
ReplaceMarkedValue
AddUnexpectedPatch
Artifact mutation
ScenarioFamily expansion
```

目标：从 Base Scenario 自动生成 Negative Cases。

### Phase 3：Planning / PreCommit Adapters

把正式两条 Workflow 的每个 Artifact 暴露给 Evaluation Runner，并完成 Planning / PreCommit Runner。

目标：完整跑通两套流程。

### Phase 4：Paired E2E

实现 Planning 输出直接进入 PreCommit，建立 `Plan → Code → Verify` 闭环。

### Phase 5：Differential / Regression

实现：

```text
ExecutionConfig versioning
compare
regression gate
determinism repeat
```

### Phase 6：Semantic Judge / Parallel Runner

只有确定性部分稳定后再加入。

## 39. 第一版 Definition of Done

第一版可以认为完成，需要同时满足：

```text
1. eval validate 能校验 Scenario / Fixture / Golden；
2. eval run 能执行 planning 与 precommit scenario；
3. 每个 Stage 的 actual artifact 可落盘；
4. ArtifactJudge / GraphJudge 可给出结构化差异；
5. 能计算 Change Recall / Impact Recall / Obligation Recall；
6. GateJudge 能识别 False Ready / False Block；
7. 能输出 firstFailedStage；
8. 至少支持 5 类 Fault Mutation；
9. 至少存在 20 个可重复 Scenario；
10. 同一 deterministic Scenario 连续运行结果一致；
11. 一个 MissingCallerAdaptation Case 必须被稳定判为 Block；
12. 一个 MissingRequiredTest Case 必须被稳定判为 Block。
```

## 40. 后续扩展

第一版稳定后再考虑：

```text
自动从真实 Commit / PR 挖掘 Scenario
自动生成 Golden Candidate 供人工审核
真实历史 Bug 作为 Regression Corpus
多语言 Fixture
基于 Mutation Coverage 反推测试数据缺口
Web Dashboard
分布式 Runner
模型 / Prompt 自动参数搜索
```

其中最有价值的长期方向是把真实历史遗漏 Bug 转换成固定 Scenario。每修复一次产品缺陷，就新增一个不会再丢失的 Evaluation Case，最终形成代码变更推理系统自己的回归知识库。

## 41. 最终实现原则

整个实现应坚持：

```text
Evaluation 不复制业务 Workflow；
Golden 不由被测 Agent 自证；
确定性事实不用 LLM Judge；
每一级 Artifact 都能独立评测；
错误必须能定位到第一次分叉；
False Ready 优先级高于总分；
Fault Mutation 是验证“能否发现遗漏”的核心手段；
Paired E2E 是最终可信度最高的测试模式。
```

第一版的核心不是做一个漂亮 Dashboard，而是先形成一条可靠的机器可执行回归链：

```text
Scenario
→ Isolated Workspace
→ Workflow
→ Artifact Collection
→ Deterministic Judge
→ Metric
→ Failure Attribution
→ Regression Gate
```

只要这条链稳定，后续增加更多 Scenario、更多 Mutation、更多 Agent / Skill A/B 配置都会非常自然。