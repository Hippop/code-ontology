# Agent 驱动的组件设计到完整变更要求规划架构

## 1. 文档目标

本文定义如何使用一个主 Agent、三个 Skill、两个 Subagent 和一组受控 MCP 能力，把组件设计文档稳定转换为可交给开发、测试和架构评审使用的完整变更要求。

本设计只覆盖**规划期**：

```text
组件设计文档
→ 结构化设计意图
→ 设计实体与 Current Graph 对齐
→ 原子 ChangeSet
→ 基于固定 Current Graph / RuleSet 的 Planning Impact
→ 节点级变更要求
→ 完整性审查
→ 确定性 Markdown
→ 人工 Gate
```

规划期只读取设计、图谱、规则和证据，不修改 Current Graph、代码或 Git。只有最终 `ChangePlanReview` 通过人工 Gate 后，后续实现 Agent 才能进入 Approved Change 的代码实现流程。

本文是在现有需求到代码设计、Change Model、Impact Rule 和 Agent Runtime 基础上的**规划阶段精简架构**。精简的对象是 Skill 和 Subagent 数量，不是中间产物、证据链和校验 Gate。

---

## 2. 核心结论

规划阶段采用：

```text
1 个主 Agent
3 个 Skill
2 个 Subagent
6 个核心 MCP 能力
6 个核心中间 Artifact
1 个最终 Markdown 视图
```

核心原则：

> **减少执行角色，不减少中间产物。**

Skill 可以合并多个连续步骤，但阶段事实必须通过独立 Artifact 固定。任何 Agent 都不能从设计文档直接跳到最终修改要求，也不能绕过 ChangeSet 直接做 Impact。

完整 Artifact 主链为：

```text
DesignIntentIR
      ↓
AlignmentArtifact
      ↓
ChangeSet
      ↓
ImpactGraph
      ↓
NodeChangeRequirementArtifact
      ↓
ChangePlanReview
      ↓
Final Change Requirement Markdown
```

其中 Markdown 不是事实源；Artifact 才是事实源。Markdown 只是已验证 Artifact 的确定性视图。

---

## 3. 职责模型

整个系统只保留五类职责：

| 类型 | 职责 | 不负责 |
| --- | --- | --- |
| `ChangePlannerAgent` | 编排流程、固定 Revision、推进 Gate、管理 Artifact | 自由扫描、自由改码、替代规则引擎 |
| Skill | 定义稳定步骤、输入输出、Hard Rules、停止条件、Tool Policy | 保存可变事实 |
| Subagent | 处理高不确定性语义判断和独立审查 | 确定性图遍历、Schema 校验 |
| MCP / Tool | 提供事实、受控查询、确定性分析和验证能力 | 自由语义推断 |
| Artifact | 固定阶段状态、证据、版本和引用关系 | 执行推理 |

统一定义为：

```text
Skill     = Procedure
Subagent  = Bounded Reasoning
MCP       = Fact / Capability
Artifact  = State
MainAgent = Orchestration
```

能由 Parser、RuleSet、Graph Engine、Schema、Ontology 或 SHACL 确定完成的工作，不应新增 Subagent。

---

## 4. 总体架构

```text
                         User / Workflow
                                │
                                ▼
                    ┌─────────────────────┐
                    │ ChangePlannerAgent  │
                    │   主规划编排 Agent   │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │ Skill 1             │
                    │ understand-change   │
                    └──────────┬──────────┘
                               │
             ┌─────────────────┼─────────────────┐
             ▼                 ▼                 ▼
      DesignIntentIR    AlignmentArtifact     ChangeSet
             │                 │                 │
             └─────────────────┴─────────────────┘
                               │
                         validate gate
                               │
                               ▼
                    ┌─────────────────────┐
                    │ Skill 2             │
                    │ analyze-impact      │
                    └──────────┬──────────┘
                               │
                               ▼
                         ImpactGraph
                               │
                         validate gate
                               │
                               ▼
                    ┌─────────────────────┐
                    │ Skill 3             │
                    │ build-change-plan   │
                    └──────────┬──────────┘
                               │
                               ▼
              NodeChangeRequirementArtifact
                               │
                               ▼
                    ChangePlanReviewer
                               │
                               ▼
                      ChangePlanReview
                               │
                         validate gate
                               │
                               ▼
                  render_change_document
                               │
                               ▼
              Final Change Requirement.md
                               │
                               ▼
                       Human ImpactReview
```

