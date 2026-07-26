# 最小可行实现与演进路线

## 1. 实施目标

第一版不追求覆盖所有语言、框架和关系，而是建立一条可验证的闭环：

```text
Git Diff
→ 语义变更定位
→ 代码与契约事实图
→ 影响传播
→ 测试推荐
→ 可解释报告
```

建议优先选择一个主语言和一个典型服务作为试点，例如 Java/Spring 服务，覆盖：

- 方法调用；
- DTO 和字段；
- JPA/MyBatis 数据库访问；
- REST/OpenAPI；
- Kafka 消息；
- 配置和 Feature Flag；
- JUnit 与 JaCoCo；
- Maven/Gradle 构建和 Kubernetes 运行版本。

---

## 2. 推荐技术分层

```text
extractors/
  source-code
  sql
  api-contract
  message-contract
  configuration
  tests
  build-runtime

ontology/
  code-ontology.ttl
  shapes.ttl

normalizer/
  stable-id
  symbol-resolution
  evidence-fusion

storage/
  graph-store
  revision-store
  artifact-store

change-analysis/
  semantic-diff
  change-classifier

impact-engine/
  traversal
  rules
  scoring
  containment
  compatibility

reporting/
  evidence-path
  test-selection
  business-view
  release-plan
```

---

## 3. 数据存储建议

### 3.1 图数据库

适合保存：

- 节点与语义关系；
- 反向依赖；
- 影响路径；
- 业务与责任映射；
- 版本和部署关系。

可选方案：Neo4j、JanusGraph、Amazon Neptune、RDF Triple Store。

### 3.2 RDF 与属性图的折中

推荐保留一套规范的本体词汇，同时允许执行层使用属性图：

```text
Ontology vocabulary
→ canonical graph model
→ RDF store or property graph projection
```

关系证据、行号、置信度和分析器来源在属性图中可作为边属性；RDF 场景可使用 RDF-star 或 Evidence 节点。

### 3.3 版本存储

至少保留：

- 当前默认分支事实图；
- PR 基线与目标 Revision；
- 当前生产 ArtifactVersion 的历史事实；
- ChangeSet 和 ImpactAssessment。

---

## 4. 阶段一：结构、调用与类型

### 目标

完成方法级波及分析。

### 节点

```text
Repository
Module
SourceFile
Type
Callable
Field
Parameter
ChangeItem
ImpactAssessment
```

### 关系

```text
declaredIn
belongsToModule
callsDirectly
mayCall
dispatchesTo
hasParameterType
hasReturnType
hasFieldType
implementsType
overridesMethod
```

### 变更类型

```text
MethodDeleted
MethodSignatureChanged
ReturnTypeChanged
FieldDeleted
FieldTypeChanged
```

### 输出

- 直接调用者；
- 多跳上游候选；
- 接口实现者；
- 确定编译影响与行为候选；
- 证据路径。

### 验收

对一组已知 PR 进行回放，比较编译错误、人工评审结果和系统输出。

---

## 5. 阶段二：字段数据流和数据库

### 目标

把类型级候选缩小到字段级真实使用，并连接数据库。

### 新增关系

```text
readsField
writesField
mapsTo
derivedFrom
readsColumn
writesColumn
executesQuery
mappedToTable
persistedAs
```

### 新增变更

```text
ColumnDeleted
ColumnRenamed
ColumnTypeChanged
ColumnNullableChanged
```

### 输出

- 真正读取或写入变化字段的方法；
- DTO → Entity → Column 证据链；
- 直接 SQL 和 ORM 使用者；
- Migration 和 Integration Test 推荐。

---

## 6. 阶段三：API 和消息契约

### 目标

支持跨服务影响。

### API

```text
APIOperation
RequestSchema
ResponseSchema
SchemaField
implementsOperation
callsRemoteOperation
consumesAPI
serializesTo
deserializesTo
```

### 消息

```text
EventType
MessageSchema
MessageField
Topic
ConsumerGroup
publishesEvent
consumesEvent
publishedTo
subscribesTo
```

### 兼容判断

第一版实现规则表：

- 请求新增必填字段；
- 响应字段删除或类型变化；
- 可空性变化；
- 枚举新增和删除；
- 消息字段删除、类型变化和缺少默认值；
- Protobuf 字段编号变化；
- 旧消息到新消费者的读取兼容。

### 输出

- Provider 和 Consumer 影响；
- 未知外部消费者风险；
- Contract Test 和 Replay Test 推荐；
- 发布先后顺序候选。

---

## 7. 阶段四：配置和运行路径

### 节点

```text
ConfigurationKey
ConfigurationValue
Environment
FeatureFlag
Secret
```

### 关系

```text
readsConfiguration
definesConfiguration
providesValueFor
overridesConfiguration
effectiveIn
guardedByFeatureFlag
dependsOnSecret
```

### 核心能力

- 计算不同环境的有效值；
- 判断文件变化是否真正影响生产；
- 识别启动失败、动态刷新、重启或重建；
- Feature Flag 的开启、关闭、灰度和变体路径；
- 结合 P95 延迟、流量和错误率判断运行风险。

---

## 8. 阶段五：测试闭环

### 节点和关系

```text
TestCase
TestFixture
TestEnvironment
TestExecution
covers
verifies
assertsContract
usesFixture
dependsOnTestEnvironment
```

