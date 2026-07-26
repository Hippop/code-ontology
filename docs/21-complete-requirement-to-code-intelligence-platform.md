# 需求到代码智能平台完整系统设计

## 1. 系统定义

本系统正式命名为：

```text
Requirement-to-Code Intelligence Platform
需求到代码智能平台
```

系统以现存代码库、契约、数据库、配置、测试、部署与运行事实为基础，以特性文档、需求文档和详细设计文档为目标输入，通过代码知识图谱、业务语义图、本体、规则引擎和 OpenCode Agent + Skill，生成可评审、可实现、可验证、可追踪的代码变更方案。

系统不是单纯的代码搜索平台，也不是允许大模型根据一份文档直接修改代码的自动编码系统。系统建立以下完整闭环：

```text
现存代码库与运行系统
→ Current Knowledge Graph

新增特性与详细设计
→ Requirement IR
→ Desired Design Graph

Current + Desired
→ Semantic Graph Diff
→ Proposed Change Graph
→ 人工评审
→ Approved Change Graph

Approved Change
→ OpenCode Implementation Agent
→ 代码与测试修改
→ CI
→ Actual Graph After Implementation
→ Reconciliation
→ Impact Analysis
→ Release Verification
```

系统必须能够回答：

1. 当前系统已经具备哪些业务能力和技术能力；
2. 某项新需求改变了哪些业务流程、规则、状态和业务对象；
3. 新需求与当前代码中的哪些 API、类、方法、表、消息和配置相关；
4. 当前能力应复用、扩展、替换还是新增；
5. 实现需求需要产生哪些代码图变化；
6. 哪些变化属于确定性必需变化，哪些只是 AI 建议；
7. 哪些公共契约、数据、消息和部署变化具有兼容风险；
8. 哪些测试、迁移、发布和回滚动作不可遗漏；
9. Agent 实际修改的代码是否严格符合批准的变更；
10. 需求最终是否通过测试、发布和运行证据得到验证。

---

## 2. 核心设计原则

### 2.1 当前事实、目标设计和实际实现严格分离

系统至少维护五类图空间：

```text
Current Knowledge Graph
Desired Design Graph
Proposed / Approved Change Graph
Actual Graph After Implementation
Impact Graph
```

设计文档中的期望内容不能写入 Current Graph；批准的变更不能直接复制成 Actual Graph；AI 候选不能自动升级为确定事实。

### 2.2 确定性事实优先

以下信息必须优先由确定性解析器生成：

```text
源码声明
类型和方法签名
静态调用
字段读写
API Schema
数据库结构
配置来源
构建依赖
部署版本
测试执行结果
```

AI 不能替代编译器、Schema Parser、数据库 Catalog、Git Diff、SHACL 和 CI。

### 2.3 Agent、Skill、Tool 和规则职责分离

```text
Agent
负责角色、上下文、阶段编排和任务执行

Skill
负责稳定、可复用、可审计的工作流程和输出契约

Tool / MCP
负责受控数据访问、图查询和 Draft Artifact 写入

规则引擎
负责确定性差异、兼容、规划、传播和质量判断

人
负责业务定义、关键映射、架构选择、批准和生产风险
```

### 2.4 所有结论必须可解释

任何业务映射、变更提案和影响结论必须保存：

```text
来源
证据
规则
模型或 Agent 版本
置信度
替代方案
人工决策
版本范围
```

### 2.5 实现完成后必须重新抽取

不能因为某个 Agent 声称已经实现，就把变更标记为完成。代码、契约、迁移、测试和配置必须重新解析，形成 Actual Graph，并与 Approved Change Graph 对账。

---

## 3. 系统参与者

| 角色 | 主要职责 |
|---|---|
| Product Owner | 确认业务目标、范围、优先级和验收条件 |
| Domain Expert | 确认业务概念、流程、规则和状态语义 |
| Architect | 确认架构边界、兼容策略和实现方案 |
| Developer | 确认代码映射、实现切片和代码变更 |
| Data Owner | 确认数据模型、迁移和数据安全 |
| Test Owner | 确认验证义务、测试策略和质量门禁 |
| SRE / Operations | 确认部署顺序、监控、回滚和运行风险 |
| Repository Scanner | 自动扫描代码库和构建模型 |
| Fact Extractor | 自动抽取代码、契约、数据和配置事实 |
| Rule Engine | 执行规划、兼容和影响规则 |
| OpenCode Agent | 在 Skill 与权限约束下执行 AI 辅助任务 |
| Review Workflow | 管理人工 Gate、审批和审计 |

---

## 4. 端到端业务流程

### 4.1 当前系统基线建立

```text
接入代码仓库
→ 固定 Branch / Commit
→ 解析 Maven / Gradle
→ 解析源码和字节码
→ 解析 Spring 语义
→ 解析 API / 消息 / 数据库 / 配置 / 测试
→ 统一 Fact IR
→ 稳定 ID 与实体消歧
→ RDF Current Graph
→ Neo4j 查询投影
→ SHACL 校验
→ RDFS / 受控 OWL 推理
```

输出：

```text
RepositorySnapshot
CurrentGraphRevision
ExtractionRun
ValidationReport
InferenceRun
```

