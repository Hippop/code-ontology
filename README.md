# Code Ontology

面向代码知识图谱、语义变更识别与全链路波及分析的本体和实现设计。

本仓库建立从源码、调用、类型、字段数据流、数据库、API、消息、配置、测试、业务语义，到构建、部署和运行版本的统一模型。设计目标不是进行无约束图遍历，而是根据变更类型、关系语义、兼容边界、运行证据和传播规则，生成可解释的影响结论。

## 文档入口

- [正式设计文档目录](docs/README.md)
- [总体架构](docs/00-overall-architecture.md)
- [业务语义建图完整设计](docs/17-business-semantic-graph.md)
- [业务图与代码图关联完整设计](docs/18-business-code-graph-linkage.md)
- [影响传播规则](docs/14-impact-propagation-rules.md)
- [RDFS、OWL、SHACL 与规则引擎边界](docs/15-rdfs-owl-shacl.md)
- [实现架构与数据管道](docs/16-implementation-architecture.md)

## 本体与示例

- [核心代码本体](ontology/code-ontology.ttl)
- [业务语义与代码图桥接本体](ontology/business-code-linkage.ttl)
- [SDN 网络管理业务领域本体](ontology/sdn-business-ontology.ttl)
- [业务图与代码图 SHACL 约束](shapes/business-code-linkage-shapes.ttl)
- [SDN 网络策略部署实例图](examples/sdn-network-policy-deployment.ttl)

## 核心原则

1. 编译器、Schema Parser 和平台连接器负责抽取事实，语义技术不替代静态分析。
2. 结构、调用、类型、数据流、契约、配置、业务和部署关系分层建模。
3. Java 类型与外部 Schema、实体与表、服务与镜像等概念保持独立，通过语义关系连接。
4. 图上可达只产生候选，真实影响由 ChangeType、上下文和规则决定。
5. 知识图、变更图和影响图分离，所有结论保留规则、证据、路径、风险和版本。
6. 传播支持 Confirmed、Contained、Rejected 和 Unresolved，识别 Mapper、Adapter、Serializer 等变化吸收点。
7. 影响结果最终连接到测试、业务能力、责任团队、构建产物、发布顺序和运行版本。
8. 业务图、代码图和项目级映射保持独立，通过 ImplementationSlice、稳定业务 ID、证据和版本化映射连接。
9. 通用业务元模型与 SDN 领域本体分层，避免把项目代码结构固化为领域语义。

## 仓库方向

后续实现目录将围绕 `ontology/`、`shapes/`、`rules/`、`extractors/`、`queries/`、`examples/` 和分析服务展开。