这条链路必须保持单向推进。需要返工时，应回到产生错误 Artifact 的阶段重新生成，而不是在后续 Artifact 中静默修补前序事实。

---

## 5. 主 Agent：`ChangePlannerAgent`

### 5.1 定位

`ChangePlannerAgent` 是规划期唯一的主编排 Agent。它负责维护分析上下文和状态，不承担所有细节推理。

它负责：

1. 固定 `repositoryId`、`requirementId`、`designRevisionId`、`currentRevision`、`ruleSetVersion` 和 `scopeType`；
2. 按顺序执行三个 Skill；
3. 创建并保存六个核心 Artifact；
4. 在每个阶段调用 Artifact Validation；
5. 根据 `Unresolved`、`Ambiguous`、Revision Drift 和 Completeness 决定继续、回退或停止；
6. 最终请求 `ImpactReview` 人工 Gate。

### 5.2 禁止事项

`ChangePlannerAgent` 不得：

- 从设计 Markdown 直接生成最终修改文档；
- 跳过 Alignment 把自然语言名称当 Current Entity；
- 跳过 ChangeSet 直接执行 Impact；
- 自己实现图传播算法；
- 把 PlantUML 声明当成 Current Graph 事实；
- 修改 Current Graph、代码或 Git；
- 因为“候选看起来合理”就把 Ambiguous Alignment 改成 Confirmed；
- 在后续阶段自动切换 `currentRevision` 或 `ruleSetVersion`。

---

## 6. 六个核心中间 Artifact

中间产物全部保留。Skill 可以合并执行步骤，但 Artifact 不合并。

### 6.1 `DesignIntentIR`

回答：**设计希望发生什么变化？**

它是组件设计场景下对 Requirement IR 的规划期投影，保留 Design Revision、Section、行号和原始证据，但暂不声明具体 Current Code Entity。

示例：

```yaml
requirementId: REQ-1001
designRevisionId: design-v1.2

designEntities:
  - id: desired:deployPolicy
    type: Interface
    name: deployPolicy

intents:
  - intentId: intent-001
    desiredEntityId: desired:deployPolicy
    operation: Modify
    aspect: Signature
    before:
      parameters: [policy]
    after:
      parameters: [policy, retryPolicy]

  - intentId: intent-002
    desiredEntityId: desired:deployPolicy
    operation: Modify
    aspect: Behavior
    after:
      failureBehavior: retry

acceptanceCriteria:
  - retryPolicy=3 时失败最多重试 3 次

evidence:
  - section: 1.1 deployPolicy
    startLine: 32
    endLine: 38

unresolved: []
```

Hard Rule：不能从自然语言描述猜具体代码实体；明确事实、推断、建议和未解决问题必须分开。

### 6.2 `AlignmentArtifact`

回答：**设计实体对应 Current Graph 中的什么？**

每次确认产生不可变 `alignmentRevision`。候选生成和候选判断可以由 AI 辅助，但候选不等于事实。

```yaml
alignmentRevision: alignment-v17
currentRevision: git:a7123c

items:
  - desiredEntityId: desired:deployPolicy
    candidates:
      - entityId: code:DeployService.deployPolicy
        confidence: 0.96
      - entityId: code:LegacyDeployService.deployPolicy
        confidence: 0.68
    selectedEntityId: code:DeployService.deployPolicy
    alignmentType: ModifyExisting
    status: Confirmed
    evidence:
      - signature-match
      - module-match
      - relation-match
```

支持的关键状态：

```text
Confirmed
NoMatch
Ambiguous
Unreviewed
Rejected
```

`Ambiguous` 和 `Unreviewed` 不能被转换成精确 Modify / Remove 目标。

### 6.3 `ChangeSet`

回答：**本次有哪些正式、原子化、机器可计算的变化？**

`ChangeSet` 是自然语言理解和确定性 Impact Engine 之间的分界线。

