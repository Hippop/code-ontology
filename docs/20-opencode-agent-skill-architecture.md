# OpenCode Agent + Skill AI 辅助架构

## 1. 文档目标

本文定义如何使用 OpenCode 作为 AI Agent 执行引擎，通过项目级 Agent、可复用 Skill、受控 Tool/MCP 和人工审批机制，为“现存代码库 + 特性/详细设计文档 → 代码图变更 → 代码实现 → 实现对账”提供具体 AI 辅助。

AI 层不替代代码解析器、本体推理器、变更规则引擎和审批工作流。最终分工为：

```text
OpenCode Agent
负责理解当前任务、选择 Skill、编排子任务、汇总结果和生成代码草案

SKILL.md
负责定义稳定、可复用、可审计的工作流程和输出契约

Custom Tool / MCP
负责访问 Current Graph、Desired Graph、Proposed Change、代码证据和审批状态

静态分析器与规则引擎
负责确定性事实、图差异、SHACL、兼容规则和影响传播

人
负责业务语义、关键映射、架构选择、破坏性变化和生产风险决策
```

系统目标不是让一个通用 Agent 自由完成全部工作，而是把 AI 行为拆成受限、可组合、可审计的能力单元。

---

## 2. 为什么采用 Agent + Skill

单一长提示词存在以下问题：

- 文档解析、代码搜索、变更规划和编码实现混在同一上下文；
- 每次执行步骤不一致，容易遗漏证据、兼容和测试；
- Agent 可能越权修改代码或把候选事实写成确定事实；
- 需求变化后无法判断是模型变化、提示词变化还是规则变化；
- 团队难以复用和评审 AI 工作方式。

Agent + Skill 将职责拆开：

```text
Agent = 角色、权限、模型、工具边界、任务编排
Skill = 领域工作流、输入要求、步骤、输出格式、停止条件
Tool = 可执行能力和数据边界
Artifact = Agent 每阶段产生的结构化结果
```

Skill 应保持窄职责。一个 Skill 只完成一个可验证阶段，例如“抽取 Requirement IR”或“生成实体对齐候选”，不能同时负责文档理解、架构决策和代码修改。

---

## 3. OpenCode 在系统中的部署位置

推荐架构：

```text
Requirement-to-Code Platform
├── Repository / Document / Graph Services
├── Rule / Alignment / Reconciliation Services
├── Review Workflow
└── OpenCode Agent Gateway
      ├── OpenCode Server Pool
      ├── Workspace Manager
      ├── Agent Session Manager
      ├── Skill Registry
      ├── Tool/MCP Gateway
      ├── Context Package Builder
      └── Agent Artifact Collector
```

OpenCode 可以采用两种运行方式。

### 3.1 开发者本地模式

```text
Developer Workstation
├── Git Worktree
├── .opencode/agents
├── .opencode/skills
├── .opencode/tools
└── OpenCode TUI / IDE Integration
```

用途：

- 开发者审阅需求变更计划；
- 在本地分支执行已批准任务；
- 生成代码和测试草案；
- 查看 Agent 证据和修改 Diff。

### 3.2 平台托管模式

```text
Agent Gateway
→ 创建隔离 Worktree / Container
→ 启动 opencode serve
→ 创建 Session
→ 发送结构化 Prompt 与 Agent 名称
→ 监听事件、权限请求和文件 Diff
→ 收集 AgentArtifact
→ 关闭或保留 Session
```

平台不得让多个需求共享可写 Worktree。推荐每个 ImplementationRun 使用独立分支、Worktree 和 OpenCode Session。

---

## 4. Agent 拓扑

推荐使用一个主编排 Agent 和六个受限子 Agent。

```text
requirement-orchestrator                 Primary Agent
├── requirement-analyst                 Subagent
├── code-graph-analyst                  Subagent
├── change-planner                      Subagent
├── architecture-reviewer               Subagent
├── implementation-agent                Subagent
└── verification-agent                  Subagent
```

### 4.1 requirement-orchestrator

职责：

