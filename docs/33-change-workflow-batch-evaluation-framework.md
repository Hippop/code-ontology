# 代码变更规划与提交前验证批量评测框架

## 1. 文档目标

本文定义一套面向 Code Ontology 变更工作流的批量评测框架，用于系统性验证以下两条核心流程的正确性、完整性和稳定性。

### 1.1 规划期流程

```text
Design Document
→ DesignIntentIR
→ AlignmentArtifact
→ Planned ChangeSet
→ Planned ImpactGraph
→ NodeChangeRequirementArtifact
→ ChangePlanReview
```

该流程回答：

> 根据设计，应该修改什么，修改会波及什么，最终每个代码节点应该满足什么要求。

### 1.2 提交前验证流程

```text
Working Tree / Git Diff
→ GitDiffSnapshot
→ WorkingTreeGraphOverlay
→ ActualChangeSet
→ ActualImpactGraph
→ ImpactObligationArtifact
→ ImplementationReconciliationArtifact
→ VerificationCoverageArtifact
→ PreCommitReview
```

该流程回答：

> 实际修改了什么，这些修改还会产生什么波及，规划要求是否全部实现，实际波及是否全部闭合，是否存在功能、测试或兼容性遗漏。

批量评测框架的目标不是只判断最终 `Ready` 或 `Block` 是否正确，而是验证整个 Artifact 链条：

```text
输入
→ 中间语义 Artifact
→ 图推理
→ 工程义务
→ 完整性判断
```

并能够定位错误最早发生在哪个阶段。

## 2. 核心设计原则

### 2.1 Artifact-first Evaluation

评测的主要对象不是最终 Markdown，也不是 Agent 最终自然语言回答，而是每一个结构化中间 Artifact。

规划流程：

```text
DesignIntentIR
AlignmentArtifact
PlannedChangeSet
PlannedImpactGraph
NodeChangeRequirementArtifact
ChangePlanReview
```

提交前流程：

```text
GitDiffSnapshot
WorkingTreeGraphOverlay
ActualChangeSet
ActualImpactGraph
ImpactObligationArtifact
ImplementationReconciliationArtifact
VerificationCoverageArtifact
PreCommitReview
```

每一个阶段都应存在 Expected Artifact 或可计算的 Expected Constraint。

### 2.2 不只测试 Happy Path

框架必须大量构造“不完整实现”。例如正确实现包含 Service、Controller、BatchJob 和 Test，则应自动派生缺 Controller、缺 BatchJob、缺 Test、默认值错误、新增意外数据库修改、行为改变但测试没更新等场景。

真正重要的问题不是一个正确实现能不能通过，而是一个故意存在遗漏的实现，系统能不能发现并阻止继续。

### 2.3 错误放行比错误阻塞更严重

评测结果必须区分 `False Block` 与 `False Ready`。其中存在遗漏却被判定为 `ReadyForImplementation` 或 `ReadyToCommit` 的 `False Ready` 属于最高严重级别错误，因此所有综合评分都应对 False Ready 设置明显更高的惩罚。

### 2.4 确定性能力与 LLM Judge 分离

可以确定性比较的 Schema、ID 引用、Graph Node、Graph Edge、Impact Path、Rule ID、Revision、Hash 和枚举禁止交给 LLM Judge，应由程序直接比较。

只有 Requirement 是否语义等价、Behavior Change 是否表达相同意思、Node Requirement 是否满足相同工程约束等无法通过结构比较可靠判断的内容，才允许使用 Semantic Judge。

## 3. 总体架构

```text
                        Scenario Dataset
                              │
                              ▼
                       Scenario Expander
                              │
                    ┌─────────┴─────────┐
                    │                   │
                Base Case          Mutation Cases
                    │                   │
                    └─────────┬─────────┘
                              ▼
                         Batch Runner
                              │
               ┌──────────────┼──────────────┐
               │                             │
      Planning Workflow Runner     PreCommit Workflow Runner
               │                             │
               ▼                             ▼
         Actual Artifacts              Actual Artifacts
               │                             │
               └──────────────┬──────────────┘
                              ▼
                         Judge Pipeline
                              │
             ┌────────────────┼────────────────┐
             ▼                ▼                ▼
      Artifact Judge      Graph Judge     Semantic Judge
                              │
                              ▼
                         Gate Judge
                              │
                              ▼
                         Metric Engine
                              │
                              ▼
                     Failure Attribution
                              │
                              ▼
                       Evaluation Report
```