```yaml
schemaVersion: planning-change/v1
changeSetId: changeset-001
requirementId: REQ-1001
designRevisionId: design-v1.2
currentRevision: git:a7123c
alignmentRevision: alignment-v17
changeSetHash: sha256:...

changes:
  - changeId: C001
    sourceIntent: intent-001
    targetEntityId: code:DeployService.deployPolicy
    operation: Modify
    aspect: Signature
    before: deployPolicy(policy)
    after: deployPolicy(policy, retryPolicy)

  - changeId: C002
    sourceIntent: intent-002
    targetEntityId: code:DeployService.deployPolicy
    operation: Modify
    aspect: Behavior
    after:
      onFailure: retry(retryPolicy)
```

Hard Rules：

- Signature、Behavior、Configuration、Data、Contract、Test、Delivery 等独立变化分别建模；
- 同一接口同时发生输入和行为变化时必须拆 Change；
- Confirmed Alignment 才可写 Current `targetEntityId`；
- NoMatch 可形成 Add；
- Ambiguous / Unreviewed 保持 Unresolved；
- Change 必须保留来源 Design Intent 和 Evidence。

### 6.4 `ImpactGraph`

回答：**每个 Change 会波及哪些实体，为什么？**

Impact 不是“可达节点列表”，而是带规则、路径、状态和停止原因的规划结果。

```yaml
impactRunId: impact-run-98
changeSetId: changeset-001
currentRevision: git:a7123c
ruleSetVersion: impact-rules-v3
scopeType: ClosedRepositoryScope

impacts:
  - impactId: I001
    changeId: C001
    seed: code:DeployService.deployPolicy
    target: code:DeployController.deploy
    path:
      - code:DeployController.deploy
      - calls
      - code:DeployService.deployPolicy
    ruleId: SIGNATURE_CALLER_PROPAGATION
    impactType: RequiredModification
    confidence: 1.0
    state: Confirmed

  - impactId: I002
    changeId: C001
    target: test:DeployPolicyTest
    ruleId: SIGNATURE_TEST_PROPAGATION
    impactType: TestModification
    state: Confirmed
```

每个 Impact 至少需要关联：

```text
Source Change
Seed
Affected Entity
Impact Type
Rule
Path
State
Confidence
Stop / Absorption Reason（如有）
Evidence / Provenance
```

### 6.5 `NodeChangeRequirementArtifact`

回答：**每个受影响节点具体应该满足什么修改要求？**

它不是 Patch，也不是宽泛建议，而是面向实现 Agent 的受控工程约束。

```yaml
planId: change-plan-001

requirements:
  - requirementId: NCR-001
    file: src/deploy/DeployController.java
    symbol: DeployController.deploy
    sourceChanges: [C001]
    sourceImpacts: [I001]
    reason: CallerOfChangedSignature

    requirements:
      - type: CallSiteChange
        action: Update deployPolicy invocation to provide retryPolicy.
        valueSource: DeployRequest.retryPolicy

      - type: Compatibility
        action: Use the declared default when retryPolicy is absent.

    evidence:
      - intent:intent-001
      - impact:I001
      - context:ctx-123
```

测试节点必须正式进入该 Artifact，而不是只写在 Markdown 附注中：

```yaml
  - requirementId: NCR-010
    file: src/test/.../DeployPolicyTest.java
    symbol: DeployPolicyTest
    requirementType: TestModification
    sourceChanges: [C001, C002]
    requirements:
      - retryPolicy = 0
      - retryPolicy = 1
      - retryPolicy = 3
      - retryPolicy exceeds allowed maximum
```

### 6.6 `ChangePlanReview`

回答：**整个规划是否完整、可信，并可以进入实现阶段？**

它是独立 Reviewer 的结构化输出，不允许只返回自然语言 `looks good`。

```yaml
reviewId: review-001
planId: change-plan-001

completeness: Partial

coverage:
  designIntentCoverage: 1.0
  alignmentCoverage: 0.95
  changeImpactCoverage: 1.0
  impactRequirementCoverage: 0.94
  testCoverage: 0.88

blockingIssues:
  - id: issue-001
    type: AmbiguousAlignment
    entity: RetryPolicyMapper

  - id: issue-002
    type: DynamicDependency
    description: callback target unresolved

decision: NeedsReview
```

只有满足定义范围内的完整性条件，才能输出：

```yaml
completeness: Complete
decision: ReadyForImplementation
```

---

## 7. 三个 Skill

### 7.1 Skill 1：`understand-change`

核心问题：**到底要改什么？**

