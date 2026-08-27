# 基于 Git Diff 的提交前波及完整性验证架构

## 1. 文档目标

本文定义代码实现完成后、Git Commit 之前，如何基于 Working Tree / Git Diff 重新构建实际语义 ChangeSet，结合代码本体和传播规则计算实际波及，并与规划阶段的变更要求进行双向对账，最终判断本次修改是否存在功能遗漏、波及遗漏、测试遗漏或计划外修改。

本文与 `31-agent-change-planning-architecture.md` 形成前后闭环：

```text
规划阶段
设计文档
→ DesignIntentIR
→ AlignmentArtifact
→ Planned ChangeSet
→ Planned ImpactGraph
→ NodeChangeRequirementArtifact
→ ChangePlanReview
→ Coding Agent

提交前验证阶段
Working Tree / Git Diff
→ GitDiffSnapshot
→ WorkingTreeGraphOverlay
→ ActualChangeSet
→ ActualImpactGraph
→ ImpactObligationArtifact
→ ImplementationReconciliationArtifact
→ VerificationCoverageArtifact
→ PreCommitReview
→ Commit Gate
```

规划阶段回答：**应该改什么。**

提交前验证阶段回答：

1. **实际改了什么；**
2. **实际变化还会波及什么；**
3. **所有规划要求是否已经实现；**
4. **所有实际波及义务是否已经闭合；**
5. **功能和测试是否存在遗漏；**
6. **当前 Working Tree 是否具备提交条件。**

系统只做提交前验证和 Gate 判定，不执行 Git Commit、Push、Merge 或部署。

---

## 2. 核心设计原则

### 2.1 不能只做 Git Diff → Impact

只从 Git Diff 计算波及，只能发现“已发生变化会影响谁”，无法发现“本来应该修改但完全没有出现在 Git Diff 中的内容”。

因此提交前验证必须同时检查两个方向：

```text
计划 → 实际
检查 Planned Requirement 是否已经实现

实际 → 波及闭包
检查 Actual Change 产生的所有 Impact Obligation 是否已经处理
```

只有两者同时成立，才能认为修改完整。

### 2.2 Planned ChangeSet 与 ActualChangeSet 必须分离

```text
Planned ChangeSet
= 设计阶段认为应该发生的变化

ActualChangeSet
= Working Tree 中真实发生的语义变化
```

二者不能覆盖，也不能因为名称和目标相同就直接视为一致，必须通过 Reconciliation 显式对账。

### 2.3 Current Graph 不被 Working Tree 污染

提交前代码尚未成为正式代码事实，因此不能把 Working Tree 扫描结果发布为新的 Current Graph。

使用临时视图：

```text
Base Current Graph
+
Working Tree Changed Files
=
WorkingTreeGraphOverlay
```

Overlay 只服务本次验证。提交完成并重新扫描后，才产生新的正式 Current Graph Revision。

### 2.4 Impact 不是最终工程义务

ImpactGraph 只能说明某个实体受到了某个 Change 的影响。

系统还必须把 Impact 转换成明确的工程义务：

```text
Impact
→ RequiredModification
→ RequiredTest
→ CompatibilityVerification
→ MigrationRequired
→ RequiredReview
→ ReleaseActionRequired
→ Contained / NoModificationRequired
```

这个中间层称为 `ImpactObligationArtifact`，它是判断“有没有漏改”的核心。

### 2.5 Review 必须绑定 Working Tree Hash

PreCommitReview 必须绑定精确的 Working Tree Snapshot：

```text
reviewedWorkingTreeHash == currentWorkingTreeHash
```

如果 Review 后代码再次变化，则原 Review 自动失效，状态为 `STALE_REVIEW`，必须重新运行验证。

---

## 3. 总体架构

规划期保持与前一文档相同的 Artifact，提交前增加新的验证链。