### 4.2 业务语义基线建立

```text
业务文档与领域资料
→ Capability
→ UseCase
→ BusinessProcess
→ BusinessProcessStep
→ BusinessRule
→ BusinessObject
→ BusinessEvent
→ BusinessState
```

随后通过 ImplementationSlice 与代码图建立版本化映射。

### 4.3 新需求进入

```text
Feature Document
Detailed Design
API Design
Database Design
Sequence Diagram
Acceptance Criteria
→ DesignDocument / DesignRevision
```

系统先执行结构解析，再由 OpenCode Requirement Analyst 加载 `extract-requirement-ir` Skill，生成 Requirement IR Draft。

### 4.4 需求评审

人工确认：

```text
业务目标
范围与非范围
关键业务规则
失败路径
兼容约束
验收条件
未解决问题
```

通过后，Requirement IR 进入 Confirmed 状态。

### 4.5 目标图生成

Confirmed Requirement IR 转换为：

```text
Desired Business Graph
Desired Technical Design Graph
```

目标图保存 Explicit、Inferred、Suggested 和 Unresolved 的来源分类。

### 4.6 设计与当前代码对齐

OpenCode Code Graph Analyst 加载 `align-design-to-code-graph` Skill：

```text
Desired Entity
→ Current Graph 候选召回
→ 稳定 ID 匹配
→ 名称和类型匹配
→ 图邻域匹配
→ ImplementationSlice 匹配
→ CandidateAlignment Draft
```

关键映射由开发人员或架构师确认。

### 4.7 语义差异与变更规划

系统确定性执行 Current/Desired Diff：

```text
Node Difference
Relation Difference
Behavior Difference
Contract Difference
Data Difference
Configuration Difference
State Difference
Test Difference
Deployment Difference
```

Change Planner Agent 加载 `plan-code-graph-change` Skill，将差异和规则组合成 Proposed Change Draft。

### 4.8 架构评审与批准

Architecture Reviewer 独立检查：

```text
是否复用了正确的现有边界
是否引入不必要的新组件
公共契约兼容是否充分
数据库迁移是否安全
事务、并发、幂等和重试是否考虑
测试和发布动作是否完整
是否存在替代方案
```

人工审批后形成 Approved Change Graph。

### 4.9 Agent 辅助实现

Implementation Agent 仅在以下条件全部满足时启动：

```text
Approved Change 存在
Architecture Decision 已确认
Base Commit 未漂移
独立 Worktree 已创建
Allowed Files 已明确
Forbidden Files 已明确
Required Tests 已明确
```

Agent 加载 `implement-approved-change` Skill，仅生成批准范围内的代码和测试修改。

### 4.10 实现后对账

```text
代码修改
→ 编译和测试
→ 重新抽取 Actual Graph
→ Approved / Actual Reconciliation
→ Missing / Unexpected / Changed Design
```

Verification Agent 独立执行 `verify-and-reconcile` Skill，不负责自动掩盖或修复偏差。

### 4.11 影响和发布验证

规则引擎生成 Impact Graph：

```text
代码影响
契约影响
数据影响
业务影响
测试影响
部署影响
运行风险
```

OpenCode Agent 只负责解释结构化影响结果，不直接创造无证据的影响结论。

---

## 5. 总体逻辑架构

```text
┌────────────────────────────────────────────────────────────┐
│ 输入与连接器                                               │
│ Git / Maven / Gradle / Source / Bytecode / OpenAPI         │
│ Database / Config / Test / Deployment / Runtime            │
│ Feature Doc / Design Doc / Diagram                         │
└────────────────────────────────────────────────────────────┘
                             ↓
┌────────────────────────────────────────────────────────────┐
│ 确定性抽取层                                               │
│ Repository Scanner                                         │
│ Java AST Extractor                                         │
│ Bytecode Call Graph Extractor                              │
│ Spring Semantic Extractor                                  │
│ Contract / Database / Config / Test Extractor              │
└────────────────────────────────────────────────────────────┘
                             ↓
┌────────────────────────────────────────────────────────────┐
│ 规范化与证据层                                             │
│ Fact IR / Requirement IR                                   │
│ Stable ID / Entity Resolution                              │
│ Evidence / Provenance / Revision                           │
└────────────────────────────────────────────────────────────┘
                             ↓
┌────────────────────────────────────────────────────────────┐
│ 图与本体层                                                 │
│ Apache Jena / TDB2 / Fuseki                                │
│ Neo4j Projection                                           │
│ RDFS / OWL / SHACL                                         │
│ Current / Desired / Proposed / Actual / Impact             │
└────────────────────────────────────────────────────────────┘
                             ↓
┌────────────────────────────────────────────────────────────┐
│ 分析与规划层                                               │
│ Semantic Diff                                              │
│ Alignment Service                                          │
│ Implementation Slice Builder                               │
│ Planning Rule Engine                                       │
│ Compatibility Analyzer                                    │
│ Impact Propagation                                         │
│ Test / Release Planner                                     │
└────────────────────────────────────────────────────────────┘
                             ↓
┌────────────────────────────────────────────────────────────┐
│ AI Agent 层                                                │
│ OpenCode Agent Gateway                                     │
│ Agent / Skill Registry                                     │
│ Context Package Builder                                    │
│ Tool / MCP Gateway                                         │
│ Artifact Collector                                         │
└────────────────────────────────────────────────────────────┘
                             ↓
┌────────────────────────────────────────────────────────────┐
│ 工作流与产品层                                             │
│ Requirement Workspace                                      │
│ Mapping Review                                              │
│ Change Plan Review                                          │
│ Agent Execution                                             │
│ Reconciliation                                              │
│ Impact Explorer                                             │
└────────────────────────────────────────────────────────────┘
```

