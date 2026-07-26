# 新增需求详细设计到代码图变更的完整设计

## 1. 文档目标

本文定义新增需求进入系统后，如何把需求说明、详细设计、流程图、时序图、接口设计、数据库设计和发布设计转换为对当前代码知识图谱的**可评审变更提案**。

系统不能把设计文档抽取结果直接写入当前代码图。设计文档描述的是期望状态，当前代码图描述的是已经存在并能够被代码、契约、数据库或运行平台验证的事实。二者必须通过独立的目标图、变更提案图和实现对账过程连接。

完整链路为：

```text
需求与详细设计文档
→ 文档结构解析
→ Requirement IR
→ 目标业务图
→ 目标技术设计图
→ 与当前知识图实体对齐
→ Current/Desired Graph Diff
→ Proposed Change Graph
→ 设计与架构评审
→ Approved Change Graph
→ 实现任务与代码修改
→ 静态分析重新抽取
→ Actual Graph After Implementation
→ 设计—实现对账
→ 测试与发布验证
```

本文解决以下问题：

- 详细设计文档中哪些内容应转换为节点、关系、约束和变化；
- 如何区分业务目标、技术设计和实现猜测；
- 如何把设计中的业务对象、流程步骤、API、消息、数据库和配置与当前代码图对齐；
- 当前系统已有能力应复用还是新增；
- 如何生成 Add、Modify、Remove、Relate、Migrate 等代码图变更提案；
- 如何保留候选、置信度、证据、替代方案和人工决策；
- 实现完成后如何验证代码是否真正符合设计。

---

## 2. 四张图必须分离

需求驱动变更需要在原有知识图、变更图、影响图之外，显式增加目标设计图和变更提案图。逻辑上建议区分四种状态图。

### 2.1 Current Knowledge Graph

当前知识图表示系统当前已知事实：

```text
已有业务能力、流程和规则
已有 API、代码、数据库和消息
已有配置、测试、构建与运行关系
当前版本和历史 Revision
```

事实来源必须可验证，例如编译器语义、OpenAPI、数据库 Catalog、配置中心、Kubernetes、APM 或人工批准的业务映射。

### 2.2 Desired Design Graph

目标设计图表示需求完成后期望成立的事实：

```text
期望新增或修改的业务流程
期望新增的业务规则
期望存在的 API、Schema、事件和数据库约束
期望的状态迁移、失败路径和发布约束
```

目标图中的节点不是当前事实，不应被普通代码查询误认为已经实现。

### 2.3 Proposed Change Graph

变更提案图描述从当前状态到目标状态所需的候选操作：

```text
新增节点
修改节点
删除或废弃节点
新增或删除关系
修改约束
数据迁移
兼容层
测试与发布动作
```

每个提案必须保存来源、目标、证据、置信度、风险、替代方案和评审状态。

### 2.4 Actual Graph After Implementation

代码实现后，由解析器重新抽取实际事实图。它与 Approved Change Graph 对账，用于判断：

```text
ImplementedAsDesigned
MissingImplementation
UnexpectedImplementation
ChangedDesign
UnverifiedRequirement
```

### 2.5 为什么不能直接修改 Current Graph

若文档中写了“新增 `PolicyBandwidthValidator`”，但代码尚未实现，直接在当前代码图创建 Method 或 Type 会造成：

- 影响分析把不存在的节点当作真实依赖；
- 测试覆盖查询误认为已有实现；
- 构建和部署分析产生虚假产物；
- 设计修改后难以区分历史提案和实际代码；
- 无法判断设计是否真正落地。

因此目标节点应使用 `DesiredEntity`、`ProposedEntity` 或独立 Named Graph 保存，只有实现后被正式抽取和对齐，才能成为当前事实。

---

## 3. 输入文档与证据模型

### 3.1 支持的输入类型

```text
需求说明书
产品需求文档
详细设计文档
架构设计记录 ADR
BPMN 或流程图
UML/时序图
状态机图
OpenAPI/AsyncAPI/Proto 草案
数据库 DDL 与 ER 图
配置清单
测试方案与验收标准
发布、迁移和回滚方案
```

不同输入需要不同解析器。自然语言章节可以由 LLM 辅助抽取；OpenAPI、Proto、SQL、BPMN 和状态机文件应优先使用确定性 Parser。

### 3.2 DocumentEvidence

所有抽取结论必须关联源证据：