## 4. 核心对象

框架建议围绕以下对象设计：

```text
EvaluationScenario
ScenarioFamily
RepositoryFixture
MutationDefinition
ExecutionConfig
WorkflowRun
StageRun
ExpectedArtifact
ActualArtifact
JudgeResult
MetricSet
FailureDiagnosis
ComparisonReport
```

## 5. EvaluationScenario

`EvaluationScenario` 是最小可执行测试单元。

### 5.1 Planning Scenario

```yaml
scenarioId: PLAN-001
workflow: planning

repositoryFixture:
  id: java-retry-service
  revision: base-v1

input:
  requirementId: REQ-001
  designDocument: designs/add-retry-policy.md

expected:
  designIntent: expected/design-intent.json
  alignment: expected/alignment.json
  changeSet: expected/change-set.json
  impactGraph: expected/impact-graph.json
  nodeRequirements: expected/node-requirements.json
  review: expected/change-plan-review.json

expectedDecision:
  ReadyForImplementation
```

### 5.2 PreCommit Scenario

```yaml
scenarioId: PRECOMMIT-001
workflow: precommit

repositoryFixture:
  id: java-retry-service
  baseRevision: base-v1

workingTree:
  patch: patches/retry-policy-complete.diff

plannedArtifacts:
  path: plans/retry-policy/

expected:
  gitDiffSnapshot: expected/git-diff.json
  actualChangeSet: expected/actual-change-set.json
  actualImpactGraph: expected/actual-impact.json
  obligations: expected/impact-obligations.json
  reconciliation: expected/reconciliation.json
  verificationCoverage: expected/verification-coverage.json
  preCommitReview: expected/precommit-review.json

expectedDecision:
  ReadyToCommit
```

## 6. ScenarioFamily

大量场景不应独立手写。应该首先定义一个正确的基础场景：

```text
Design
+
Repository
+
Expected Plan
+
Correct Implementation
```

然后通过 Mutation 派生多个 Case。例如：

```text
ScenarioFamily: retry-policy

Base:
  正确设计
  正确规划结果
  正确实现

Variants:
  happy-path
  missing-controller
  missing-batch-job
  missing-test
  wrong-default-value
  unexpected-db-change
  dynamic-callback-unresolved
```

这样一个业务场景就能同时测试大量失败模式。

## 7. Repository Fixture

Repository Fixture 建议分四级。

### 7.1 L1 Micro Fixture

节点规模建议 10～30，主要用于精确验证单条规则。例如：

```text
Controller
   ↓ calls
Service
   ↓ calls
Repository

ServiceTest
   ↓ tests
Service
```

适合测试 ParameterAdded、ReturnTypeChanged、CallerPropagation 和 TestPropagation。

### 7.2 L2 Feature Fixture

规模建议 50～200 nodes，包含完整功能切片：Controller、DTO、Mapper、Service、Repository、Config、Database 和 Tests，用于验证功能级 Planning、完整波及、Node Requirement 和 PreCommit Closure。

### 7.3 L3 Architecture Fixture

包含多个 Module、API、Messaging、Database、Configuration、Shared Library 和 Tests，主要测试跨模块影响、契约传播、兼容边界、Adapter 吸收、消息消费者和数据库迁移。

### 7.4 L4 Real Repository Corpus

使用真实项目固定 Revision，主要用于复杂代码鲁棒性、性能、Token 消耗、MCP Call 数量、大图传播和真实语义噪声。

Real Repository 不应该替代 Micro Fixture。Micro Fixture 用于回答系统哪里错了，Real Repository 用于回答系统在真实环境中效果如何。

## 8. Scenario Generator

为了形成大规模数据集，应提供 Scenario Generator。核心模型：

```text
Base Repository Fixture
+
Change Mutation
+
Graph Topology
+
Design Wording Variant
+
Implementation Variant
=
EvaluationScenario
```

例如：

```yaml
mutation:
  type: AddParameter

target:
  DeployService.deployPolicy

parameter:
  name: retryPolicy
  type: RetryPolicy

expectedPropagation:
  - callers
  - tests

implementationVariant:
  complete
```

系统可以自动生成设计文档、Expected DesignIntent、Expected ChangeSet、Expected Impact 和正确实现 Patch，然后再通过 `implementationVariant: missing-one-caller` 形成 Negative Case。

