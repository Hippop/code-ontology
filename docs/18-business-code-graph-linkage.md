# 业务图与代码图关联完整设计

## 1. 设计目标

业务图描述系统的业务意图，代码图描述系统的技术事实。二者不能合并，也不能只通过名称相似度建立弱关联。

完整关联链应为：

```text
BusinessCapability
→ UseCase
→ BusinessProcess
→ BusinessProcessStep
→ ImplementationSlice
→ API、代码、数据、消息、配置、测试和部署节点
```

系统需要回答：

- 某个业务步骤由哪些技术节点共同实现；
- 某条业务规则由哪些代码、数据库约束和配置保证；
- 某个业务对象在 DTO、领域对象、数据库和消息中有哪些表示；
- 某个代码变化会影响哪些步骤、规则、流程和能力；
- 代码重构后，业务映射是否失效；
- 新需求产生的目标业务图应转换成哪些代码图变更提案。

---

## 2. 为什么不能直接把步骤绑定到一个方法

一个业务步骤通常横跨多个技术层。例如“向目标设备下发流表”可能涉及：

```text
PolicyDeploymentService
FlowRuleCompiler
OpenFlowAdapter
DeviceSessionManager
FLOW_MOD 远程操作
flow_deployment 表
南向超时配置
设备确认消息
集成测试
```

如果只建立：

```text
PushFlowRules implementedBy OpenFlowAdapter.installFlows
```

会遗漏业务步骤真正依赖的技术切片。

另一方面，把步骤关联到整个调用闭包又会引入日志、指标、框架和通用工具等大量噪声。

因此需要独立节点 `ImplementationSlice`，在业务粒度和代码粒度之间形成可治理边界。

---

## 3. ImplementationSlice 模型

### 3.1 定义

`ImplementationSlice` 表示完成一个业务步骤或实现一条业务规则所需的一组技术实体和边界。

```text
ImplementationSlice
├── sliceId
├── implementsStep
├── primaryEntry
├── supportingCode
├── contractEntry
├── representedObjects
├── persistenceObjects
├── remoteOperations
├── messageContracts
├── configurations
├── tests
├── runtimeUnits
├── confidence
├── evidence
└── lifecycleStatus
```

### 3.2 技术角色

切片中的技术节点不能全部使用相同关系。推荐区分：

```text
hasPrimaryEntry
containsSupportingCode
usesContractEntry
readsBusinessData
writesBusinessData
callsExternalOperation
publishesTechnicalEvent
consumesTechnicalEvent
dependsOnConfiguration
verifiedBy
runsInDeployableUnit
```

业务侧关系：

```text
ImplementationSlice implementsProcessStep BusinessProcessStep
ImplementationSlice enforcesBusinessRule BusinessRule
ImplementationSlice realizesUseCase UseCase
```

### 3.3 主要实现与支持实现

```text
CodeEntity primaryImplementsStep BusinessProcessStep
CodeEntity supportsStep BusinessProcessStep
```

`primaryImplementsStep` 用于业务入口、应用服务或核心算法入口；`supportsStep` 用于查询、转换、校验、适配和基础设施支持。

SDN 示例：

```text
PathComputationService.compute
    primaryImplementsStep ComputeConstrainedPath

TopologyGraphService.currentGraph
    supportsStep ComputeConstrainedPath

ConstraintEvaluator.evaluate
    supportsStep ComputeConstrainedPath

ConstraintEvaluator.excludeDownLinks
    enforcesRule ExcludeUnavailableLinkFromPath
```

---

## 4. 业务节点与技术节点的桥接关系

### 4.1 API 与 UseCase

```text
APIOperation realizesUseCase UseCase
```

例如：

```text
POST /network-policies/{id}/deploy
    realizesUseCase DeployNetworkPolicy
```

同一 UseCase 可以由多个 API、任务或消息入口实现，因此不是一对一关系。

### 4.2 代码与流程步骤

```text
CodeEntity primaryImplementsStep BusinessProcessStep
CodeEntity supportsStep BusinessProcessStep
```

不建议把所有被调用方法都直接关联到步骤。低层技术节点应通过 ImplementationSlice 间接归属，或者使用 `supportsStep` 并附带证据和角色。

### 4.3 代码与业务规则

```text
CodeEntity enforcesRule BusinessRule
DatabaseConstraint enforcesRule BusinessRule
ConfigurationKey configuresRule BusinessRule
```

例如：

```text
DeviceEligibilityValidator.validate
    enforcesRule OnlyOnlineManagedDeviceCanReceiveFlow

flow_rule_unique_constraint
    enforcesRule NoConflictingFlowRulesOnDevice

path.disjoint.required
    configuresRule CriticalPolicyRequiresDisjointPaths
```