```text
                         Coding Agent
                              │
                              ▼
                    Working Tree / Git Diff
                              │
                              ▼
             ┌────────────────────────────────┐
             │ PreCommitVerificationAgent     │
             │ 主编排 Agent                    │
             └───────────────┬────────────────┘
                             │
                             ▼
             ┌────────────────────────────────┐
             │ Skill 1                        │
             │ extract-actual-change          │
             └───────────────┬────────────────┘
                             │
             ┌───────────────┼──────────────────┐
             ▼               ▼                  ▼
       GitDiffSnapshot  WorkingTreeGraphOverlay ActualChangeSet
                             │
                             ▼
             ┌────────────────────────────────┐
             │ Skill 2                        │
             │ verify-impact-closure          │
             └───────────────┬────────────────┘
                             │
                             ▼
                     ActualImpactGraph
                             │
                             ▼
                  ImpactObligationArtifact
                             │
                ┌────────────┴─────────────┐
                ▼                          ▼
ImplementationReconciliationArtifact  VerificationCoverageArtifact
                │                          │
                └────────────┬─────────────┘
                             ▼
             ┌────────────────────────────────┐
             │ Skill 3                        │
             │ review-precommit-completeness  │
             └───────────────┬────────────────┘
                             │
                             ▼
                   PreCommitReviewer
                             │
                             ▼
                     PreCommitReview
                             │
                 ┌───────────┴───────────┐
                 ▼                       ▼
            ReadyToCommit            BlockCommit
```

整个系统保持：

```text
1 个主 Agent
3 个 Skill
2 个 Subagent
7 个核心 MCP Tool
8 个核心提交前 Artifact
1 个 Commit Gate
```

---

## 4. 主 Agent：PreCommitVerificationAgent

### 4.1 定位

`PreCommitVerificationAgent` 是提交前验证流程唯一编排者，负责固定分析输入、执行 Skill、调度 Subagent、保存 Artifact、执行 Gate 和输出最终判定。

### 4.2 职责

```text
固定 Base Revision / Graph Revision / RuleSet / Working Tree Snapshot
→ 执行实际变更抽取
→ 执行实际波及分析
→ 生成 Impact Obligation
→ 执行计划—实际对账
→ 执行测试与验证覆盖检查
→ 调用独立 Reviewer
→ 生成 PreCommitReview
```

### 4.3 禁止事项

主 Agent 不得：

- 修改业务代码；
- 自己替代 Diff Parser 生成确定性结构变化；
- 绕过 ActualChangeSet 直接从文本 Diff 猜 Impact；
- 把 Working Tree Overlay 发布为 Current Graph；
- 自动把 Unresolved 判定为 Complete；
- 执行 Commit、Push、Merge、Tag 或 Deploy。

---

## 5. 固定输入与分析身份

每次提交前验证必须固定：

```text
repositoryId
baseRevision
baseCurrentGraphRevision
workingTreeSnapshotHash
plannedChangeSetId
nodeChangeRequirementArtifactId
plannedImpactGraphId
ruleSetVersion
analysisScope
```

其中：

- `baseRevision`：本次 Working Tree 修改所基于的 Git Revision；
- `baseCurrentGraphRevision`：与 baseRevision 对应的正式 Current Graph；
- `workingTreeSnapshotHash`：当前 staged、unstaged、untracked 等完整工作区状态的稳定 Hash；
- `plannedChangeSetId`：规划阶段批准的 ChangeSet；
- `nodeChangeRequirementArtifactId`：Coding Agent 的实现要求来源；
- `ruleSetVersion`：实际 Impact 计算使用的传播规则版本。

Revision 或 Hash 不一致时不得复用之前结果。

---

## 6. Skill 1：extract-actual-change

### 6.1 目标

回答：**Coding Agent 实际改变了什么语义？**

### 6.2 输入

```text
Repository
Base Revision
Base Current Graph Revision
Working Tree
```

### 6.3 输出

```text
GitDiffSnapshot
WorkingTreeGraphOverlay
ActualChangeSet
```

### 6.4 阶段一：GitDiffSnapshot

不能只执行普通 `git diff`。Snapshot 必须覆盖完整 Working Tree：