## 9. Mutation DSL

Mutation 是整个批量评测框架最重要的能力之一。

### 9.1 Structural Mutation

```text
AddParameter
RemoveParameter
ChangeParameterType
ChangeReturnType
AddField
RemoveField
RenameField
MoveMethod
ChangeVisibility
```

### 9.2 Behavior Mutation

```text
RetryBehaviorChanged
TimeoutChanged
ExceptionBehaviorChanged
FallbackChanged
TransactionChanged
CachingChanged
SideEffectChanged
SecurityBehaviorChanged
```

### 9.3 Contract / Data Mutation

```text
ApiFieldAdded
ApiFieldRequiredChanged
ResponseSchemaChanged
DatabaseColumnAdded
DatabaseColumnTypeChanged
ConfigAdded
ConfigDefaultChanged
MessageSchemaChanged
```

### 9.4 Fault Injection Mutation

第一版重点支持：

```text
DropPlannedChange
DropCallerAdaptation
DropIndirectImpact
DropRequiredTest
WrongParameterSource
WrongDefaultValue
WrongExceptionBehavior
WrongMapper
MissingMigration
UnexpectedImplementation
BehaviorChangedWithoutTest
```

Fault Injection 的目标是验证 PreCommit Gate 是否真的具备发现遗漏的能力。

## 10. Golden Artifact

Golden 不能由被测试的 Agent 自己生成，建议有三种来源。

### 10.1 Deterministic Golden

适合 GitDiffSnapshot、AST Change、Graph Node、Graph Edge、ID 和 Revision，由程序直接计算。

### 10.2 Rule-derived Golden

例如：

```text
SignatureChanged
+
incoming calls
=
RequiredModification
```

可以由 Reference Rule Engine 生成 ExpectedImpactGraph 和 ExpectedImpactObligation。

### 10.3 Human-reviewed Golden

用于复杂 DesignIntent、Behavior Change、Architecture Boundary 和 Semantic Node Requirement，由人工确认。

每个 Expected Artifact 应标记：

```yaml
oracle:
  type: deterministic
```

或者：

```yaml
oracle:
  type: rule-derived
```

或者：

```yaml
oracle:
  type: human-reviewed
```

## 11. Planning Workflow 评测

规划流程逐阶段测试：

```text
Design
      ↓
DesignIntentIR
      ↓
AlignmentArtifact
      ↓
PlannedChangeSet
      ↓
PlannedImpactGraph
      ↓
NodeChangeRequirementArtifact
      ↓
ChangePlanReview
```

### 11.1 DesignIntent Evaluation

检查设计变化是否全部识别、是否产生虚假设计变化、Explicit / Inferred 是否混淆、Evidence 是否完整、Unresolved 是否正确保留。

核心指标：Intent Precision、Intent Recall、Evidence Completeness。

### 11.2 Alignment Evaluation

检查 Desired Entity 是否映射到正确 Current Entity、NoMatch 是否正确、Ambiguous 是否正确保留。

核心指标：Alignment Accuracy、False Confirmation Rate、Ambiguity Detection Recall。

尤其需要测试 PolicyService 与 LegacyPolicyService 同时存在的场景。系统不确定时应该输出 Ambiguous，而不是为了继续流程自动选择。

### 11.3 ChangeSet Evaluation

检查是否正确拆分原子 Change、operation 是否正确、aspect 是否正确、before / after 是否正确、target 是否正确。

核心指标：Change Precision、Change Recall、Change Classification Accuracy。

### 11.4 Planned Impact Evaluation

比较 ExpectedImpactGraph 与 ActualImpactGraph，指标包括 Impact Node Precision、Impact Node Recall、Impact Edge Precision、Impact Edge Recall、Impact Path Recall 和 Propagation Rule Accuracy。

Impact Recall 是最重要指标之一。

### 11.5 Node Requirement Evaluation

检查 Required Impact 是否都有 Requirement、文件定位是否正确、Symbol 是否正确、Change 来源是否正确、Impact 来源是否正确、测试要求是否完整。

核心指标：Requirement Coverage、Requirement Semantic Accuracy、Test Requirement Recall。

### 11.6 ChangePlanReview Evaluation

重点验证存在 unresolved 时有没有错误放行、存在漏 Impact 时有没有错误 Complete、存在测试缺口时有没有错误 Ready。

