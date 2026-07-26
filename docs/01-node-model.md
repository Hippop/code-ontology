# 节点模型

## 1. 节点建模的判断标准

节点应代表可独立识别、可稳定定位、可能成为变更目标、依赖对象、契约边界或责任边界的实体。不是所有 AST 节点都适合进入长期图谱。表达式、语句、调用点和访问点应作为证据节点按需物化，避免图规模失控。

最终判断标准：

- 是否有稳定 ID；
- 是否可能独立变化；
- 是否会被其他实体依赖；
- 是否需要独立归属、版本、责任或风险；
- 是否能显著提升影响精度。

## 2. 节点顶层分类

```text
ImpactAnalysisEntity
├── CodeEntity
├── ArchitectureEntity
├── ContractEntity
├── DataEntity
├── ConfigurationEntity
├── VerificationEntity
├── BusinessEntity
├── DeliveryEntity
├── ChangeEntity
└── AnalysisEntity
```

### CodeEntity

Repository、Module、Package/Namespace、SourceFile、Type、Class、Interface、Enum、Callable、Method、Function、Constructor、Field、Property、Parameter。Lambda、脚本入口、存储过程等只在确有定位和传播价值时建模。

### ArchitectureEntity

System、Subsystem、BoundedContext、Component、ArchitectureLayer、LogicalService。它们表达逻辑架构，而不是源码目录或部署镜像。

### ContractEntity

APIOperation、APIParameter、RequestSchema、ResponseSchema、ErrorSchema、SchemaField、EventType、CommandMessage、MessageSchema、MessageField、Topic、Queue、ConsumerGroup。

### DataEntity

Database、Schema、Table、Column、View、Index、Constraint、Sequence、StoredProcedure、Query、CacheKey、SearchIndexField。

### ConfigurationEntity

ConfigurationKey、ConfigurationValue、ConfigurationSource、EnvironmentVariable、FeatureFlag、Secret、Environment、Profile。

### VerificationEntity

TestSuite、TestCase、Assertion、TestFixture、TestEnvironment、TestExecution、CompatibilityScenario。

### BusinessEntity

BusinessDomain、BoundedContext、BusinessCapability、BusinessProcess、ProcessStep、UseCase、BusinessRule、Requirement、AcceptanceCriterion、Team、Role。

### DeliveryEntity

BuildTarget、BuildArtifact、ArtifactVersion、DeployableUnit、Release、Deployment、RuntimeInstance、DeploymentAction、ReleaseGate。

### Change/Analysis

ChangeSet、ChangeItem、ImpactAssessment、ImpactEvidence、ImpactPath、CompatibilityAssessment。

## 3. 节点类型与语义角色分离

结构类型回答“它是什么”，语义角色回答“它在系统中承担什么职责”。

```text
UserController.updateUser
├── Method
├── ControllerMethod
├── ContractProvidingMethod
└── BusinessCriticalCode
```

角色可以通过注解、关系、规则和人工映射推导。不要为每种组合创建永久子类，否则类层级会爆炸。

## 4. 代码节点粒度

### 必须独立的成员节点

Method、Field、Parameter 应独立建模。字段级影响、参数位置、重载、覆盖、读写关系和契约映射都依赖这一粒度。

### 可选证据节点

CallSite、FieldAccessSite、ValueFlowStep、AnnotationInstance、QueryOccurrence。它们适合保存行号、参数位置、条件、循环、分派类型和置信度，但不应默认成为全仓库长期核心节点。

## 5. 代码类型与外部模式分离

以下对象不能合并：

```text
Java DTO Field ≠ JSON Schema Field
Entity Field ≠ Database Column
Java Event Class ≠ Message Schema
Controller Method ≠ API Operation
Logical Service ≠ Container Image
```

必须通过 `serializesTo`、`deserializesTo`、`persistedAs`、`implementsOperation`、`deployedAs` 等关系连接。分离后才能表示重命名吸收、版本适配、转换器和多重映射。

## 6. 稳定 ID 设计

推荐 ID 由命名空间、实体类别和规范化签名构成：

```text
repo://owner/name
module://repo/path
file://repo/path/File.java
type://repo/module/com.example.UserService
method://.../UserService#getUser(UserId):User
field://.../UserDTO#email
api://user-service/rest/GET/api/v1/users/{id}
column://user-db/public/user_table/email
```

重命名和移动会改变物理 ID，因此还应支持 LogicalEntity 与 Revision：

```text
LogicalCodeEntity hasRevision CodeEntityRevision
```

Revision 绑定 Commit/ArtifactVersion，逻辑节点用于跨版本追踪。

## 7. 核心属性

所有节点至少应包含：`id`、`name`、`entityType`、`sourceSystem`、`validFrom`、`validTo`、`confidence`、`evidenceRef`。代码节点增加语言、签名、可见性、文件位置；契约节点增加版本和可见范围；部署节点增加版本、环境和状态。

## 8. 版本与时间

不要在原节点上覆盖历史事实。对需要混部、历史回放和旧版本依赖分析的实体，使用 Revision 或有效时间区间。当前视图只是某一时间点的投影。

## 9. 注意事项

- 不要将字符串相同当作同一实体；必须结合命名空间和语义解析。
- 不要把 Type 和业务能力一一映射。
- 不要给所有局部变量建永久节点。
- 不要因 RDFS 多重类型推断而认为节点“身份冲突”；结构类型和角色可以共存。
- 节点缺失表示知识未采集，不表示实体不存在。