一条规则可能由多种技术机制共同保证。删除其中一个实现节点，不一定立即意味着规则失效，需要分析其余实现是否仍充分。

### 4.4 类型与业务对象

```text
CodeType representsBusinessObject BusinessObject
CodeField representsBusinessAttribute BusinessAttribute
```

例如：

```text
PolicyEntity representsBusinessObject NetworkPolicy
PolicyRequest representsBusinessObject NetworkPolicy
PolicyEntity.status representsBusinessAttribute PolicyDeploymentStatus
```

`representsBusinessObject` 不表示两个节点相等，更不能使用 `owl:sameAs`。

### 4.5 数据库与业务语义

```text
Table storesBusinessObject BusinessObject
Column storesBusinessAttribute BusinessAttribute
DatabaseConstraint enforcesRule BusinessRule
```

例如：

```text
network_policy storesBusinessObject NetworkPolicy
network_policy.deployment_status storesBusinessAttribute PolicyDeploymentStatus
```

数据库节点只表示持久化形式。业务对象可以横跨多张表，也可能没有直接持久化。

### 4.6 技术消息与业务事件

```text
EventType representsBusinessEvent BusinessEvent
MessageField representsBusinessAttribute BusinessAttribute
```

例如：

```text
PolicyDeployedEventV2
    representsBusinessEvent NetworkPolicyDeployed
```

业务事件强调事实语义，技术事件强调 Schema、版本、Topic、生产者和消费者。

### 4.7 测试与业务节点

```text
TestCase verifies BusinessRule
TestCase verifies BusinessProcessStep
TestCase verifies AcceptanceCriterion
TestCase verifies UseCase
```

例如：

```text
ExcludeDownLinkTest verifies ExcludeUnavailableLinkFromPath
PartialDeploymentRollbackTest verifies RollbackOnPartialDeploymentFailure
PolicyDeploymentE2ETest verifies DeployNetworkPolicy
```

`covers` 不能替代 `verifies`。测试执行过某段代码，不等于其断言验证了对应业务语义。

---

## 5. 实体对齐方法

业务图和代码图的关联，本质上是实体对齐与实现边界识别。

### 5.1 显式标识

最高置信度方式是在技术资产中携带稳定业务 ID。

Java 示例：

```java
@ImplementsProcessStep("sdn.step.compute-constrained-path")
public NetworkPath compute(Policy policy, Topology topology) {
    // ...
}
```

规则示例：

```java
@EnforcesBusinessRule("sdn.rule.exclude-unavailable-link")
public boolean isEligible(NetworkLink link) {
    // ...
}
```

OpenAPI 示例：

```yaml
paths:
  /network-policies/{id}/deploy:
    post:
      operationId: deployNetworkPolicy
      x-use-case: sdn.usecase.deploy-network-policy
      x-process-step: sdn.step.receive-policy-request
```

显式标识适合关键入口、核心规则和状态迁移，不建议给所有低层方法添加业务注解。

### 5.2 外部映射配置

对于已有系统，可以将映射放入独立文件：

```yaml
implementationSlices:
  - id: sdn.slice.compute-path
    processStep: sdn.step.compute-constrained-path
    primaryEntries:
      - com.example.sdn.PathComputationService#compute
    supportingCode:
      - com.example.sdn.TopologyGraphService#currentGraph
      - com.example.sdn.ConstraintEvaluator#evaluate
    tests:
      - com.example.sdn.PathComputationServiceTest
```

外部配置可以在不侵入业务代码的情况下治理映射，但必须在 CI 中校验目标实体是否仍存在。

### 5.3 结构化契约与模型对齐

确定性对齐来源包括：

```text
OpenAPI operationId
Proto service/method
AsyncAPI channel/message
数据库全限定表列名
构建模块坐标
代码全限定符号
Requirement ID 注解
```

这些信息优先于名称相似度。

### 5.4 静态图扩展

确认主要入口后，可以沿受控关系扩展 ImplementationSlice：

```text
callsDirectly
readsField
writesField
readsColumn
writesColumn
callsRemoteOperation
publishesEvent
consumesEvent
readsConfiguration
```

扩展过程必须包含停止条件：

```text
最大调用深度
服务边界
业务能力边界
公共契约边界
置信度阈值
变化吸收点
通用基础设施包过滤
```

不允许将所有传递调用者或被调用者自动归入业务步骤。

### 5.5 LLM 候选映射

LLM 可以根据文档、方法名、注释、调用上下文和测试名称生成候选映射：