## 12. PreCommit Workflow 评测

提交前流程：

```text
Git Diff
     ↓
GitDiffSnapshot
     ↓
WorkingTreeGraphOverlay
     ↓
ActualChangeSet
     ↓
ActualImpactGraph
     ↓
ImpactObligationArtifact
     ↓
ImplementationReconciliationArtifact
     ↓
VerificationCoverageArtifact
     ↓
PreCommitReview
```

## 13. GitDiffSnapshot Evaluation

必须确认完整捕获 staged、unstaged、untracked、rename 和 delete。

测试重点包括新文件未 `git add`、文件 Rename、删除实现、多文件部分 staged，避免只看普通 `git diff` 导致漏变更。

## 14. WorkingTreeGraphOverlay Evaluation

检查 Working Tree 临时图是否正确反映 Added Node、Removed Node、Modified Node、Added Edge、Removed Edge，并验证 Overlay 不污染 Current Graph。

## 15. ActualChangeSet Evaluation

测试 Structural Change Detection、Behavior Change Detection、Contract Change Detection、Data Change Detection 和 Configuration Change Detection。

这里尤其要区分 Parser 能确定的变化与 SemanticDiffAnalyst 推断的变化，后者必须包含 Evidence 和 Confidence。

## 16. Actual Impact Evaluation

实际 ChangeSet 应重新做独立 Impact。必须允许 `ActualImpactGraph != PlannedImpactGraph`，因为真实实现可能产生设计阶段没有预测到的新关系。

重点指标仍然是 Impact Recall。

## 17. Impact Obligation Evaluation

ImpactGraph 只说明谁受影响，ImpactObligation 必须进一步说明这个节点需要承担什么工程义务。

至少支持：

```text
RequiredModification
RequiredTest
CompatibilityVerification
MigrationRequired
ReleaseActionRequired
RequiredReview
Contained
```

评测需要检查 Expected Impact 到 Expected Obligation 是否正确。核心指标：Obligation Precision、Obligation Recall。

## 18. Implementation Reconciliation Evaluation

必须同时评测两个方向。

### 18.1 Plan → Actual

检查规划要求是否真正实现。可能结果：

```text
Conformed
MissingPlannedImplementation
SemanticMismatch
ExplicitlyDeferred
```

### 18.2 Actual Impact → Actual

检查实际变化产生的波及义务是否已经闭合。结果：

```text
Satisfied
Contained
MissingPropagationImplementation
Unverified
```

另外还必须识别 `UnexpectedImplementation`，即实现中出现了规划完全没有要求的变化。

## 19. VerificationCoverage Evaluation

不要只使用 Line Coverage，至少分为 Structural Coverage 与 Semantic Obligation Coverage。

Structural Coverage 检查受影响节点是否存在验证手段；Semantic Obligation Coverage 检查 Behavior / Acceptance Criterion 是否存在明确 Test Scenario。

例如 retryPolicy=0、retryPolicy=1、retryPolicy=3、retry exhausted。即使 Line Coverage 100%，缺少 retry exhausted 仍然是不完整。

核心指标：Test Obligation Recall、Acceptance Coverage、Required Test Pass Rate。

## 20. Judge Pipeline

评测至少由四类 Judge 构成。

### 20.1 Artifact Judge

完全确定性。检查 JSON Schema、字段类型、枚举、Revision、Hash、ID 引用、Evidence Reference 和 Cross Artifact Reference。

### 20.2 Graph Judge

比较 Node Set、Edge Set、Path、Rule 和 Impact Type，输出 Precision、Recall、Missing Nodes、Extra Nodes、Missing Paths 和 Wrong Rules。

### 20.3 Semantic Judge

仅用于结构比较无法覆盖的内容。例如 Expected “调用 deployPolicy 时必须传入 retryPolicy” 与 Actual “更新 deployPolicy 调用以提供 retryPolicy 参数”属于语义等价。

Semantic Judge 输出应是结构化的：

```yaml
equivalent: true
confidence: 0.95
differences: []
```

Semantic Judge 不能直接决定 Gate。

### 20.4 Gate Judge

比较 Expected Decision 与 Actual Decision，例如：

```text
ReadyForImplementation
NeedsReview
BlockImplementation
ReadyToCommit
BlockCommit
```

重点记录 FalseReady 和 FalseBlock。

## 21. 指标体系