```text
staged changes
unstaged changes
untracked files
renames
moves
deletes
binary change metadata
submodule pointer changes（如适用）
```

示例：

```yaml
diffId: diff-run-001
repositoryId: repo-001
baseRevision: abc123
workingTreeHash: sha256:xxx
changedFiles:
  - path: src/DeployService.java
    status: Modified
  - path: src/DeployController.java
    status: Modified
  - path: src/RetryPolicy.java
    status: Added
  - path: tests/DeployPolicyTest.java
    status: Modified
```

`GitDiffSnapshot` 是后续所有 Artifact 的输入身份之一。

### 6.5 阶段二：WorkingTreeGraphOverlay

针对变更文件执行增量语义扫描，构建：

```text
Base Current Graph
+
Changed File Semantic Delta
=
WorkingTreeGraphOverlay
```

示例：

```yaml
overlayId: worktree-overlay-001
baseRevision: abc123
workingTreeHash: sha256:xxx
addedNodes:
  - code:RetryPolicy
modifiedNodes:
  - code:DeployService.deployPolicy
addedEdges:
  - source: code:DeployService.deployPolicy
    relation: calls
    target: code:RetryPolicy.shouldRetry
removedEdges: []
```

Overlay 必须支持新增、删除和修改后的实体，不得要求实体必须预先存在于 Base Current Graph。

### 6.6 阶段三：ActualChangeSet

`ActualChangeSet` 不是文件级 Modified 列表，而是实际语义变化集合。

例如：

```diff
-deployPolicy(policy)
+deployPolicy(policy, retryPolicy)
```

应生成：

```yaml
changeId: AC001
targetEntityId: code:DeployService.deployPolicy
operation: Modify
aspect: Signature
before: deployPolicy(policy)
after: deployPolicy(policy, retryPolicy)
evidence:
  file: src/DeployService.java
  diffId: diff-run-001
```

同一方法新增 Retry 行为时，再生成独立变化：

```yaml
changeId: AC002
targetEntityId: code:DeployService.deployPolicy
operation: Modify
aspect: Behavior
behaviorType: Retry
sourceDiff: diff-run-001
```

变化必须原子化；Signature、Behavior、Configuration、Contract、Data、Test、Delivery 等不能因为发生在同一个文件中就合并为单一 Change。

### 6.7 确定性变化与语义变化分工

Parser / Diff Engine 负责：

```text
Type Added/Removed
Method Added/Removed
Parameter Added/Removed/TypeChanged
Field Changed
Inheritance Changed
API/Schema Changed
Configuration Changed
Database Schema Changed
Call Edge Changed
```

LLM 只处理难以纯静态确定的语义变化候选，例如：

```text
RetryBehaviorChanged
TransactionBehaviorChanged
FallbackBehaviorChanged
ExceptionBehaviorChanged
CachingBehaviorChanged
ConcurrencyBehaviorChanged
SecurityBehaviorChanged
SideEffectChanged
```

所有 LLM 语义结论必须保存 Diff Evidence、置信度和分析器版本。

---

## 7. Subagent 1：SemanticDiffAnalyst

### 7.1 作用

`SemanticDiffAnalyst` 只服务 `extract-actual-change`，用于识别代码 Diff 中静态分析器难以完全表达的行为语义变化。

### 7.2 输入

只接收受控上下文：

```text
Diff Hunk
Before Symbol Context
After Symbol Context
Static Semantic Delta
相关 Design / Planned Change（可选）
```

不得自由读取整个仓库后自行生成新的事实范围。

### 7.3 输出

```yaml
semanticChanges:
  - type: RetryBehaviorChanged
    targetEntityId: code:DeployService.deployPolicy
    confidence: 0.93
    evidenceRefs:
      - diff:hunk-12
    rationale: failure path now retries according to retryPolicy
```

### 7.4 边界

Subagent 的输出是语义变化候选，必须通过 Artifact Validation 才能进入正式 ActualChangeSet。

---

## 8. Skill 2：verify-impact-closure

