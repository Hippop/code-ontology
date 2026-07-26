# 业务语义建图完整设计

## 1. 目标与适用范围

业务语义图用于描述系统为什么存在、提供哪些能力、业务过程如何运行、业务对象如何变化，以及系统必须遵守哪些约束。它不是代码调用图的中文别名，也不是把 Controller、Service、数据库表重新命名为业务名。

本文给出一套可复用于企业后端系统的业务语义元模型，并以 SDN 网络管理后端为主要示例。最终模型采用三层结构：

```text
通用业务元模型
+
SDN 领域本体
+
具体项目的业务实例图
```

通用层定义 Capability、UseCase、Process、Step、Rule、Object、Event、State 等基本语法；SDN 领域层定义设备、端口、链路、拓扑、路径、网络策略、流表等领域概念；项目层记录当前产品实际支持的流程、规则和责任边界。

业务语义图应支持以下问题：

- 系统提供哪些业务能力；
- 某个用例经过哪些业务步骤；
- 每个步骤操作哪些业务对象；
- 哪些业务规则决定步骤能否执行；
- 哪些状态迁移和业务事件由步骤产生；
- 哪些需求和验收条件依附于流程；
- 哪些关键业务语义当前缺少实现、测试或负责人。

---

## 2. 建模原则

### 2.1 业务图描述意图，不描述实现细节

业务语义图应该使用业务参与者能够理解的语言：

```text
管理员提交网络策略
→ 系统校验策略合法性
→ 系统计算满足约束的网络路径
→ 系统编译设备流表
→ 系统向目标设备下发
→ 系统确认策略生效
```

下面的内容属于代码图，而不是业务图：

```text
PolicyController.deploy()
→ PolicyDeploymentService.deploy()
→ PathComputationService.compute()
→ OpenFlowAdapter.installFlows()
```

业务步骤不应以技术实现命名，例如不要把 `调用 OpenFlowAdapter` 当作业务步骤，应使用 `向目标网络设备下发流表`。

### 2.2 业务能力比页面、接口和微服务稳定

页面、菜单、API、服务部署单元都可能重构。业务能力通常更加稳定。

不推荐：

```text
设备列表页面
拓扑页面
策略 Controller
flow-service
```

推荐：

```text
设备生命周期管理
网络拓扑发现与维护
网络策略编排与部署
流表生命周期管理
网络故障检测与恢复
```

一个能力可以由多个服务实现，一个服务也可以支持多个能力。

### 2.3 流程步骤必须处于业务与代码之间的合适粒度

过粗的步骤无法关联实现：

```text
处理网络策略
```

过细的步骤已经退化成代码：

```text
创建 HashMap
遍历邻接表
调用 repository.save
```

合适的业务步骤应满足：

- 业务或架构人员能够理解；
- 有明确输入和输出；
- 能定义成功、失败和补偿；
- 能关联一个或多个业务规则；
- 通常可以由一个技术实现切片完成。

例如：

```text
计算满足策略约束的网络路径
```

### 2.4 业务对象是不同技术表示的语义中心

同一个业务概念在系统中可能出现多个技术表示：

```text
ManagedDevice
├── DeviceDTO
├── DeviceEntity
├── OpenFlowDevice
├── device 表
├── DeviceResponse
└── DeviceConnectedEvent 中的 device 信息
```

不能把 `DeviceEntity` 直接当作业务对象本身。应建立独立的 `BusinessObject: ManagedDevice`，再让多个技术节点表示或存储它。

### 2.5 业务规则必须成为一等节点

关键业务规则不应只隐藏在 `if`、数据库约束或配置中。例如：

```text
只有已纳管且在线的设备才能接收流表
路径计算必须排除不可用链路
部分设备下发失败时必须回滚已成功设备
```

规则成为独立节点后，可以关联实现代码、数据库约束、配置、测试和需求。

---

## 3. 通用业务元模型

### 3.1 顶层类别

```text
BusinessEntity
├── BusinessDomain
├── BusinessCapability
├── Actor
├── UseCase
├── BusinessProcess
├── BusinessProcessStep
├── BusinessObject
├── BusinessAttribute
├── BusinessRule
├── BusinessEvent
├── BusinessState
├── StateTransition
├── Requirement
├── AcceptanceCriterion
├── ServiceLevelObjective
└── ImplementationSlice
```

`ImplementationSlice` 是业务图与代码图之间的桥接节点，详细定义见《业务图与代码图关联设计》。

### 3.2 BusinessDomain

业务领域表示顶层业务范围。SDN 示例：

```text
SDNNetworkManagement
```

关系：

```text
BusinessDomain containsCapability BusinessCapability
BusinessDomain containsBusinessObject BusinessObject
BusinessDomain definesRule BusinessRule
```

### 3.3 BusinessCapability