第一版建议至少记录：Intent Precision、Intent Recall、Alignment Accuracy、Change Precision、Change Recall、Impact Precision、Impact Recall、Path Recall、Obligation Recall、Requirement Coverage、Reconciliation Accuracy、Test Obligation Recall、Evidence Completeness、Gate Accuracy、False Ready Rate、Determinism、Token Cost、MCP Calls 和 Latency。

其中最重要的是 Impact Recall、Obligation Recall 和 Gate Safety。

## 22. Safety Weighted Score

综合指标不能简单平均，建议提高 Impact Recall、Obligation Recall 和 Gate Safety 的权重。例如：

```text
Score =
0.10 ChangePrecision
+ 0.15 ChangeRecall
+ 0.20 ImpactRecall
+ 0.20 ObligationRecall
+ 0.10 TestObligationRecall
+ 0.25 GateSafety
```

同时增加独立惩罚：

```text
False Block = -1
False Ready = -10
```

实际发布标准不应只看综合分，还应设置硬门槛，例如 `False Ready = 0`、Impact Recall 与 Obligation Recall 不低于指定阈值。

## 23. Failure Attribution

批量评测不能只输出 `Pass Rate = 84%`，必须知道第一次错在哪里。

例如最终漏掉 `AdminController`，框架沿 Artifact Lineage 检查：

```text
DesignIntent
↓
Alignment
↓
ChangeSet
↓
Impact
↓
Requirement
```

如果 ChangeSet 正确、Graph 正确、Impact 缺 AdminController，则：

```yaml
failureDiagnosis:
  firstFailedStage: ImpactAnalysis
  missingEntity: AdminController.deploy
  likelyCause:
    SIGNATURE_CALLER_PROPAGATION did not fire
```

## 24. Artifact Lineage Comparator

建议独立实现 `ArtifactLineageComparator`，负责比较规划链：

```text
DesignIntent
→ Alignment
→ Change
→ Impact
→ Requirement
→ Review
```

以及提交前链：

```text
ActualChange
→ ActualImpact
→ Obligation
→ Reconciliation
→ Verification
→ Gate
```

第一次 Expected / Actual 出现分叉的位置，就是 Root Failure Stage，用于 Skill、Rule 和 Agent Prompt 优化。

## 25. 执行模式

框架至少支持三种运行模式。

### 25.1 Stage Evaluation

例如只测试 `ChangeSet → ImpactGraph`，执行快、定位准确，适合 Rule 回归。

### 25.2 Workflow Evaluation

完整执行 `Design → ChangePlan` 或 `GitDiff → PreCommitReview`，用于验证 Agent + Skill + MCP 的组合效果。

### 25.3 Paired E2E Evaluation

这是最终最重要模式：

```text
Design
→ Planning
→ Correct / Faulty Implementation
→ Git Diff
→ PreCommit Verification
```

完整测试 `Plan → Code → Verify`。

## 26. Paired Scenario 示例

基础需求：`deployPolicy` 新增 `retryPolicy`。

规划预期：

```text
NCR01 DeployService
NCR02 DeployController
NCR03 BatchDeployJob
NCR04 DeployPolicyTest
```

正确实现包含 Service、Controller、BatchJob、Test，Expected 为 `ReadyToCommit`。

Fault Injector 删除 BatchJob adaptation 后，Expected 为：

```text
BlockCommit
MissingPropagationImplementation
```

再删除 retry exhausted test 后，Expected 为：

```text
BlockCommit
MissingTest
```

一个业务需求即可形成多个可自动执行 Scenario。

## 27. ExecutionConfig

每次 Run 都必须固定 Agent / Skill / Rule / Model 版本：

```yaml
executionConfig:
  mainAgent:
    name: PreCommitVerificationAgent
    version: v2

  skills:
    extractActualChange: v3
    verifyImpactClosure: v5
    precommitReview: v2

  subagents:
    semanticDiffAnalyst:
      version: v7
    preCommitReviewer:
      version: v4

  ruleSet:
    version: impact-rules-v9

  model:
    name: model-x

  mcp:
    version: graph-mcp-v5
```

这样评测结果才具有可重复性。

## 28. Differential Evaluation

框架必须支持 Baseline Configuration VS Candidate Configuration，例如比较 Skill v1 与 Skill v2，在同一批 Scenario 上分别执行。

最终输出：