- 接收 Requirement ID、Design Revision 和 Repository Snapshot；
- 判断当前处于抽取、对齐、规划、实现还是对账阶段；
- 调用对应子 Agent；
- 保持阶段顺序和人工 Gate；
- 汇总结构化 Artifact；
- 不直接修改业务代码。

禁止：

- 自行批准 CandidateAlignment；
- 跳过设计评审进入实现；
- 把 Desired Graph 当成 Current Graph；
- 直接执行 Git Commit、Push、Merge 或部署。

### 4.2 requirement-analyst

职责：

- 加载 `extract-requirement-ir` Skill；
- 阅读特性文档和详细设计证据；
- 抽取 Requirement、流程变化、业务规则、业务对象、契约、配置、验收条件；
- 区分 Explicit、Inferred、Suggested、Unresolved；
- 生成 Requirement IR 草案。

权限：只读文档和仓库；允许读取需求上下文工具；禁止编辑代码。

### 4.3 code-graph-analyst

职责：

- 加载 `align-design-to-code-graph` Skill；
- 查询 Current Knowledge Graph；
- 查找稳定 ID、符号、API、Schema、表、配置和测试候选；
- 生成 CandidateAlignment 和 ImplementationSlice 候选；
- 提供代码位置与图路径证据。

权限：只读代码和图；禁止修改代码、图事实和审批状态。

### 4.4 change-planner

职责：

- 加载 `plan-code-graph-change` Skill；
- 读取 Requirement IR、Desired Graph、Current Graph、已确认 Alignment；
- 使用 Graph Diff 和规划规则生成 Proposed Change；
- 生成兼容评估、验证义务、实现任务和依赖；
- 输出替代方案和未解决问题。

权限：只能创建 Draft Proposal；不能批准提案。

### 4.5 architecture-reviewer

职责：

- 独立检查规划结果；
- 检查跨服务边界、公共契约、数据库迁移、消息兼容、并发、事务和部署风险；
- 验证 Proposed Change 是否与证据一致；
- 输出 ReviewFinding，不直接修改代码。

该 Agent 与 change-planner 使用不同提示和独立上下文，避免规划者自我确认。

### 4.6 implementation-agent

职责：

- 仅处理 Approved Change Graph；
- 加载 `implement-approved-change` Skill；
- 在独立 Worktree 中修改批准范围内的文件；
- 运行编译、静态检查和目标测试；
- 生成 Patch、修改说明和未完成项。

权限：编辑必须 ask 或由平台预批准特定路径；允许安全构建命令；禁止 commit、push、merge 和生产操作。

### 4.7 verification-agent

职责：

- 加载 `verify-and-reconcile` Skill；
- 读取 Approved Change、代码 Diff、Actual Graph 和测试结果；
- 检查实现是否符合设计；
- 输出 ImplementedAsDesigned、MissingImplementation、UnexpectedImplementation、ChangedDesign 或 Unverified；
- 不修改代码。

---

## 5. Skill 目录设计

仓库级 Skill 放在：

```text
.opencode/skills/<skill-name>/SKILL.md
```

推荐初始 Skill 集：

```text
orchestrate-requirement-change
extract-requirement-ir
align-design-to-code-graph
plan-code-graph-change
implement-approved-change
verify-and-reconcile
explain-change-impact
```

每个 Skill 由以下部分组成：

```text
YAML Frontmatter
├── name
├── description
├── compatibility
└── metadata

Markdown Body
├── 适用条件
├── 前置条件
├── 输入契约
├── 工作步骤
├── Tool 使用规则
├── 输出契约
├── 证据要求
├── 停止条件
└── 禁止事项
```

Skill 不应存储环境密钥、真实 API Token 或可变业务事实。项目事实通过 Tool/MCP 动态读取。

---

## 6. Agent、Skill 和 Tool 的调用关系

```text
用户或平台
  ↓
requirement-orchestrator
  ↓ task(requirement-analyst)
requirement-analyst
  ↓ skill(extract-requirement-ir)
  ↓ ontology_requirement_context
  ↓ ontology_record_agent_artifact
RequirementIRDraft
```

随后：

```text
requirement-orchestrator
  ↓ task(code-graph-analyst)
code-graph-analyst
  ↓ skill(align-design-to-code-graph)
  ↓ ontology_graph_query
  ↓ ontology_alignment_candidates
CandidateAlignmentDraft
```