它内部顺序生成三个独立 Artifact：

```text
Design Document
      ↓
DesignIntentIR
      ↓
AlignmentArtifact
      ↓
ChangeSet
```

#### 输入

```text
repositoryId
requirementId
designRevisionId
currentRevision
Component Design Document
```

#### 使用能力

```text
get_design_context
search_code_entities
get_entity_context
validate_artifact
ChangeAnalyst Subagent（仅在需要语义判断时）
```

#### 工作步骤

1. 固定 Design Revision 和 Current Revision；
2. 从设计文档提取设计实体、接口、字段、行为、GWT、配置、数据、测试和 Evidence；
3. 生成并校验 `DesignIntentIR`；
4. 对每个 Desired Entity 搜索 Current Graph 候选；
5. 对高歧义候选调用 `ChangeAnalyst`；
6. 生成并校验 `AlignmentArtifact`；
7. 将每个独立设计变化原子化为 Change；
8. 生成并校验 `ChangeSet`。

#### Hard Rules

- 不减少任何中间 Artifact；
- 不从自然语言直接猜代码实体；
- PlantUML 只作为 Design Evidence；
- Ambiguous Alignment 不强行确认；
- Change 必须原子化；
- 每个 Change 必须可回溯 Design Intent；
- ChangeSet 未校验通过不得进入 Impact。

#### Stop Conditions

出现以下情况必须停止或返回 NeedsReview：

```text
Design Revision 缺失
Current Revision 不存在或不属于目标 Repository
关键设计事实无 Evidence
Modify / Remove 的关键 Alignment 未确认
Artifact 校验失败
Revision 漂移
```

### 7.2 Skill 2：`analyze-impact`

核心问题：**这些变化会波及什么？**

这是规划系统中最应保持确定性的阶段。

#### 输入

```text
Validated ChangeSet
currentRevision
ruleSetVersion
scopeType
```

#### 输出

```text
ImpactGraph
```

#### 使用能力

```text
analyze_change_impacts
validate_artifact
```

默认不调用 Subagent。Graph Traversal、方向判断、传播、吸收、停止和状态转换由 Ontology / Graph / Rule Engine 完成。

#### 核心模型

```text
ImpactGraph = F(ChangeSet, CurrentGraphRevision, RuleSetVersion, Scope)
```

相同的 ChangeSet Hash、Current Revision、RuleSet Version 和 Scope 应产生可重放的结果。

#### Hard Rules

- 图可达只产生候选，规则决定真实传播语义；
- 依赖方向和影响传播方向分离；
- 每条路径保存 Rule、State、Confidence 和 Stop Reason；
- 动态回调、反射、函数指针、运行时路由等无法证明的关系保持 Unresolved；
- 不能因为分析程序正常结束就宣称 Completeness=Complete。

### 7.3 Skill 3：`build-change-plan`

核心问题：**每个受影响节点到底要满足什么修改要求，并且计划是否完整？**

#### 输入

```text
DesignIntentIR
AlignmentArtifact
Validated ChangeSet
Validated ImpactGraph
```

#### 输出

```text
NodeChangeRequirementArtifact
ChangePlanReview
Final Change Requirement Markdown
```

#### 使用能力

```text
get_entity_context
validate_artifact
render_change_document
ChangePlanReviewer Subagent
```

#### 工作步骤

1. 对每个 `RequiredModification`、`TestModification`、`ReviewRequired` Impact 读取精确节点 Context；
2. 将 Change + Impact Path + Code Context + Design Evidence 组合为 Node Change Requirement；
3. 按文件、符号、字段、契约、配置和测试组织 Requirement；
4. 生成并校验 `NodeChangeRequirementArtifact`；
5. 调用独立 `ChangePlanReviewer`；
6. 生成并校验 `ChangePlanReview`；
7. 只有 Artifact 校验通过后，调用确定性 Renderer 输出 Markdown。

#### Hard Rules

- 先确定 Impact Node，再读取有界 Context，不允许无目标地把整个仓库交给模型；
- Requirement 应是约束，不是“适当修改”“酌情处理”类宽泛建议；
- 每个 Required Modification 必须关联 Change 和 Impact；
- 行为、契约、配置变化必须有可验证 Test Obligation 或明确说明为何不需要；
- Markdown 不得成为新的事实来源。