---

## 6. 技术架构与推荐技术栈

### 6.1 平台后端

```text
Java 21
Spring Boot
Spring Web
Spring Security
Spring Batch
Spring Scheduling
Spring JDBC
```

核心平台服务建议保持模块化单体起步，抽取任务和 Agent 执行采用独立 Worker。

### 6.2 仓库和代码解析

| 能力 | 技术 |
|---|---|
| Git | JGit |
| Maven | Maven Model API |
| Gradle | Gradle Tooling API |
| Java AST | Eclipse JDT |
| 字节码和调用图 | SootUp |
| 深层程序分析备选 | WALA |
| 多语言结构解析 | Tree-sitter |
| Spring 语义 | 自定义 JDT Extractor |
| SQL | SQL AST Parser |
| OpenAPI | OpenAPI Parser |
| Protobuf | Descriptor API |
| 数据库 Catalog | JDBC Metadata |
| Kubernetes | Kubernetes Java Client |

### 6.3 图和语义

```text
Apache Jena
Jena TDB2
Jena Fuseki
Jena SHACL
Protégé
Neo4j
```

职责：

```text
Jena/TDB2
保存本体、RDF 事实、Named Graph、推理和校验结果

Fuseki
提供 SPARQL 查询和图数据服务

Neo4j
提供调用路径、依赖路径、影响路径和交互式图探索

Protégé
用于本体设计、小规模推理和一致性检查
```

### 6.4 平台存储

```text
PostgreSQL
保存用户、任务、审批、Agent Run、Artifact、规则版本和审计状态

对象存储
保存原始设计文档、源码证据、扫描产物、报告和大型 Diff

OpenSearch（可选）
保存全文代码和文档索引

向量索引（可选）
仅用于候选召回，不作为事实存储
```

### 6.5 AI 执行

```text
OpenCode
.opencode/agents
.opencode/skills
.opencode/tools
Remote MCP
Isolated Git Worktree
```

### 6.6 前端

```text
React
TypeScript
Cytoscape.js
Monaco Editor
```

---

## 7. 服务模块设计

### 7.1 Repository Service

职责：

```text
仓库注册
认证配置
Branch / Commit 固定
Worktree 管理
变更文件识别
扫描触发
```

核心实体：

```text
Repository
RepositoryCredentialRef
RepositorySnapshot
CommitSnapshot
WorktreeLease
```

### 7.2 Build Model Service

职责：

```text
Maven Effective Model
Gradle Project Model
Module 和 SourceSet
Classpath
Generated Source
Build Target
```

### 7.3 Extraction Service

由多个 Extractor Plugin 组成：

```text
JavaSourceExtractor
BytecodeExtractor
SpringExtractor
ContractExtractor
DatabaseExtractor
ConfigurationExtractor
TestExtractor
DeploymentExtractor
RuntimeExtractor
```

统一输出 Fact IR。

### 7.4 Entity Resolution Service

负责：

```text
稳定 URI
重命名和移动匹配
逻辑实体与 Revision
跨解析器实体合并
业务对象与技术表示映射
```

### 7.5 Knowledge Graph Service

负责：

```text
RDF Dataset
Named Graph 生命周期
Current Graph 发布
Desired Graph 写入
Proposed / Approved Graph 管理
Actual Graph 版本
Impact Graph
SPARQL Query Template
Neo4j Projection
```

### 7.6 Ontology and Validation Service

负责：

```text
Ontology Import
RDFS 推理
受控 OWL 推理
SHACL 校验
Inference Materialization
Validation Profile
```

### 7.7 Document Ingestion Service

负责：

```text
文档上传
版本和 Hash
章节分段
表格解析
设计证据定位
图表或时序图结构化
```

输出 DesignDocument、DesignRevision、DesignSection 和 DocumentEvidence。

### 7.8 Requirement Service

负责：

```text
Requirement IR
业务目标
流程和规则变化
目标技术实体
验收条件
未解决问题
评审状态
```

### 7.9 Alignment Service

负责：

```text
精确匹配
候选召回
图邻域评分
语义评分
CandidateAlignment
人工确认
```

### 7.10 Implementation Slice Service

负责在业务步骤和代码图之间形成受控边界：

```text
Primary Entry
Supporting Code
Contract Entry
Business Data
Persistence Object
Remote Operation
Technical Event
Configuration
Test
Deployable Unit
```

### 7.11 Semantic Diff Service

比较 Current 和 Desired：

```text
Add / Remove / Modify Entity
Add / Remove Relation
Constraint Change
Behavior Change
Contract Change
Data Change
State Transition Change
```

### 7.12 Change Planning Service

负责：

