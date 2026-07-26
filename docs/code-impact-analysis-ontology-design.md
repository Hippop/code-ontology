# 代码本体与变更波及分析总体设计

## 1. 文档目标

本文定义一套面向大型软件系统的代码本体与变更波及分析模型。它覆盖从源码实体到业务能力、从静态依赖到运行版本的完整链路，目标是回答以下问题：

- 这次变更实际改变了什么语义？
- 哪些代码、数据、接口、消息和配置可能受影响？
- 哪些影响是确定的，哪些只是候选或高风险推测？
- 变化在哪个 Mapper、Adapter、Service、Serializer 或 Converter 被吸收？
- 应执行哪些测试，当前有哪些验证缺口？
- 哪些业务能力、需求和团队需要关注？
- 哪些产物需要重建，哪些服务需要部署，发布顺序如何确定？

本设计不把 OWL 推理机当作静态分析器，也不把图可达性直接等价为影响结论。完整系统由事实抽取、语义本体、图查询、传播规则、运行证据和解释生成共同组成。

---

## 2. 核心原则

### 2.1 节点代表可识别、可变化、可依赖的实体

不建议把所有 AST 节点都放进长期知识图谱。优先建模：

- 可独立定位；
- 可稳定赋予标识；
- 会作为变更目标；
- 会成为依赖、契约或责任边界；
- 对波及分析有实际价值。

语句、表达式、调用点和字段访问点可作为证据节点或按需展开，而不是默认全部物化。

### 2.2 类型、角色和实例分离

一个节点可以同时具有多个类型或语义角色。例如：

```text
UserController.updateUser
├── Method
├── ControllerMethod
├── ContractProvidingMethod
└── BusinessCriticalCode
```

`Method` 是结构类型，`ControllerMethod`、`ContractProvidingMethod` 等是通过注解、关系和规则识别出的语义角色。

### 2.3 结构关系不等于影响关系

```text
Method declaredIn Type
Type belongsToModule Module
```

只说明位置和归属，不表示同一类或模块中的所有节点会相互波及。结构关系主要用于定位、聚合、边界识别、构建和责任继承。

### 2.4 依赖事实不等于影响结论

```text
A calls B
```

只说明 A 依赖 B。B 的日志文本变化通常不会让 A 需要修改；B 的签名删除则会对 A 产生确定编译影响。影响必须由 `ChangeType + RelationType + Context` 共同判断。

### 2.5 图上可达不等于真实受影响

调用闭包、数据流路径和业务流程路径用于发现候选。候选需要经过规则判断，最终状态可以是：

```text
Candidate
Confirmed
Contained
Rejected
Unresolved
```

### 2.6 依赖图、变更图和影响图分离

- **Knowledge Graph**：稳定的代码、契约、数据、测试和业务事实；
- **Change Graph**：某次 Commit、PR 或 Release 的语义变化；
- **Impact Graph**：针对本次变化生成的影响结论、路径、证据和测试建议。

---

## 3. 总体架构

```text
Source Code / Build / Runtime / Requirements
                    │
                    ▼
            Fact Extractors
  AST / Compiler / Bytecode / SQL / OpenAPI /
  Schema Registry / Coverage / Git / K8s / APM
                    │
                    ▼
             Canonical Fact Layer
        stable ids + revisions + evidence
                    │
                    ▼
        RDFS / OWL Semantic Ontology
    class hierarchy / property hierarchy / inverse
                    │
          ┌─────────┴─────────┐
          ▼                   ▼
       SHACL              Graph Store
 data completeness      traversal / paths /
 and constraints        aggregation / search
          │                   │
          └─────────┬─────────┘
                    ▼
              Rule Engine
 change classification / propagation / containment /
 compatibility / risk / deployment ordering
                    │
                    ▼
              Impact Results
 affected entities / evidence paths / tests /
 business impact / teams / release plan
```

职责建议：