---

## 8. 两个 Subagent

### 8.1 `ChangeAnalyst`

服务于 `understand-change`。

它合并原本容易拆成多个角色的设计理解和实体对齐判断，只处理**高不确定性语义问题**。

典型任务：

```text
设计中的 deployPolicy 到底对应：
A. DeployService.deployPolicy
B. LegacyDeployService.deployPolicy
C. PolicyManager.apply
```

它可以根据名称、类型、模块、签名、调用关系、设计流程和证据给出候选排序、解释和置信度。

它的输出效果是：

```text
复杂设计文本
→ 更稳定的结构化 Design Intent

Desired Entity + Current Candidates
→ 推荐 Alignment / Ambiguous / NoMatch
```

但必须遵守：

```text
Subagent Recommendation ≠ Confirmed Fact
```

是否能进入精确 Change 仍由 Alignment 状态和 Gate 决定。

### 8.2 `ChangePlanReviewer`

服务于 `build-change-plan`，与规划生成逻辑保持独立。

它从反方向检查：

```text
DesignIntentIR
      ↓
AlignmentArtifact
      ↓
ChangeSet
      ↓
ImpactGraph
      ↓
NodeChangeRequirementArtifact
```

必须检查至少六类覆盖：

1. **Intent Coverage**：每个设计变化是否进入至少一个 Change；
2. **Alignment Coverage**：Modify / Remove 是否具有可用 Current Entity；
3. **Impact Coverage**：每个 Change 是否有 Seed / Impact Result；
4. **Requirement Coverage**：每个 Required Modification 是否有 Node Requirement；
5. **Test Coverage**：行为和契约变化是否形成测试义务；
6. **Risk / Unresolved**：是否仍存在 Ambiguous Alignment、动态依赖、外部依赖、缺失图源、Revision Drift 或证据缺口。

Reviewer 不修改前序 Artifact，只输出 `ChangePlanReview` 和返工目标。

---

## 9. 六个核心 MCP / Tool 能力

这里定义的是逻辑能力边界，不要求与当前实现函数一一同名。若现有 MCP 保持只读，Artifact Validation 和 Rendering 也可以由同一 Agent Gateway 下的受控 Tool 提供；无论实现形态如何，都不能写 Current Graph。

### 9.1 `get_design_context`

作用：读取固定需求和设计上下文。

返回：

```text
Requirement
DesignRevision
Document Content / Parsed Sections
DocumentEvidence
Revision Hash
```

要求：必须按指定 Revision 读取，不能自动切换到“最新版本”。

### 9.2 `search_code_entities`

作用：为 Desired Entity 搜索 Current Graph 候选。

可使用：

```text
name
type
module
signature
relations
stable id
```

输出候选和图证据，不自动 Confirm Alignment。

### 9.3 `get_entity_context`

作用：为某个 Current Entity 提供有界、可追溯上下文。

返回至少包括：

```text
entityId
file
symbol
type
signature
parents
callers
callees
fields
contracts
tests
relevant relations
source location
provenance
```

它是 Alignment 和 Node Requirement 阶段最常用的查询工具。

### 9.4 `analyze_change_impacts`

作用：执行规则感知的 Planning Impact。

输入：

```text
Validated ChangeSet
repositoryId
currentRevision
ruleSetVersion
scopeType
```

输出：

```text
ImpactRun
Seed Resolution
Impact Nodes / Edges
Paths
Rules
States
Confidence
Absorption / Stop Reason
Completeness Signals
```

这是整个系统最核心的确定性分析能力，不应由 LLM 自行模拟。

### 9.5 `validate_artifact`

统一验证六类核心 Artifact。

按 Artifact Type 执行：

```text
JSON / Schema
Ontology
SHACL
Cross Reference
Revision Consistency
Evidence Presence
Stable ID / Hash
```

关键交叉引用必须验证，例如：

```text
Change.sourceIntent → DesignIntentIR.intentId
Change.targetEntityId → Confirmed Alignment
Impact.changeId → ChangeSet.changeId
NodeRequirement.sourceImpacts → ImpactGraph.impactId
Review.planId → NodeChangeRequirementArtifact.planId
```

### 9.6 `render_change_document`

作用：将已验证 Artifact 确定性渲染为 Markdown。

输入：

