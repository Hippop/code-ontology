# 实现架构与数据管道

## 1. 目标

本章描述最终系统如何落地，而不是只给阶段性 MVP。实现应支持多语言、多仓库、增量更新、版本化知识图、规则重算、运行证据和可解释报告。

## 2. 总体组件

```text
Source Connectors
  → Language/Schema/Runtime Extractors
  → Normalization & Entity Resolution
  → Fact Store / Knowledge Graph
  → Semantic Materialization
  → Change Detection
  → Impact Rule Engine
  → Analysis Graph
  → Query/API/Report/IDE/CI Integrations
```

### Source Connectors

Git、构建系统、包管理、OpenAPI/Proto/AsyncAPI、数据库 Catalog、配置中心、测试覆盖、CI/CD、Kubernetes、APM、需求和服务目录。

### Extractors

语言解析器应基于编译器语义、LSP、字节码或 IR；SQL 使用 AST；契约使用正式 Schema Parser；运行平台使用 API 而非日志文本优先。

### Normalization

负责稳定 URI、命名规范、类型统一、版本、时间、环境、置信度和 evidenceRef。实体对齐服务处理重命名、移动、生成代码和跨仓库契约对应。

## 3. 存储架构

推荐逻辑上分四类存储：

1. 原始证据库：保存解析结果、源位置、Diff、Trace 和外部引用；
2. 知识图谱：规范化长期事实和版本 Revision；
3. 分析图：按 AnalysisRun 保存 Change/Impact/Path；
4. 指标/搜索库：全文、向量、时序和大规模运行指标。

RDF Store 适合本体、SPARQL、Named Graph 和推理；Property Graph 适合高性能路径和边属性。可采用双存储，但必须有统一 Canonical ID，避免语义漂移。

## 4. 版本化策略

核心实体使用 LogicalEntity + Revision。Revision 绑定 Commit、ArtifactVersion 或环境快照；关系也要有 validFrom/validTo 或 Named Graph 版本。当前视图由最新有效 Revision 生成。

运行实例绑定 ArtifactVersion，ArtifactVersion 绑定代码 Revision，支持分析生产旧版本和混部。

## 5. 增量更新

每次提交只重新解析变化文件及其语义依赖；对调用、类型和生成代码做受控反向失效。Schema、配置和部署数据按各自版本/时间增量写入。

更新流程：写入新 Revision → 计算实体对齐 → 关闭旧事实有效期 → 重建受影响推导 → 生成 ChangeItem → 触发影响分析。不要直接原地覆盖所有节点。

## 6. Change Detection

多层 Detector：TextDiff、ASTDiff、SymbolDiff、BytecodeDiff、SchemaDiff、SQL/DDL Diff、ConfigDiff、DeploymentDiff、Behavior Heuristic。Detector 输出原始变化和 confidence；Semantic Change Classifier 组合成最终 ChangeItem。

## 7. 规则引擎

规则输入是 ChangeItem、邻接关系、节点角色、边属性、环境、版本和运行指标。输出 ImpactAssessment、DerivedChange、Decision 和 EvidenceRequirement。

规则按领域模块化：call、type、dataflow、database、api、message、config、test、business、delivery。规则运行必须可中断、限深、去重和重放。

## 8. 分析运行模型

```text
AnalysisRun
├── input ChangeSet
├── knowledgeSnapshot
├── ontologyVersion
├── ruleSetVersion
├── runtimeSnapshot
├── status
└── generated ImpactAssessments
```

同一 ChangeSet 可以在不同规则/运行快照下重算。报告不能只保存最终 JSON，应保存 AnalysisRun 和路径。

## 9. 查询与服务接口

核心 API：

- 查询实体和上下文；
- 创建/读取 ChangeSet；
- 执行影响分析；
- 获取按代码、服务、业务、团队和发布视图聚合结果；
- 获取证据路径和拒绝原因；
- 获取推荐测试和 Release Plan；
- 提交人工确认/拒绝反馈。

IDE/PR Bot 应展示最相关路径和修复建议；架构门户展示全局依赖、治理缺口和历史趋势。

## 10. 数据质量

每个采集器发布 coverage、freshness、error、unresolved symbols 和 source version。SHACL 在入库和快照阶段运行。影响报告必须附带 DataCoverage：覆盖哪些仓库、环境、消费者和运行时间窗口。

低质量关系不能静默参与高确定性规则。规则应声明最低 evidence 等级。

## 11. 性能设计

- 关系按 source/target/type/version 建索引；
- 热点逆边物化；
- 预计算 SCC、模块/服务聚合和方法摘要；
- ChangeType 驱动关系白名单；
- 使用路径预算和优先队列先展开高置信高风险边；
- 大规模运行指标存时序库，只将摘要和引用写图；
- 分析结果缓存键包含知识快照和规则版本。

## 12. 安全与权限

代码、Secret、生产配置和需求可能具有不同权限。图查询和报告按 Repository、Team、Environment、DataClassification 做访问控制。Secret 永不入图明文；源代码片段证据按权限延迟获取。

## 13. 可观测性

监控采集延迟、节点/边数量、未解析率、规则命中、候选到确认比例、人工推翻率、分析耗时、路径爆炸和测试推荐命中率。人工反馈用于调整规则和映射置信度，而不是直接训练出不可解释结论。

## 14. 交付物

最终仓库应逐步包含：

```text
ontology/        核心本体、模块本体和版本说明
shapes/          SHACL 约束
rules/           传播规则 DSL/实现
extractors/      语言与平台采集器
schemas/         事实和分析事件 Schema
docs/            设计、示例和决策记录
examples/        端到端示例图
queries/         SPARQL/Cypher 查询
services/        分析 API 与任务执行
```

## 15. 验收标准

系统不仅要“找到更多节点”，还要做到：

- 关键变化有稳定、可解释的影响路径；
- 可区分 Confirmed、Contained、Rejected 和 Unresolved；
- 字段级、契约级和运行版本级误报可控；
- 推荐测试能覆盖关键路径；
- 发布计划能识别旧版本和兼容顺序；
- 人工评审可以追溯和反馈；
- 规则升级可在同一历史 ChangeSet 上重算。

## 16. 注意事项

- 不先选图数据库再倒推语义；
- 不将 LLM 作为唯一解析器；
- 不用单一当前快照处理历史和运行混部；
- 不在事实层写入临时影响状态；
- 不忽略采集范围和新鲜度；
- 实现细节可以演进，但 Canonical ID、关系方向和变化语义必须稳定。