| 组件 | 主要职责 |
|---|---|
| 编译器、AST、字节码和专用分析器 | 计算调用、类型、字段读写、控制流和数据流事实 |
| RDFS | 统一类和关系层级，支持通用查询 |
| OWL | 逆关系、有限属性链、语义角色分类 |
| SHACL | 图数据完整性和治理约束 |
| 图数据库 | 路径搜索、反向依赖、聚合、最短路径和中心性 |
| 规则引擎 | 新旧值比较、兼容性、传播、吸收、风险和发布顺序 |
| 运行时数据 | 调整优先级、暴露范围和实际版本状态 |
| LLM | 语义映射候选、规则解释和影响报告，不替代确定性分析 |

---

## 4. 节点模型

### 4.1 代码节点

```text
CodeEntity
├── Repository
├── Module
├── PackageOrNamespace
├── SourceFile
├── Type
│   ├── Class
│   ├── Interface
│   ├── Struct
│   ├── Record
│   ├── Enum
│   └── AnnotationType
├── Callable
│   ├── Method
│   ├── Function
│   ├── Constructor
│   ├── Lambda
│   ├── StoredProcedure
│   └── ScriptEntry
├── Field
├── Property
├── Parameter
└── EnumValue
```

第一版不需要为所有局部变量和表达式建长期节点。高级数据流、污点分析和自动修复场景再引入 `ValueNode`、`CallSite`、`FieldAccessSite`。

### 4.2 架构节点

```text
ArchitectureEntity
├── System
├── Subsystem
├── BoundedContext
├── Component
├── ArchitectureLayer
├── LogicalService
└── ExternalSystem
```

架构节点用于表达逻辑边界，不应与代码 Module、容器镜像或运行实例合并。

### 4.3 契约节点

```text
ContractEntity
├── APIOperation
├── APIParameter
├── RequestSchema
├── ResponseSchema
├── ErrorSchema
├── SchemaField
├── EventType
├── CommandMessage
├── MessageSchema
└── MessageField
```

代码 DTO 和外部 Schema 推荐分离，以表达命名、序列化、版本和兼容适配。

### 4.4 数据节点

```text
DataEntity
├── Database
├── DatabaseSchema
├── Table
├── Column
├── View
├── Index
├── Constraint
├── Query
├── CacheKey
└── SearchIndex
```

实体类和数据库表不是同一个节点，字段和数据库列也不是同一个节点，应通过映射关系连接。

### 4.5 配置与运行节点

```text
ConfigurationEntity
├── ConfigurationKey
├── ConfigurationValue
├── ConfigurationSource
├── EnvironmentVariable
├── FeatureFlag
└── Secret

RuntimeEntity
├── Environment
├── RuntimeCluster
├── RuntimeInstance
├── RoutingPolicy
└── RuntimeMetric
```

配置键与配置值必须分离，以支持不同环境、来源和优先级。

### 4.6 测试节点

```text
VerificationEntity
├── TestSuite
├── TestCase
│   ├── UnitTest
│   ├── IntegrationTest
│   ├── ContractTest
│   ├── EndToEndTest
│   ├── MigrationTest
│   ├── PerformanceTest
│   └── SecurityTest
├── TestFixture
├── TestEnvironment
├── Assertion
└── TestExecution
```

### 4.7 业务和组织节点

```text
BusinessEntity
├── BusinessDomain
├── BusinessCapability
├── BusinessProcess
├── BusinessProcessStep
├── UseCase
├── BusinessRule
├── Requirement
├── AcceptanceCriterion
├── BusinessEvent
└── ServiceLevelObjective

OrganizationEntity
├── Team
├── Role
├── Person
├── OnCallGroup
└── ReviewPolicy
```

### 4.8 构建与部署节点

```text
DeliveryEntity
├── BuildTarget
├── BuildArtifact
├── ArtifactVersion
├── DeployableUnit
├── Release
├── Deployment
├── DeploymentAction
├── DeploymentEnvironment
└── RuntimeInstance
```

### 4.9 变更和影响节点

```text
ChangeEntity
├── ChangeSet
│   ├── Commit
│   ├── PullRequest
│   └── ReleaseChangeSet
└── ChangeItem

ImpactEntity
├── ImpactAssessment
├── ImpactEvidence
├── ImpactPath
└── CompatibilityAssessment
```