```text
DocumentEvidence
├── documentId
├── documentVersion
├── sectionId
├── paragraphOrElementId
├── sourceText
├── sourceType
├── extractor
├── extractorVersion
├── confidence
└── contentHash
```

设计文档更新后，可通过 `contentHash` 和节点来源判断哪些目标事实需要重算。

### 3.3 事实、推断和建议分离

抽取结果应分为：

- **ExplicitDesignFact**：文档明确说明，例如“新增 POST API”；
- **InferredDesignFact**：由上下文推断，例如“该步骤可能需要事务”；
- **ImplementationSuggestion**：系统建议的技术实现，例如“建议复用现有 Repository”；
- **UnresolvedDesignQuestion**：设计缺失或冲突，例如“部分下发失败是否立即回滚”。

只有显式事实和经人工确认的推断才能进入 Approved Design Graph。ImplementationSuggestion 不能伪装成需求事实。

---

## 4. Requirement IR：需求设计中间模型

非结构化文档应先转换成稳定、可校验的 Requirement IR，再生成图。Requirement IR 是文档世界与图世界之间的契约。

### 4.1 顶层结构

```yaml
requirement:
  id: REQ-SDN-2026-001
  title: 支持带宽约束的网络策略部署
  version: 1.0
  goal: 部署网络策略时只选择满足最小可用带宽的链路
  priority: high
  owner: network-policy-team

scope:
  included:
    - 策略请求新增 minimumBandwidthMbps
    - 路径计算排除可用带宽不足的链路
    - 带宽数据过期时拒绝部署
    - 记录路径选择证据
  excluded:
    - 实时带宽预留
    - 多路径流量拆分

actors:
  - network-administrator
  - automation-system

capabilities:
  - network-policy-orchestration
  - path-computation
  - topology-observation

business_processes:
  - id: deploy-bandwidth-constrained-policy
    trigger: 提交包含最小带宽约束的网络策略
    preconditions:
      - 拓扑已同步
      - 链路带宽数据未过期
    steps:
      - id: validate-bandwidth-constraint
        action: 校验最小带宽参数
      - id: load-bandwidth-topology
        action: 读取包含可用带宽的拓扑
      - id: compute-constrained-path
        action: 排除带宽不足链路并计算路径
      - id: deploy-policy
        action: 编译并下发策略
    failure_flows:
      - id: bandwidth-data-stale
        action: 拒绝部署并返回带宽数据过期错误
      - id: no-feasible-path
        action: 返回不存在满足约束的路径

business_rules:
  - id: BR-SDN-BW-001
    statement: 所选路径上的每条链路可用带宽不得低于策略要求
  - id: BR-SDN-BW-002
    statement: 带宽采样时间超过允许时限时不得用于路径计算

business_objects:
  - NetworkPolicy
  - NetworkLink
  - NetworkTopology
  - NetworkPath

api_changes:
  - operation: POST /network-policies/{id}/deploy
    action: modify
    request_field:
      name: minimumBandwidthMbps
      type: integer
      required: false

state_changes:
  - object: NetworkPolicy
    transition: Validating -> Rejected
    reason: BANDWIDTH_DATA_STALE

configuration_changes:
  - key: topology.bandwidth.max-age
    action: add
    type: duration
    default: PT30S

acceptance_criteria:
  - id: AC-SDN-BW-001
    statement: 返回路径不得包含可用带宽低于要求的链路
  - id: AC-SDN-BW-002
    statement: 带宽数据过期时返回明确错误且不下发任何流表
```

### 4.2 Requirement IR 的语义分区

Requirement IR 至少分为：

```text
BusinessIntent
BusinessProcessDesign
BusinessRuleDesign
DataAndStateDesign
ContractDesign
PersistenceDesign
MessagingDesign
ConfigurationDesign
SecurityAndComplianceDesign
VerificationDesign
DeliveryAndMigrationDesign
```

分区的意义是让后续规则使用不同策略。业务规则不能直接按 API 字段变化处理；数据库迁移也不能按普通节点新增处理。

### 4.3 IR 校验

进入建图前应检查：

- Requirement 是否有稳定 ID、版本和业务目标；
- 每个关键流程是否有触发、入口、成功结果和失败结果；
- 每条 BusinessRule 是否具有可判定陈述；
- API、事件、数据库和配置变化是否标明 add/modify/remove；
- Breaking Change 是否描述兼容和迁移策略；
- AcceptanceCriterion 是否可被测试验证；
- 设计中的名称是否存在歧义或未定义缩写。