### 8.1 目标

回答：

> ActualChangeSet 产生了哪些实际波及？每一个波及点形成了什么工程义务？这些义务是否已经被本次实现满足？

### 8.2 输入

```text
Validated ActualChangeSet
Base Current Graph
WorkingTreeGraphOverlay
RuleSetVersion
Planned ChangeSet
Planned ImpactGraph
NodeChangeRequirementArtifact
Acceptance Criteria
```

### 8.3 阶段一：ActualImpactGraph

核心公式：

```text
ActualImpactGraph =
F(
  ActualChangeSet,
  BaseCurrentGraph + WorkingTreeGraphOverlay,
  RuleSetVersion,
  Scope
)
```

同样的 ChangeSet、Overlay、RuleSet 和 Scope 必须得到可重放的 Impact 结果。

示例：

```yaml
impactRunId: actual-impact-run-001
changeId: AC001
seed: code:DeployService.deployPolicy
impacts:
  - impactId: AI001
    target: code:DeployController.deploy
    rule: SIGNATURE_CALLER_PROPAGATION
    impactType: RequiredModification
    path:
      - code:DeployController.deploy
      - calls
      - code:DeployService.deployPolicy
  - impactId: AI002
    target: code:BatchDeployJob.execute
    rule: SIGNATURE_CALLER_PROPAGATION
    impactType: RequiredModification
  - impactId: AI003
    target: code:AdminController.deploy
    rule: SIGNATURE_CALLER_PROPAGATION
    impactType: RequiredModification
  - impactId: AI004
    target: test:DeployPolicyTest
    rule: SIGNATURE_TEST_PROPAGATION
    impactType: TestModification
```

### 8.4 ActualImpactGraph 与 PlannedImpactGraph 分离

实际实现可能引入设计阶段没有预见的新依赖，因此：

```text
ActualImpactGraph != PlannedImpactGraph
```

这种差异不能自动视为错误，但必须进入 Reconciliation 和 Review。

---

## 9. ImpactObligationArtifact

### 9.1 为什么需要 Obligation

ImpactGraph 说明“谁受影响”，但 Commit Gate 需要判断“这个受影响节点必须做什么”。

因此把每个实际 Impact 转换为工程义务：

```text
Actual Impact
→ Engineering Obligation
```

### 9.2 Obligation 类型

第一版至少支持：

```text
RequiredModification
RequiredTest
RequiredReview
CompatibilityVerification
MigrationRequired
ReleaseActionRequired
Contained
NoModificationRequired
Unresolved
```

### 9.3 示例

```yaml
impactId: AI003
node: code:AdminController.deploy
obligationType: RequiredModification
reason: Caller must adapt to changed callee signature.
satisfactionRule:
  type: ActualChangeOrContainment
  expectedChangeAspect: CallSite
sourceRule: SIGNATURE_CALLER_PROPAGATION
```

测试义务：

```yaml
impactId: AI004
node: test:DeployPolicyTest
obligationType: RequiredTest
reason: Changed retry behavior requires verification.
requiredScenarios:
  - retryPolicy=0
  - retryPolicy=1
  - retryPolicy=3
  - retry exhausted
```

### 9.4 Obligation 满足判定

不能简单以“文件发生修改”作为满足条件。

例如 RequiredModification 必须满足：

```text
存在语义上匹配的 Actual Change
OR
存在经规则证明的 Containment / Compatibility Evidence
```

否则状态为：

```text
MissingPropagationImplementation
```

---

## 10. ImplementationReconciliationArtifact

这一 Artifact 同时承担两个方向的对账。

### 10.1 Plan → Actual Reconciliation

检查：

```text
NodeChangeRequirementArtifact
→ ActualChangeSet
```

用于发现规划要求完全没有实现的情况。

状态建议：

```text
Conformed
PartiallyConformed
MissingPlannedImplementation
ExplicitlyDeferred
ChangedDesign
Unverified
```

示例：

