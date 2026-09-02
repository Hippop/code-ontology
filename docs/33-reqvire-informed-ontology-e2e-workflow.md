# Reqvire 启发下的本体驱动端到端全流程

## 1. 文档定位

本文基于 2026-08-28 拉取后的仓库状态，统一回答三个问题：

1. Reqvire 相关思路给仓库带来了什么变化；
2. 哪些能力已经在 `main` 可执行，哪些只存在于远端功能分支或架构文档；
3. 最新的本体驱动需求到代码闭环应如何从事实建图一直推进到提交和发布。

分析基线：

```text
main: 1b9d12f
  Merge pull request #5 from Hippop/docs/agent-change-planning-architecture

远端功能分支: origin/feat/engineering-semantics-closed-loop
分支头: 57675d8
  docs: document engineering MCP tools
```

实现状态更新：本文完成后的当前工作树已经把该功能分支的工程语义资产集成到主干
代码，并新增 Requirement IR 物化、统一 MCP、确定性代码生成、项目自模型和提交前
Commit Gate。可执行说明见
[本体驱动需求到代码闭环：可执行实现](34-ontology-e2e-implementation.md)。下文的
“远端功能分支”描述保留为引入时的来源分析，不再代表当前工作树状态。

这里的“Reqvire 引入”必须准确理解为：**吸收 Reqvire 的工程语义模型，而不是把
Reqvire 软件包直接接入平台**。当前 `main` 和远端功能分支都没有 Reqvire 依赖、
子模块、CLI 调用或运行时耦合。功能分支文档也明确声明“不是复制 Reqvire”，而是
吸收其显式所有权、契约、验证、证据、覆盖率和 typed impact 思路。