```text
规则模板执行
Required Proposal
Recommended Proposal
Alternative Proposal
Verification Obligation
Implementation Task DAG
Compatibility Assessment
```

### 7.13 Review Workflow Service

负责：

```text
Requirement Review Gate
Alignment Review Gate
Architecture Review Gate
Data Review Gate
Security Review Gate
Release Review Gate
```

### 7.14 Agent Gateway

负责管理 OpenCode：

```text
OpenCode Server Pool
Session 创建
Agent 选择
Skill 白名单
Context Package
权限请求
Worktree
Artifact 回收
Diff 回收
Run 审计
```

### 7.15 Reconciliation Service

负责：

```text
Approved Change 与 Actual Graph 对比
结构对账
行为对账
契约对账
数据迁移对账
测试对账
设计偏差分类
```

### 7.16 Impact Service

负责：

```text
Impact Rule
Change Propagation
Compatibility
Risk
Test Selection
Release Planning
Business Projection
```

---

## 8. 图空间与 Named Graph 设计

推荐 Named Graph：

```text
urn:graph:ontology:core
urn:graph:ontology:business
urn:graph:ontology:sdn
urn:graph:current:{repository}:{commit}
urn:graph:business:{domain}:{revision}
urn:graph:desired:{requirement}:{designRevision}
urn:graph:proposed:{changeSet}
urn:graph:approved:{changeSet}
urn:graph:actual:{repository}:{commit}
urn:graph:impact:{analysisRun}
urn:graph:runtime:{environment}:{snapshot}
urn:graph:inferred:{baseGraph}:{inferenceRun}
```

每个图必须拥有：

```text
graphId
graphType
baseRevision
createdAt
createdBy
sourceArtifact
status
validationStatus
```

---

## 9. 核心数据模型

### 9.1 实体与 Revision

```text
LogicalEntity
EntityRevision
RelationFact
Evidence
```

逻辑实体保持跨版本连续，Revision 绑定具体 Commit、Schema Version、环境或文档版本。

### 9.2 Requirement IR

```text
RequirementIR
├── Requirement
├── CapabilityChange
├── UseCaseChange
├── ProcessChange
├── BusinessRuleChange
├── BusinessObjectChange
├── ContractChange
├── DataChange
├── ConfigurationChange
├── AcceptanceCriterion
├── ExplicitDesignFact
├── InferredDesignFact
├── ImplementationSuggestion
└── UnresolvedDesignQuestion
```

### 9.3 Alignment

```text
CandidateAlignment
├── desiredEntity
├── currentCandidate
├── alignmentType
├── confidence
├── evidence
├── alternatives
├── modelVersion
└── reviewStatus
```

### 9.4 Change Planning

```text
DesignChangeSet
ProposedChange
ApprovedChange
DesignDecision
VerificationObligation
ImplementationTask
CompatibilityAssessment
```

### 9.5 Agent Artifact

```text
AgentRun
├── runId
├── agentName
├── skillName
├── skillVersion
├── modelId
├── sessionId
├── stage
├── contextHash
├── inputRefs
├── evidenceRefs
├── assumptions
├── unresolvedQuestions
├── outputArtifact
├── permissionEvents
├── diffRef
└── status
```

---

## 10. OpenCode Agent 体系

### 10.1 Agent 拓扑

```text
requirement-orchestrator
├── requirement-analyst
├── code-graph-analyst
├── change-planner
├── architecture-reviewer
├── implementation-agent
└── verification-agent
```

### 10.2 主编排状态机

```text
Extract
→ RequirementReview
→ Align
→ AlignmentReview
→ Plan
→ ArchitectureReview
→ Approved
→ Implement
→ Verify
→ Impact
→ ReleaseReview
→ Completed
```

任何 Gate 未通过时，主 Agent 必须停止，不能自动跳过。

### 10.3 Requirement Analyst

输入：

```text
DesignRevision
DocumentEvidence
已有业务语义
文档模板
```

输出：

```text
RequirementIRDraft
DesiredEntityDraft
UnresolvedQuestion
Evidence Mapping
```

禁止：

```text
查询或修改业务代码
把实现建议写成设计事实
自行批准需求语义
```

### 10.4 Code Graph Analyst

输入：

```text
Confirmed Requirement IR
Desired Entity
Current Graph Revision
```

输出：

```text
CandidateAlignmentDraft
ImplementationSliceDraft
Evidence and Alternatives
```

禁止自行确认关键映射。

### 10.5 Change Planner

输入：

```text
Confirmed Alignment
Semantic Graph Diff
Planning Rule Set
```

输出：

```text
ProposedChangeDraft
VerificationObligation
ImplementationTaskDraft
CompatibilityAssessment
```

### 10.6 Architecture Reviewer

作为独立 Agent，不与 Change Planner 共享结论偏好。

检查：

```text
边界是否合理
复用是否正确
变更是否最小
兼容是否充分
迁移是否安全
测试是否完整
发布是否可控
```

### 10.7 Implementation Agent

仅允许：

```text
读取 Approved Change Context
读取指定代码文件
编辑 allowedFiles
运行允许的编译和测试命令
生成 Diff 和实现报告
```

禁止：

```text
git commit
git push
git merge
kubectl
helm
terraform
访问 Secret
编辑 forbiddenFiles
```