```text
DesignIntentIR
AlignmentArtifact
ChangeSet
ImpactGraph
NodeChangeRequirementArtifact
ChangePlanReview
```

输出：

```text
Final Change Requirement.md
```

要求固定章节、排序、字段、转义和引用格式。相同 Artifact 应得到相同 Markdown。

---

## 10. Gate 与状态推进

规划期至少有四类 Gate，但只有需要责任判断的地方必须人工参与。

### 10.1 Input Revision Lock

自动 Gate。固定：

```text
repositoryId
requirementId
designRevisionId
currentRevision
ruleSetVersion
scopeType
```

后续阶段不能隐式替换。

### 10.2 Artifact Validation Gate

自动 Gate。每个核心 Artifact 生成后立即校验，失败则停止当前阶段。

### 10.3 Alignment Review Gate

对于关键 Modify / Remove、Ambiguous、高风险跨边界映射，应进入人工 Review；NoMatch 可在明确设计实体的前提下生成 Add。

确认后生成不可变 `alignmentRevision`。

### 10.4 ImpactReview Gate

最终人工 Gate，消费 `ChangePlanReview` 和最终 Markdown。

只有：

```text
completeness = Complete
decision = ReadyForImplementation
revision checks = Passed
blocking issues = 0
```

才允许后续 Implementation Agent 获取 Approved Change / Node Change Requirements。

---

## 11. 完整可追溯链

所有最终要求必须能向上追溯到设计证据：

```text
Design Document
    ↓ section / line / evidence
DesignIntentIR.intentId
    ↓
AlignmentArtifact.alignmentRevision
    ↓
ChangeSet.changeId
    ↓
ImpactGraph.impactId
    ↓
NodeChangeRequirement.requirementId
    ↓
Final Markdown Section
```

例如：

```text
DeployController.java
        ↑
NCR-001
        ↑
Impact I001
        ↑
Change C001
        ↑
Intent intent-001
        ↑
Design Section 1.1 / Line 32-38
```

系统必须能够回答：

- 为什么要改这个文件；
- 是哪个设计变化导致；
- 通过哪条本体关系传播过来；
- 使用了哪条 Rule；
- 当前结论来自什么代码和设计证据；
- 为什么认为已经 Complete，或者为什么只能判定 Partial。

---

## 12. 最终变更文档结构

最终 Markdown 固定为七部分。

### 12.1 Analysis Context

包含：

```text
Requirement ID
Design Revision
Current Graph Revision
Alignment Revision
RuleSet Version
ChangeSet Hash
Scope
Graph Sources
```

### 12.2 Design Intent

来自 `DesignIntentIR`，说明设计究竟要求改变什么，不混入代码实现猜测。

### 12.3 Entity Alignment

来自 `AlignmentArtifact`，列出 Desired → Current 映射、候选、置信度、证据和 Unresolved。

### 12.4 ChangeSet

列出正式原子变化：

| Change | Target | Operation | Aspect | Source Intent |
| --- | --- | --- | --- | --- |
| C001 | DeployService.deployPolicy | Modify | Signature | intent-001 |
| C002 | DeployService.deployPolicy | Modify | Behavior | intent-002 |

### 12.5 Impact Analysis

列出：

```text
Affected Entity
Impact Type
Path
Rule
State
Confidence
Stop / Absorption Reason
```

### 12.6 Node Change Requirements

主体按：

```text
File
  └─ Symbol
      ├─ Why
      ├─ Required Changes
      ├─ Compatibility
      ├─ Test Obligation
      ├─ Source Change
      └─ Impact / Context Evidence
```

组织。

### 12.7 Completeness & Gate

来自 `ChangePlanReview`：

```text
Completeness
Coverage
Blocking Issues
Review Required
Revision Check
Decision
```

未满足完整性条件时明确输出：

```text
NOT READY FOR IMPLEMENTATION
```

通过后才输出：

```text
READY FOR IMPLEMENTATION
```

---

## 13. 示例：接口新增 retryPolicy

设计文档明确：

```text
deployPolicy 增加 retryPolicy 参数；
失败时最多重试 retryPolicy 次；
默认值为 3。
```

规划链如下。

### 13.1 DesignIntentIR

```text
intent-001 Signature: + retryPolicy
intent-002 Behavior: failure → retry
intent-003 Default: retryPolicy = 3
```