---

## 5. 标识、版本与证据

### 5.1 稳定标识

节点 ID 不应只使用文件行号。建议组合：

```text
repository + revision-independent logical identity + language symbol identity
```

示例：

```text
java://repo/user-service/com.example.user.UserService#updateUser(UserRequest)
```

需要同时区分：

- `LogicalCodeEntity`：跨版本的逻辑身份；
- `CodeEntityRevision`：某个 Commit 或 ArtifactVersion 中的具体版本。

### 5.2 边证据

每条分析边建议记录：

```text
analysisSource
confidence
sourceRevision
sourceFile
sourceLocation
firstObservedAt
lastObservedAt
environment
```

静态确定关系、运行观测关系和启发式推测不得互相覆盖。

### 5.3 置信度与风险分离

```text
confidence = 低，但 risk = Critical
```

可以表示一个反射候选可能触发核心支付逻辑。反之，日志改动可能 `confidence = High`、`risk = Low`。

---

## 6. 结构关系

结构关系回答“节点在哪里、属于什么边界”。

```text
structurallyRelatedTo
├── contains / containedIn
├── declares / declaredIn
├── declaredInFile / fileDeclares
├── belongsToModule
├── belongsToComponent
├── belongsToService
├── packagedInto
├── deployedAs
├── nestedIn
└── ownedBy
```

典型定位链：

```text
SourceFile
→ Method
→ Type
→ Module
→ Component
→ Service
```

结构关系支持：

- Git Diff 定位；
- 模块和服务聚合；
- 构建、部署和责任继承；
- 边界风险计算。

结构关系本身不应传播语义影响。例如一个方法变化不表示同类所有兄弟方法都受影响。

---

## 7. 调用关系

### 7.1 关系定义

```text
callRelation
├── callsDirectly
├── mayCall
├── observedCalls
├── dispatchesTo
├── invokesReflectively
├── callsAsynchronously
└── registersCallback
```

事实方向统一使用：

```text
Caller → Callee
```

被调用方法发生变化时沿反方向寻找调用者。

### 7.2 直接调用与可达性分离

不得把 `callsDirectly` 或模糊的 `calls` 声明为传递属性。

```text
A callsDirectly B
B callsDirectly C
```

只能推出：

```text
A mayReach C
```

不能推出 `A callsDirectly C`。

间接可达关系应由图查询计算，例如：

```sparql
?caller code:callsDirectly+ code:ChangedMethod .
```

### 7.3 动态分派

```text
PaymentService.pay
    callsDirectly PaymentProvider.pay

PaymentProvider.pay
    dispatchesTo AliPayProvider.pay
    dispatchesTo WechatPayProvider.pay
```

接口调用、反射、回调和依赖注入需要保存分派类型及置信度。

### 7.4 调用影响方向

- Callee 删除或签名变化：直接 Caller 通常高风险；
- Caller 变化：不能自动把所有 Callee 标为受影响；
- 实现变化：上游通常是行为回归候选，而非确定编译影响；
- RPC 和 HTTP 不使用本地 `callsDirectly`，而使用 `callsRemoteOperation`。

---

## 8. 类型与声明依赖

```text
typeDependency
├── hasParameterType
├── hasReturnType
├── hasFieldType
├── hasGenericArgument
├── extendsType
├── implementsType
├── overridesMethod
├── referencesType
├── instantiatesType
├── catchesExceptionType
├── declaresThrownType
└── annotatedWith
```

类型发生变化时通常反向寻找声明依赖者：

```text
Type
← hasParameterType
Method
```

重要规则：

- 接口方法变化同时向实现者和调用者传播；
- `overridesMethod` 提供方法级精确映射，避免把实现类全部方法标红；
- 泛型的原始类型与参数类型分别建模；
- 类型别名使用 `aliasesType` 或 `hasUnderlyingType`，不使用 `owl:sameAs`；
- 枚举值应作为节点，新增响应枚举值可能破坏严格消费者；
- 异常声明和捕获是行为传播的重要证据。

---

## 9. 字段访问与数据流