```text
CandidateMapping
├── businessEntity
├── technicalEntity
├── proposedRelation
├── confidence
├── evidence
├── alternatives
└── reviewStatus
```

LLM 映射必须先进入 Candidate 状态，不能直接成为确定事实。

---

## 6. 证据等级与映射状态

### 6.1 证据等级

确定证据：

```text
显式业务 ID
代码注解
设计文档中的全限定技术标识
OpenAPI 扩展字段
```

强证据：

```text
名称、类型、所属服务和数据对象共同匹配
API 路径、方法和 Schema 同时匹配
技术事件名称和字段 Schema 匹配
```

中等证据：

```text
调用链与业务步骤输入输出一致
测试断言与业务规则一致
```

弱证据：

```text
包名、类名或自然语言相似
LLM 单独语义判断
```

### 6.2 映射状态

```text
Candidate
Confirmed
Rejected
Stale
Broken
Superseded
```

映射属性：

```text
confidence
evidenceRef
source
validFrom
validTo
approvedBy
lastVerifiedCommit
mappingVersion
```

代码重构导致目标实体消失时，映射应变为 `Broken`，而不是删除业务步骤。

---

## 7. 示例：网络策略部署的业务—代码关联

### 7.1 业务流程

```text
ReceivePolicyRequest
→ ValidatePolicySemantics
→ ComputeConstrainedPath
→ CompileDeviceFlowRules
→ PushFlowRulesToDevices
→ WaitForDeviceAcknowledgements
→ PersistDeploymentResult
→ PublishDeploymentOutcome
```

### 7.2 用例入口

```text
POST /network-policies/{id}/deploy
    realizesUseCase DeployNetworkPolicy
```

### 7.3 接收请求切片

```text
ImplementationSlice: ReceivePolicyRequestSlice
primaryEntry: PolicyController.deploy
contractEntry: POST /network-policies/{id}/deploy
representedObject: NetworkPolicy
configuration: policy.deploy.enabled
verification: PolicyDeployContractTest
```

### 7.4 路径计算切片

```text
ImplementationSlice: ComputePathSlice
primaryEntry: PathComputationService.compute
supportingCode:
  TopologyGraphService.currentGraph
  ConstraintEvaluator.evaluate
  ShortestPathAlgorithm.findPath
businessInputs:
  NetworkPolicy
  NetworkTopology
businessOutput:
  NetworkPath
rules:
  ExcludeUnavailableLinkFromPath
  TenantCanUseOnlyOwnedResources
tests:
  PathComputationServiceTest
  ExcludeDownLinkTest
```

### 7.5 南向下发切片

```text
ImplementationSlice: PushFlowRulesSlice
primaryEntry: OpenFlowAdapter.installFlows
supportingCode:
  DeviceSessionManager.getSession
  FlowRuleEncoder.encode
externalOperation:
  OpenFlow FLOW_MOD
persistence:
  flow_deployment
configuration:
  openflow.request.timeout
  openflow.retry.max-attempts
events:
  FlowRuleInstallationRequested
  FlowRuleInstalled
tests:
  OpenFlowAdapterIntegrationTest
  PartialDeploymentRollbackTest
```

### 7.6 规则关联

```text
DeviceEligibilityValidator.validate
    enforcesRule OnlyOnlineManagedDeviceCanReceiveFlow

ConstraintEvaluator.excludeDownLinks
    enforcesRule ExcludeUnavailableLinkFromPath

PolicyDeploymentCoordinator.rollback
    enforcesRule RollbackOnPartialDeploymentFailure
```

---

## 8. 从新增需求到代码图变更提案

业务图与代码图关联后，可以将新增需求转换成目标图差异。

### 8.1 三图分离

```text
Current Knowledge Graph
Desired Business/Design Graph
Proposed Change Graph
```

当前知识图只保存实际存在且可验证的事实；目标图描述需求完成后应具备的业务和设计事实；变更提案图描述从当前状态到目标状态所需的节点、关系和约束变化。

### 8.2 需求对齐

新增需求首先连接已有业务节点：

```text
Requirement realizesUseCase UseCase
Requirement changesProcessStep BusinessProcessStep
Requirement introducesRule BusinessRule
Requirement hasAcceptanceCriterion AcceptanceCriterion
```

然后通过已有 ImplementationSlice 找到当前实现切片。

### 8.3 图差异类型

```text
ProposedNodeAddition
ProposedNodeModification
ProposedNodeDeletion
ProposedRelationAddition
ProposedRelationRemoval
ProposedConstraintChange
ProposedImplementationTask
```

例如新增“关键网络策略必须使用链路不相交双路径”规则，可以推导：