### 10.8 Verification Agent

独立读取：

```text
Approved Change
Code Diff
Actual Graph
Test Result
```

输出：

```text
ImplementedAsDesigned
MissingImplementation
UnexpectedImplementation
ChangedDesign
PartiallyImplemented
Unverified
```

---

## 11. Skill 体系

### 11.1 `orchestrate-requirement-change`

负责端到端阶段编排、Gate 检查和 Artifact 完整性。

### 11.2 `extract-requirement-ir`

负责从设计文档生成 Requirement IR，并区分 Explicit、Inferred、Suggested 和 Unresolved。

### 11.3 `align-design-to-code-graph`

负责目标实体到 Current Graph 的候选对齐和实现切片候选生成。

### 11.4 `plan-code-graph-change`

负责 Graph Diff 到变更提案、兼容评估、验证义务和任务 DAG。

### 11.5 `implement-approved-change`

负责在批准范围和文件白名单内修改代码和测试。

### 11.6 `verify-and-reconcile`

负责 Approved Change 与 Actual Graph 对账。

### 11.7 `explain-change-impact`

负责根据结构化 Impact Graph 输出开发、测试、架构和发布视角解释。

Skill 必须包含：

```text
name
description
version
owner
stage
preconditions
steps
output contract
stop conditions
forbidden actions
```

---

## 12. Agent Tool / MCP 设计

Agent 不应直接执行任意 SPARQL、Cypher 或数据库查询。平台提供白名单能力。

### 12.1 Context Tool

```text
ontology_requirement_context
```

返回：

```text
Requirement
DesignRevision
Current Stage
Allowed Action
Approval State
Relevant Artifact
```

### 12.2 Graph Query Tool

```text
ontology_graph_query
```

允许 QueryType：

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

限制：

```text
最大深度
最大节点数
最大路径数
固定超时
只读
```

### 12.3 Draft Write Tools

```text
ontology_alignment_candidates
ontology_change_plan_draft
ontology_record_agent_artifact
```

只能写 Candidate 或 Draft，不能批准变更，也不能写 Current Graph。

### 12.4 Reconciliation Tool

```text
ontology_reconciliation_context
```

返回 Approved Change、Actual Graph 子图和验证义务。

---

## 13. Context Package 设计

为了避免 Agent 无边界读取整个仓库，平台构建阶段化 Context Package。

### 13.1 文档分析包

```text
Requirement ID
DesignRevision
相关章节
原文证据
已有业务术语
输出 Schema
```

### 13.2 对齐包

```text
Confirmed Requirement IR
Desired Entity
Current Graph 候选
代码摘要
图邻域
历史映射
```

### 13.3 规划包

```text
Semantic Diff
Confirmed Alignment
ImplementationSlice
规划规则
兼容矩阵
部署依赖
```

### 13.4 实现包

```text
Approved Changes
Architecture Decisions
Allowed Files
Forbidden Files
Relevant Source
Required Tests
Acceptance Criteria
Forbidden Changes
```

每个包生成 `contextHash`，用于审计和重放。

---

## 14. 人工 Gate 设计

### 14.1 Requirement Review Gate

确认：

```text
业务目标
范围
规则
状态
失败路径
验收标准
```

### 14.2 Alignment Review Gate

确认：

```text
主要代码入口
业务规则实现边界
ImplementationSlice
复用或新增决策
```

### 14.3 Architecture Review Gate

确认：

```text
架构方案
公共契约
数据迁移
消息兼容
配置作用域
部署和回滚
```

### 14.4 Security / Data Gate

以下变化强制触发：

```text
认证和授权
租户隔离
Secret
个人或敏感数据
不可逆迁移
```

### 14.5 Release Gate

确认：

```text
测试结果
实际影响
部署顺序
监控
回滚
运行验证
```

---

## 15. 自动化、AI 和人的责任边界

### 15.1 代码自动化

```text
仓库扫描
构建模型解析
代码、契约和数据库抽取
Current Graph 生成
Graph Diff
正式规则执行
SHACL
测试执行
Actual Graph 生成
Reconciliation 基础比较
```

### 15.2 AI 辅助

```text
需求文档理解
业务语义候选
代码实体候选匹配
ImplementationSlice 候选
变更计划补充
架构替代方案
代码与测试草案
影响解释
```

### 15.3 人工负责

```text
业务语义最终定义
关键映射确认
架构选择
破坏性兼容决策
风险接受
代码评审
生产发布
```

治理原则：

```text
机器负责能证明的事实
AI 负责可能正确的候选和解释
人负责需要承担责任的决策
```

---

## 16. 规划规则体系

规则分为：

```text
通用软件规则
领域规则
组织治理规则
项目局部规则
```

### 16.1 API 字段新增

自动展开：

```text
Contract Schema
Request / Response DTO
Mapper
Business Attribute Mapping
Compatibility Assessment
Contract Test
Documentation
```

### 16.2 业务规则新增

自动展开：

```text
Rule Enforcer 候选
Validator / Domain Service
失败类型
错误契约
单元测试
集成测试
业务映射
```

### 16.3 消息事件新增

自动展开：