```text
dataDependency
├── fieldAccess
│   ├── readsField
│   └── writesField
├── valueFlow
│   ├── passesValueTo
│   ├── assignsValueTo
│   └── returnsValueFrom
└── transformationRelation
    ├── mapsTo
    ├── derivedFrom
    └── convertsTo
```

字段级关系用于把：

```text
“方法参数使用了 UserDTO”
```

缩小为：

```text
“方法实际读取了 UserDTO.email”
```

### 9.1 `mapsTo` 与 `assignsValueTo`

- `assignsValueTo`：某次具体代码实现中的值流；
- `mapsTo`：跨 DTO、领域模型、数据库和事件的稳定语义映射。

### 9.2 `derivedFrom`

用于表示计算、聚合、格式化和转换：

```text
fullName derivedFrom firstName
fullName derivedFrom lastName
```

不建议直接声明为传递属性，间接来源由图算法计算并保留路径。

### 9.3 变化吸收

```text
API EmailAddress
→ Mapper 转成 String
→ Entity 仍为 String
```

Mapper 是确定受影响节点，同时可能是传播吸收点。

---

## 10. 数据存储关系

```text
persistenceDependency
├── readsTable
├── writesTable
├── readsColumn
├── writesColumn
├── executesQuery
├── mappedToTable
├── persistedAs
├── usesIndex
├── derivesFrom
└── reliesOnDefaultValue
```

推荐同时保留表级和列级关系：

- 表级适合粗粒度扫描、共享表识别；
- 列级适合删除、重命名、类型和可空性变化分析。

复杂 SQL 推荐建 `Query` 节点：

```text
Callable → executesQuery → Query
Query → readsColumn / writesColumn → Column
```

动态 SQL 使用 `mayReadColumn`、`mayWriteColumn` 和置信度，不伪装成确定关系。

数据库变化规则示例：

- `nullable true → false`：优先沿 `writesColumn` 查找可能写空值的路径；
- `nullable false → true`：优先沿 `readsColumn` 检查空值处理；
- 默认值变化：关注未显式写该列的 Insert；
- 索引变化：形成性能影响而非编译影响；
- 当前主分支不再使用旧列，不代表生产旧版本已经停止使用。

---

## 11. API 与同步契约

### 11.1 节点和关系

```text
Service --exposes--> APIOperation
Callable --implementsOperation--> APIOperation
APIOperation --hasRequestSchema--> RequestSchema
APIOperation --hasResponseSchema--> ResponseSchema
Schema --hasSchemaField--> SchemaField
CodeField --serializesTo--> SchemaField
SchemaField --deserializesTo--> ConsumerField
Consumer --consumesAPI--> APIOperation
ConsumerMethod --callsRemoteOperation--> APIOperation
```

API 操作与 Controller 方法不是同一个节点。内部方法可以重构而契约保持不变。

### 11.2 兼容性方向

请求和响应的兼容判断方向不同：

- 请求新增必填字段：通常破坏旧客户端；
- 响应新增可选字段：通常兼容，但严格反序列化器可能失败；
- 响应字段删除或类型变化：高风险；
- 响应从 non-null 变为 nullable：旧消费者可能出现空值错误；
- 枚举响应新增值：旧消费者的穷举分支可能失效。

### 11.3 未知消费者

没有识别到消费者，不等于不存在消费者。公开 API 应保留 `UnknownExternalConsumerRisk`。

### 11.4 错误和安全契约

API 契约还包括：

```text
状态码
错误 Schema
认证要求
授权要求
Header
Media Type
```

异常映射从 409 变为 500，即使方法签名不变，也属于明显契约行为变化。

---

## 12. 消息与异步事件

### 12.1 基础模型

```text
ProducerMethod --publishesEvent--> EventType
EventType --hasMessageSchema--> MessageSchema
EventType --publishedTo--> Topic
ConsumerGroup --subscribesTo--> Topic
ConsumerMethod --consumesEvent--> EventType
CodeType --serializesAsMessage--> MessageSchema
MessageSchema --deserializesMessageAs--> ConsumerCodeType
```

Producer 与 Consumer 之间不使用普通方法调用边。