校验失败不应阻止保存草稿，但应阻止自动批准变更提案。

---

## 5. 从 Requirement IR 构建目标业务图

### 5.1 业务节点生成

Requirement IR 转换为：

```text
Requirement
UseCase
BusinessProcess
BusinessProcessStep
BusinessRule
BusinessObject
BusinessAttribute
BusinessEvent
BusinessState
StateTransition
AcceptanceCriterion
```

例如 `BR-SDN-BW-001` 转换为：

```text
MinimumBandwidthConstraint
    a PathEligibilityRule
    constrains NetworkLink
    governs ComputeConstrainedPath
```

### 5.2 复用已有节点还是新增节点

不能仅根据名称决定。匹配顺序建议为：

1. 稳定业务 ID 完全匹配；
2. Requirement/设计显式引用已有节点；
3. 同一 Capability 下名称、定义和约束一致；
4. 业务对象属性和状态机结构一致；
5. LLM 语义相似度候选。

若已有 `ComputeConstrainedPath` 已支持延迟、跳数和链路状态约束，新增带宽约束通常应修改已有步骤并增加规则，而不是创建另一个含义重叠的“计算带宽路径”流程。

### 5.3 业务图变化类型

```text
AddCapability
AddUseCase
AddProcess
AddProcessStep
ModifyProcessStep
AddBusinessRule
ModifyBusinessRule
AddBusinessAttribute
AddStateTransition
AddAcceptanceCriterion
DeprecateBusinessSemantics
```

业务层变化是后续技术变更推导的根因，不应被技术节点变化替代。

---

## 6. 构建目标技术设计图

详细设计中的技术部分生成 Desired Technical Graph。它可以引用当前实体，也可以描述尚不存在的期望实体。

### 6.1 技术设计节点

```text
DesiredAPIOperation
DesiredSchema
DesiredSchemaField
DesiredCodeRole
DesiredDatabaseObject
DesiredEventType
DesiredConfigurationKey
DesiredTestObligation
DesiredDeploymentAction
```

`DesiredCodeRole` 不必一开始绑定具体类名。例如：

```text
DesiredCodeRole: BandwidthConstraintEvaluator
role = BusinessRuleEnforcer
implements = BR-SDN-BW-001
preferredBoundary = PathComputationComponent
```

这允许系统先表达“需要一个规则执行点”，再判断当前代码中能否由 `ConstraintEvaluator` 扩展实现。

### 6.2 显式技术设计与架构推导

文档明确写出的类型、API 和表属于显式设计；系统根据模式补充的测试、错误映射或发布动作属于推导提案。

例如：

```text
显式设计：请求新增 minimumBandwidthMbps
推导提案：
- Request DTO 字段变化
- OpenAPI SchemaFieldAdded
- 参数校验
- 契约测试
- 旧客户端兼容评估
```

推导提案必须标记 `derivedByRule`，不能伪装为文档原文。

---

## 7. 设计实体与当前代码图对齐

实体对齐的目标是判断目标设计中的概念应复用、修改、扩展还是新增当前技术实体。

### 7.1 对齐对象

```text
业务对象 ↔ CodeType、Table、Schema、EventType
业务属性 ↔ Field、Column、SchemaField、MessageField
业务步骤 ↔ ImplementationSlice、APIOperation、Callable
业务规则 ↔ Validator、DomainMethod、DatabaseConstraint、ConfigurationKey
业务事件 ↔ EventType、Topic、MessageSchema
期望技术角色 ↔ 当前 Component、Type、Method
```

### 7.2 CandidateAlignment

每个候选对齐应建成节点：

```text
CandidateAlignment
├── desiredEntity
├── currentEntity
├── alignmentType
├── confidence
├── evidence
├── conflictingEvidence
├── alternatives
└── reviewStatus
```

`alignmentType`：

```text
ExactReuse
ExtendExisting
ModifyExisting
SemanticAlias
ReplaceExisting
NoMatch
Ambiguous
```

### 7.3 对齐证据

高到低建议为：

```text
ExplicitStableId
FullyQualifiedName
OpenAPIOperationIdOrSchemaRef
DatabaseQualifiedName
ExistingBusinessMapping
SameImplementationSlice
SignatureAndTypeMatch
CallAndDataFlowContext
NameAndDescriptionSimilarity
LLMSemanticInference
```