```text
Business Event
Technical Event Type
Message Schema
Producer
Consumer
Compatibility
Replay
Idempotency
Deployment Ordering
```

### 16.4 数据库约束新增

自动展开：

```text
历史数据扫描
应用预校验
Migration
Constraint
Rollback
Integration Test
Monitoring
```

### 16.5 配置项新增

自动展开：

```text
ConfigurationKey
Default
Environment Override
Reader
Refresh Policy
Deployment Values
Configuration Test
```

---

## 17. 兼容性分析

### 17.1 API

检查：

```text
Required Field
Default
Nullable
Enum
Status Code
Authentication
Consumer Version
```

### 17.2 消息

检查：

```text
Schema Compatibility
Field Default
Old Consumer
Replay
Ordering
Idempotency
Lagging Consumer
```

### 17.3 数据库

检查：

```text
Existing Data
Read / Write Version
Expand-Migrate-Contract
Index Cost
Lock Risk
Rollback
```

### 17.4 配置

检查：

```text
Default
Scope
Environment Override
Dynamic Refresh
Missing Value
Secret Handling
```

---

## 18. 实现任务 DAG

每个 Approved Change 转成 ImplementationTask：

```text
ModifyCode
AddCode
ModifyContract
AddMigration
ModifyConfiguration
AddTest
ModifyDeployment
UpdateDocumentation
```

任务属性：

```text
taskId
proposalId
repository
module
suggestedFiles
allowedFiles
forbiddenFiles
dependsOn
acceptanceCriteria
requiredTests
owner
status
```

任务 DAG 用于控制 Agent 的修改范围和执行顺序。

---

## 19. 设计—实现对账

### 19.1 结构对账

检查目标节点、属性和关系是否实际存在。

### 19.2 行为对账

检查：

```text
条件是否真正执行
数据是否真正读取
失败是否真正阻断后续动作
事务和异常语义是否符合设计
```

### 19.3 契约对账

重新解析 OpenAPI、Protobuf 或消息 Schema，而不是只检查 DTO。

### 19.4 数据对账

检查 Migration、真实 Catalog、应用映射和兼容顺序。

### 19.5 测试对账

区分：

```text
代码被覆盖
业务规则被验证
负向场景被验证
发布行为被验证
```

---

## 20. 影响分析

ImpactAssessment 包含：

```text
affectedEntity
impactType
certainty
severity
risk
evidence
path
decision
recommendedAction
```

传播状态：

```text
Candidate
Confirmed
Contained
Rejected
Unresolved
```

传播不能只依赖图可达性。规则必须结合：

```text
ChangeType
RelationType
方向
兼容性
上下文
证据
运行版本
```

---

## 21. 产品界面

### 21.1 Repository Workspace

展示：

```text
仓库
Commit
模块
扫描状态
抽取器状态
图版本
质量指标
```

### 21.2 Requirement Workspace

展示：

```text
原始文档
Requirement IR
目标图
证据定位
未解决问题
评审状态
```

### 21.3 Alignment Review

并排展示：

```text
设计实体
当前代码候选
图邻域
源码证据
评分组成
替代候选
```

### 21.4 Change Plan Review

展示：

```text
Semantic Diff
Required Proposal
Recommended Proposal
Alternative
Compatibility
Risk
Task DAG
Human Gate
```

### 21.5 Agent Run Console

展示：

```text
Agent / Skill
Stage
Session
Context Hash
Tool Calls
Permission Requests
Artifact
Code Diff
Test Results
```

### 21.6 Reconciliation View

展示：

```text
Approved vs Actual
Missing
Unexpected
Changed Design
Test Evidence
```

### 21.7 Impact Explorer

支持业务、代码、数据、测试、部署和运行视图。

---

## 22. 平台 API

### 22.1 Repository

```http
POST /api/repositories
POST /api/repositories/{id}/snapshots
POST /api/repositories/{id}/scans
GET  /api/repositories/{id}/graph-revisions
```

### 22.2 Documents and Requirements

```http
POST /api/design-documents
POST /api/design-documents/{id}/revisions
POST /api/design-revisions/{id}/extract
GET  /api/requirements/{id}/ir
POST /api/requirements/{id}/review
```

### 22.3 Alignment

```http
POST /api/alignments/runs
GET  /api/alignments/runs/{id}
POST /api/alignments/{id}/confirm
POST /api/alignments/{id}/reject
```

### 22.4 Planning

```http
POST /api/change-plans
GET  /api/change-plans/{id}
POST /api/change-plans/{id}/review
POST /api/change-plans/{id}/approve
```

### 22.5 Agent

```http
POST /api/agent-runs
GET  /api/agent-runs/{id}
POST /api/agent-runs/{id}/permissions/{permissionId}
GET  /api/agent-runs/{id}/artifacts
GET  /api/agent-runs/{id}/diff
```

### 22.6 Reconciliation and Impact

```http
POST /api/reconciliation-runs
GET  /api/reconciliation-runs/{id}
POST /api/impact-analyses
GET  /api/impact-analyses/{id}
```

---

## 23. 事件模型