业务能力表示组织或系统长期具备的业务能力。

SDN 能力体系示例：

```text
SDNNetworkManagement
├── DeviceLifecycleManagement
├── TopologyDiscoveryAndMaintenance
├── NetworkIntentManagement
├── NetworkPolicyManagement
├── PathComputation
├── FlowRuleProvisioning
├── FaultDetectionAndRecovery
├── PerformanceMonitoring
└── ConfigurationCompliance
```

能力属性建议包含：

```text
canonicalId
name
description
criticality
owner
status
validFrom
validTo
```

能力之间可建立：

```text
containsCapability
dependsOnCapability
supportsCapability
```

`dependsOnCapability` 主要用于业务风险聚合，不应直接作为确定性技术影响边。

### 3.4 Actor

Actor 表示与系统发生业务交互的角色或外部主体：

```text
NetworkAdministrator
TenantAdministrator
AutomationSystem
MonitoringSystem
ManagedNetworkDevice
ExternalOrchestrator
```

关系：

```text
Actor performsUseCase UseCase
Actor participatesInProcess BusinessProcess
Actor receivesBusinessEvent BusinessEvent
```

### 3.5 UseCase

UseCase 表示参与者希望完成的具体业务目标：

```text
OnboardNetworkDevice
DeployNetworkPolicy
QueryCurrentTopology
RecoverFromLinkFailure
DetectConfigurationDrift
```

关系：

```text
BusinessCapability containsUseCase UseCase
Actor performsUseCase UseCase
UseCase includesProcess BusinessProcess
Requirement realizesUseCase UseCase
```

UseCase 不应与 REST API 合并，同一 UseCase 可以由 Web API、自动化任务和外部编排接口共同实现。

### 3.6 BusinessProcess

业务流程描述完成用例的过程：

```text
NetworkPolicyDeploymentProcess
DeviceOnboardingProcess
LinkFailureRecoveryProcess
TopologySynchronizationProcess
```

属性建议包含：

```text
trigger
preconditions
completionCondition
failurePolicy
compensationPolicy
criticality
```

关系：

```text
UseCase includesProcess BusinessProcess
BusinessProcess containsStep BusinessProcessStep
BusinessProcess hasEntryStep BusinessProcessStep
BusinessProcess hasExitStep BusinessProcessStep
BusinessProcess ownedBy Team
```

### 3.7 BusinessProcessStep

步骤关系：

```text
containsStep
precedes
follows
branchesTo
joinsFrom
compensatedBy
triggeredByBusinessEvent
producesBusinessEvent
requiresPrecondition
hasBusinessInput
hasBusinessOutput
governedBy
transitionsState
```

步骤建议记录：

```text
stepId
name
description
stepKind
successCondition
failureCondition
sequenceOrder
isCompensationStep
```

### 3.8 BusinessObject 与 BusinessAttribute

SDN 业务对象示例：

```text
ManagedDevice
NetworkNode
PhysicalPort
LogicalPort
NetworkLink
NetworkTopology
NetworkPath
NetworkIntent
NetworkPolicy
FlowRule
FlowRuleSet
DeviceConfiguration
DeploymentTask
Fault
Alarm
Tenant
```

业务属性示例：

```text
ManagedDevice
├── deviceId
├── managementAddress
├── protocol
├── administrativeState
├── operationalState
└── capabilitySet
```

关系：

```text
BusinessObject hasBusinessAttribute BusinessAttribute
BusinessProcessStep hasBusinessInput BusinessObject
BusinessProcessStep hasBusinessOutput BusinessObject
BusinessRule constrainsBusinessObject BusinessObject
BusinessRule constrainsBusinessAttribute BusinessAttribute
```

业务属性应记录数据类型以外的语义：单位、枚举语义、是否敏感、是否属于业务标识、生命周期和来源。

### 3.9 BusinessRule

推荐规则类别：

```text
ValidationRule
AuthorizationRule
StateTransitionRule
ConsistencyRule
UniquenessRule
RoutingRule
AvailabilityRule
CompensationRule
ComplianceRule
```

SDN 示例：

```text
OnlyOnlineManagedDeviceCanReceiveFlow
ExcludeUnavailableLinkFromPath
TenantCanUseOnlyOwnedResources
NoConflictingFlowRulesOnDevice
AllTargetDevicesMustAcknowledge
RollbackOnPartialDeploymentFailure
CriticalPolicyRequiresDisjointPaths
```

规则属性：

```text
ruleId
statement
severity
ruleType
scope
sourceRequirement
owner
validFrom
validTo
```

关系：

```text
BusinessProcessStep governedBy BusinessRule
BusinessRule constrainsBusinessObject BusinessObject
BusinessRule constrainsBusinessAttribute BusinessAttribute
BusinessRule enablesStateTransition StateTransition
BusinessRule satisfiesAcceptanceCriterion AcceptanceCriterion
```