```yaml
plannedRequirementId: NCR-003
target: code:DeployConfig.retryPolicy
expected: Add configuration default
actualChanges: []
status: MissingPlannedImplementation
```

### 10.2 Actual Impact → Actual Reconciliation

检查：

```text
ImpactObligationArtifact
→ ActualChangeSet / Context / Test Evidence
```

状态建议：

```text
Satisfied
Contained
MissingPropagationImplementation
UnexpectedImplementation
Unverified
```

示例：

```yaml
impactId: AI003
target: code:AdminController.deploy
obligation: RequiredModification
actualChanges: []
containmentEvidence: []
status: MissingPropagationImplementation
```

### 10.3 Unexpected Implementation

如果 ActualChangeSet 中存在无法映射到 Planned Change、Node Requirement 或传播义务的变化，例如设计没有任何数据库变化但实际新增 DDL，应标记：

```text
UnexpectedImplementation
```

计划外变化不一定错误，但必须经过人工 Review 后才能提交。

---

## 11. VerificationCoverageArtifact

### 11.1 目标

代码修改闭包不等于功能验证闭包。系统还必须证明 Change、Impact 和 Acceptance Criterion 已经被适当测试或验证。

### 11.2 两类 Coverage

#### Structural Coverage

检查：

```text
受影响代码节点
→ 是否存在需要的 Test / Verification
```

#### Semantic Obligation Coverage

检查：

```text
Behavior Change / Acceptance Criterion
→ 是否存在对应测试场景
```

不能使用单纯 Line Coverage 替代语义覆盖。

### 11.3 示例

```yaml
verificationId: VC-001
changeId: AC002
behavior: RetryBehaviorChanged
acceptanceCriteria:
  - AC-RETRY-001
requiredScenarios:
  - retryPolicy=0
  - retryPolicy=1
  - retryPolicy=3
  - retry exhausted
mappedTests:
  - DeployPolicyTest.retryZero
  - DeployPolicyTest.retryThree
missingScenarios:
  - retry exhausted
status: Incomplete
```

### 11.4 Test Evidence

测试结果必须带：

```text
testId
testCommand
testType
result
executionHash
workingTreeHash
timestamp
relatedChange
relatedImpact
relatedAcceptanceCriterion
```

Working Tree 变化后，旧 Test Evidence 也必须按策略失效或重新确认。

---

## 12. Skill 3：review-precommit-completeness

### 12.1 目标

回答：**当前 Working Tree 是否已经具备提交条件？**

### 12.2 输入

必须至少包含：

```text
DesignIntentIR
AlignmentArtifact
Planned ChangeSet
Planned ImpactGraph
NodeChangeRequirementArtifact
ChangePlanReview
GitDiffSnapshot
WorkingTreeGraphOverlay
ActualChangeSet
ActualImpactGraph
ImpactObligationArtifact
ImplementationReconciliationArtifact
VerificationCoverageArtifact
```

### 12.3 Review 不是再次生成 Change

此 Skill 不再修改 ChangeSet、Impact 或 Requirement，只进行跨 Artifact 完整性验证和风险归纳。

主要检查：

```text
Planned Requirement 是否全部有实现结论
Actual Change 是否全部可解释
Actual Impact 是否全部形成 Obligation
Required Obligation 是否全部 Satisfied / Contained
Behavior Change 是否全部映射到验证场景
Critical / High Unresolved 是否为 0
Unexpected Implementation 是否全部人工确认
Revision / RuleSet / WorkingTreeHash 是否一致
```

---

## 13. Subagent 2：PreCommitReviewer

### 13.1 作用

`PreCommitReviewer` 是独立审查者，只消费固定快照，不参与前面的 ActualChangeSet、Impact 或 Requirement 生成。

其目标是避免分析流程自己证明自己正确。

### 13.2 反向审查方式

Reviewer 应从最终要求向设计反向追踪：

```text
Test Evidence
↑
Impact Obligation
↑
Actual Impact
↑
Actual Change
↑
Planned Requirement
↑
Design Intent
```

### 13.3 重点发现