### 12.2 Event、Command 和 Notification 分离

- `DomainEvent`：已发生的业务事实；
- `CommandMessage`：要求特定目标执行动作；
- `NotificationMessage`：状态或提示。

删除唯一命令消费者与删除某个事件订阅者的业务含义不同。

### 12.3 异步契约不仅是字段

还需要建模：

```text
事件业务含义
发布条件和发布时机
Message Key 和分区策略
顺序保证
幂等 Key
投递语义
重试策略
死信队列
历史消息保留和重放
```

Schema 不变但 `OrderPaid` 从“支付已成功”变成“支付请求已提交”，属于严重 `EventMeaningChanged`。

### 12.4 历史重放

兼容性至少检查：

```text
旧消息 → 新消费者
新消息 → 旧消费者
```

消息系统不能只检查当前 Producer 和当前 Consumer。

---

## 13. 配置、环境变量、Feature Flag 和 Secret

### 13.1 配置模型

```text
ConfigurationSource --definesConfiguration--> ConfigurationKey
ConfigurationValue --providesValueFor--> ConfigurationKey
ConfigurationValue --effectiveIn--> Environment
HigherPriorityValue --overridesConfiguration--> LowerPriorityValue
CodeEntity --readsConfiguration--> ConfigurationKey
```

配置键与环境值分离，规则引擎计算每个环境的最终有效值。

### 13.2 Feature Flag

```text
CodeEntity --guardedByFeatureFlag--> FeatureFlag
```

需要记录启用条件：

```text
enabledWhenFlagTrue
enabledWhenFlagFalse
variant
rolloutPercentage
targetSegment
```

从 5% 扩大到 100% 可能不需要部署，但会产生容量、依赖和业务暴露风险。

### 13.3 Secret

```text
Service --dependsOnSecret--> Secret
```

只存储 Secret 的身份、版本、来源、轮换和刷新策略，不保存明文。

### 13.4 配置变化规则

- 删除必填且无默认值配置：可能导致启动失败；
- 修改低优先级文件但生产被环境变量覆盖：生产有效值不变；
- 修改超时、重试、并发和缓存：形成运行和容量影响；
- 修改安全开关：提高安全风险；
- 配置在 BuildTime、StartupTime 或 Runtime 消费，决定重建、重启或动态刷新。

---

## 14. 测试、覆盖与验证

```text
TestCase --covers--> Entity
TestCase --verifies--> EntityOrBehavior
TestCase --assertsContract--> ContractEntity
TestCase --validatesSchema--> Schema
TestCase --verifiesFailureMode--> FailureMode
TestCase --usesFixture--> TestFixture
TestCase --dependsOnTestEnvironment--> TestEnvironment
```

### 14.1 `covers` 不等于 `verifies`

`covers` 表示测试执行时经过某段代码；`verifies` 表示测试的设计目标和断言确实验证该行为。

优先级通常是：

```text
verifies / assertsContract / validatesSchema
>
covers
>
同模块或命名推测
```

### 14.2 测试选择

测试推荐综合：

```text
直接验证关系
契约关系
字段级数据流
运行覆盖
业务关键度
历史失败率
测试稳定性
执行成本
```

### 14.3 验证缺口

在开放世界假设下，没有覆盖记录只能表达：

```text
当前已采集的数据中未发现相关测试
```

不能用 OWL 单独断言绝对不存在测试。应使用 SHACL、SPARQL `NOT EXISTS` 或规则引擎，在明确数据边界下生成治理结果。

---

## 15. 业务能力、需求与责任

```text
CodeEntity --supportsCapability--> BusinessCapability
CodeEntity --implementsRequirement--> Requirement
CodeEntity --implementsAcceptanceCriterion--> AcceptanceCriterion
CodeEntity --enforcesRule--> BusinessRule
CodeEntity --implementsProcessStep--> BusinessProcessStep
BusinessProcess --containsStep--> BusinessProcessStep
BusinessProcessStep --precedes--> BusinessProcessStep
BusinessProcessStep --compensatedBy--> CompensationStep
Entity --ownedBy--> Team
Capability --accountableTo--> Team
Entity --reviewedBy--> Team
```