### 推荐策略

优先级：

```text
直接 verifies / assertsContract
> 字段或契约数据流关联
> 动态覆盖
> 静态调用关联
> 同模块和命名推测
```

### 输出

- 最小回归测试集合；
- 必须测试与建议测试；
- Fixture 失效；
- 字段级契约覆盖缺口；
- 高风险节点未发现已知验证。

---

## 9. 阶段六：业务与组织语义

### 节点

```text
BusinessCapability
BusinessProcess
BusinessRule
Requirement
AcceptanceCriterion
Team
```

### 关系

```text
supportsCapability
implementsRequirement
implementsAcceptanceCriterion
enforcesRule
implementsProcessStep
ownedBy
accountableTo
reviewedBy
```

### 数据来源

- 服务目录和架构目录；
- Issue、需求和 PR 链接；
- OpenAPI Tag；
- DDD 模块；
- 代码注解；
- LLM 生成候选，人工确认。

### 输出

- 受影响能力、流程、规则和验收条件；
- 跨团队评审列表；
- 面向开发、测试、架构和业务的不同视图。

---

## 10. 阶段七：构建、部署和发布顺序

### 节点

```text
BuildArtifact
ArtifactVersion
DeployableUnit
Release
Deployment
Environment
RuntimeInstance
```

### 关系

```text
builtFrom
packagedInto
dependsOnArtifact
deployedAs
deployedTo
runsVersion
partOfRelease
mustPrecede
canCoexistWith
```

### 核心能力

- 源码变化到构建产物；
- 共享库到消费者服务；
- 当前生产运行版本；
- 数据库 Contract 操作前的旧版本依赖检查；
- Provider/Consumer 发布顺序；
- 滚动混部、灰度和回滚安全。

---

## 11. 规则引擎最小设计

规则输入：

```text
ChangeType
SourceNodeType
RelationType
TargetNodeType
Before / After
Environment
RuntimeEvidence
PathContext
```

规则输出：

```text
ImpactType
PropagationState
Certainty
RiskLevel
PropagationAction
DerivedChangeType
ReasonCode
RecommendedTests
```

示例：

```yaml
id: METHOD_DELETED_DIRECT_CALLER
when:
  changeType: MethodDeleted
  relationType: callsDirectly
then:
  impactType: CompileImpact
  state: Confirmed
  certainty: high
  action: Continue
```

规则应版本化，并在 ImpactAssessment 中记录 `ruleId` 和 `analysisVersion`。

---

## 12. 查询接口建议

### 12.1 变更影响分析

```http
POST /impact-analysis
```

输入：

```json
{
  "repository": "Hippop/code-ontology",
  "baseRevision": "...",
  "targetRevision": "...",
  "environment": "production"
}
```

输出：

```json
{
  "changeSet": "...",
  "impacts": [],
  "tests": [],
  "businessImpacts": [],
  "deploymentPlan": [],
  "unresolved": []
}
```

### 12.2 解释接口

```http
GET /impacts/{impactId}/explanation
```

返回：

- 变化起点；
- 证据路径；
- 命中规则；
- 影响分类；
- 吸收或继续传播原因；
- 推荐测试和评审者。

### 12.3 图查询接口

支持按节点查询：

- 直接和间接调用者；
- 字段读写者；
- API、消息和数据库消费者；
- 当前运行版本；
- 相关测试和业务能力。

---

## 13. 质量指标

建议持续统计：

```text
Precision：报告的影响中实际相关比例
Recall：真实影响被发现的比例
Confirmed / Candidate 比例
人工拒绝率
未解决候选数量
平均证据路径长度
测试推荐命中率
影响分析耗时
增量更新耗时
```

可使用历史 PR、编译结果、测试失败和事故记录作为评估数据集。

---

## 14. 增量更新策略

每次 Commit 或 PR：

1. 解析变更文件；
2. 更新相关符号和调用边；
3. 更新受影响 Query、Schema 和配置；
4. 保留未变化节点和稳定 ID；
5. 生成 ChangeItem；
6. 只从变化节点执行局部传播；
7. 将结果与基线分析版本关联。

避免每次完整重建全仓图。

---

## 15. 推荐的首个演示场景

选择一个包含以下链路的功能：

```text
REST Request DTO
→ Service
→ Repository
→ Database Column
→ Domain Event
→ Kafka Consumer
→ Consumer Database
```

演示变更：

```text
email: String → EmailAddress
```

系统应输出：

- 直接读取和写入位置；
- Mapper 是否吸收变化；
- 数据库是否需要 Converter 或 Migration；
- API Schema 是否变化；
- 事件 Schema 和消费者是否变化；
- 推荐测试；
- 业务能力和团队；
- 产物和发布顺序。

这是验证整体设计最有效的纵向切片。

---

## 16. 完成定义

第一版达到以下条件即可视为可用：

- 支持一个主语言和框架；
- 支持方法、字段、API、消息、数据库和配置六类变更；
- 每个影响结果包含证据路径和原因；
- 可以识别至少一种变化吸收场景；
- 可以生成测试推荐；
- 可以定位构建产物和生产运行版本；
- 对历史样本达到可接受的准确率；
- 分析结果可由开发者审阅和纠正，纠正结果能够反馈到映射或规则中。