| Metric | Baseline | Candidate | Delta |
|---|---:|---:|---:|
| Change Recall | 91% | 95% | +4% |
| Impact Recall | 88% | 96% | +8% |
| Obligation Recall | 90% | 97% | +7% |
| False Ready | 7 | 1 | -6 |
| Token Cost | 18k | 13k | -28% |
| MCP Calls | 32 | 21 | -34% |

只有这种方式，才能客观判断 Skill 修改、Prompt 修改、RuleSet 修改或 Model 更换到底有没有提升。

## 29. Regression Gate

任何新的 Skill、Agent Prompt、RuleSet、MCP 或 Ontology 版本进入主分支前，都可以跑固定 Evaluation Dataset。

例如：

```text
critical scenarios: 100
standard scenarios: 500
extended scenarios: 2000
```

发布 Gate：

```text
Critical False Ready = 0
Impact Recall 不下降
Obligation Recall 不下降
Regression Cases <= threshold
```

否则阻止评测配置进入稳定版本。

## 30. 目录结构建议

```text
evaluation/

  scenarios/
    planning/
    precommit/
    paired/

  scenario-families/

  fixtures/
    micro/
    feature/
    architecture/
    real/

  mutations/
    structural/
    behavior/
    contract/
    fault-injection/

  goldens/

  runners/
    planning_runner.py
    precommit_runner.py
    paired_runner.py

  judges/
    artifact_judge.py
    graph_judge.py
    semantic_judge.py
    gate_judge.py

  lineage/
    artifact_lineage_comparator.py

  metrics/
    metric_engine.py
    safety_score.py

  reports/
```

## 31. 第一版实现范围

第一版不需要追求几千个场景。建议：

```text
20 个 Micro Scenario
10 个 Feature Scenario
5 类 Fault Mutation
```

约为：

```text
30 Base Scenarios × 6 Variants ≈ 180 Cases
```

优先覆盖 Parameter Change、Return Type Change、Behavior Change、Configuration Change 和 DTO / API Change。

## 32. 第一版 Fault Mutation

优先实现：

```text
1. MissingPlannedChange
2. MissingCallerAdaptation
3. MissingRequiredTest
4. UnexpectedImplementation
5. WrongSemanticImplementation
```

这五类已经能够有效测试系统当前最重要的问题：是否能够发现功能遗漏。

## 33. 第一版最重要指标

初期 Dashboard 不需要几十个指标，先突出：

```text
Change Recall
Impact Recall
Obligation Recall
Test Obligation Recall
False Ready Rate
Stage Failure Distribution
```

优先级：

```text
False Ready
>
Impact Recall
>
Obligation Recall
>
Test Obligation Recall
>
其他指标
```

## 34. 与两套 Agent Workflow 的关系

批量评测框架本身不替代原来的 Skill、Agent 和 MCP。

关系应当是：

```text
                   Evaluation Harness
                          │
          ┌───────────────┴───────────────┐
          ▼                               ▼
 Planning Workflow                 PreCommit Workflow
          │                               │
          ▼                               ▼
     Artifact Chain                  Artifact Chain
          │                               │
          └───────────────┬───────────────┘
                          ▼
                       Judges
                          │
                          ▼
                       Metrics
```

Evaluation Harness 是外部观察者，不参与被测试 Workflow 的正常推理。

## 35. 最终定位

这套系统可以定义为：

> **Ontology-driven Change Workflow Evaluation Harness**

它评测的不是单一 Agent，也不是单一代码图算法，而是整个 Document Understanding、Entity Alignment、Semantic Change Detection、Ontology Impact Reasoning、Impact Obligation Generation、Implementation Reconciliation、Test Verification 和 Agent Review Gate 的完整可靠性。

最终核心判断不是 Agent 是否给出了一个看起来合理的答案，而是：

```text
该识别的 Change 是否全部识别；
该传播的 Impact 是否全部传播；
该产生的 Obligation 是否全部产生；
规划要求被故意漏实现时能否发现；
实际代码产生新的波及时能否发现；
必要测试被故意删除时能否发现；
存在任何关键遗漏时，
PreCommit Gate 是否能够稳定阻止提交。
```

因此整个批量测试框架最终服务于一个目标：

> **持续证明 Code Ontology 驱动的变更规划与提交前验证流程，真的具备发现软件变更遗漏的能力，而不仅仅是生成一份看起来完整的分析报告。**