```text
MissingPlannedImplementation
MissingPropagationImplementation
MissingTest
UnexpectedImplementation
AmbiguousContainment
UnresolvedDynamicDependency
RevisionDrift
RuleSetMismatch
StaleReview
UnverifiedBehavior
```

### 13.4 禁止事项

Reviewer 不得：

- 修改代码；
- 修改 ActualChangeSet；
- 修改 ImpactGraph；
- 自己补写缺失的 Test Evidence；
- 把 Unresolved 直接降级为 Complete；
- 执行 Commit。

---

## 14. PreCommitReview Artifact

最终 Review 必须是结构化 Artifact，而不是一句自然语言“看起来没有问题”。

示例：

```yaml
reviewId: precommit-review-001
repositoryId: repo-001
baseRevision: abc123
baseCurrentGraphRevision: graph-abc123
workingTreeHash: sha256:xxx
ruleSetVersion: impact-rules-v3

planReconciliation:
  complete: false

impactClosure:
  complete: false

verificationCoverage:
  complete: false

blockingIssues:
  - type: MissingPlannedImplementation
    plannedRequirementId: NCR-003
    entity: code:DeployConfig.retryPolicy

  - type: MissingPropagationImplementation
    impactId: AI003
    entity: code:AdminController.deploy

  - type: MissingTest
    behavior: retry-exhausted

unexpectedChanges: []
unresolved: []

decision: BlockCommit
```

通过时：

```yaml
completeness: Complete
decision: ReadyToCommit
```

---

## 15. Commit Gate

### 15.1 ReadyToCommit 不是评分阈值

不建议通过“95% 完成”之类的分数自动放行。Commit Gate 应使用硬条件。

第一版建议：

```text
所有 Planned Requirement
= Conformed / ExplicitlyDeferred(已人工批准)

所有 RequiredModification
= Satisfied / Contained

所有 RequiredTest
= Mapped + Passed

所有 CompatibilityVerification
= Verified

所有 UnexpectedImplementation
= Reviewed

Critical / High Unresolved
= 0

currentWorkingTreeHash
= reviewedWorkingTreeHash
```

满足全部条件才输出：

```text
ReadyToCommit
```

否则：

```text
BlockCommit
```

### 15.2 Review 失效

以下任何变化都使 Review 失效：

```text
Working Tree 变化
Base Revision 变化
Graph Revision 变化
RuleSet Version 变化
Planned ChangeSet 变化
NodeChangeRequirementArtifact 变化
```

必须重新运行受影响阶段。

---

## 16. MCP Tool 设计

MCP 仍然按照能力设计，而不是按照 Workflow Step 设计。

第一版建议保留 7 个核心工具。

### 16.1 get_git_diff_snapshot

作用：

```text
Working Tree
→ immutable GitDiffSnapshot
```

职责：

- 读取 staged / unstaged / untracked；
- 识别 rename / delete / added；
- 计算 Working Tree Hash；
- 输出文件和 Diff Evidence；
- 只读，不执行 add、reset、checkout 或 commit。

### 16.2 build_worktree_graph_overlay

作用：

```text
Base Current Graph
+
Changed Files
→ WorkingTreeGraphOverlay
```

职责：

- 增量解析变化文件；
- 生成 added / modified / removed nodes；
- 生成关系 delta；
- 支持新增实体；
- 不发布 Current Graph。

### 16.3 get_entity_context

复用规划阶段工具。

作用：

```text
Entity
→ bounded current/worktree context
```

用于获取：

```text
file
symbol
signature
callers
callees
fields
tests
contracts
configuration
provenance
```

### 16.4 analyze_change_impacts

复用规划阶段核心 Impact Tool。

输入从 Planned ChangeSet 切换为 ActualChangeSet，并允许指定：

```text
graphView = BaseCurrentGraph + WorkingTreeGraphOverlay
```

输出 ActualImpactGraph。

### 16.5 select_verification_tests

作用：

```text
ActualChangeSet
+
ActualImpactGraph
+
Acceptance Criteria
+
Test Graph
→ Verification Obligations
```