### 3.10 BusinessEvent

业务事件表示已经发生的业务事实：

```text
DeviceDiscovered
DeviceConnected
DeviceDisconnected
LinkDown
TopologyChanged
NetworkPolicyDeploymentStarted
NetworkPolicyDeployed
NetworkPolicyDeploymentFailed
NetworkPolicyRolledBack
FlowRuleInstalled
ConfigurationDriftDetected
```

关系：

```text
BusinessProcessStep producesBusinessEvent BusinessEvent
BusinessProcessStep triggeredByBusinessEvent BusinessEvent
BusinessEvent changesBusinessState BusinessState
BusinessEvent belongsToCapability BusinessCapability
```

业务事件不包含 Topic、Schema Registry、序列化格式等技术信息。

### 3.11 BusinessState 与 StateTransition

策略部署状态示例：

```text
Draft
→ Validating
→ Compiling
→ Deploying
→ Deployed
```

失败路径：

```text
Validating → Rejected
Compiling → CompileFailed
Deploying → PartiallyDeployed
Deploying → DeploymentFailed
PartiallyDeployed → RollingBack
RollingBack → RolledBack
```

状态迁移节点：

```text
StateTransition
├── fromState
├── toState
├── triggeredByBusinessEvent
├── guardedBy
├── performedByStep
└── producesBusinessEvent
```

状态迁移必须明确 Guard 条件。例如从 `Deploying` 到 `Deployed` 的 Guard 可以是 `AllTargetDevicesMustAcknowledge`。

### 3.12 Requirement 与 AcceptanceCriterion

需求不是业务图的唯一中心，需求应连接稳定业务节点：

```text
Requirement realizesUseCase UseCase
Requirement changesBusinessProcess BusinessProcess
Requirement introducesRule BusinessRule
Requirement hasAcceptanceCriterion AcceptanceCriterion
```

验收标准示例：

```text
AC-1 离线设备不能接收新流表
AC-2 路径结果不得包含 Down 链路
AC-3 部分下发失败时必须完成回滚
AC-4 所有设备确认后策略状态必须变为 Deployed
```

---

## 4. SDN 领域本体

### 4.1 领域对象体系

```text
SDNBusinessObject
├── ManagedDevice
│   ├── PhysicalSwitch
│   ├── VirtualSwitch
│   └── Router
├── NetworkPort
├── NetworkLink
├── NetworkTopology
├── NetworkPath
├── NetworkIntent
├── NetworkPolicy
├── FlowRule
├── FlowRuleSet
├── MeterPolicy
├── GroupPolicy
├── DeviceConfiguration
├── DeploymentTask
├── NetworkFault
└── NetworkAlarm
```

### 4.2 领域能力体系

```text
SDNBusinessCapability
├── DeviceLifecycleManagement
├── TopologyDiscoveryAndMaintenance
├── NetworkIntentManagement
├── NetworkPolicyOrchestration
├── PathComputation
├── SouthboundProvisioning
├── FlowRuleLifecycleManagement
├── NetworkFaultRecovery
├── NetworkObservation
└── ConfigurationCompliance
```

### 4.3 领域规则体系

```text
SDNBusinessRule
├── DeviceEligibilityRule
├── TopologyConsistencyRule
├── PathConstraintRule
├── FlowConflictRule
├── DeploymentConsistencyRule
├── RollbackRule
├── TenantIsolationRule
└── ControllerAuthorityRule
```

### 4.4 领域事件体系

```text
SDNBusinessEvent
├── DeviceLifecycleEvent
├── TopologyEvent
├── PolicyLifecycleEvent
├── FlowRuleLifecycleEvent
├── FaultEvent
└── ConfigurationComplianceEvent
```

---

## 5. 示例：网络策略部署业务图

### 5.1 能力与用例

```text
Capability: NetworkPolicyOrchestration
Capability: PathComputation
Capability: SouthboundProvisioning

Actor: NetworkAdministrator
UseCase: DeployNetworkPolicy
```

### 5.2 流程步骤

```text
S1 ReceivePolicyRequest
S2 AuthorizeTenant
S3 ValidatePolicySemantics
S4 ReadCurrentTopology
S5 ComputeConstrainedPath
S6 CompileDeviceFlowRules
S7 PushFlowRulesToDevices
S8 WaitForDeviceAcknowledgements
S9 PersistDeploymentResult
S10 PublishDeploymentOutcome
```

失败与补偿：

```text
PushFlowRulesToDevices
    branchesTo PartialDeployment

PartialDeployment
    compensatedBy RollbackInstalledFlowRules
```

### 5.3 输入输出