```text
RepositorySnapshotCreated
ExtractionCompleted
CurrentGraphPublished
DesignRevisionCreated
RequirementIRDrafted
RequirementIRConfirmed
DesiredGraphPublished
AlignmentDrafted
AlignmentConfirmed
ChangePlanDrafted
ChangePlanApproved
AgentRunStarted
AgentArtifactRecorded
CodePatchGenerated
ActualGraphPublished
ReconciliationCompleted
ImpactAnalysisCompleted
ReleaseApproved
RequirementVerified
```

每个事件保存：

```text
eventId
correlationId
requirementId
repositoryId
revision
runId
timestamp
actor
```

---

## 24. 安全与权限

### 24.1 代码和文档权限

平台必须继承：

```text
仓库权限
组织权限
业务域权限
设计文档权限
生产运行数据权限
```

### 24.2 AI 数据边界

```text
仓库白名单
目录排除
Secret 扫描
敏感字段脱敏
模型路由
数据保留策略
审计日志
```

### 24.3 Agent 最小权限

分析 Agent 默认只读；实现 Agent 需要人工授权；Git 提交、推送、合并和部署命令禁止。

### 24.4 Tool 安全

```text
白名单 QueryType
参数化查询
深度限制
结果限制
超时
幂等键
租户隔离
审计
```

---

## 25. 可靠性和幂等

### 25.1 Run Idempotency

每次任务使用：

```text
repositorySnapshot
requirementRevision
ruleSetVersion
extractorVersion
contextHash
```

生成幂等键。

### 25.2 版本漂移

如果 Agent 执行期间 Base Commit 变化：

```text
停止实现
重新计算 Current Graph
重新验证 Alignment 和 Plan
```

### 25.3 部分失败

各阶段 Artifact 独立持久化，失败后从最近合法阶段恢复。

### 25.4 Agent 输出不合法

如果 Agent 输出不符合 JSON Schema：

```text
拒绝写入
记录 Validation Error
要求同一 Agent 修复 Artifact
达到重试上限后转人工
```

---

## 26. 可观测性与质量指标

### 26.1 抽取质量

```text
解析成功率
未解析符号率
调用候选数量
Schema 漂移数量
SHACL 违规数量
```

### 26.2 AI 质量

```text
Requirement IR 人工修改率
Alignment Top-1 准确率
候选接受率
Proposal 接受率
Agent 越权请求率
Artifact Schema 失败率
```

### 26.3 闭环质量

```text
Approved / Actual 一致率
Missing Implementation 比率
Unexpected Change 比率
测试遗漏率
影响误报和漏报
发布回滚率
```

### 26.4 Trace

必须支持：

```text
设计原文
→ Requirement IR
→ Desired Entity
→ Alignment
→ Graph Diff
→ Proposed Change
→ Approved Change
→ Agent Patch
→ Actual Entity
→ Test Evidence
→ Release Evidence
```

---

## 27. 部署架构

### 27.1 起步部署

```text
Docker Compose
├── platform-api
├── extraction-worker
├── agent-gateway
├── fuseki
├── neo4j
├── postgres
└── object-storage
```

### 27.2 生产部署

```text
Kubernetes
├── API Deployment
├── Extraction Worker Pool
├── Planning Worker Pool
├── OpenCode Server Pool
├── Isolated Worktree Job
├── Fuseki / TDB2 StatefulSet
├── Neo4j
├── PostgreSQL
├── Object Storage
└── Observability Stack
```

Agent Worktree 应使用短生命周期隔离卷和最小网络权限。

---

## 28. SDN 场景完整示例

需求：

> 网络策略支持最小带宽约束。路径中的每条链路可用带宽不得低于策略要求；带宽数据超过 30 秒不得用于计算；失败时不得向设备下发流表。

### 28.1 Current Graph

```text
DeployPolicyRequest
    hasField policyId

PathConstraint
    hasField maxHops

PathComputationService.compute
    calls ConstraintEvaluator.evaluate

ConstraintEvaluator
    enforces ExcludeDownLinkRule

OpenFlowAdapter.installFlows
    performs FLOW_MOD
```

### 28.2 Requirement Analyst 输出

```text
BusinessRule: MinimumAvailableBandwidthRule
BusinessRule: BandwidthDataFreshnessRule
Desired Field: minimumBandwidthMbps
Desired Config: topology.bandwidth.max-age
Acceptance: 失败时不得调用 FLOW_MOD
```

### 28.3 Code Graph Analyst 候选

```text
PathConstraint                  0.96
ConstraintEvaluator.evaluate   0.93
PathComputationService.compute 0.88
TopologyMetricService          0.84
```

人工确认：

```text
PathConstraint 承载请求约束
ConstraintEvaluator 执行链路资格规则
TopologyMetricService 提供带宽和采样时间
```

### 28.4 Semantic Diff

```text
Add Field minimumBandwidthMbps
Add Rule MinimumAvailableBandwidthRule
Add Rule BandwidthDataFreshnessRule
Add Config topology.bandwidth.max-age
Add Error Contract
Add Negative Acceptance Criterion
```

### 28.5 Proposed Change

```text
修改 OpenAPI
修改 Request DTO
修改 PathConstraint
修改 Mapper
修改 ConstraintEvaluator
读取 Link.availableBandwidth
读取 bandwidthSampleTime
新增配置项
新增异常和错误响应
新增单元、契约和负向集成测试
```