规划阶段：

```text
requirement-orchestrator
  ↓ task(change-planner)
change-planner
  ↓ skill(plan-code-graph-change)
  ↓ ontology_graph_query
  ↓ ontology_change_plan_draft
ProposedChangeDraft
```

人工批准后：

```text
requirement-orchestrator
  ↓ task(implementation-agent)
implementation-agent
  ↓ skill(implement-approved-change)
  ↓ read / grep / lsp / edit / bash
Patch + TestResult
```

实现后：

```text
静态分析平台重新生成 Actual Graph
  ↓
requirement-orchestrator
  ↓ task(verification-agent)
verification-agent
  ↓ skill(verify-and-reconcile)
  ↓ ontology_reconciliation_context
ReconciliationReport
```

---

## 7. Context Package

Agent 不应直接接收整个代码库、本体图和所有文档。平台需要针对阶段构造最小上下文包。

```text
AgentContextPackage
├── runId
├── stage
├── requirementId
├── designRevisionId
├── repositorySnapshot
├── approvedScope
├── evidenceRefs
├── desiredEntities
├── currentEntityCandidates
├── implementationSlices
├── proposedChanges
├── architectureDecisions
├── acceptanceCriteria
├── allowedFiles
├── forbiddenFiles
├── allowedTools
└── outputSchema
```

### 7.1 文档分析上下文

包含：

- 当前 Design Revision；
- 相关上一版本；
- 文档章节和图表解析结果；
- 已存在的业务词汇和稳定 ID；
- Requirement IR Schema；
- 禁止臆造规则。

### 7.2 代码对齐上下文

包含：

- Desired Entity；
- 当前图候选；
- 候选邻域子图；
- 符号位置和源码摘要；
- 历史映射；
- Alignment 输出 Schema。

### 7.3 实现上下文

包含：

- Approved Change；
- Architecture Decision；
- ImplementationSlice；
- 允许修改文件；
- 禁止修改文件；
- 必须保留的兼容条件；
- 必须通过的测试；
- 不允许的实现方式。

---

## 8. Tool 与 MCP 设计

OpenCode 内置文件、搜索、LSP、编辑和 Bash 工具。业务平台能力通过自定义 Tool 或 MCP 暴露。

推荐工具集合：

```text
ontology_requirement_context
读取 Requirement、DesignRevision、RequirementIR 和证据

ontology_graph_query
按受控 QueryType 查询 Current、Desired、Proposed、Actual 或 Impact 子图

ontology_alignment_candidates
提交或读取 CandidateAlignment 草案

ontology_change_plan_draft
提交 Proposed Change 草案，不能直接批准

ontology_reconciliation_context
读取 Approved/Actual 对账上下文

ontology_record_agent_artifact
保存 Agent 结构化输出、模型、Skill、证据和会话信息
```

生产系统建议将图平台封装为单一 `code-ontology` MCP Server，避免把 Fuseki、Neo4j、PostgreSQL 和对象存储分别暴露给 Agent。

MCP Server 内部负责：

```text
身份认证
租户和项目权限
查询模板白名单
最大图深度
最大结果数
敏感字段脱敏
Draft/Approved 写入隔离
审计日志
幂等键
```

Agent 不应拥有任意 SPARQL、Cypher 或 SQL 写权限。图查询应优先使用受控 QueryType，例如：

```text
ENTITY_NEIGHBORHOOD
IMPLEMENTATION_SLICE
BUSINESS_TRACE
CALL_PATH
CONTRACT_CONSUMERS
DATA_DEPENDENCIES
CHANGE_CONTEXT
IMPACT_PATHS
```

---

## 9. Artifact 模型

每个 Agent 阶段必须生成结构化 Artifact，而不是只返回自然语言。

```text
AgentArtifact
├── artifactId
├── artifactType
├── runId
├── sessionId
├── agentName
├── skillName
├── skillVersion
├── modelId
├── inputContextHash
├── outputPayload
├── evidenceRefs
├── assumptions
├── unresolvedQuestions
├── confidence
├── createdAt
└── supersedesArtifact
```

