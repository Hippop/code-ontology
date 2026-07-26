# 代码本体与变更波及分析总体设计

本文档路径保留为兼容入口。完整设计已经拆分为正式专题文档集，所有节点、关系、传播思想、最终建模、证据来源和注意事项均在以下章节中维护：

1. [总体架构](00-overall-architecture.md)
2. [节点模型](01-node-model.md)
3. [结构关系](02-structural-relations.md)
4. [调用关系](03-call-relations.md)
5. [类型与声明依赖](04-type-dependencies.md)
6. [字段访问与数据流](05-field-data-flow.md)
7. [数据库模型](06-database-model.md)
8. [API 与同步契约](07-api-contract-model.md)
9. [消息与异步契约](08-messaging-model.md)
10. [配置、环境变量、Feature Flag 与 Secret](09-configuration-model.md)
11. [测试、覆盖与验证](10-testing-model.md)
12. [业务、需求、规则与责任](11-business-ownership-model.md)
13. [构建、部署、运行时与发布](12-build-deployment-runtime.md)
14. [变更模型](13-change-model.md)
15. [影响传播规则](14-impact-propagation-rules.md)
16. [RDFS、OWL、SHACL 与规则引擎边界](15-rdfs-owl-shacl.md)
17. [实现架构与数据管道](16-implementation-architecture.md)

## 统一结论

本系统不是 AST 图数据库，也不是 `dependsOn+` 查询器。它由长期知识图、语义变更图和按分析运行隔离的影响图组成。静态分析和平台连接器产生事实；RDFS/OWL 统一语义；SHACL 保证数据质量；图算法发现限定候选路径；规则引擎根据 ChangeType、关系语义、环境、版本和兼容边界产生 Confirmed、Contained、Rejected 或 Unresolved 的影响结论。

从本页进入阅读时，建议先阅读总体架构，再根据实现工作进入对应专题。