返回：

```text
required tests
existing mapped tests
missing scenarios
contract tests
integration tests
manual verification obligations
```

### 16.6 run_verification_checks

作用：受控执行验证命令。

允许：

```text
compile
static check
selected unit tests
integration tests
contract tests
approved validation commands
```

禁止：

```text
commit
push
merge
rebase
tag
deploy
production mutation
```

输出结构化 Test / Validation Evidence，并绑定 Working Tree Hash。

### 16.7 validate_artifact

统一验证提交前 Artifact：

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

校验范围包括：

```text
JSON Schema
Ontology / SHACL（适用时）
Revision consistency
WorkingTreeHash consistency
Cross-reference integrity
Change → Impact coverage
Impact → Obligation coverage
Requirement → Actual reconciliation coverage
Evidence completeness
```

---

## 17. Skill、Subagent、MCP 与 Artifact 的职责边界

```text
Skill
= Procedure / Policy
说明这个阶段应该如何完成

Subagent
= Bounded Semantic Reasoning
解决静态规则难以直接确定的不确定性

MCP Tool
= Fact / Deterministic Capability
读取 Git、图谱、执行传播、测试和校验

Artifact
= Immutable Stage State
固定阶段输出、证据和 Revision

PreCommitVerificationAgent
= Orchestration
严格按照 Artifact 状态推进流程
```

核心原则：

> 能由 Parser、Graph Engine、Rule Engine 和 Validator 确定的内容，不交给 Subagent；Subagent 只处理语义判断和独立审查。

---

## 18. 中间 Artifact 总表

| Artifact | 核心问题 |
| --- | --- |
| `GitDiffSnapshot` | 当前 Working Tree 到底变了哪些文件和行 |
| `WorkingTreeGraphOverlay` | 修改后的临时代码语义图是什么 |
| `ActualChangeSet` | 实际发生了哪些原子语义变化 |
| `ActualImpactGraph` | 实际变化会波及哪些实体 |
| `ImpactObligationArtifact` | 每个波及点必须采取什么工程动作 |
| `ImplementationReconciliationArtifact` | 规划要求和实际波及义务是否都被实现 |
| `VerificationCoverageArtifact` | 功能、行为和测试义务是否被验证 |
| `PreCommitReview` | 当前 Working Tree 是否可以提交 |

这些 Artifact 都保留，不因为 Skill / Subagent 数量减少而合并。

---

## 19. 与规划阶段 Artifact 的完整追溯

提交前验证必须能够回答任意一个修改要求为什么存在。

完整链路：

```text
Design Evidence
      ↓
DesignIntentIR
      ↓
AlignmentArtifact
      ↓
Planned ChangeSet
      ↓
NodeChangeRequirementArtifact
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

同时允许发现由实际代码引入的新波及：

```text
ActualChangeSet
      ↓
Unexpected Actual Impact
      ↓
New Impact Obligation
      ↓
Additional Required Modification / Test
```

这类新增义务必须进入 Review，不能因为规划阶段未发现就忽略。

---

## 20. 完整示例

规划阶段产生：

```text
NCR-001 DeployService.deployPolicy
增加 retryPolicy

NCR-002 DeployController.deploy
传递 retryPolicy

NCR-003 BatchDeployJob.execute
使用默认 retryPolicy

NCR-004 DeployPolicyTest
增加 retry 行为测试
```

Coding Agent 实际修改：

```text
DeployService.java
DeployController.java
DeployPolicyTest.java
```

忘记修改 BatchDeployJob。

### 20.1 ActualChangeSet

```text
AC001 DeployService.deployPolicy SignatureChanged
AC002 DeployService.deployPolicy RetryBehaviorChanged
AC003 DeployController.deploy CallSiteChanged
AC004 DeployPolicyTest TestChanged
```

### 20.2 ActualImpactGraph

代码本体发现：

```text
DeployService.deployPolicy
├── DeployController.deploy
├── BatchDeployJob.execute
└── AdminController.deploy
```

其中 `AdminController` 在规划阶段没有被发现。

### 20.3 Impact Obligation

```text
DeployController.deploy
→ RequiredModification
→ Satisfied by AC003