Artifact 类型：

```text
RequirementIRDraft
DesiredGraphDraft
CandidateAlignmentDraft
ImplementationSliceDraft
ProposedChangeDraft
ArchitectureReview
ImplementationPatch
TestExecutionReport
ReconciliationReport
ImpactExplanation
```

自然语言说明只能作为 Artifact 的 `summary`，核心结果必须符合 JSON Schema。

---

## 10. 人工 Gate

### Gate A：Requirement IR 确认

必须人工确认：

- 业务目标和范围；
- BusinessRule；
- 失败语义；
- 验收标准；
- Explicit 与 Inferred 的边界。

### Gate B：实体对齐确认

必须人工确认：

- 关键流程步骤的 primary implementation；
- 多候选或跨服务映射；
- 公共 API、消息和数据库对象对应关系；
- AI 置信度低于阈值的映射。

### Gate C：变更计划批准

必须人工确认：

- 架构方案；
- 兼容策略；
- 数据迁移；
- 安全和租户隔离；
- 部署与回滚；
- 可修改范围。

### Gate D：代码合并

必须人工完成 Code Review。OpenCode Agent 只产生 Patch 和测试证据，不直接 Merge。

### Gate E：生产发布

由现有 CI/CD 和审批系统执行，OpenCode 无生产发布权限。

---

## 11. 权限模型

权限遵循最小能力原则。

### 11.1 全局默认

```text
read              allow，但拒绝 .env 和凭据文件
search/lsp        allow
skill             仅允许项目白名单
subagent task     仅允许编排拓扑内 Agent
edit              ask
bash              ask，安全只读和测试命令可 allow
external path     deny
git commit/push   deny
network fetch     默认 ask 或 deny
```

### 11.2 只读 Agent

`requirement-analyst`、`code-graph-analyst`、`change-planner`、`architecture-reviewer` 和 `verification-agent` 默认：

```text
edit deny
bash deny 或仅允许测试查询
git write deny
```

### 11.3 实现 Agent

`implementation-agent`：

```text
edit ask
bash:
  git status/diff/log allow
  mvn/gradle compile/test allow
  formatter/linter allow
  git commit/push deny
external_directory deny
```

即使启用 OpenCode auto mode，显式 deny 仍必须覆盖高风险命令。

---

## 12. Skill 版本与治理

Skill 是工程资产，必须版本化和评审。

推荐在 metadata 中记录：

```text
version
owner
stage
artifact-type
risk-level
```

Skill 变化需要：

- Pull Request；
- 示例输入和期望输出；
- 回归样例；
- 安全审查；
- 兼容说明；
- 指标对比。

不建议让 Agent 自动修改生产 Skill。Agent 可以生成 Skill 改进建议，但必须通过人工 PR。

---

## 13. 质量评估

### 13.1 Requirement IR

指标：

```text
实体抽取 Precision / Recall
业务规则漏检率
Explicit/Inferred 分类准确率
未解决问题发现率
人工修改比例
```

### 13.2 Entity Alignment

指标：

```text
Top-1 / Top-3 准确率
自动确认准确率
人工拒绝率
跨服务误配率
证据完整率
```

### 13.3 Change Planning

指标：

```text
提案接受率
漏掉的工程层数量
错误目标文件率
兼容风险漏检率
测试建议命中率
```

### 13.4 Implementation

指标：

```text
编译一次通过率
测试一次通过率
越界文件修改率
人工返工量
Proposed/Actual 一致率
```

---

## 14. 失败恢复

Agent 每个阶段必须支持恢复，不从头重跑整个需求。

```text
Session 失败
→ 保留已完成 Artifact
→ 标记失败步骤和最后 Tool Call
→ 创建新 Session
→ 注入已验证 Artifact 和剩余任务
```

典型失败：

- Tool/MCP 超时；
- 上下文过大；
- 无候选实体；
- 多个候选评分接近；
- 构建失败；
- 测试环境缺失；
- Agent 修改了禁止文件；
- 设计文档存在冲突。

发生以下情况必须停止并请求人工：