关键业务规则和破坏性契约变化不能只依赖最后两类弱证据。

### 7.4 SDN 示例

设计角色：

```text
BandwidthConstraintEvaluator
```

当前候选：

```text
ConstraintEvaluator.evaluate(PathConstraint, Link)
confidence = 0.91
alignmentType = ExtendExisting
```

证据：

- 已属于 `PathComputationSlice`；
- 已执行链路状态、跳数和延迟规则；
- 参数中已有 `PathConstraint`；
- 相同 Component 和责任团队。

替代候选：新建 `BandwidthConstraintEvaluator`，confidence 0.63。架构评审可以选择复用或拆分。

---

## 8. Current/Desired Graph Diff

图差异不只是节点增删，还包括关系、约束、状态和边界变化。

### 8.1 差异操作

```text
AddEntity
ModifyEntity
RemoveEntity
DeprecateEntity
AddRelation
RemoveRelation
ModifyRelation
AddConstraint
ModifyConstraint
RemoveConstraint
AddStateTransition
ModifyCompatibility
AddMigration
AddVerificationObligation
AddDeliveryConstraint
```

### 8.2 差异计算键

差异比较应基于：

```text
LogicalEntityId
EntityRevision
canonicalId
signature
semanticRole
relationType
context
constraintExpression
versionAndEnvironment
```

不能仅比较 URI 或名称。

### 8.3 三值与开放世界

“目标图有、当前图未找到”不总等于必须新增。可能是：

```text
真正不存在
已有但尚未抽取
动态实现无法识别
存在但没有业务映射
外部系统负责
```

因此 Diff 结果应支持：

```text
MissingConfirmed
MissingSuspected
ExistingMatched
ExistingIncompatible
Unknown
```

只有 `MissingConfirmed` 才能直接生成高置信新增提案。

---

## 9. Proposed Change Graph

### 9.1 核心节点

```text
DesignChangeSet
ProposedChange
ProposedEntity
CandidateAlignment
DesignDecision
ImplementationTask
VerificationObligation
MigrationAction
DeliveryAction
DesignEvidence
```

### 9.2 ProposedChange 分类

```text
ProposedNodeAddition
ProposedNodeModification
ProposedNodeRemoval
ProposedRelationAddition
ProposedRelationRemoval
ProposedConstraintChange
ProposedBehaviorChange
ProposedContractChange
ProposedDataMigration
ProposedConfigurationChange
ProposedTestChange
ProposedDeploymentChange
```

### 9.3 核心关系

```text
DesignChangeSet derivedFrom Requirement
DesignChangeSet containsProposedChange ProposedChange
ProposedChange targetsCurrentEntity CurrentEntity
ProposedChange proposesEntity DesiredEntity
ProposedChange basedOnAlignment CandidateAlignment
ProposedChange supportedByEvidence DesignEvidence
ProposedChange derivedByRule PlanningRule
ProposedChange requiresDecision DesignDecision
ProposedChange createsTask ImplementationTask
ProposedChange requiresVerification VerificationObligation
ProposedChange dependsOn ProposedChange
```

### 9.4 状态机

```text
Extracted
→ Aligned
→ Proposed
→ UnderReview
→ Approved | Rejected | NeedsRevision
→ Implementing
→ Implemented
→ Verified
→ Released
```

候选变更和批准变更必须分开。需求文档自动转换最多到 `Proposed`，除非组织明确允许某些低风险规则自动批准。

---

## 10. 设计模式规则库

从设计差异到工程变化不能完全依赖自由文本生成，应使用可版本化规则库。

### 10.1 API 字段新增规则

输入：

```text
SchemaFieldAdded
```

候选输出：

```text
修改 OpenAPI Schema
修改或生成 Request/Response DTO
检查反序列化与校验逻辑
检查 Mapper 和业务属性映射
生成契约兼容评估
新增/修改契约测试
检查 SDK 和消费者影响
```

### 10.2 业务规则新增规则

输入：

```text
BusinessRuleAdded
```

候选输出：

```text
查找现有 RuleEnforcer 或 Validator
扩展现有实现或新增规则执行节点
关联 primary/supporting ImplementationSlice
确定失败类型和错误契约
增加单元与业务规则测试
若规则依赖数据库约束，增加 Migration
若由配置控制，增加 ConfigurationKey
```

