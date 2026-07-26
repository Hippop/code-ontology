# RDFS、OWL、SHACL 与规则引擎边界

## 1. 设计目标

语义技术的价值是统一概念、减少重复查询逻辑并提供可解释推理，但不能替代编译器、数据流分析和影响规则。最终架构必须明确每种技术负责什么、不负责什么。

## 2. RDFS 职责

### 类层级

统一不同语言和协议：Method、Function、Constructor 都是 Callable；RESTOperation、GraphQLOperation、RPCMethod 都是 APIOperation；KafkaTopic、RabbitQueue 归入消息通道层级。

### 属性层级

```text
callsDirectly subPropertyOf callRelation
callRelation subPropertyOf executionDependsOn
executionDependsOn subPropertyOf dependsOn
```

这使上层查询可以统一，不必枚举全部技术子关系。

### domain/range

用于推断类型和文档表达，不是完整性验证。错误 Triple 不会被 RDFS 自动拒绝，反而可能推导出意外类型。

## 3. OWL 职责

### inverseOf

适合稳定逆关系：declares/declaredIn、callsDirectly/isDirectlyCalledBy、readsField/isReadBy、exposes/exposedBy、ownedBy/ownsEntity。

### 等价、互斥和角色分类

可定义语义角色：EventProducer = Callable and publishesEvent some EventType；PersistentWriter = Callable and writesData some DatabaseObject；ContractProvidingMethod = Callable and implementsOperation some APIOperation。

### 有限属性链

稳定结构派生可使用属性链，例如 `publishesEvent ○ publishedTo → publishesTo`。不要用属性链直接推导 `affects`，因为影响需要 ChangeType、兼容、上下文和状态。

### sameAs 的严格限制

`owl:sameAs` 仅用于两个 URI 确实表示同一现实实体。Java Field 与 JSON Field、Entity 与 Table、Alias 与 Underlying Type、EventType 与 Topic 均不是 sameAs。

## 4. 不应使用 TransitiveProperty 的关系

不要把 callsDirectly、mapsTo、derivedFrom、readsData、dependsOn 声明为通用传递属性。它们在不同路径和上下文中语义会变化。间接可达由图查询产生，并保留路径长度、边界和证据。

某些纯结构 contains 闭包也应谨慎：文件包含、声明包含、部署包含可能不是同一种传递语义，推荐限定关系路径而非一个全局 contains*。

## 5. 开放世界假设

OWL 中未记录某关系，不能推出关系不存在。因此“未发现消费者”“未发现测试”“未发现旧版本依赖”必须绑定数据集范围和时间。需要闭包判断时使用采集快照、SPARQL NOT EXISTS、规则或 SHACL，并在结果中说明范围。

## 6. SHACL 职责

SHACL 校验图数据质量和治理要求：

- Method 必须定位到 File/Module；
- APIOperation 必须有实现、响应和可见性；
- MessageSchema 必须有版本和 Topic；
- ConfigurationKey 必须有类型、owner 和 required/default；
- CriticalCapability 必须有 accountable team；
- Public API 必须有 ContractTest；
- ColumnDeleted 必须有关联 Migration 和 ReleaseGate。

SHACL 不是新旧版本兼容比较器，也不负责跨过程数据流。

## 7. 规则引擎职责

规则引擎处理：

- ChangeType 与关系组合；
- before/after 比较；
- 配置优先级和环境有效值；
- API/消息/数据库兼容矩阵；
- 状态机、派生变化和吸收；
- 风险、测试和发布顺序；
- 数值、时间、运行版本和缺失信息。

规则可用 Drools、Datalog、自研 DSL 或代码实现，但规则结果必须可追踪到版本和证据。

## 8. 图算法职责

图算法负责限定关系集合上的路径、最短/高置信路径、SCC、中心度、边界聚合和影响范围。算法输出候选结构，不直接替代语义规则。

## 9. 推理与物化策略

建议分层：

1. 原始事实图不可变或可追溯；
2. RDFS/OWL 推导写入独立 Named Graph；
3. 高频逆边和稳定派生可物化；
4. 影响结论写入按 AnalysisRun 隔离的图；
5. 规则版本变化时删除并重建影响图，不重写原始事实。

避免全量 OWL DL 推理覆盖超大代码图。优先使用受控 profile、增量物化和查询时推理。

## 10. 命名与 URI

本体命名空间、实例命名空间和版本命名空间分离。关系名称使用明确动词和方向；避免泛化 `uses`、`relatedTo` 作为主要事实。每个属性应有 label、comment、domain/range（用于说明）、inverse、evidence requirement 和传播说明文档。

## 11. RDF-star 与边属性

CallSite、confidence、sourceLocation、environment 等边属性可使用 RDF-star、Statement 节点或属性图。选择取决于存储。无论实现形式如何，语义层必须保留“关系事实”和“证据/上下文”分离。

## 12. 注意事项

- RDFS/OWL 推理不是静态分析；
- SHACL 不是影响传播引擎；
- domain/range 不是类型断言校验；
- sameAs 误用会导致灾难性合并；
- 复杂属性链容易过度推理；
- 推理结果必须能区分 asserted 与 inferred；
- 本体版本升级需要迁移策略和兼容性说明。