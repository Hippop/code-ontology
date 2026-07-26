# 代码本体与波及分析设计文档

本目录是 `code-ontology` 的正式设计基线。文档不是概念速览，而是面向实现、评审和长期演进的完整建模说明。

## 阅读顺序

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

## 统一写作结构

每个专题包含：为什么需要这一层、核心设计思想、最终类与关系、传播语义、证据来源、示例、常见误区和实现注意事项。

## 三张图

完整系统明确区分：

- **知识图谱**：长期存在的代码、契约、数据、业务和部署事实；
- **变更图**：某次 Commit、PR、Release 中发生的语义变化；
- **影响图**：针对某次变化生成的候选、确定影响、吸收点、证据、测试和风险结论。

三张图分离，是保证模型可解释、可重算和可版本化的基础。