### 13.2 AlignmentArtifact

```text
desired:deployPolicy
→ code:DeployService.deployPolicy
status = Confirmed
```

### 13.3 ChangeSet

```text
C001 Signature Modify
C002 Behavior Modify
C003 Configuration / Default Change
```

### 13.4 ImpactGraph

规则发现：

```text
DeployController.deploy     RequiredModification
BatchDeployJob.run          RequiredModification
DeployPolicyTest            TestModification
```

每个结论保留 caller / testedBy 路径和传播 Rule。

### 13.5 NodeChangeRequirementArtifact

```text
DeployService.deployPolicy
- 增加 retryPolicy
- 实现失败重试
- 保持默认值兼容

DeployController.deploy
- 调用 deployPolicy 时传入 retryPolicy
- 参数来源 DeployRequest.retryPolicy

BatchDeployJob.run
- 无显式值时使用默认策略

DeployPolicyTest
- retryPolicy=0/1/3
- 超限场景
- 最大重试行为
```

### 13.6 ChangePlanReview

如果仍存在动态 callback 无法解析：

```text
Completeness = Partial
Decision = NeedsReview
```

只有所有定义范围内的关键链路闭合，才进入 `ReadyForImplementation`。

---

## 14. 与现有仓库设计的关系

本文不替代现有全链路 Agent 设计，而是收敛**从详细设计到完整变更要求**这一规划子流程。

与现有概念的关系：

```text
Requirement IR
→ DesignIntentIR 是组件设计规划所需的聚焦投影

Desired Design Graph
→ 为 Desired Entity 和 Design Evidence 提供图空间

Alignment
→ 继续保持候选、确认和 Revision 语义

ChangeSet / ChangeItem
→ 继续作为原子变化的统一模型

Impact Rules / Impact Graph
→ 继续由规则引擎和图引擎完成确定性传播

Approved Change / Implementation Agent
→ 位于本文流程之后，不在规划期修改代码
```

现有 `.opencode/agents/` 和 `.opencode/skills/` 可以继续支持完整需求到实现闭环。若后续落地本精简设计，优先采用“规划期 Facade Skill / Orchestrator 收敛”的方式复用已有能力，而不是立即删除全链路角色。

也就是说：

```text
全链路仍可有 Requirement / Planning / Architecture / Implementation / Verification 角色

但单次“设计 → 完整变更要求”规划任务内部
只暴露：
ChangePlannerAgent + 3 Skill + 2 Subagent
```

这样既保留端到端治理，又降低单个规划任务的 Agent 编排复杂度。

---

## 15. 最终约束

整个设计必须长期遵守以下规则：

1. **减少 Skill / Subagent，不减少 Artifact。**
2. `DesignIntentIR → AlignmentArtifact → ChangeSet → ImpactGraph → NodeChangeRequirementArtifact → ChangePlanReview` 不可跳级。
3. Current、Desired、Change、Impact 等图空间继续分离。
4. Current Revision、Design Revision 和 RuleSet Version 一旦开始分析即固定。
5. 能由规则表达的影响语义不交给 Subagent。
6. Subagent 只处理高不确定性语义判断和独立审查。
7. MCP / Tool 提供受控事实和确定性能力，不承担自由推理。
8. 每个 Change、Impact 和 Node Requirement 都必须有 Evidence 和 Provenance。
9. 测试要求是正式 Node Requirement，不是文档附注。
10. `Complete` 表示在声明 Scope 内证据闭合，不表示“程序成功运行完”。
11. Markdown 只是 Artifact 的确定性视图。
12. 人工 Gate 之前，规划期不修改 Current Graph、代码或 Git。
13. 最终交付不是代码 Patch，而是可直接作为后续 Coding Agent 输入的、结构化且可追溯的完整变更要求。

最终可以把整个规划系统概括为：

```text
Understand Change
      ↓
DesignIntentIR
      ↓
AlignmentArtifact
      ↓
ChangeSet
      ↓
Analyze Impact
      ↓
ImpactGraph
      ↓
Build Change Plan
      ↓
NodeChangeRequirementArtifact
      ↓
Independent Review
      ↓
ChangePlanReview
      ↓
Deterministic Markdown
      ↓
Human Gate
      ↓
Implementation Agent
```