### 10.3 业务事件新增规则

```text
Add EventType
Add MessageSchema
Add Producer/Serializer
Add Topic 或复用路由
Add Consumer Subscription
Add Compatibility Assessment
Add Contract/Replay/Idempotency Tests
Add Deployment Order Constraint
```

### 10.4 数据库约束新增规则

```text
Add DatabaseConstraint
检查历史数据是否满足
Add PreMigrationValidation
Add MigrationScript
Add ApplicationValidation
Add FailureMapping
Add Integration/Migration/Rollback Tests
```

### 10.5 配置新增规则

```text
Add ConfigurationKey
确定 BuildTime/Startup/Runtime
确定默认值和环境覆盖
确定动态刷新或重启要求
增加边界值测试
增加部署和回滚说明
```

### 10.6 SDN 带宽约束规则展开

业务设计：路径每条链路可用带宽大于等于要求。

候选工程变化：

```text
1. Modify API request schema
   add minimumBandwidthMbps

2. Modify business attribute mapping
   PolicyRequest.minimumBandwidthMbps
   → NetworkPolicy.minimumBandwidth

3. Extend PathConstraint
   add minimumAvailableBandwidth

4. Extend ConstraintEvaluator
   enforce MinimumBandwidthConstraint

5. Add topology attribute mapping
   LinkMetrics.availableBandwidth
   represents AvailableBandwidth

6. Add staleness rule
   BandwidthSample.timestamp + maxAge

7. Add configuration
   topology.bandwidth.max-age

8. Add failure contract
   BANDWIDTH_DATA_STALE
   NO_FEASIBLE_PATH

9. Add tests
   rule test
   path computation test
   stale data test
   API contract test
   end-to-end no-flow-installation test
```

---

## 11. 变更规划算法

```text
input:
    requirementDocumentVersion
    currentKnowledgeGraphRevision

ir = parseAndNormalize(requirementDocumentVersion)
validate(ir)

desiredBusinessGraph = buildBusinessGraph(ir)
desiredTechnicalGraph = buildTechnicalDesignGraph(ir)

alignments = resolveEntities(
    desiredBusinessGraph + desiredTechnicalGraph,
    currentKnowledgeGraphRevision
)

reviewRequired(alignments where ambiguous or lowConfidence)

graphDiff = compare(
    currentKnowledgeGraphRevision,
    desiredBusinessGraph + desiredTechnicalGraph,
    alignments
)

proposedChanges = []
for diff in graphDiff:
    rules = planningRules.match(diff, architectureContext)
    for rule in rules:
        proposedChanges += rule.expand(diff, alignments)

mergeEquivalentChanges(proposedChanges)
linkDependencies(proposedChanges)
calculateRiskAndReviewPolicy(proposedChanges)
createDesignChangeSet(proposedChanges)
```

### 11.1 去重和合并

多个设计事实可能产生相同技术变化。例如 API 字段新增和业务属性新增都可能推导修改 `PolicyRequest`。系统应按：

```text
目标逻辑实体
变化维度
目标 Revision
上下文
```

合并提案，但保留多个来源证据和规则。

### 11.2 依赖排序

```text
BusinessObject/Rule Design
→ Contract/Data Model
→ Core Implementation
→ Adapter/Integration
→ Tests
→ Migration
→ Deployment/Rollout
```

实际发布顺序仍由兼容性决定，不能直接从开发任务顺序推导。

---

## 12. 设计评审与人工决策

### 12.1 必须人工确认的场景

```text
多个高相似代码候选
公共 API 或消息破坏性变化
数据库删除和不可逆迁移
新增跨服务职责
业务规则语义不完整
SDN 部分下发失败的补偿策略
控制器集群一致性和主从边界
动态或反射代码无法定位
```

### 12.2 DesignDecision

```text
DesignDecision
├── decisionId
├── question
├── alternatives
├── selectedAlternative
├── rationale
├── decidedBy
├── decidedAt
└── affectsProposedChanges
```

例如：

```text
问题：带宽约束应扩展通用 ConstraintEvaluator 还是新增独立 Evaluator？
选择：扩展通用 ConstraintEvaluator
原因：现有约束组合框架已支持插件式规则，避免重复路径遍历。
```

批准后的决定应成为后续实体对齐和代码生成的确定证据。

---

## 13. 从 Proposed Change 生成实现任务

