# 语言与技术栈复核

## 当前栈

| 层 | 语言与运行时 | 主要组件 | 结论 |
| --- | --- | --- | --- |
| 平台后端 | Python 3.11+ | SQLite、PyYAML、RDFLib、pySHACL、tree-sitter Java、stdlib HTTP/MCP | 保留。图谱、RDF/SHACL、文本解析和轻量服务组合与 Python 生态匹配 |
| 图谱智能 | Python + 外部 CLI | 内建 Java/Spring 抽取器、CodeGraph 1.5.0 Sidecar、确定性混合检索/社区/流程/跨仓图 | 保留双引擎；外部 Sidecar 失败时不污染内建事实图 |
| Agent Runtime | Python Adapter + Codex/OpenCode | Codex `exec --json`、OpenCode Server、Git Worktree、Patch/Policy/Test | 运行时已解耦；本机优先 Codex，容器回退 OpenCode |
| MCP | Python | MCP 2025-11-25，兼容 2025-06-18/2025-03-26，stdio + Streamable HTTP，14 个只读工具 | 适合接入 Codex、OpenCode 和通用 MCP Client |
| Web 工作台 | TypeScript 5.9.3、React 19.2.8 | Vite 7.3.6、Cytoscape 3.34.0 | 保留。版本由 lockfile 固定，类型检查和生产构建均已通过 |
| Java 示例 | Java 17 | Spring Boot 4.1.0、Maven、JUnit/Mockito | 已与容器 Java 17 对齐，并补齐可执行 parent 和测试 |
| 容器 | Node 24 Bookworm + Python 3 + JRE 17 | OpenCode 1.18.5、CodeGraph 1.5.0 | Node 同时承载 Web build 和两个 npm CLI；版本固定以保证可重现 |

源文件以 Markdown 设计文档和 Python 实现为主，另外包含 Java 示例、RDF/SHACL
TTL、JSON 图谱基线、TypeScript/React 工作台、YAML 规则与部署配置。没有第二套
后端语言或框架需要合并。

## 已执行的调整

1. Java 示例从未解析 dependencyManagement 的 Maven 文件改为正式 Spring Boot
   parent；Java 从 21 调整为 17，与容器 JRE 和 Agent 验证环境一致。
2. Spring Boot parent 更新到 4.1.0。官方项目页当前列出的稳定版本是
   [Spring Boot 4.1.0](https://spring.io/projects/spring-boot/)，官方教程仍以
   [Java 17](https://docs.spring.io/spring-boot/tutorial/first-application/index.html)
   作为可用前置。
3. 修复样例测试的空 service，使其成为真正可运行的 Mockito/JUnit 基线；加入
   `target/` ignore，构建产物不再污染平台补丁。
4. Agent 层从 OpenCode 单实现改成 Codex/OpenCode Adapter 协议；状态机、策略和
   Artifact 不再依赖单一模型运行时。
5. 平台包版本升到 0.3.0，MCP serverInfo、HTTP Server Header 和 Python 包版本
   保持一致。
6. Java 抽取器升到 0.2.0，区分仓内未解析调用和已知外部调用；样例扫描结果为
   71 nodes、97 edges、0 unresolved、7 external calls，基线比较无漂移。

## 不建议现在调整的部分

- 不把 Python 后端重写为 Java 或 TypeScript。当前核心依赖 RDFLib、pySHACL、
  tree-sitter 和确定性图算法，重写只会增加双实现差异，没有证明的性能收益。
- 不把内建 SQLite 立即换成图数据库。当前图空间有版本隔离、规范化 JSON 双写、
  可移植基线和只读 MCP；单机 MVP 用 SQLite 更容易重放和测试。规模化部署再把
  Current/Actual/Impact 投影到 Neo4j/Fuseki，同时保留 SQLite 审计元数据。
- 不把 CodeGraph 作为唯一事实源。它是增强 Sidecar，内建抽取器仍负责可重现的
  Java/Spring、API、数据库、配置和测试事实。
- 不在平台容器内打包个人 Codex 登录状态。容器默认使用 OpenCode；本地 Codex
  通过宿主已登录 CLI 接入，避免复制认证材料。

## 下一阶段扩展条件

只有出现对应规模或可靠性需求时再执行：

- 多实例写入：SQLite 元数据迁移 PostgreSQL；
- 大型跨仓查询：把文本快照异步投影到图数据库；
- 大 Artifact：迁移对象存储；
- 并发 Agent：从进程内调度迁移到短生命周期 Job/Worker；
- 生产身份：为 MCP/API 接入 OIDC、细粒度租户和仓库授权。

这些是部署形态演进，不要求改变 Requirement IR、五类变更图、MCP 工具协议或
Codex/OpenCode Adapter 边界。