### 15.1 能力作为稳定聚合中心

Requirement 会不断新增和关闭，BusinessCapability 更稳定。推荐：

```text
Requirement contributesTo Capability
CodeEntity supportsCapability Capability
```

### 15.2 业务规则

规则可能由方法、数据库唯一约束、消息去重和锁共同实现。业务规则作为独立节点，可以把数据库和配置变化解释为真实业务后果。

### 15.3 责任类型分离

- `ownedBy`：日常维护；
- `accountableTo`：业务结果责任；
- `operatedBy`：生产运行；
- `reviewedBy`：必要评审。

责任关系用于通知、治理和协作成本，不替代技术依赖关系。

---

## 16. 构建、部署与运行版本

```text
BuildArtifact --builtFrom--> CodeEntity
CodeEntity --packagedInto--> BuildArtifact
DeployableUnit --dependsOnArtifact--> BuildArtifact
DeployableUnit --deployedAs--> ArtifactVersion
Deployment --deployedTo--> Environment
RuntimeInstance --runsVersion--> ArtifactVersion
ArtifactVersion --partOfRelease--> Release
DeploymentAction --mustPrecede--> DeploymentAction
```

### 16.1 源码、产物和部署影响分离

```text
SourceImpact
BuildImpact
PackagingImpact
DeploymentImpact
RuntimeCompatibilityImpact
```

源码变化不一定改变产物，产物变化也不一定要求所有消费者立即部署。

### 16.2 运行版本

数据库列删除、消息升级和回滚判断必须考虑当前运行的旧 ArtifactVersion，而不只分析主分支源码。

### 16.3 发布顺序

发布顺序不能简单由调用方向推导，必须基于方向性兼容矩阵：

```text
新 Consumer 是否能读旧消息？
旧 Consumer 是否能读新消息？
新应用是否能读旧数据库？
旧应用是否能读新数据库？
```

### 16.4 Expand–Migrate–Contract

数据库破坏性变化推荐：

```text
Expand → Deploy compatible application → Migrate → Contract
```

`Contract` 操作必须等待所有依赖旧结构的运行版本下线。

### 16.5 混部与回滚

滚动部署期间检查：

```text
缓存格式
Session 格式
数据库双读双写
消息 Schema
分布式锁 Key
幂等 Key
```

二进制可回滚不代表数据和业务状态可安全回滚。

---

## 17. 变更模型

### 17.1 ChangeSet 与 ChangeItem

```text
ChangeSet --containsChange--> ChangeItem
ChangeItem --changesEntity--> Entity
```

ChangeItem 保存：

```text
changeType
targetEntity
beforeValue
afterValue
sourceChangeSet
confidence
detectedBy
breakingLevel
```

### 17.2 语义变化类型

基础 Add/Delete/Modify 不足以驱动波及分析。建议至少包括：

```text
MethodDeleted
MethodSignatureChanged
MethodImplementationChanged
ReturnTypeChanged
ExceptionBehaviorChanged
TransactionBehaviorChanged
FieldTypeChanged
SchemaFieldRemoved
ColumnTypeChanged
EventMeaningChanged
ConfigurationValueChanged
FeatureFlagRolloutChanged
SecretRotated
```

一个 ChangeItem 可以同时产生多个影响类型。

---

## 18. 影响模型和传播状态

### 18.1 ImpactAssessment

每个影响结论建独立节点：

```text
sourceChange
affectedEntity
impactType
propagationState
certainty
riskLevel
pathLength
containmentStatus
reasonCode
ruleId
analysisVersion
```

影响类型：

```text
CompileImpact
BehaviorImpact
ContractImpact
DataImpact
RuntimeImpact
DeploymentImpact
SecurityImpact
PerformanceImpact
VerificationImpact
BusinessImpact
```

### 18.2 传播状态

```text
Candidate
Confirmed
Contained
Rejected
Unresolved
```

- `Confirmed`：有明确证据；
- `Contained`：当前节点需要适配，但对外变化被吸收；
- `Rejected`：路径存在但该变化不构成影响；
- `Unresolved`：动态或外部信息不足。