ImplementationTask 不应简单等同一个 ProposedChange。一个任务可以实现多个紧密相关变更，一个变更也可能被多个团队拆分执行。

```text
ImplementationTask
├── title
├── targetRepository
├── targetComponent
├── owners
├── proposedChanges
├── dependencies
├── acceptanceCriteria
├── requiredTests
├── deliveryConstraints
└── status
```

SDN 示例任务：

```text
Task-1 扩展策略 API 和领域约束模型
Task-2 将链路带宽指标接入拓扑快照
Task-3 实现最小带宽路径约束规则
Task-4 增加带宽数据过期保护
Task-5 增加 API、规则、路径和 E2E 测试
Task-6 增加配置、监控和灰度发布策略
```

任务创建后，`ProposedChange` 仍是语义真源，任务系统只是执行视图。

---

## 14. 实现后的实际图抽取

开发完成后必须重新运行：

```text
语言解析器
OpenAPI/Proto/AsyncAPI Parser
SQL/Schema Parser
配置抽取器
测试与覆盖抽取器
构建和部署抽取器
```

产生新的 EntityRevision 和实际 ChangeItem。不能根据开发者把任务标记为完成就认定设计已实现。

### 14.1 Proposed 与 Actual 对齐

```text
ProposedEntity ↔ ActualEntityRevision
ProposedRelation ↔ ActualRelation
ProposedConstraint ↔ ActualConstraint
VerificationObligation ↔ TestCase/TestExecution
DeliveryAction ↔ DeploymentEvidence
```

### 14.2 对账结论

```text
ImplementedAsDesigned
PartiallyImplemented
MissingImplementation
AlternativeImplementation
UnexpectedImplementation
DesignNoLongerApplicable
CannotVerify
```

`AlternativeImplementation` 不一定是失败，但需要补充 DesignDecision，更新目标图和映射。

---

## 15. 设计—实现对账规则

### 15.1 节点存在性

设计要求新增 `minimumBandwidthMbps`，实际 OpenAPI 和 DTO 都应存在对应字段。

### 15.2 关系存在性

设计要求 `ConstraintEvaluator` 执行 `MinimumBandwidthConstraint`，不仅要找到新方法，还要验证调用路径和 `enforcesRule` 映射。

### 15.3 行为与约束

字段和方法存在不代表规则已实现。需要结合：

```text
条件表达式或规则注册
字段数据流
失败分支
测试断言
运行证据
```

### 15.4 负向要求

验收标准“带宽数据过期时不得下发流表”需要验证：

```text
StaleData 分支
不会到达 OpenFlowAdapter.installFlows
测试验证零次南向调用
```

仅验证错误码不充分。

### 15.5 测试义务

每个 AcceptanceCriterion 和关键 BusinessRule 应至少有一个 `verifies` 测试。覆盖关系只能作为补充证据。

---

## 16. 失败、回退与版本演进

### 16.1 文档变化

详细设计版本从 1.0 更新到 1.1 时，旧 Proposed Change 不应覆盖。创建新的 DesignRevision，并标记：

```text
supersedes
invalidatesProposal
retainsDecision
```

### 16.2 需求取消

未实现提案标记 `Cancelled`；已实现内容需要产生新的回退或废弃 ChangeSet，不能删除历史。

### 16.3 部分实现

允许一个 DesignChangeSet 跨多个 PR 和 Release。每个 ProposedChange 独立跟踪 Implemented/Verified 状态，Requirement 的整体状态由完成策略聚合。

### 16.4 当前代码图变化

需求设计期间主分支可能已发生变化。批准或实施前应重新基于最新 KnowledgeGraphRevision 执行对齐和 Diff，检测：

```text
TargetMoved
TargetDeleted
ConflictingChange
AlreadyImplemented
ArchitectureBoundaryChanged
```

---

## 17. LLM、解析器、规则引擎和人工的职责

### 17.1 LLM

适合：

```text
文档章节识别
业务实体和规则候选抽取
自然语言与代码语义候选对齐
缺失问题识别
变更解释和任务描述生成
```

不适合无确认地：

```text
写入当前事实图
判定数据库迁移安全
确认外部消费者不存在
批准破坏性契约变化
把名称相似当作实体相同
```

### 17.2 确定性解析器

负责 OpenAPI、Proto、AsyncAPI、SQL、BPMN、状态机、代码 AST/IR、构建和运行平台事实。