```text
ReceivePolicyRequest
    hasBusinessInput NetworkPolicy

ComputeConstrainedPath
    hasBusinessInput NetworkPolicy
    hasBusinessInput NetworkTopology
    hasBusinessOutput NetworkPath

CompileDeviceFlowRules
    hasBusinessInput NetworkPath
    hasBusinessOutput FlowRuleSet

PushFlowRulesToDevices
    hasBusinessInput FlowRuleSet
    hasBusinessOutput DeploymentTask
```

### 5.4 规则

```text
AuthorizeTenant governedBy TenantCanUseOnlyOwnedResources
ComputeConstrainedPath governedBy ExcludeUnavailableLinkFromPath
CompileDeviceFlowRules governedBy NoConflictingFlowRulesOnDevice
WaitForDeviceAcknowledgements governedBy AllTargetDevicesMustAcknowledge
PartialDeployment governedBy RollbackOnPartialDeploymentFailure
```

### 5.5 事件和状态

```text
PushFlowRulesToDevices
    producesBusinessEvent NetworkPolicyDeploymentStarted

WaitForDeviceAcknowledgements
    producesBusinessEvent NetworkPolicyDeployed

PartialDeployment
    producesBusinessEvent NetworkPolicyDeploymentFailed
```

状态迁移：

```text
Draft → Validating → Compiling → Deploying → Deployed
Deploying → PartiallyDeployed → RollingBack → RolledBack
```

---

## 6. 从文档到业务图

### 6.1 文档结构化

需求和设计文档应被分为：

```text
业务目标
范围与非范围
参与者
当前流程
目标流程
业务规则
业务对象
状态变化
事件
异常与补偿
验收标准
SLO
责任团队
```

### 6.2 业务中间模型

建议先转换为 Requirement IR，而不是直接生成 RDF：

```yaml
process:
  id: sdn.process.policy-deployment
  actor: sdn.actor.network-administrator
  steps:
    - id: sdn.step.compute-path
      input: [NetworkPolicy, NetworkTopology]
      output: [NetworkPath]
      rules: [sdn.rule.exclude-unavailable-link]
```

中间模型经过校验、实体去重和人工确认后，再转换成业务图。

### 6.3 证据与置信度

每个自动抽取事实都应记录：

```text
sourceDocument
sourceSection
sourceText
extractor
extractorVersion
confidence
reviewStatus
approvedBy
validFrom
validTo
```

业务图不能只保留最终结果而丢失证据。

---

## 7. 标识与版本化

稳定 ID 示例：

```text
sdn.capability.policy-orchestration
sdn.usecase.deploy-network-policy
sdn.process.policy-deployment
sdn.step.compute-constrained-path
sdn.rule.exclude-unavailable-link
sdn.event.network-policy-deployed
```

业务定义发生实质语义变化时，应创建新 Revision，而不是直接覆盖历史：

```text
BusinessEntity
    hasRevision BusinessEntityRevision
```

映射、规则和流程关系也应记录有效时间，确保能够解释历史发布版本。

---

## 8. SHACL 治理要求

建议验证：

- 每个 UseCase 至少属于一个 BusinessCapability；
- 每个 BusinessProcess 至少包含一个入口步骤和一个完成步骤；
- 每个关键步骤至少有输入、输出或明确副作用；
- 每个 StateTransition 必须有 fromState 和 toState；
- 每个关键业务规则必须有关联负责人；
- 每个 Requirement 必须至少有一个 AcceptanceCriterion；
- 每个关键流程必须有已确认的 ImplementationSlice；
- LLM 推断关系必须包含 confidence 和 evidenceRef。

SHACL 负责模型完整性，不负责判断业务规则本身是否正确。

---

## 9. 常见错误

### 9.1 把页面或微服务当业务能力

页面和服务是技术边界，能力是业务结果。

### 9.2 把 Java 类当业务对象

业务对象可以对应多个 DTO、Entity、表和消息 Schema。

### 9.3 流程步骤直接使用方法名

这会让业务图随重构快速失效。

### 9.4 只建成功流程

SDN 系统中的超时、部分失败、重试、回滚和控制器切换通常比正常路径更重要。

### 9.5 规则只保存在自然语言文档

规则需要连接实现、约束、配置和测试。

### 9.6 自动抽取结果直接成为事实

自然语言抽取应先成为 Candidate，经过规则或人工确认后再进入正式业务图。

---

## 10. 最终模型摘要

```text
BusinessDomain
→ BusinessCapability
→ UseCase
→ BusinessProcess
→ BusinessProcessStep

BusinessProcessStep
→ BusinessObject / BusinessAttribute
→ BusinessRule
→ BusinessEvent
→ StateTransition
→ AcceptanceCriterion
```

该模型的通用部分适用于多数后端系统；设备、链路、拓扑、路径、策略、流表及其规则属于 SDN 领域扩展。