### 18.3 节点传播行为

```text
PassThrough
Transform
Contain
Amplify
```

例如 Mapper 可以转换类型并吸收外部契约变化；全局异常处理器可能把底层异常变化放大为 API 500 行为变化。

---

## 19. 传播规则

通用规则结构：

```text
WHEN
    ChangeType = X
    AND SourceNodeType = Y
    AND RelationType = Z
    AND TargetNodeType = T
    AND ContextCondition
THEN
    create ImpactAssessment
    set ImpactType / Certainty / Risk
    choose Continue / Stop / Decay / Escalate / Review
```

传播决策：

```text
Continue
Stop
ContinueWithDecay
Branch
Escalate
RequireManualReview
```

### 19.1 示例：方法删除

```text
MethodDeleted + callsDirectly
→ DirectCaller Confirmed CompileImpact
```

通过 `mayCall` 或反射边传播时降为 Possible 或 Unresolved。

### 19.2 示例：返回类型变化

- 调用者使用返回值且类型不兼容：Confirmed CompileImpact；
- 调用者忽略返回值：通常无编译影响，保留行为候选；
- Service 内部适配并保持公开签名：Service Confirmed + Contained。

### 19.3 示例：字段类型变化

```text
String → EmailAddress
```

- 调用 `.trim()`：确定编译影响；
- 只做非空判断：可能仍兼容；
- 通过 Converter 转回 String：当前层吸收。

### 19.4 示例：数据库列可空性

- `true → false`：沿写入路径寻找 null；
- `false → true`：沿读取路径寻找缺失空值处理。

### 19.5 示例：配置超时

```text
newTimeout < observedP95
→ High RuntimeImpact
```

继续关联重试、熔断、外部 API 和业务 SLO。

### 19.6 派生变化

传播到下一节点的不是简单 `affected=true`，而是新的可观察变化：

```text
Repository ReturnTypeChanged
→ Service InternalAdaptationRequired
→ 若公开签名变化，再派生 Service ReturnTypeChanged
```

---

## 20. RDFS、OWL、SHACL 和规则引擎的边界

### 20.1 RDFS

适合：

- `subClassOf` 类层级；
- `subPropertyOf` 关系层级；
- domain/range 语义推断；
- 通用查询抽象。

需要注意：RDFS domain/range 用于推断，不是输入校验。

### 20.2 OWL

适合：

- inverseOf；
- 等价类和语义角色；
- 有限、稳定的属性链；
- 多类型分类。

不适合：

- 完整调用图和数据流计算；
- 新旧值数值比较；
- 配置优先级；
- 复杂兼容矩阵；
- 缺失数据的闭世界判断；
- 完整风险评分。

不要滥用 `owl:sameAs`。代码类型与 Schema、实体与表、字段与列通常是映射关系而非同一实体。

### 20.3 SHACL

适合验证图的完整性与治理要求，例如：

- Public API 必须有响应 Schema 和 ContractTest；
- MessageSchema 必须有版本、Topic 和生产者；
- FeatureFlag 必须有 Owner 和过期时间；
- Critical Capability 必须有责任团队；
- ColumnDeleted 必须有迁移和运行版本证明。

### 20.4 图算法

适合：

- 反向依赖遍历；
- 路径搜索；
- 可达闭包；
- 最短证据路径；
- 强连通组件；
- 边界聚合和中心性。

### 20.5 规则引擎

负责最终影响判断、吸收、兼容性、风险、测试选择和发布计划。

---

## 21. 端到端示例

变化：

```text
UserRequest.email
String → EmailAddress
```

### 21.1 变化定位

```text
ChangeItem CHG-001
changeType = FieldTypeChanged
target = UserRequest.email
before = String
after = EmailAddress
```

### 21.2 代码和数据流

```text
UserRequest.email
← readsField
UserValidator.validate

UserRequest.email
← readsField
UserMapper.toEntity
→ writesField
User.email
```

如果 Mapper 转回 String 且实体类型不变：

```text
UserMapper = ConfirmedImpact + ContainmentPoint
User.email = Rejected TypeImpact
```