BatchDeployJob.execute
→ RequiredModification
→ Missing

AdminController.deploy
→ RequiredModification
→ Missing

DeployPolicyTest
→ RequiredTest
→ PartiallySatisfied
```

### 20.4 Plan Reconciliation

```text
NCR-001 → Conformed
NCR-002 → Conformed
NCR-003 → MissingPlannedImplementation
NCR-004 → PartiallyConformed
```

### 20.5 Verification Coverage

```text
retryPolicy=0     → Covered
retryPolicy=1     → Covered
retryPolicy=3     → Covered
retry exhausted   → Missing
```

### 20.6 PreCommitReview

```text
Blocking Issues:
- BatchDeployJob: MissingPlannedImplementation
- AdminController: MissingPropagationImplementation
- retry exhausted: MissingTest

Decision:
BlockCommit
```

这说明系统同时发现：

1. **规划中明确要求但实现遗漏的内容；**
2. **实际代码变化新增、规划阶段没有预见的波及；**
3. **行为语义对应的测试场景遗漏。**

---

## 21. 两套流程形成完整闭环

整个系统最终可以抽象成：

```text
设计阶段
DesignIntent
→ SHOULD

实现阶段
Coding Agent
→ CODE

提交前
ActualChangeSet
→ DID

本体推理
ImpactObligation
→ MUST

对账和验证
PreCommitReview
→ COMPLETE?
```

因此代码本体不只是回答“某个方法依赖谁”，而是参与构建完整的软件变更正确性闭环：

```text
What should change?
→ Planned Change

What did change?
→ Actual Change

What else must change because of it?
→ Impact Obligation

Did we satisfy every planned and derived obligation?
→ Reconciliation + Verification

Can this exact Working Tree be committed?
→ PreCommit Gate
```

---

## 22. 第一版推荐边界

为了控制实现复杂度，第一版建议只支持：

```text
单 Repository
单 Base Revision
ClosedRepositoryScope
Java / 当前已支持语言
代码结构、调用、字段、配置、API、测试关系
Git Working Tree Overlay
固定 RuleSetVersion
受控编译和测试命令
```

第一版暂不要求解决所有运行时动态关系。以下情况允许进入 `Unresolved`：

```text
reflection
runtime dependency injection ambiguity
dynamic callback
function pointer
generated code not available
external repository consumer
runtime-only configuration routing
```

但只要这些 Unresolved 位于 Critical / High 风险传播路径，就必须阻止 `ReadyToCommit`，除非经过显式人工 Gate。

---

## 23. 最终结论

提交前验证架构保持与规划阶段相同的设计原则：减少 Agent 和 Skill 数量，但不减少中间 Artifact，也不允许 LLM 绕过确定性事实链。

最终推荐结构为：

```text
1 个主 Agent
PreCommitVerificationAgent

3 个 Skill
extract-actual-change
verify-impact-closure
review-precommit-completeness

2 个 Subagent
SemanticDiffAnalyst
PreCommitReviewer

7 个 MCP Tool
get_git_diff_snapshot
build_worktree_graph_overlay
get_entity_context
analyze_change_impacts
select_verification_tests
run_verification_checks
validate_artifact

8 个提交前 Artifact
GitDiffSnapshot
WorkingTreeGraphOverlay
ActualChangeSet
ActualImpactGraph
ImpactObligationArtifact
ImplementationReconciliationArtifact
VerificationCoverageArtifact
PreCommitReview
```

系统最重要的判断不是“所有受影响节点都在 Git Diff 中”，而是：

> **每一个 Planned Requirement 和每一个由实际变化派生出的 Impact Obligation，都必须有可追溯的实现、吸收、验证或人工决策证据。**

只有这一条件在精确 Working Tree Snapshot 上成立，系统才能输出 `ReadyToCommit`。