```text
Add BusinessRule CriticalPolicyRequiresDisjointPaths
Modify ComputeConstrainedPath step
Modify PathComputationService.compute
Add DisjointPathAlgorithm
Add configuration path.disjoint.required
Add path result fields
Add rule tests and performance tests
Potentially modify API response and deployment state
```

这些是提案，在代码真正修改并重新抽取前，不得写入当前事实图。

### 8.4 实现后对账

代码合并后重新抽取实际图，并比较：

```text
Approved Proposed Change Graph
vs
Actual Code Graph
```

输出：

```text
ImplementedAsDesigned
MissingImplementation
UnexpectedImplementation
ChangedDesign
UnverifiedRequirement
```

---

## 9. 业务影响反向传播

当代码节点发生变化时，可沿以下方向返回业务图：

```text
ChangedCodeEntity
→ belongsTo ImplementationSlice
→ implements BusinessProcessStep
→ belongsTo BusinessProcess
→ realizes UseCase
→ belongsTo BusinessCapability
```

规则影响：

```text
ChangedCodeEntity
→ enforcesRule BusinessRule
→ governs BusinessProcessStep
```

对象影响：

```text
ChangedField
→ representsBusinessAttribute BusinessAttribute
→ belongsTo BusinessObject
→ usedBy BusinessProcessStep
```

不能因为某个支持节点变化就直接判定整个能力发生业务行为变化。需要结合变更类型和吸收判断：

- 日志变化：能力内部技术变化；
- 路径过滤条件变化：业务规则影响；
- 唯一入口删除：能力可用性影响；
- 技术事件 Schema 变化：业务集成风险；
- 算法性能变化：SLO 或运行风险。

---

## 10. CI 与治理

建议在 CI 中验证：

### 10.1 主要实现完整性

每个关键 BusinessProcessStep 至少存在一个已确认的 `primaryImplementsStep` 或 ImplementationSlice。

### 10.2 映射目标有效性

映射的全限定代码符号、API、表列和测试必须在当前版本存在。

### 10.3 关键规则实现完整性

关键 BusinessRule 至少有关联实现节点，必要时要求数据库或配置机制。

### 10.4 验证覆盖

关键规则和验收条件至少有一个 `TestCase verifies` 关系。

### 10.5 变更审查

若 PR 删除或修改主要实现节点，必须重新确认业务映射并生成业务影响报告。

### 10.6 映射漂移

当业务步骤关联代码的调用和数据切片发生显著变化时，标记 MappingDrift，要求重新评审 ImplementationSlice。

---

## 11. RDFS、OWL 和 SHACL 的职责

RDFS 负责：

```text
BusinessEntity 类层级
业务关系层级
SDN 领域类型继承
```

OWL 适合定义：

```text
inverseOf
某些稳定角色分类
例如 BusinessImplementingCode
```

OWL 不适合通过任意调用闭包推断业务实现，也不适合判断映射是否足够。

SHACL 适合验证：

```text
关键步骤是否有主要实现
映射是否有证据和置信度
StateTransition 是否完整
关键规则是否有测试
```

静态分析、实体对齐、切片扩展和变更推导应由专门服务和规则引擎完成。

---

## 12. 常见错误

### 12.1 一个步骤绑定一个方法

会丢失数据库、配置、消息和外部协议依赖。

### 12.2 所有被调用方法都属于业务步骤

会把日志、指标和通用框架代码混入业务实现切片。

### 12.3 名称相似即确定关联

同名方法在不同上下文可能具有不同业务意义。

### 12.4 业务对象与 Entity 或表合并

会阻碍 DTO、消息和数据库之间的统一追踪。

### 12.5 技术事件与业务事件使用 sameAs

技术消息版本变化不等于业务事件语义变化，反之亦然。

### 12.6 重构后直接删除映射

应保留业务节点，并将映射标记为 Broken，寻找替代实现。

### 12.7 只做业务到代码的正向查询

还必须支持代码变化反向聚合到步骤、规则、流程和能力。

---

## 13. 最终模型摘要

```text
BusinessCapability
→ UseCase
→ BusinessProcess
→ BusinessProcessStep
→ ImplementationSlice

ImplementationSlice
→ APIOperation
→ CodeEntity
→ Table / Column
→ EventType
→ ConfigurationKey
→ TestCase
→ DeployableUnit

CodeEntity / DatabaseConstraint / ConfigurationKey
→ BusinessRule

CodeType / CodeField / Table / Column / EventType
→ BusinessObject / BusinessAttribute / BusinessEvent
```

该关联机制是通用的；SDN 项目需要在通用模型之上定义自己的设备、拓扑、路径、策略、流表、状态和规则词汇。