### 17.3 规则引擎

负责 Requirement IR 校验、图差异解释、工程模式展开、兼容评估、依赖排序、风险和评审策略。

### 17.4 人工评审

负责领域语义、职责边界、复用与新建选择、破坏性兼容、迁移与补偿策略。

---

## 18. 系统组件

```text
DesignDocumentConnector
→ DocumentStructureParser
→ RequirementIRExtractor
→ RequirementIRValidator
→ DesiredBusinessGraphBuilder
→ DesiredTechnicalGraphBuilder
→ EntityResolutionService
↔ CurrentKnowledgeGraph
→ SemanticGraphDiffer
→ ChangePlanningRuleEngine
→ ProposedChangeGraphStore
→ DesignReviewService
→ TaskIntegration
→ ActualGraphExtractor
→ DesignImplementationReconciler
→ VerificationAndReleaseGate
```

### 18.1 存储建议

- 原始文档和解析证据存对象库；
- Requirement IR 使用版本化文档存储；
- Desired/Proposed/Approved Graph 使用独立 Named Graph 或独立图空间；
- Current Knowledge Graph 保持事实纯净；
- Reconciliation Result 按 AnalysisRun 保存，不覆盖历史。

---

## 19. API 设计建议

```text
POST /requirements/{id}/design-revisions
POST /design-revisions/{id}/extract
POST /design-revisions/{id}/validate
POST /design-revisions/{id}/align
POST /design-revisions/{id}/plan-changes
GET  /design-change-sets/{id}
POST /proposed-changes/{id}/approve
POST /design-change-sets/{id}/reconcile
GET  /requirements/{id}/traceability
```

每个异步分析操作产生 `AnalysisRun`，记录输入版本、工具版本、规则版本和结果图。

---

## 20. SHACL 与治理约束

建议验证：

```text
Requirement 必须有稳定 ID 和至少一个目标能力或 UseCase
BusinessRule 必须关联来源和至少一个受约束对象或步骤
DesiredEntity 必须关联 DesignRevision
ProposedChange 必须关联 Requirement、证据和状态
Modify/Remove 提案必须有目标当前实体
低置信对齐不能自动 Approved
BreakingContractChange 必须有 CompatibilityAssessment
DataMigration 必须有 rollback 或 irreversibility 声明
Critical AcceptanceCriterion 必须产生 VerificationObligation
Implemented 提案必须关联 Actual Entity 或人工豁免证据
```

---

## 21. 常见错误

### 错误一：让 LLM 根据设计文档直接创建代码节点

目标节点尚未实现，只能存在于 Desired/Proposed Graph。

### 错误二：把文档中的类名当成必须实现方案

类名可能只是设计建议。应先建 DesiredCodeRole，再由实体对齐和架构决策决定复用或新增。

### 错误三：只生成开发任务，不生成语义变更

任务会拆分、合并和改名，不能作为需求追踪的唯一真源。

### 错误四：只比较文件 Diff

需求目标涉及业务规则、契约、数据和运行约束，必须做图级和语义级对账。

### 错误五：未找到当前实体就直接新增

开放世界下可能是抽取缺失、动态实现或映射缺失，应先输出 MissingSuspected。

### 错误六：实现存在就认为验收完成

需要测试、行为路径和运行证据，特别是负向要求和补偿流程。

### 错误七：批准后不重新基于最新代码图计算

长周期需求期间代码会演进，实施前必须重新对齐和检测冲突。

---

## 22. 最终追踪链

```text
DesignDocumentRevision
→ RequirementIR
→ Requirement / UseCase / Process / Rule / AcceptanceCriterion
→ DesiredBusinessGraph
→ DesiredTechnicalGraph
→ CandidateAlignment
→ SemanticGraphDiff
→ DesignChangeSet
→ ProposedChange
→ DesignDecision
→ ImplementationTask
→ Commit / PullRequest / ActualChangeItem
→ ActualEntityRevision
→ TestCase / TestExecution
→ DeploymentEvidence
→ RequirementVerified
```

这条链确保系统不仅知道“某需求关联了哪些 Commit”，还能解释：

- 需求希望改变什么业务语义；
- 为什么选择修改这些代码和契约；
- 哪些提案被接受、拒绝或替换；
- 实际实现与批准设计是否一致；
- 哪些验收标准已经有测试和运行证据；
- 后续代码变化会回归哪些需求和业务规则。