如果实体同步改成 EmailAddress：

```text
User.email
→ persistedAs user_table.email
→ mapsTo UserChangedEvent.email
→ mapsTo UserResponse.email
```

### 21.3 契约传播

- Serializer 仍输出字符串：API ContractImpact 被吸收；
- Serializer 输出对象：API SchemaFieldTypeChanged，继续传播到 Web、Mobile 和服务消费者；
- Message Schema 同步变为对象：继续传播到事件消费者和历史重放。

### 21.4 测试选择

```text
必须：UserMapperTest、UserApiContractTest
高优先级：UserRepositoryIntegrationTest、UserChangedEventContractTest
消费者：Consumer Contract Test、Historical Replay Test
```

### 21.5 业务和责任

```text
受影响能力：用户资料维护、用户变更通知
业务规则：邮箱格式必须合法
涉及团队：UserPlatformTeam、NotificationTeam
```

### 21.6 部署计划

若形成破坏性 API 和消息变化：

```text
1. 先发布兼容消费者
2. 部署 Provider 的兼容版本
3. 灰度启用新格式
4. 等待旧客户端和历史消息窗口结束
5. 删除旧兼容结构
```

---

## 22. 常见错误

1. 把每个 AST 节点都长期物化，导致图规模失控；
2. 把 Controller 方法等同于 API 操作；
3. 把生产者和消费者直接连成普通调用；
4. 把实体和表、字段和列合并成同一节点；
5. 把 `calls`、`mapsTo` 或 `derivedFrom` 随意声明为传递属性；
6. 把图可达直接标记为 Affected；
7. 把运行时未观测到关系解释为关系不存在；
8. 把覆盖率等同于行为验证；
9. 忽略配置优先级和环境有效值；
10. 忽略历史运行版本、滚动混部和历史消息重放；
11. 只记录技术负责人，不记录业务责任和必要评审；
12. 把兼容性表示为无方向的布尔值；
13. 使用当前主分支图判断数据库 Contract 操作是否安全；
14. 让 LLM 直接决定确定性依赖或安全发布顺序，而没有结构化证据。

---

## 23. 推荐的第一版范围

### 节点

```text
Repository、Module、SourceFile、Type、Callable、Field
APIOperation、Schema、SchemaField
EventType、MessageSchema、MessageField、Topic
Table、Column、Query
ConfigurationKey、FeatureFlag
TestCase
BusinessCapability、Team
BuildArtifact、DeployableUnit、RuntimeVersion
ChangeItem、ImpactAssessment
```

### 关系

```text
contains、declares、belongsToModule、belongsToService
callsDirectly、mayCall、dispatchesTo
hasParameterType、hasReturnType、hasFieldType、overridesMethod
readsField、writesField、mapsTo
readsColumn、writesColumn、persistedAs
implementsOperation、hasRequestSchema、hasResponseSchema、serializesTo
publishesEvent、consumesEvent、publishedTo
readsConfiguration、guardedByFeatureFlag
covers、verifies、assertsContract
supportsCapability、ownedBy
packagedInto、dependsOnArtifact、runsVersion
```

### 传播能力

第一版先支持：

- 方法删除和签名变化；
- 字段类型、删除和重命名；
- API 请求/响应字段变化；
- 消息字段变化；
- 数据库列变化；
- 配置值和 Feature Flag 变化；
- 直接测试推荐；
- 构建产物和运行版本定位。

---

## 24. 结论

可落地的代码波及分析不是单一调用图，也不是单纯 OWL 推理。它需要形成以下闭环：

```text
事实抽取
→ 统一本体
→ 语义化变更
→ 多关系候选传播
→ 规则判断和变化吸收
→ 证据化影响结论
→ 测试和业务映射
→ 构建部署与运行验证
```

系统最终输出的不应只是“受影响文件列表”，而应是可以支撑研发决策的解释性结果：

```text
为什么受影响
影响属于什么类型
结论有多确定
风险有多严重
变化在哪里停止
应该执行哪些测试
需要哪些团队评审
如何安全发布和回滚
```