```text
公共契约删除
不可逆数据库迁移
跨租户安全变化
生产凭据访问
需求与批准设计冲突
无法证明关键业务规则的实现位置
连续重复工具调用或无进展
```

---

## 15. SDN 示例

需求：网络策略支持最小带宽约束。

### 15.1 requirement-analyst

加载 `extract-requirement-ir`，生成：

```text
BusinessRule: MinimumAvailableBandwidthRule
BusinessRule: BandwidthFreshnessRule
BusinessAttribute: NetworkPolicy.minimumBandwidthMbps
AcceptanceCriterion: 过期指标时不得下发 FLOW_MOD
```

### 15.2 code-graph-analyst

查询 Current Graph，得到候选：

```text
PathConstraint                       0.96
ConstraintEvaluator.evaluate         0.93
PathComputationService.compute       0.90
TopologyMetricService.getBandwidth  0.82
```

并生成 ImplementationSlice 候选。

### 15.3 change-planner

加载规划 Skill 和规则，生成：

```text
修改 OpenAPI Request Schema
修改 PathConstraint
修改 Request Mapper
修改 ConstraintEvaluator
读取 availableBandwidth 和 sampleTime
新增 topology.bandwidth.max-age
新增错误契约
新增负向集成测试
```

### 15.4 architecture-reviewer

检查：

- 规则是否属于 ConstraintEvaluator；
- 未指定 minimumBandwidth 时是否保持旧行为；
- 指标过期是否允许降级；
- 是否改变南向协议；
- 是否引入性能风险。

### 15.5 implementation-agent

仅在计划批准后修改白名单文件，运行相关测试，不 Commit、不 Push。

### 15.6 verification-agent

对账：

```text
字段存在                      ImplementedAsDesigned
规则调用存在                  ImplementedAsDesigned
过期指标阻止 FLOW_MOD         由负向测试验证
新增未批准缓存                UnexpectedImplementation
```

---

## 16. 推荐仓库结构

```text
.opencode/
├── agents/
│   ├── requirement-orchestrator.md
│   ├── requirement-analyst.md
│   ├── code-graph-analyst.md
│   ├── change-planner.md
│   ├── architecture-reviewer.md
│   ├── implementation-agent.md
│   └── verification-agent.md
├── skills/
│   ├── orchestrate-requirement-change/SKILL.md
│   ├── extract-requirement-ir/SKILL.md
│   ├── align-design-to-code-graph/SKILL.md
│   ├── plan-code-graph-change/SKILL.md
│   ├── implement-approved-change/SKILL.md
│   ├── verify-and-reconcile/SKILL.md
│   └── explain-change-impact/SKILL.md
└── tools/
    └── ontology.ts

opencode.json
```

---

## 17. 实施顺序

### 阶段一：只读分析闭环

实现：

```text
requirement-analyst
code-graph-analyst
change-planner
architecture-reviewer
```

只生成 Draft Artifact，不允许修改代码。

### 阶段二：人工批准后的本地实现

启用 `implementation-agent`，限制文件白名单和命令白名单。

### 阶段三：平台托管 OpenCode Server

通过 Agent Gateway 创建 Session、发送任务、处理权限请求、获取文件 Diff 和保存 Artifact。

### 阶段四：MCP 统一工具网关

将图查询、对齐、规划和对账接口封装为 `code-ontology` MCP Server。

### 阶段五：评估和持续改进

对 Skill、Agent、模型和规则分别建立版本与质量指标，避免把所有误差都归因于模型。

---

## 18. 最终原则

```text
Agent 负责角色化执行和编排；
Skill 负责稳定工作流和输出契约；
Tool/MCP 负责受控事实访问和草案写入；
规则引擎负责确定性规划和传播；
OpenCode 文件工具负责批准范围内的代码修改；
人负责业务定义、架构决策、风险接受、合并和发布。
```

任何 AI 结果必须能够追溯到：

```text
Requirement / DesignRevision
→ Agent
→ Skill Version
→ Tool Evidence
→ AgentArtifact
→ Human Decision
→ Code Diff
→ Actual Graph
→ Verification Evidence
```

只有形成这条链，Agent 辅助才是可治理的工程能力，而不是不可审计的聊天式代码生成。