### 28.6 Architecture Decision

```text
字段可选，未提供时保持旧行为
规则复用 ConstraintEvaluator
不修改南向协议
过期数据直接拒绝，不降级
失败时不得调用 OpenFlowAdapter
```

### 28.7 Implementation Agent

允许文件：

```text
OpenAPI Schema
DeployPolicyRequest
PathConstraint
ConstraintEvaluator
ConfigurationProperties
相关测试
```

禁止：

```text
OpenFlow 协议 Schema
部署生产配置
其他服务仓库
```

### 28.8 Reconciliation

检查：

```text
字段是否真实存在
规则是否读取带宽
规则是否校验采样时间
失败是否阻断 FLOW_MOD
OpenAPI 是否一致
测试是否断言南向未调用
```

---

## 29. 推荐工程目录

```text
requirement-to-code-platform/
├── platform-api/
├── repository-service/
├── build-model-service/
├── extraction-worker/
├── extractors/
│   ├── java-jdt/
│   ├── bytecode-sootup/
│   ├── spring/
│   ├── contract/
│   ├── database/
│   ├── configuration/
│   ├── test/
│   └── deployment/
├── fact-model/
├── entity-resolution/
├── knowledge-graph/
├── ontology-service/
├── graph-projection-neo4j/
├── document-ingestion/
├── requirement-service/
├── alignment-service/
├── implementation-slice-service/
├── semantic-diff-service/
├── change-planning-service/
├── compatibility-service/
├── impact-service/
├── review-workflow/
├── agent-gateway/
├── reconciliation-service/
├── web-ui/
├── ontology/
├── shapes/
├── rules/
├── examples/
└── .opencode/
```

---

## 30. 分阶段建设计划

### 阶段一：当前代码图

交付：

```text
Repository Scan
Java / Spring Extractor
Fact IR
Neo4j Code Graph
基础查询界面
```

验收：能够从 API 查到 Controller、Service、Repository 和 Table 路径。

### 阶段二：RDF 与本体

交付：

```text
Jena / TDB2 / Fuseki
核心本体
SHACL
Named Graph
RDFS 推理
```

验收：能够加载代码事实并执行 SPARQL、SHACL 和基础推理。

### 阶段三：业务图和映射

交付：

```text
Business Ontology
SDN Ontology
ImplementationSlice
Mapping Review
```

验收：能够从业务步骤定位完整代码实现切片。

### 阶段四：需求规划

交付：

```text
Document Ingestion
Requirement IR
Desired Graph
Alignment
Semantic Diff
Proposed Change
```

验收：能够把一份详细设计转为可评审的代码图变更方案。

### 阶段五：OpenCode Agent 闭环

交付：

```text
Agent Gateway
OpenCode Server Pool
Agent / Skill
Tool / MCP
Artifact
Worktree
```

验收：能够在人工批准后生成受限代码 Patch 和测试 Patch。

### 阶段六：对账和影响

交付：

```text
Actual Graph
Reconciliation
Impact Graph
Test Selection
Release Plan
```

验收：能够判断实现是否符合设计，并解释业务、代码和发布影响。

### 阶段七：运行闭环

交付：

```text
Deployment Graph
Runtime Trace
Configuration Snapshot
Production Verification
```

验收：需求从设计到生产运行证据形成完整追踪。

---

## 31. 最终验收标准

完整系统应达到：

1. 能从真实 Java/Spring 仓库生成版本化代码知识图；
2. 能加载和校验 RDF/OWL/SHACL 本体资产；
3. 能建立业务流程、规则和代码实现切片；
4. 能把详细设计转换为 Requirement IR 和 Desired Graph；
5. 能生成有证据、置信度和替代方案的实体对齐候选；
6. 能自动计算 Current/Desired Semantic Diff；
7. 能生成覆盖代码、契约、数据库、消息、配置、测试和部署的变更提案；
8. 能通过人工 Gate 形成 Approved Change；
9. 能使用 OpenCode Agent + Skill 在文件白名单内生成 Patch；
10. 能阻止 Agent 执行提交、推送、合并和生产部署；
11. 能重新生成 Actual Graph 并进行设计—实现对账；
12. 能生成可解释的 Impact Graph、测试选择和发布建议；
13. 所有事实、候选、规则、Agent 输出和人工决定均可审计和重放。

---

## 32. 最终系统结论

本系统的核心不是某一个大模型、某一种图数据库或某一个静态分析器，而是建立一套分层可信机制：

```text
编译器和连接器
→ 提供可证明事实

RDF、本体、SHACL 和规则
→ 提供结构化语义和确定性判断

OpenCode Agent + Skill
→ 提供文档理解、候选匹配、规划补全和受控实现

人工 Gate
→ 提供业务、架构、安全和生产责任决策

Actual Graph + Reconciliation
→ 提供最终实现真实性
```

最终形成：

```text
特性文档
→ 业务语义
→ 目标设计
→ 当前代码对齐
→ 变更规划
→ 人工批准
→ Agent 辅助实现
→ 实际图验证
→ 影响与发布
→ 运行证据
```

这是一个面向长期工程治理的需求到代码智能平台，而不是一次性的代码生成工具。