[Reqvire 官方模型](https://github.com/reqvire-org/reqvire)以 Git 原生的 Ontology、
Capability、Requirement、Contract、Verification、Evidence 和 Implementation
Link 组织工程知识。本仓库保留自己的代码本体、图空间、规则、Agent 状态机和
治理边界，只把适合现有平台的语义补入。

## 2. 核心结论

最新全流程不是另起一套 Reqvire 流程，而是在现有五类图空间和执行状态机之间
补上一条“工程意图主轴”：

```text
Ontology / Concept
        ↓ constrains
Capability
        ↓ owns
Engineering Requirement
        ├─ defines → Requirement Contract
        ├─ constrainedBy → Semantic Contract → Ontology Asset
        ├─ implementedBy ← Code Entity
        └─ verifiedBy ← Verification Method ← Verification Objective
                              ↓ satisfiedBy
                        Verification Evidence
```

这条主轴同时服务两个方向：

```text
设计 → 规划 → 实现
回答“应该改什么”

实际 Diff → 实际波及 → 对账 → 验证证据
回答“实际改了什么、有没有漏改、能不能提交和发布”
```

平台必须继续保持：

- 编译器、Parser 和连接器提供代码事实；
- OWL/RDFS 表达共享语义；
- SHACL 校验图内不变量；
- 版本化规则产生 typed impact 和工程义务；
- Agent 只处理受限语义判断和编排；
- 人工 Gate 承担需求、对齐、架构、批准、提交和发布责任；
- Current、Desired、Proposed、Approved、Actual 和 Impact 不互相覆盖。

## 3. Reqvire 思路引入后的变化

### 3.1 从“需求节点”升级为工程语义闭环

原平台已有 Requirement、Acceptance Criterion、Code Entity、Test、Change 和 Impact，
但 Requirement 与契约、验证方法、执行证据之间主要通过规划对象间接连接。

远端功能分支新增：

| 语义对象 | 作用 |
| --- | --- |
| `EngineeringRequirement` | 进入严格治理的需求；继承现有 `code:Requirement` |
| `RequirementContract` | 需求拥有的 Specification、Behavior、Constraint、State、I/O 契约 |
| `SemanticContract` | 基于本体、可复用且可约束多个需求的语义契约 |
| `OntologyAsset` | Semantic Contract 使用的本体资产 |
| `VerificationObjective` | 要证明什么，不直接拥有执行证据 |
| `VerificationMethod` | Test、Formal Proof、Analysis、Inspection、Demonstration |
| `VerificationEvidence` | 测试执行、证明、分析报告等可审计证据 |
| `EngineeringSubmodel` | 以 Capability 为根组织一个工程语义子图 |

`EngineeringRequirement` 采用渐进式治理，现有 `code:Requirement` 不会被新约束
一次性强制迁移。

### 3.2 从“有关联”升级为显式所有权

新增模型明确了三类责任关系：

```text
顶层 EngineeringRequirement
→ 必须且只能显式归属一个 Capability

子 EngineeringRequirement
→ 可以从父 Requirement 继承 Capability ownership

RequirementContract
→ 必须且只能由一个 EngineeringRequirement 拥有
```

这解决了普通知识图中“多个节点互相关联，但谁承担工程义务并不明确”的问题。

### 3.3 验证从测试列表升级为 Objective—Method—Evidence

验证链被拆成三个生命周期不同的对象：

```text
VerificationObjective
→ VerificationMethod
→ VerificationEvidence
→ concrete Test / Proof / Report Artifact
```

它允许区分：

- 计划证明什么；
- 选择什么验证方式；
- 验证是否真正执行；
- 证据是否可审计；
- 哪个 Requirement 最终被满足。

### 3.4 Coverage 被拆成三个指标

功能分支以 leaf Engineering Requirement 为统计口径：

```text
Implementation Coverage
= 被代码实现的 leaf Requirement / 全部 leaf Requirement

Verification Coverage
= 被 Verification Method 或 Test 验证的 leaf Requirement / 全部 leaf Requirement

Verification Evidence Coverage
= 拥有执行证据的 Verification Method / 全部 Verification Method
```

父需求上挂一个测试不能再掩盖子需求的实现或验证缺口。

### 3.5 Context 从相似检索升级为工程关系白名单

工程上下文收集只沿显式允许的关系遍历，例如：

```text
Capability / Requirement
Requirement / Contract
Semantic Contract / Ontology
Verification / Evidence
Requirement / Implementation
Requirement / Test
Call / Field / API implementation
```

这样给 Agent 的是受工程语义约束的 context package，而不是任意相似节点集合。

### 3.6 Impact 从图可达升级为显式 typed rule

功能分支坚持现有平台原则：图可达只产生候选，只有显式规则才能产生
`Confirmed` impact。新增确定性规则覆盖：

- Capability → Requirement；
- Requirement 父子传播；
- Requirement ↔ Requirement Contract；
- Ontology → Semantic Contract → Requirement；
- Requirement ↔ Implementation；
- Requirement → Verification / Test；
- Callee → Caller；
- Field → Reader / Writer；
- API Operation → Implementation。

Verification 或 Test 自身变化只把 Requirement 作为上下文，不继续向实现和契约
扩散，避免“一处测试修改导致整个功能重做”的过度传播。

### 3.7 新增 CLI 和只读 MCP 入口

远端功能分支新增四个确定性能力：

```text
engineering_validate
engineering_coverage
engineering_collect
engineering_impact
```

同一算法提供 CLI 和只读 MCP 入口，复用平台 `{nodes, edges}` 图结构和 SQLite 图
快照，不允许通过 MCP 修改 Current Graph。

## 4. 当前落地状态

### 4.1 状态总表

| 能力 | 状态 | 代码或文档基线 |
| --- | --- | --- |
| 源码扫描、Current Graph、文本快照和基线 | `main` 已实现 | `repository_scan.py`、`graph_baseline.py` |
| Requirement IR、Desired Graph、Alignment、Change Plan | `main` 已实现 | `document_ingestion.py`、`analysis_workflow.py` |
| 四个人工 Gate 和失败阶段重试 | `main` 已实现 | `workflow_orchestration.py` |
| 受控 Worktree、Patch、测试、Actual Graph | `main` 已实现 | `agent_runtime.py`、`service.py` |
| Reconciliation、Impact、Release Advice | `main` 已实现 | `verification_workflow.py` |
| 七类图空间、只读图谱 MCP、审计和重放 | `main` 已实现 | `mcp_gateway.py`、`store.py` |
| 工程语义本体、SHACL、Coverage、Context、typed impact | 当前工作树已集成 | `engineering_semantics.py`、统一 MCP |
| Requirement IR → 工程语义图和 Agent Context | 当前工作树已实现 | `engineering_workflow.py`、`service.py` |
| 本体契约 → 确定性 Python 代码生成 | 当前工作树已实现 | `ontology_codegen.py`、项目自模型 |
| Working Tree 双向对账和 Commit Gate | 当前工作树已实现 | `precommit_verification.py` |
| 精简规划 Artifact 链 | `main` 架构设计，尚未接入状态机 | `docs/31-agent-change-planning-architecture.md` |
| Git Diff 提交前双向完整性验证 | `main` 架构设计，尚未实现 | `docs/32-precommit-impact-verification-architecture.md` |

### 4.2 当前 `main` 的真实可执行链

当前状态机仍是六角色、四人工 Gate 的流程：

```text
Repository Scan
→ Current Graph
→ Design Ingestion
→ requirement-analyst
→ Requirement IR + Desired Graph
→ Human RequirementReview
→ code-graph-analyst
→ Alignment
→ Human AlignmentReview
→ change-planner
→ Change Plan
→ architecture-reviewer
→ Human ArchitectureReview
→ Human ChangeApproval + execution policy
→ implementation-agent in isolated Worktree
→ Patch + Required Tests + Actual Graph
→ Reconciliation + Impact
→ verification-agent
→ Workflow Completed
→ Human Release Gate remains required
```

因此不能把 31、32 号架构文档描述的新 Artifact 和 Tool 当作已经可调用的功能。

### 4.3 引入时的系统接线缺口及当前处理

工程语义分支引入时只覆盖 Validation、Coverage、Context 和 Impact。当前工作树已经
补齐 IR 物化、统一 MCP、代码生成、自模型、提交前双向对账和 Commit Gate；仍需在
后续演进中继续统一以下平台级问题：

1. Repository Scanner 仍以代码事实抽取为主；权威业务语义由项目自模型和确认后的
   Requirement IR 提供，不能靠 Scanner 猜测；
2. `engineering_impact` 使用 Python 内置规则，而现有 Planning 使用 YAML RuleSet，
   两套规则尚未统一版本和审计身份；
3. Coverage、Context 和 typed impact 可通过现有通用 Agent Artifact API 固化，但
   还没有为每一种工程 Artifact 提供独立 HTTP 资源端点。

## 5. 统一的本体和图空间模型

### 5.1 五个语义平面

```text
┌──────────────────────────────────────────────────────────────┐
│ 1. 事实平面                                                  │
│ Repository / Code / API / DB / Message / Config / Test       │
│ Build / Deploy / Runtime                                     │
└────────────────────────────┬─────────────────────────────────┘
                             │ implements / verifies
┌────────────────────────────▼─────────────────────────────────┐
│ 2. 工程意图平面                                              │
│ Ontology / Capability / EngineeringRequirement               │
│ RequirementContract / SemanticContract                       │
│ VerificationObjective / Method / Evidence                    │
└────────────────────────────┬─────────────────────────────────┘
                             │ desired / aligned
┌────────────────────────────▼─────────────────────────────────┐
│ 3. 规划平面                                                  │
│ RequirementIR / DesignIntentIR / Alignment / ChangeSet       │
│ PlannedImpact / NodeChangeRequirement / ApprovedChange       │
└────────────────────────────┬─────────────────────────────────┘
                             │ implementation
┌────────────────────────────▼─────────────────────────────────┐
│ 4. 执行与对账平面                                            │
│ Worktree / Patch / ActualChangeSet / ActualGraph             │
│ ImpactObligation / Reconciliation / VerificationCoverage     │
└────────────────────────────┬─────────────────────────────────┘
                             │ evidence / release
┌────────────────────────────▼─────────────────────────────────┐
│ 5. 交付与运行平面                                            │
│ BuildArtifact / ReleasePlan / Deployment / RuntimeEvidence   │
│ AuditEvent / Replay                                          │
└──────────────────────────────────────────────────────────────┘
```

### 5.2 图空间不能合并

| 图空间 | 回答的问题 | 写入来源 |
| --- | --- | --- |
| Current | 当前代码和工程事实是什么 | Scanner、Parser、受信 Connector |
| Business / Engineering | 能力、需求、契约和验证语义是什么 | 受控模型资产、确认后的映射 |
| Desired | 设计希望系统成为什么 | 已确认 Requirement IR |
| Proposed | 建议如何从 Current 到 Desired | Planning Rule、受控 Agent 草案 |
| Approved | 人工批准执行什么 | Change Approval Gate |
| Actual | Worktree 实际实现了什么 | 实现后重新扫描，不复制 Approved |
| Impact | 变化实际波及谁、义务是否闭合 | 版本化 typed rule 和对账引擎 |

Working Tree 在提交前只能形成临时 Overlay，不能污染 Current Graph。提交完成并由
正式 Scanner 重新发布后，才产生新的 Current Revision。

### 5.3 每次分析的身份

每个 Artifact 至少绑定：

```text
repositoryId
requirementId
designRevisionId
baseRevision
currentGraphRevision
ontologyVersion
ruleSetVersion
alignmentRevision
workingTreeSnapshotHash（提交前阶段）
producerAgent / producerSkill / toolVersion
inputArtifactIds
contentHash
```

任一 Revision、RuleSet、Ontology 或 Working Tree Hash 漂移，依赖它的 Review 和
Gate 都必须失效并重新计算。

## 6. 最新端到端全流程

### 阶段 0：固定仓库和治理基线

输入：Git Repository、分支或 Commit、规则、本体、Repository Policy。

执行：

1. 确认源仓库身份、允许根目录和干净状态；
2. 固定 `baseRevision`、Ontology Version 和 RuleSet Version；
3. 扫描源码、契约、数据库、配置、测试、构建和部署资产；
4. 发布带文本快照的 Current Graph；
5. 运行 Parser 基线、RDF/OWL 解析和 SHACL 校验；
6. 若索引内容与 Git Revision 漂移，阻断后续查询。

输出：`CurrentGraphRevision`、`GraphBaseline`、`ValidationReport`。

### 阶段 1：建立工程语义主轴

输入：领域本体、Capability、Requirement、Contract、Verification Plan。

执行：

1. 把稳定能力定义为 Capability；
2. 把需严格治理的 leaf 义务建模为 Engineering Requirement；
3. 区分 Requirement-owned Contract 和可复用 Semantic Contract；
4. 将 Semantic Contract 绑定 Ontology Asset；
5. 为每个 leaf Requirement 建立 Verification Objective 和预期 Method；
6. 连接已有 Code Entity、Test 和工程 Artifact；
7. 运行 ownership、contract 和 verification SHACL。

输出：`EngineeringSemanticGraphRevision`、初始 Coverage 缺口。

注意：计划期允许 Verification Method 尚未产生执行 Evidence。Evidence 的强制约束
应按图空间或生命周期启用，不能让 Desired / Planned Graph 因“尚未执行测试”而
天然不合规。

### 阶段 2：设计输入和 Requirement IR

输入：特性、需求或组件详细设计文档。

执行：

1. 保存 Design Document 和不可变 Design Revision；
2. 抽取明确事实、推断、建议和未解决问题；
3. 生成 Requirement IR / DesignIntentIR；
4. 物化 Desired Graph，不写 Current Graph；
5. 映射到 Engineering Requirement、Contract 和 Verification Objective 草案；
6. 由人工执行 `RequirementReview`。

输出：确认后的 `RequirementIR`、`DesignIntentIR`、`DesiredGraphRevision`。

### 阶段 3：实体对齐

输入：Desired Graph、Current Graph、Engineering Semantic Graph。

执行：

1. 通过稳定 ID、结构、路径、签名、契约和业务关系生成候选；
2. 对每个 Desired Entity 保存候选、证据、置信度和替代方案；
3. AI 可以解释候选，不能把候选升级为 Current 事实；
4. `Ambiguous` 或 `Unresolved` 必须停在 `AlignmentReview`；
5. 人工确认后生成不可变 `alignmentRevision`。

输出：`AlignmentArtifact`。

### 阶段 4：规划变更和 Planned Impact

输入：DesignIntentIR、AlignmentArtifact、固定 Current Revision、RuleSet。

执行：

1. 生成原子 ChangeSet；
2. 用显式 typed rule 计算 Planned ImpactGraph；
3. 把 Impact 转换为节点级修改、测试、兼容、迁移、评审和发布义务；
4. 生成 `NodeChangeRequirementArtifact`；
5. 独立 Reviewer 反向检查 Requirement、Change、Impact 和义务完整性；
6. 通过 Architecture / Impact Review 后渲染确定性 Markdown。

输出：

```text
ChangeSet
PlannedImpactGraph
NodeChangeRequirementArtifact
ChangePlanReview
Final Change Requirement Markdown
```

Markdown 只是视图，Artifact 才是事实源。

### 阶段 5：人工批准和执行策略

人工 `ChangeApproval` 必须同时批准：

```text
Approved ChangeSet
allowedFiles
forbiddenFiles
requiredTests
securityDataDecision
migration / compatibility obligations
```

没有批准的 Change、独立 Worktree 或文件白名单，Implementation Agent 不得编辑。

### 阶段 6：隔离实现

执行：

1. 平台从固定 Base Revision 创建独立 Worktree；
2. Agent 只接收批准的节点级要求和受限工程 Context；
3. 每次修改关联 proposalId 或 verificationObligationId；
4. 禁止 Commit、Push、Merge、Tag 和 Deploy；
5. 平台重新计算 Binary Patch、Changed Files 和 Patch Hash；
6. 校验 HEAD、路径策略和 Required Tests；
7. 保存 Test Execution 作为候选 Verification Evidence。

输出：`AgentRun`、`PatchArtifact`、`TestExecutionArtifact`。

### 阶段 7：提交前实际变更抽取

提交前快照必须覆盖 staged、unstaged、untracked、rename、delete、binary metadata
和 submodule pointer：

```text
Working Tree
→ GitDiffSnapshot
→ WorkingTreeGraphOverlay
→ ActualChangeSet
```

结构变化由 Parser 确定；行为、状态、错误语义等变化可以由受限 SemanticDiff
Analyst 给出带证据的候选。Overlay 只服务本次验证。

### 阶段 8：实际波及和双向对账

必须同时执行两个方向：

```text
Plan → Actual
检查所有批准要求是否已实现

Actual → Impact Closure
检查实际变化引出的全部工程义务是否闭合
```

完整 Artifact 链：

```text
ActualChangeSet
→ ActualImpactGraph
→ ImpactObligationArtifact
→ ImplementationReconciliationArtifact
→ VerificationCoverageArtifact
```

对账至少区分：

```text
Conformed
PartiallyImplemented
MissingImplementation
AlternativeImplementation
UnexpectedImplementation
CannotVerify
DeferredToReleaseGate
```

### 阶段 9：提交前独立审查和 Commit Gate

`PreCommitReviewer` 不重新生成 Change，只审查固定 Artifact：

- Planned Requirement 是否全部对账；
- Actual Impact 是否全部转成 Obligation；
- Required Modification、Test、Compatibility、Migration 是否闭合；
- Verification Method 是否有与当前 Patch Hash 绑定的 Evidence；
- 是否存在未批准文件、意外实现或未解决结论。

只有全部 hard condition 通过才能得到 `ReadyToCommit`。Review 必须绑定
`workingTreeSnapshotHash`；代码再次变化后自动成为 `STALE_REVIEW`。

平台本身仍不执行 Git Commit。Commit 由外部受权流程完成。

### 阶段 10：提交后发布新的 Current Graph

外部流程提交后：

1. Scanner 从新 Commit 重新抽取正式代码事实；
2. 发布新的 Current Graph Revision；
3. 对比提交前 Overlay 与提交后 Current，确认没有发布漂移；
4. 将实现关系、测试关系和 Evidence Link 固化到工程语义图；
5. 重新计算三类 Coverage。

提交前 Overlay 不能直接提升为 Current Graph。

### 阶段 11：发布验证和运行证据

输入：Impact、Reconciliation、Verification Evidence、Release Policy。

执行：

1. 计算发布顺序、兼容窗口、Canary 和回滚要求；
2. 阻断未通过的 Verification Check；
3. 对生产发布执行独立人工 Release Gate；
4. 收集 Deployment、Runtime Instance、Telemetry 和 Incident Evidence；
5. 将 Runtime Evidence 关联到 Release、Requirement 和 Verification；
6. 完成审计链校验和 Requirement Replay。

输出：`ReleasePlan`、`ReleaseApproval`、`RuntimeEvidence`、`AuditChain`。

## 7. Gate 总表

| Gate | 责任人 | 阻断条件 |
| --- | --- | --- |
| RequirementReview | 产品/需求负责人 | 未解决需求语义、验收标准不明确 |
| AlignmentReview | 代码/领域负责人 | Current Entity 映射歧义 |
| ArchitectureReview / ImpactReview | 架构负责人 | 方案、波及或兼容义务不完整 |
| ChangeApproval | 变更负责人 | 未批准 ChangeSet、路径或测试策略 |
| PreCommitReview | 独立 Reviewer | 计划—实际不一致、Actual Impact 未闭合、证据不足 |
| Commit Gate | 代码库负责人/受权自动化 | Working Tree Hash 漂移或 Hard Condition 失败 |
| Release Gate | 发布负责人 | 发布被阻断、验证失败或风险未接受 |

人工可以接受风险，但必须留下 actor、decision、rationale、输入 Revision 和 Artifact
Hash；人工决定不能回写或伪造机器事实。

## 8. 角色和工具边界

```text
Parser / Scanner
→ 生成 Current / Actual 的可证明事实

Ontology / SHACL
→ 定义语义和静态不变量

Rule Engine
→ 生成可重算的 typed impact 和 obligation

Agent / Subagent
→ 处理设计理解、候选判断、独立审查和受控实现

Skill
→ 固定步骤、输入输出、停止条件和 Tool Policy

MCP / Tool
→ 提供版本化事实、确定性分析和受控 Artifact 操作

Human Gate
→ 对不可自动承担的业务和工程责任作决定
```

禁止让 Agent 自由扫描整个仓库后直接产出最终修改要求，也禁止让 Markdown、Prompt
或 AI 候选成为事实源。

## 9. 当前可直接运行的流程

在 `main` 上可运行现有受控闭环：

```bash
python3 -m venv .venv
.venv/bin/pip install -e .

.venv/bin/code-ontology-platform validate

python3 scripts/run_codex_requirement_workflow.py \
  --repository /absolute/path/to/clean/repository \
  --design examples/designs/sdn-minimum-bandwidth.md \
  --database /tmp/code-ontology-workflow.db \
  --worktree-root /tmp/code-ontology-worktrees \
  --rules rules/requirement-change-planning-rules.yaml \
  --workflow-id ontology-e2e \
  --approve-gates \
  --required-test "mvn test" \
  --report /tmp/code-ontology-workflow-report.json
```

不传 `--approve-gates` 时，脚本会停在第一个人工 Gate。该脚本覆盖到 Actual Graph、
Reconciliation、Impact 和 Release Advice，但不包含 32 号文档定义的新 Commit Gate。

工程语义 CLI/MCP 只有在功能分支合并后才能从 `main` 安装使用。

## 10. 合并和实现优先级

### P0：合并语义模型但先消除生命周期冲突

1. 将功能分支 rebase 到最新 `main`；
2. 统一文档编号和 README 导航；
3. 把 Verification Evidence 的 SHACL `minCount 1` 改为按图空间或状态启用：
   Planned 阶段允许无执行证据，Actual / Release 阶段强制证据；
4. 保持 legacy `code:Requirement` 的渐进迁移策略。

### P1：把语义层接入现有工作流

1. Requirement IR → Engineering Requirement / Contract / Objective；
2. Alignment 和 Change Plan 读取 Engineering Context；
3. Planning 与 Actual Impact 复用同一规则定义；
4. 在 Artifact 中固定 Ontology / RuleSet Version；
5. 将四个 engineering 工具并入统一 MCP 目录或提供清晰的双 Server 生命周期管理。

### P2：实现规划期精简 Artifact

按 31 号文档实现 `DesignIntentIR → AlignmentArtifact → ChangeSet →
PlannedImpactGraph → NodeChangeRequirementArtifact → ChangePlanReview`，复用现有
Requirement、Alignment、Architecture 和 Change Approval Gate，不复制状态机。

### P3：实现提交前验证链

按 32 号文档实现 Working Tree Snapshot、Overlay、ActualChangeSet、Impact
Obligation、双向 Reconciliation、Verification Coverage、PreCommitReview 和
Commit Gate。

### P4：提交后和运行期闭环

将新 Commit 扫描为正式 Current Revision，固化 Evidence Link，并把 Release、
Deployment 和 Runtime Evidence 纳入同一审计和重放链。

## 11. 完成定义

只有同时满足以下条件，才能称为“最新的基于本体的端到端闭环”已经完整落地：

1. Capability、Engineering Requirement、Contract、Implementation、Verification
   和 Evidence 可以跨图空间追溯；
2. Requirement IR 能自动生成受治理的工程语义草案，并经过人工确认；
3. Planning 和 Actual 使用同一版本化 typed rule；
4. Planned Requirement 与 Actual Impact 两个方向都完成对账；
5. leaf Requirement 的 Implementation、Verification 和 Evidence Coverage 可计算；
6. PreCommitReview 绑定精确 Working Tree Hash，变化后自动失效；
7. Commit 后由 Scanner 重新发布 Current Graph，不提升临时 Overlay；
8. Release 和 Runtime Evidence 可回溯到 Requirement、Change、Code 和 Test；
9. 所有 Agent、Tool、Rule、Ontology、Artifact 和人工决定进入可验证审计链；
10. 平台始终不替代代码库 Commit 权限和生产 Release 权限。

这条链路的最终价值不是生成更多图，而是让每个工程结论都能回答：

```text
它来自哪个需求和本体定义？
由哪个版本的事实和规则推导？
谁批准了它？
代码实际是否实现？
波及是否闭合？
验证证据在哪里？
当前结论是否仍与最新 Revision 一致？
```
