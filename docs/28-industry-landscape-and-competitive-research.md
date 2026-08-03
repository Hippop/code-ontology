# 需求到代码智能平台：行业全景、竞品与可用项目调研报告

> 调研对象：本仓库 `Code Ontology / Requirement-to-Code Intelligence Platform`  
> 调研截止：2026-07-31（Asia/Shanghai）  
> 证据范围：项目源码与测试、厂商官方文档、项目官方仓库、官方产品页和少量原始论文  
> 结论性质：桌面研究与代码库审阅，不等同于对所有商业产品完成采购级 PoC

## 1. 执行摘要

### 1.1 一句话结论

市场上已经有很多产品分别解决“代码图谱”“架构治理”“需求追踪”“影响分析”
“Agent 编码”“测试选择”中的一部分，但截至调研日，没有发现一个公开产品同时完整
覆盖本项目的核心闭环：

```text
需求/详细设计
→ Requirement IR / Desired Graph
→ Current-Desired 语义差异
→ Proposed / Approved Change
→ 受控 Agent 实现
→ Actual Graph 重新抽取
→ Approved-Actual 对账
→ Impact / Test / Release Gate
→ 可审计运行证据
```

因此，本项目的差异化不应表述为“又一个代码知识图谱”或“又一个 MCP Server”，而应
表述为：

> **面向复杂和受监管软件的需求变更保证平台（Requirement Change Assurance
> Platform）：用版本化语义图和确定性证据，证明一项需求被如何设计、批准、实现、
> 验证，以及为什么可以或不可以发布。**

### 1.2 最重要的五项判断

1. **最直接、最强的企业竞品是 CAST Imaging。** CAST 已提供深度语义分析、150+
   技术、应用知识库、影响分析、Neo4j 图、GraphRAG 和 MCP。它在多语言、遗留系统
   理解、企业部署和商业成熟度上明显领先，但公开能力仍以“理解现有应用”为中心，
   没有展示本项目这种 Desired/Approved/Actual 分离与设计—实现对账闭环。
2. **Lattix 是最容易被低估的相似产品。** 它不仅有 DSM 和架构规则，还公开提供
   需求追踪、UML/SysML 与代码映射、跨域变更影响分析。它对高可靠、系统工程市场
   很有竞争力，但 Agent 执行和需求到实际代码的自动对账不是其公开主线。
3. **代码图谱 + MCP 已迅速商品化。** CodeGraph、CodeGraphContext、GitNexus、
   Codebase-Memory、OpenTology、Understand Anything 等项目在 2026 年密集出现。
   “把代码建成图并通过 MCP 给 Agent”本身不会形成持久壁垒。
4. **传统工具正快速吸收 Agent 能力。** CAST 已加入 GraphRAG/MCP；Sonargraph
   已公开面向 Agent 的 Architecture MCP；Sourcegraph、Augment、GitHub 都在强化
   跨仓上下文和 Agent 工作流。单纯依赖“Agent 可查询图谱”的领先窗口很短。
5. **本项目的产品覆盖面领先于工程成熟度。** 当前仓库有可执行的 Java/Spring
   纵向闭环和 31 项通过的自动化测试，但仍是单节点参考实现：主要扫描能力集中于
   Java/Spring，SQLite/同步 Worker、缺少企业身份、生产队列、大仓性能基准、真实
   CI/CD 与运行平台连接器。近期优先级应是“可验证的生产化”，不是继续横向增加概念。

### 1.3 推荐战略

采用“**内核自研、能力集成、系统连接**”路线：

- 自研并守住：图空间隔离、Requirement IR、语义差异、Approved-Actual 对账、
  变更保证案例、证据链、规则版本和 Human Gate。
- 集成而非重造：SCIP/Kythe 的编译器级索引、Joern/CodeQL 的数据流、OpenRewrite/
  Moderne 的确定性改码、CodeGraph 的轻量探索、SeaLights/Develocity 的测试选择。
- 连接而非替代：DOORS Next、Jama、Polarion、GitLab/Azure DevOps 的需求资产；
  Backstage/Cortex/Port 的服务与所有权；GitHub/GitLab/现有 CI/CD 的最终交付。
- 首个商业切入点：**大型 Java/Spring 系统的受控需求变更与发布前证据闭环**，
  尤其适合金融、运营商、制造、政企和其他重审批场景。

---

## 2. 本项目基线

### 2.1 产品定义

根据仓库的 [总入口设计](21-complete-requirement-to-code-intelligence-platform.md)、
[总体架构](00-overall-architecture.md) 和
[符合性审计](23-complete-platform-compliance-audit.md)，本项目将以下对象放进同一
版本化语义体系，但保持不同图空间和概念边界：

- 代码结构、调用、类型与字段数据流；
- API、数据库、消息、配置和测试；
- 业务能力、流程、规则、需求、责任团队；
- 构建、部署、运行版本和运行证据；
- Current、Business、Desired、Proposed、Approved、Actual、Impact 七类图空间；
- 需求确认、实体对齐、架构复核、变更批准和发布判断；
- 受限 Agent、隔离 Worktree、文件/命令白名单、测试和实现对账。

### 2.2 已实现能力

调研期间直接运行：

```text
python3 -m unittest discover -s tests -v
→ Ran 31 tests in 160.593s
→ OK
```

当前参考实现已经具备：

- Java/Spring/Maven、OpenAPI、SQL、配置、Kafka 和测试的版本化扫描；
- RDF/RDFS/OWL/SHACL 资产与语义校验；
- 设计文档 → Requirement IR → Desired Graph；
- 多候选实体对齐、Implementation Slice、Semantic Diff 和 Change Plan；
- Requirement、Alignment、Architecture、Change Approval 四类人工 Gate；
- OpenCode 受控执行、Actual Graph、Reconciliation、Impact 与 Release Advice；
- SQLite + 规范化 JSON 图快照、Hash、审计链和 Replay；
- React/Cytoscape 图谱工作台；
- CodeGraph 1.5.0 Sidecar、混合检索、Community、Process、跨仓契约图；
- 只读 stdio / Streamable HTTP MCP Server。

### 2.3 当前生产化边界

这些限制对竞品判断至关重要：

- 核心确定性扫描目前以 Java/Spring 为主，多语言主要依赖 Sidecar；
- Tree-sitter 抽取还不能等同于完整编译器 Binding Resolution；
- 当前是 SQLite、文件快照和同步 Worker 的单节点实现；
- 尚未完成 PostgreSQL/Neo4j/Fuseki 投影、对象存储和可恢复任务队列；
- 缺少 OIDC/RBAC、职责分离、Tenant 强隔离和企业审计导出；
- 缺少大仓库、超大图、增量抽取和多租户并发基准；
- 尚未接入真实企业 CI、制品、部署、运行和可观测平台；
- 仓库根目录没有发现明确的 LICENSE 文件，这会阻碍外部采用、合作和商业化尽调。

### 2.4 真正要保护的产品内核

竞品很多，但本项目不应把所有已有能力都当作壁垒。较难被通用工具替代的是：

1. **五态事实分离**：Current、Desired、Approved、Actual、Impact 不相互污染；
2. **批准方案与真实实现对账**：不是只看 Diff 或 Agent 自述；
3. **跨层变化语义**：代码、API、表、消息、配置、测试、部署和业务共同建模；
4. **变更传播状态**：Confirmed、Contained、Rejected、Unresolved，而非无界可达；
5. **机器事实、AI 候选、人工责任分层**；
6. **每项发布结论都有 Evidence、Rule、Version、Path 和 Human Decision**。

---

## 3. 调研方法与评价框架

### 3.1 纳入范围

“同类、相似或可用项目”分成六层：

| 层级 | 解决的问题 | 代表项目 |
|---|---|---|
| A. 应用知识图与影响分析 | 深度理解现有代码和跨技术依赖 | CAST、Lattix、Sonargraph、Understand |
| B. 代码智能与规模化变更 | 搜索、导航、跨仓分析、自动重构 | Sourcegraph、Moderne/OpenRewrite、CodeScene |
| C. 开源代码图与 Agent 上下文 | 本地建图、影响半径、MCP | CodeGraph、GitNexus、CodeGraphContext、OpenTology |
| D. 程序分析底座 | 编译器级索引、控制流、数据流、安全查询 | SCIP、Kythe、Joern、CodeQL、Semgrep |
| E. 需求与生命周期追踪 | 需求—设计—任务—测试—审计 | DOORS Next、Jama、Polarion、GitLab、Azure DevOps |
| F. 交付补充系统 | Agent、测试选择、服务目录、运行事实 | GitHub Agents、OpenHands、SeaLights、Backstage、Cortex |

### 3.2 评分维度

评分只表示“与本项目目标闭环的功能贴合度”，不是通用产品排名。

| 维度 | 权重 | 说明 |
|---|---:|---|
| 代码事实 | 15 | 结构、调用、类型、数据流、契约、数据库、配置等确定性事实 |
| 业务与需求语义 | 15 | 需求、流程、规则、业务对象、设计和责任关系 |
| 变更规划与影响 | 15 | 语义差异、变化类型、影响路径、兼容与变更任务 |
| 版本治理与对账 | 15 | Current/Desired/Approved/Actual 分离、基线、实际对账 |
| Agent 与执行治理 | 10 | 上下文、受控改码、权限、隔离、Human Gate |
| 测试/发布/运行 | 10 | 测试选择、验证、发布建议、运行证据 |
| 多语言/多仓与规模 | 10 | 技术覆盖、跨仓、企业规模 |
| 解释/审计与治理 | 10 | 证据、规则、追踪、权限、审计和企业控制 |

每一维按 0–5 评分，再折算为 100 分。分数来自公开文档和当前仓库能力，不代表通过
统一样例实测。为避免“功能多等于可上线”的误导，另列企业成熟度。

---

## 4. 市场全景

### 4.1 企业级直接或高相似产品

| 项目 | 核心定位 | 与本项目重叠 | 主要缺口/边界 | 判断 |
|---|---|---|---|---|
| [CAST Imaging](https://doc.castsoftware.com/imagingexpress/) | 自动生成应用知识库、深度语义分析、影响分析、可视化、AI/MCP | 代码/数据依赖图、影响路径、GraphRAG、MCP、企业部署 | 公开材料未展示 Requirement IR、Approved/Actual 对账和受控实现闭环 | **最强直接威胁** |
| [Lattix](https://www.lattix.com/products/) | DSM、架构发现、规则、跨域系统分析 | 影响分析、需求追踪、UML/SysML—代码映射、架构规则 | Agent 实现、Actual Graph 对账不是公开主线 | **高相似，系统工程强** |
| [Sonargraph](https://eclipse.hello2morrow.com/doc/standalone/) | 代码依赖、架构 DSL、违规检查、重构模拟、CI Gate | 依赖事实、架构目标、快照、规则、Agent MCP | 需求/业务语义、跨交付链对账较弱 | **架构治理强竞品** |
| [Moderne](https://docs.moderne.io/) / [OpenRewrite](https://docs.openrewrite.org/) | 企业级跨仓分析和确定性自动重构 | 类型感知影响分析、变更规划、批量实现、结果表 | 不以业务本体、审批图和运行证据为中心 | **实现引擎/合作方兼竞品** |
| [Sourcegraph](https://sourcegraph.com/docs) | 全局代码搜索、精确导航、AI、批量变更 | 跨仓代码图、影响定位、Agent 上下文、Batch Changes、MCP | 需求语义、批准状态、Actual 对账与发布证据不是主线 | **代码智能入口强竞品** |
| [CodeScene](https://codescene.io/docs/) | 行为代码分析、热点、变更耦合、Code Health | 基于历史的变化风险、PR Delta、测试/缺失变化信号 | 缺少显式多层语义图和需求到实现闭环 | **风险排序能力强** |
| [SciTools Understand](https://scitools.com/) | 多语言静态分析、交叉引用、图、指标、合规 | 调用/控制流/依赖图、遗留代码理解、功能安全认证 | 需求规划、Agent 编排和发布闭环不突出 | **解析成熟，可作为标杆** |
| [ArchGuard](https://github.com/archguard/archguard) | 开源架构工作台和架构治理 | 容器/组件/代码级分析、适应度函数、可视化 | 活跃度和企业产品化弱于商业竞品；无完整需求闭环 | **国内开源参考** |

### 4.2 新一代代码图谱与 MCP 项目

| 项目 | 模型与能力 | 许可证/形态 | 对本项目的意义 |
|---|---|---|---|
| [CodeGraph 1.5.0](https://colbymchenry.github.io/codegraph/) | Tree-sitter、20+ 语言、符号/调用、Impact、Affected Tests、MCP、本地索引 | MIT；本地优先 | 已集成，适合继续作为可替换源码 Sidecar |
| [CodeGraphContext](https://github.com/CodeGraphContext/CodeGraphContext) | Tree-sitter + 可选 SCIP、23 种语言、多图数据库、CLI/MCP | MIT；本地或外部图数据库 | 多语言接入和后端抽象值得借鉴；需评估数据质量 |
| [GitNexus](https://github.com/nxpatterns/gitnexus) | 浏览器/本地建图、Community、Process、GraphRAG、MCP、Agent Hooks | PolyForm Noncommercial；商业使用受限 | 产品思路相近，但不宜把源代码纳入商用核心 |
| [Codebase-Memory](https://github.com/DeusData/codebase-memory-mcp) | 66 语言 Tree-sitter 图、影响分析、Community、MCP | MIT；研究论文和开源实现 | 是“图谱为 Agent 降 Token”的重要基准对手 |
| [OpenTology](https://github.com/Younkyum/opentology) | RDF/SPARQL/RDFS/SHACL、6 语言、影响分析、会话/决策持久记忆、MCP | MIT；Oxigraph WASM | 与本项目技术哲学最相近的新项目，应持续跟踪 |
| [Understand Anything](https://github.com/Egonex-AI/Understand-Anything) | 静态骨架 + 多 Agent 语义丰富 + 交互知识图/导览 | MIT；本地插件 | 强调“可教学的代码图”；LLM 成本和事实可信度需区分 |
| [FalkorDB Code-Graph](https://docs.falkordb.com/genai-tools/code-graph.html) | Python/Java/C# 图、GraphRAG、Web/CLI、Git 历史 | MIT；FalkorDB | 可参考 GraphRAG 与产品体验，不适合替代完整事实层 |
| [Bevel code-to-knowledge-graph](https://github.com/Bevel-Software/code-to-knowledge-graph) | 基于 LSP 的代码知识图、Neo4j、影响与架构洞察 | MPL-2.0；Kotlin/JVM | LSP/编译器事实接入的候选参考 |
| [CartographAI mcp-server-codegraph](https://github.com/CartographAI/mcp-server-codegraph) | 函数、类、调用、继承、MCP | MIT；轻量 | 功能较窄，说明基础 MCP 图能力进入同质化 |
| [code-graph-mcp](https://github.com/sdsrss/code-graph-mcp) | 10 语言 Tree-sitter、HTTP 路由、调用图、Impact | 开源项目 | Watchlist；适合纳入统一基准，不宜逐个集成 |

截至 2026-07-31 的 GitHub API 快照显示，CodeGraph、CodeGraphContext、
Codebase-Memory、Understand Anything 等项目都在近期高频更新。Star 和下载量只能
说明关注度，不能证明抽取准确率、安全性或企业可用性。这个子市场的结论是：

> **符号图、影响半径、Community、GraphRAG、MCP 很快会成为 Agent 工具的标配。**

### 4.3 程序分析和代码事实底座

| 项目 | 强项 | 不覆盖 | 推荐角色 |
|---|---|---|---|
| [Joern / Code Property Graph](https://docs.joern.io/code-property-graph/) | AST + CFG + 数据流/控制依赖统一图、跨语言查询、安全分析 | 需求、审批、发布闭环 | 数据流与程序切片 Sidecar |
| [CodeQL](https://codeql.github.com/docs/codeql-overview/about-codeql/) | 完整 AST、控制流、数据流数据库和路径查询；成熟安全规则 | 产品级需求变更语义 | 安全/数据流证据；注意 CLI 商业授权 |
| [SCIP](https://github.com/scip-code/scip) | 语言无关、编译器级定义/引用/实现协议；多语言 Indexer | 业务模型、变化和影响规则 | **多语言事实的首选标准接入层** |
| [Kythe](https://www.kythe.io/docs/kythe-overview.html) | 编译器/构建元数据、跨语言关联、可扩展代码图标准 | 完整产品工作流 | 大规模跨语言索引参考或高级适配器 |
| [Semgrep](https://semgrep.dev/products/pro-engine/) | 易写规则、跨文件/过程数据流、CI 与安全治理 | 通用需求到代码闭环 | 规则发现、安全 Gate 和额外证据 |
| [OpenRewrite](https://docs.openrewrite.org/concepts-and-explanations/lossless-semantic-trees) | 类型归属、格式保持 LST、可组合确定性 Recipe | 长期知识图和需求治理 | 批准后确定性实现引擎 |
| [Bazel Query](https://bazel.build/query/language) | 构建依赖图、目标与测试查询 | 业务语义 | 构建/测试事实连接器 |

关键许可判断：

- SCIP、Kythe、Joern、OpenRewrite 是 Apache-2.0，CodeGraph 是 MIT，适合商用集成；
- GitNexus 是 PolyForm Noncommercial，不是宽松开源许可；
- GitHub 的 `github/codeql` 查询仓库是 MIT，但 CodeQL CLI 本身受
  [GitHub CodeQL 条款](https://docs.github.com/en/code-security/concepts/code-scanning/codeql/codeql-cli)
  约束：私有仓库商业使用需要相应 GitHub Code Security 许可；
- 商业引擎输出可以作为外部 Evidence Provider，不要使核心事实模型绑定单一供应商。

### 4.4 需求、追踪与 ALM

| 产品 | 强项 | 与本项目关系 |
|---|---|---|
| [IBM DOORS Next / ELM](https://www.ibm.com/docs/en/engineering-lifecycle-management-suite/doors-next/7.1.0?topic=requirements-traceability) | 需求基线、评审、Link Validity、变更影响、需求—开发—测试追踪、OSLC、审计 | 最成熟的需求事实源和集成对象；也会争夺“端到端追踪”预算 |
| [Jama Connect](https://help.jamasoftware.com/ah/en/getting-to-know-jama-connect-features/traceability-from-requirements-to-test.html) | Live Traceability、Traceability Information Model、影响分析、风险和验证 | 强调实时追踪，适合成为上游 Requirement Provider |
| [Siemens Polarion](https://www.siemens.com/de-ch/products/polarion/requirements/) | 需求、测试、ALM、合规、变更控制 | 制造/汽车/医疗市场的重要上游与采购竞品 |
| [Azure DevOps](https://learn.microsoft.com/en-us/azure/devops/pipelines/test/requirements-traceability) | Work Item—测试—Bug—代码—Pipeline 追踪 | 适合以连接器方式复用现有事实 |
| [GitLab Requirements](https://docs.gitlab.com/user/project/requirements/) | 需求资产、Requirements Report、CI 满足状态 | 覆盖较轻，但 GitLab Agent/CI 一体化使其具备平台优势 |

这些产品证明“追踪链和审计”有稳定预算，但它们通常依赖人工链接或工具级 Artifact
链接；本项目的机会是自动生成、验证和解释到方法、字段、API、表、消息、配置的
**语义实现切片**，并将实现结果反向对账。

### 4.5 Agent、测试、服务目录和运行事实

| 领域 | 代表项目 | 可复用价值 |
|---|---|---|
| 云端 Coding Agent | [GitHub Copilot cloud/third-party agents](https://docs.github.com/en/copilot/concepts/agents/about-third-party-coding-agents)、[GitLab Duo Agent Platform](https://docs.gitlab.com/user/duo_agent_platform/) | 异步 Issue→PR、Ephemeral Runner、安全扫描、审计和人工 Review；本项目不应绑定单一 Agent |
| 开源 Agent Runtime | [OpenHands](https://docs.openhands.dev/openhands/usage/agents)、[OpenCode](https://opencode.ai/docs/agents) | 沙箱、权限、Agent SDK、Skills；可作为可替换执行层 |
| 测试选择 | [SeaLights TIA](https://docs.sealights.co/sup/test-impact-analysis)、[Develocity PTS](https://develocity.ai/product/predictive-test-selection/)、[Launchable](https://help.launchableinc.com/features/predictive-test-selection/) | 用覆盖/历史/ML 选择测试；可与图规则结果融合，而不是自研全部统计模型 |
| 服务目录 | [Backstage](https://backstage.io/docs/features/software-catalog/)、[Cortex](https://www.cortex.io/products/catalog)、[Port](https://docs.port.io/)、[Datadog Catalog](https://docs.datadoghq.com/internal_developer_portal/use_cases/dependency_management/) | 服务、团队、所有权、运行依赖和 Scorecard；适合补全责任与运行事实 |

GitHub 的 Agent 环境、安全扫描、Firewall、Skills 和 MCP 正在快速完善。其公开文档
仍明确要求人工验证 Agent 结果。这与本项目“Agent 输出不是事实、必须 Actual
Graph 回抽和 Reconciliation”的原则相符，也说明执行层会越来越标准化，平台应把
Agent 当作可替换 Worker。

---

## 5. 重点竞品深度分析

### 5.1 CAST Imaging

**已核验能力**

- 官方称对应用全部 Artifact 做深度语义和上下文分析，识别代码元素、数据结构及依赖；
- 支持 150+ 技术，包括 Java/JEE、.NET、Web、Mainframe、SQL、NoSQL；
- 可做对象、Transaction、Data Call Graph 和变更影响分析；
- PostgreSQL 分析库投影到 Neo4j 用于图导航；
- 3.6.5 引入 GraphRAG：源码/生成内容 Embedding、业务实体和关系抽取、Topic 聚类；
- MCP Server 可把结构图和 GraphRAG 提供给 GitHub Copilot、Claude Desktop 等客户端；
- 支持 Windows、Docker、Kubernetes、多 Analysis Node 和企业管理。

**优势**

1. 多语言和遗留技术覆盖是本项目短期无法正面复制的；
2. 静态分析深度、企业部署、扩展生态和商业背书强；
3. 已同时覆盖传统图查询和自然语言业务问题；
4. 对大型应用理解、迁移和现代化具有清晰采购场景。

**相对缺口**

- 公开资料的核心仍是 Current Application Knowledge Base；
- GraphRAG 业务语义主要由 AI 从现有代码提取，不等同于经人工确认的 Requirement IR；
- 未见 Desired/Proposed/Approved/Actual 独立图空间；
- 未见批准变更与实际实现逐项对账；
- 未见受限 Agent 根据 Approved Change 修改代码后再回抽的闭环。

**对策**

- 不与 CAST 竞争“支持最多语言/技术”；
- 将 CAST 视为可选 Current Graph/Evidence Provider；
- 以“需求变更保证和批准—实现对账”占据 CAST 上方的治理层；
- 必须尽快把业务语义和对账 UI 做成一眼可见的产品差异，而非只存在于文档。

### 5.2 Lattix

**已核验能力**

- DSM 和 Conceptual Architecture Diagram；
- 自动提取代码、UML/SysML 等依赖；
- 规则化架构控制、影响分析、循环和耦合发现；
- Enterprise 版提供需求 Traceability + Gap Analysis；
- 把 UML/SysML 模型与源码匹配；
- Multi-domain Matrix 连接跨域关系做变更影响分析；
- 支持 C/C++、Java、.NET、Python、UML/SysML。

**为什么重要**

Lattix 的公开能力已经跨越“代码图”与“系统工程模型”，是最接近“业务/需求—代码—
影响”思路的成熟产品之一。在汽车、航空、医疗、嵌入式和复杂系统市场，本项目会
直接遇到它。

**本项目可差异化**

- 自然语言设计文档到 Requirement IR；
- AI 候选与人工确认分层；
- Approved Change 图和 Agent 受控实现；
- Actual Graph 和 Reconciliation；
- API/消息/数据库/配置/发布的显式软件语义。

### 5.3 Moderne / OpenRewrite

**已核验能力**

- OpenRewrite LST 是类型归属、格式保持的语义树；
- Recipe 可以搜索并准确修改代码，且可组合为大型迁移；
- Moderne 提供组织级多仓 Repository Catalog、批量执行、结果表和可视化；
- 可先写 Search Recipe 做变更前完整 Edit-site/Impact 分析；
- Moddy 把自然语言 Agent 与 LST/Recipe 的确定性能力结合；
- 官方 Recipe Catalog 在调研时展示 7,000+ Recipe。

**威胁**

如果本项目把价值重点放在“Agent 能批量改代码”，Moderne 会更强：其变更是类型感知、
格式保持、可重复的确定性转换，企业规模和迁移场景也更成熟。

**合作价值**

把已批准、规则化程度高的 Change Proposal 编译成 OpenRewrite Recipe：

```text
Approved Change
→ Recipe 选择/参数生成
→ Dry Run / Data Table
→ 人工确认
→ 确定性 Transformation
→ Actual Graph / Reconciliation
```

LLM Agent 只处理无法 Recipe 化的长尾变化。这样会显著提高可重复性和审计性。

### 5.4 Sourcegraph

**已核验能力**

- 跨代码托管平台和跨仓搜索；
- 基于 SCIP 的 Precise Code Navigation；
- Java/Kotlin/Scala、Go、TS/JS、C/C++、Rust、Python、Ruby、.NET 等 Indexer；
- Deep Search、Cody、Code Graph Context、Batch Changes、Code Insights；
- MCP Server 和企业自托管。

**优势**

- 编译器级定义/引用/实现关系和跨仓导航；
- 是开发者日常代码入口，使用频率优势明显；
- Search、Graph、AI 和批量变更形成协同。

**边界**

SCIP 主要表达代码导航事实，不表达业务需求、数据库迁移、配置优先级、发布版本和
Human Gate。Sourcegraph 更适合作为本项目的代码事实/检索 Provider，而非完全替代。

### 5.5 Sonargraph

**已核验能力**

- Java/Kotlin、C/C++、C#、Python 等语言模型；
- 方法/字段级依赖、快照、虚拟模型、重构模拟；
- 可读 Architecture DSL、接口/连接器、依赖类型限制；
- IDE 和 CI 构建 Gate；
- 2026-07 官方公开 Architecture MCP：Java 编译器绑定、Architecture 规则、循环、
  Baseline 和面向 Agent 的精确依赖查询。

**竞争判断**

Sonargraph 正把“架构规则在 CI 检查”前移到“Agent 写依赖之前”。这是对本项目
Change Plan/Agent Guardrail 的直接竞争信号。其公开文章也明确区分 MCP 快速内环与
Sonargraph CI 权威 Gate，这一产品分层值得借鉴。

**注意**

官方文章在调研日仍把 26.2.0 MCP 描述为即将发布，不能仅凭文章把全部能力当作已
GA；采购或集成前需核验正式 Release Artifact。

### 5.6 IBM DOORS Next / ELM

**已核验能力**

- Requirement Baseline、Review、Configuration、Change Set；
- 需求之间及需求—开发—测试—设计 Artifact 的有类型关系；
- Suspect Link/Link Validity、Coverage 和变更影响；
- OSLC 跨工具集成；
- 审批、报表、权限和大组织治理。

**竞争判断**

DOORS Next 控制了高价值需求源和合规预算。直接替代它会让本项目承担复杂的文档协作、
电子签名、配置管理和监管适配。更优路线是：

```text
DOORS/Jama/Polarion
→ 需求事实、基线、批准状态

本项目
→ 自动语义映射、代码/契约/数据变更计划、Actual 对账、发布证据
```

优先实现 OSLC 或可配置 REST Connector，比另做完整需求编辑器更有商业价值。

### 5.7 CodeGraph、CodeGraphContext 与 Codebase-Memory

这三类工具共同定义了本地 Agent 代码图谱的基础能力：

- Tree-sitter 多语言解析；
- 文件、类、函数、调用、继承、Import 图；
- 搜索、Callers/Callees、Impact、Affected Tests；
- 本地数据库、增量/新鲜度、MCP；
- Community/Process/GraphRAG；
- 少量工具调用返回高密度上下文。

[Codebase-Memory 论文](https://www.alphaxiv.org/abs/2603.27277)报告了一个值得重视的
权衡：其公开实验中图方案用约 10 倍更少 Token、2.1 倍更少工具调用，但总体回答
质量为 83%，低于文件探索 Agent 的 92%。无论具体实验能否独立复现，这都说明：

> 图谱适合回答结构问题和缩小候选范围，但不应成为 Agent 唯一事实源；关键结论仍需
> 回到源码、编译器、Schema、测试和运行证据。

这与本项目“Sidecar 只补充、不替代 Current Graph”和“图可达不等于真实影响”的
路线一致。

### 5.8 OpenTology

OpenTology 是值得重点监控的早期项目，因为它与本项目共享很多技术选择：

- RDF Named Graph、SPARQL、RDFS、SHACL；
- 代码依赖、Symbol、Call Graph 和影响分析；
- 决策、Issue、Knowledge、Session 持久记忆；
- MCP、自动同步和 Agent 行为指令；
- 本地 Oxigraph WASM。

当前公开边界：

- 文件/符号影响为主；
- 没有成熟 Requirement IR、Desired/Approved/Actual 图空间；
- 没有批准变更规划、受控实现和确定性对账；
- 项目很新，企业性能、安全和治理证据不足。

它证明“RDF + Agent Memory + Impact”也会快速普及。本项目应避免只宣传本体技术，
而要宣传本体约束所支撑的**变更责任与发布证明**。

### 5.9 CodeScene

CodeScene 不依赖完整静态语义图，而是利用 Git 历史、Ticket 和组织行为识别：

- 高频变化热点；
- Code Health；
- 文件/函数/架构级 Change Coupling；
- Knowledge Loss/Ownership 风险；
- PR Delta Analysis 和质量 Gate；
- “预期变化缺失”之类的风险信号。

这是本项目当前的明显盲点。本项目的影响判断主要基于显式关系和规则，后续应把
CodeScene 式的**时间和组织信号**作为 Evidence/Risk Prior，不要把它们混成确定事实：

```text
静态语义影响
+ 历史共同变化
+ 生产调用/覆盖
+ 责任与人员风险
→ 更好的优先级和人工评审顺序
```

### 5.10 GitHub/GitLab Agent 平台

GitHub 已公开：

- Issue/Prompt → 异步 Agent → Pull Request；
- GitHub Actions 驱动的 Ephemeral Environment；
- 运行测试和 Linter；
- CodeQL、Secret、依赖安全扫描；
- Firewall、Skills、Hooks、MCP、自定义 Agent；
- 人工 Review、评论迭代和最终 Merge。

GitLab Duo Agent Platform 也把多 Agent/Flow 放进完整 DevSecOps 生命周期。

**含义**

本项目不应把“启动一个 Agent、创建 Worktree、执行测试”当作长期独占能力。真正的
价值是向任何 Agent 提供：

- 经批准的变更合同；
- 可编辑/禁止文件和验证义务；
- 结构化 Current/Desired/Impact 上下文；
- Agent 完成后独立生成的 Actual/Reconciliation；
- 可供现有 PR/CI Gate 消费的机器可读 Verdict。

---

## 6. 能力评分矩阵

### 6.1 与目标闭环的贴合度

| 产品/项目 | 代码事实 | 业务需求 | 变更影响 | 版本对账 | Agent 治理 | 测试发布 | 多语言规模 | 审计治理 | 加权贴合度 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **本项目当前能力** | 4 | 5 | 5 | 5 | 5 | 4 | 2 | 4 | **87** |
| CAST Imaging | 5 | 3 | 4 | 2 | 2 | 2 | 5 | 5 | **70** |
| IBM DOORS Next / ELM | 1 | 5 | 4 | 4 | 1 | 5 | 2 | 5 | **68** |
| Moderne / OpenRewrite | 5 | 1 | 4 | 3 | 3 | 2 | 5 | 4 | **67** |
| Jama Connect | 1 | 5 | 4 | 3 | 1 | 4 | 2 | 5 | **63** |
| Lattix | 4 | 3 | 4 | 2 | 1 | 2 | 4 | 4 | **61** |
| Sonargraph | 4 | 1 | 4 | 2 | 3 | 2 | 4 | 4 | **59** |
| Sourcegraph | 5 | 1 | 3 | 1 | 4 | 1 | 5 | 4 | **58** |
| GitHub Agent Platform | 3 | 1 | 2 | 2 | 5 | 3 | 4 | 5 | **58** |
| CodeScene | 3 | 1 | 4 | 2 | 1 | 3 | 4 | 4 | **54** |
| OpenTology | 3 | 2 | 2 | 2 | 4 | 1 | 3 | 2 | **47** |
| CodeGraphContext | 4 | 0 | 2 | 1 | 4 | 1 | 4 | 2 | **43** |
| CodeGraph | 3 | 0 | 3 | 1 | 4 | 2 | 3 | 2 | **43** |
| Joern | 5 | 0 | 2 | 1 | 1 | 0 | 4 | 3 | **40** |

### 6.2 为什么不能只看上表

本项目的 87 分表示“参考实现覆盖目标概念的程度”，不表示生产竞争力。企业成熟度是
另一张表：

| 产品/项目 | 企业成熟度（0–5） | 依据 |
|---|---:|---|
| CAST、IBM ELM、GitHub | 5.0 | 大型商业产品、企业部署、权限/支持/生态 |
| Moderne、Sourcegraph、Jama、CodeScene | 4.5 | 成熟商业平台和企业规模案例 |
| Lattix、Sonargraph、Understand | 4.0 | 长期专业市场、成熟分析能力 |
| Joern/CodeQL 作为分析底座 | 4.0 | 技术成熟，但不是相同产品形态 |
| CodeGraph | 2.5 | 活跃、关注度高，但项目很新，企业控制有限 |
| CodeGraphContext/Codebase-Memory | 2.0 | 快速发展，仍需基准和安全验证 |
| **本项目当前参考实现** | **1.5** | 单节点、Java/Spring 为主、缺少生产连接器和规模证据 |
| OpenTology | 1.0 | 很早期 |

因此正确结论不是“本项目已经领先所有产品”，而是：

> **产品架构占据了一个少见的完整位置；能否形成优势，取决于把该架构压缩成可部署、
> 可度量、可集成、可证明的产品。**

---

## 7. 差距、威胁与机会

### 7.1 当前关键差距

#### P0：会直接阻碍试点

1. **编译器级 Java 精度不足**  
   Tree-sitter 适合快速抽取，但重载、泛型、反射、框架代理、生成代码和跨模块解析需要
   JDT/Javac/SCIP/字节码证据。
2. **缺少增量和大仓性能基准**  
   市场对手已强调数十万文件、跨仓和实时索引；本项目当前只有小型样例基线。
3. **缺少真实系统连接器**  
   没有 DOORS/Jira/GitHub/GitLab、CI、制品、Kubernetes、APM 的完整真实闭环。
4. **企业安全和权限不足**  
   Bearer Token 不能替代 OIDC、RBAC、Tenant/Repository/Environment 级授权和职责分离。
5. **产品许可证不明确**  
   根目录缺少 LICENSE，会使外部试用、贡献、嵌入和采购尽调无法判断。

#### P1：会削弱结果可信度

6. 缺少影响分析 Precision/Recall、Top-K Alignment 和 Test Selection Recall 指标；
7. 规则库仍小，缺少真实 API、数据库、Kafka、配置和部署事故样例；
8. 缺少历史变化、生产覆盖、动态 Trace 和组织信号；
9. 需求文档抽取对真实复杂模板、表格、附件和多版本冲突覆盖不足；
10. 前端缺少面向决策者的“Change Assurance Case”，目前图探索仍偏工程视角。

#### P2：会限制规模化商业

11. 多语言事实标准和 Provider 插件协议未稳定；
12. 缺少规则/领域本体/连接器的版本兼容与 Marketplace；
13. 缺少 HA、备份恢复、Artifact Retention、审计导出和数据驻留；
14. 缺少成本模型：单仓扫描、每次需求、每次 Agent Run 的时间和资源预算；
15. 缺少第三方 Agent 的统一执行/结果契约。

### 7.2 最大竞争威胁

| 威胁 | 概率 | 影响 | 应对 |
|---|---:|---:|---|
| CAST 把需求/设计和 Agent 改码纳入现有知识图平台 | 高 | 高 | 抢先固化 Approved-Actual 对账和开放连接层 |
| GitHub/GitLab 把 Requirement/Issue→Agent→PR→CI 全部原生化 | 高 | 高 | 做独立 Change Assurance Gate，不做 Git 平台替代品 |
| Sourcegraph/Augment 的上下文引擎使通用 Agent 足够好 | 高 | 中 | 强调可证明变更，不强调“更懂代码” |
| Moderne 用 Recipe + Agent 覆盖大规模需求实现 | 中 | 高 | 集成 Recipe，把确定性改码变成平台能力 |
| 新开源代码图谱快速复制 MCP/Impact/Community | 很高 | 中 | 不把这些当壁垒；用统一 Benchmark 选择 Provider |
| 企业认为完整语义建模过重，采用简单 Trace Link | 中 | 高 | 从高风险变更切入，证明漏改/返工/审计收益 |

### 7.3 最大市场机会

1. **受监管变更保证**：需求、设计、代码、测试和批准必须可追踪；
2. **大型遗留系统的变更前审计**：不仅“代码怎么工作”，还要“这项需求该改哪里”；
3. **AI 代码产量上升后的验证瓶颈**：Agent 写得更快，人无法线性增加 Review；
4. **跨 API/事件/数据的兼容性风险**：普通代码助手和单仓图容易漏掉；
5. **多 Agent 统一治理层**：企业会同时使用 Copilot、Codex、Claude、OpenCode 等；
6. **现有 ALM 与现代代码智能之间的断层**：需求工具知道“谁关联谁”，不知道真实实现；
7. **发布证据自动化**：把审计材料从人工拼表变成可重放 Assurance Package。

---

## 8. 建议的产品定位

### 8.1 不推荐的定位

- “企业级代码知识图谱”：CAST、Sourcegraph、Joern 和大量 MCP 项目会稀释差异；
- “代码影响分析平台”：CAST、Lattix、CodeScene、SeaLights 都有成熟话语权；
- “AI 自动写代码”：GitHub、GitLab、OpenHands、OpenCode、Moderne 竞争过强；
- “需求管理平台”：DOORS、Jama、Polarion 的协作和合规壁垒很高；
- “万能软件数字孪生”：范围过大、价值证明周期过长。

### 8.2 推荐的定位

中文：

> **需求变更保证平台：在 Agent 或开发者改码之前确定影响和批准边界，在改码之后用
> 实际代码图、测试和运行证据证明实现是否符合设计。**

英文：

> **Requirement Change Assurance Platform — deterministic, auditable
> requirement-to-implementation reconciliation for complex software systems.**

### 8.3 首选客户画像

优先级从高到低：

1. 100+ 开发者、50+ 服务或大型单体、Java/Spring 为主；
2. 有正式详细设计、架构评审、变更审批和发布 Gate；
3. API/Kafka/数据库迁移多，漏改成本高；
4. 已使用 DOORS/Jama/Polarion/Jira/Azure DevOps 中至少一种；
5. 正在引入多个 AI Coding Agent，但安全团队要求可审计；
6. 金融、运营商、制造、汽车、医疗、政企和关键基础设施。

不宜作为首批客户：

- 小型绿地团队；
- 没有正式需求和测试资产的早期创业公司；
- 以前端/脚本为主且架构变化极快的代码库；
- 只需要代码搜索或简单 PR Review 的团队。

### 8.4 最小可销售产品

首个商业版本不应交付全部“最终架构”，而应交付一个可证明 ROI 的闭环：

```text
输入
  一份已批准详细设计
  一个 Java/Spring 仓库或服务集合
  GitHub/GitLab PR + CI

输出
  1. 需求语义和未决问题
  2. 受影响 API/类/方法/表/消息/配置
  3. 经人工确认的 Change Contract
  4. Agent/开发者实现后的结构化偏差
  5. 必跑测试、兼容风险和发布 Verdict
  6. 可下载审计证据包
```

首要销售指标：

- 设计评审准备时间下降；
- 漏改项在 PR 前发现的比例；
- 人工影响分析时间下降；
- Agent PR 被打回次数下降；
- 发布审计材料准备时间下降；
- Reconciliation 识别到的真实偏差数。

---

## 9. Build / Buy / Integrate 决策

### 9.1 必须自研

| 能力 | 原因 |
|---|---|
| Requirement IR 与 Explicit/Suggested/Unresolved | 是需求语义治理核心 |
| Current/Desired/Proposed/Approved/Actual/Impact 图隔离 | 是防止 AI 候选污染事实的核心约束 |
| Semantic Diff 与 Change Proposal 模型 | 决定跨层规划和解释 |
| Approved-Actual Reconciliation | 最关键差异化 |
| Evidence/Rule/Confidence/Human Decision 模型 | 审计和责任基础 |
| Change Assurance Case / Replay Package | 最终客户价值载体 |
| Provider/Agent 中立契约 | 防止被单一分析器或 Agent 锁定 |

### 9.2 优先集成

| 能力 | 首选项目 | 建议 |
|---|---|---|
| 快速多语言源码图 | CodeGraph | 保持 Sidecar、版本固定、新鲜度协议和文本快照 |
| 编译器级跨语言索引 | SCIP | 定义 `ScipFactProvider`，优先 Java 后 TS/Python/Go |
| 深度数据流/程序切片 | Joern；企业可选 CodeQL | 只把结论作为带 Provenance 的 Evidence |
| 确定性代码迁移 | OpenRewrite/Moderne | 把适合的 Approved Change 编译成 Recipe |
| 安全规则 | Semgrep/CodeQL | 作为 Security Review 和 Verification Provider |
| 需求系统 | DOORS OSLC、Jama、Polarion、GitLab/Azure | 先做只读摄取和批准状态同步 |
| 服务/所有权 | Backstage、Cortex、Port | 导入服务、Team、On-call、Scorecard |
| 测试选择 | SeaLights/Develocity/Launchable 或 Bazel | 融合图规则和外部推荐，保留原因 |
| Agent Runtime | OpenCode、GitHub Agents、OpenHands、Codex 等 | 统一 `AgentRun` 和 `Artifact` 契约 |
| 运行证据 | OpenTelemetry、Datadog 等 | 只存摘要、版本关联和证据引用 |

### 9.3 不建议近期自研

- 全语言编译器与类型系统；
- 通用 Git 托管和 PR 系统；
- 完整需求协作文档编辑器；
- 通用 CI/CD；
- 通用 APM 和时序数据库；
- 大而全的代码安全规则库；
- 通用 AI Coding Agent；
- 自有向量模型或图数据库。

---

## 10. 技术路线建议

### 10.1 Provider 化事实层

将当前 Scanner 重构为带能力声明和证据质量的 Provider：

```text
FactProvider
├── JavaSpringProvider        # 当前确定性领域抽取
├── ScipProvider              # 编译器级定义/引用/实现
├── CodeGraphProvider         # 轻量多语言探索
├── JoernProvider             # CFG/DDG/切片
├── CodeQlProvider            # 安全/数据流，可选商业
├── OpenApiProvider
├── DatabaseProvider
├── MessagingProvider
├── BuildProvider
└── RuntimeProvider
```

每条事实至少记录：

```text
provider
providerVersion
repositoryRevision
factSchemaVersion
confidence
sourceLocation
evidenceHash
generatedAt
freshness
```

同一关系允许多 Provider 证据，冲突不能静默覆盖。

### 10.2 用 SCIP 补精度而不是盲目扩 Tree-sitter

推荐顺序：

1. Java：当前 Spring/Schema 语义 + SCIP/JDT 编译器关系；
2. TypeScript：SCIP TypeScript + OpenAPI/前端调用；
3. Python：SCIP Python + FastAPI/Django；
4. Go：SCIP/原生工具 + gRPC/Kubernetes；
5. C#：SCIP .NET + ASP.NET/Entity Framework。

Tree-sitter 保留为零配置 Fallback，返回质量等级；编译器 Index 可用时优先。

### 10.3 把图谱查询与真实影响分开

继续坚持：

```text
Reachability Candidate
+ ChangeType
+ Compatibility Rule
+ Context
+ Runtime/History Evidence
+ Boundary/Absorber
→ ImpactAssessment
```

不要把所有关系声明为传递属性，也不要用 GraphRAG 生成的业务关系直接进入 Current
Graph。CAST/OpenTology/GitNexus 的发展会让“自然语言问图”成为标配，本项目的可信度
取决于是否能清楚展示：

- 哪些是解析事实；
- 哪些是推导；
- 哪些是 AI 候选；
- 哪些经人确认；
- 哪些被测试或运行证据验证。

### 10.4 把 Reconciliation 做成一等产品

建议创建面向一次需求的 `Change Assurance Case`：

```text
Requirement Baseline
├── Confirmed Requirement IR
├── Alignment Decisions
├── Approved Change Contract
├── Implementation Patch / Agent Runs
├── Actual Semantic Delta
├── Approved-vs-Actual Findings
├── Impact and Test Evidence
├── Security/Data/Architecture Reviews
├── Release Verdict
└── Hash-chained Audit Timeline
```

UI 首页不再先展示“图有多少节点”，而先展示：

- 需求是否清晰；
- 哪些变化已批准；
- 哪些实现缺失或超范围；
- 哪些验证未完成；
- 哪些风险阻止发布；
- 谁做了最后决定。

### 10.5 让 Agent 可替换

定义与 OpenCode 无关的最小执行协议：

```text
AgentRequest
  approvedChangeRevision
  repositoryRevision
  allowedFiles
  forbiddenFiles
  allowedCommands
  requiredTests
  contextResources
  deadline

AgentResult
  patch
  artifacts
  commands
  testObservations
  declaredAssumptions
  policyEvents
  provider/model/version
```

平台独立验证：

- Worktree/Branch 基线；
- 实际文件范围；
- Commit/Push/Deploy 事件；
- 独立测试；
- Actual Graph；
- Reconciliation。

这样可同时接 OpenCode、Codex、GitHub Agent、GitLab Duo、OpenHands 或内部 Agent。

---

## 11. 12 个月路线图

### 阶段 0：0–2 个月，建立可信基准

1. 明确许可证、贡献和商业使用政策；
2. 建立 10–20 个真实 Java/Spring 仓样例，覆盖多模块、反射、生成代码；
3. 建立 50+ Seeded Change：API、DB、Kafka、配置、权限、事务；
4. 评估 Tree-sitter、CodeGraph、SCIP/JDT、Joern 的节点/关系 Precision/Recall；
5. 建立 Alignment Top-K、Impact Precision/Recall、Test Recall、Reconciliation Accuracy；
6. 发布第一版 Change Assurance Case UI 和导出包。

**阶段 Gate**

- Java Symbol/Call 关系 Precision ≥ 95%，Recall ≥ 90%（在声明范围内）；
- 高风险契约变化 Recall ≥ 95%；
- Reconciliation 对 Seeded Deviation 的识别率 ≥ 95%；
- 所有结论可回到 Source Location 与 Provider。

### 阶段 1：2–4 个月，可试点产品

1. GitHub/GitLab Repository、PR、CI 连接器；
2. Jira/Azure DevOps 需求连接器；选一个 DOORS/Jama 做试点；
3. PostgreSQL、对象存储、可恢复 Job Queue；
4. OIDC、RBAC、Tenant/Repository 隔离和审计导出；
5. 增量抽取、取消/重试、资源配额；
6. Java 编译器级 Binding 和跨模块解析；
7. CI Check：输出 Pass/Needs Review/Blocked。

**阶段 Gate**

- 100 万 LOC 仓库有可接受的首扫和增量时间；
- 失败任务可原地恢复，无需重跑全流程；
- 两个真实客户仓库跑通只读影响分析；
- 一个客户跑通 Requirement→PR→Reconciliation→CI Verdict。

### 阶段 2：4–8 个月，扩大连接和确定性执行

1. SCIP Provider；优先 TypeScript 和 Python；
2. OpenRewrite Recipe Executor；
3. 跨仓 HTTP/Event/Schema 契约；
4. Backstage/Cortex/Port 所有权接入；
5. OpenTelemetry/APM 运行证据；
6. SeaLights/Develocity/Launchable 或 Bazel 测试推荐接入；
7. CodeScene 式历史 Change Coupling 和 Knowledge Risk。

**阶段 Gate**

- 至少三语言、五类 Provider 可并行产出和对账；
- 跨仓契约变化能定位 Provider/Consumer 与 Owner；
- 规则化变化优先走确定性 Recipe，Agent 处理长尾；
- 运行证据能绑定 Artifact Version 与 Graph Revision。

### 阶段 3：8–12 个月，形成行业产品

1. 金融/运营商/制造领域规则包；
2. API、数据、事件和配置兼容性规则 Marketplace；
3. HA、备份恢复、数据驻留、保留策略；
4. Agent Provider SDK；
5. Portfolio 级变更风险和发布编排；
6. Assurance Evidence API，与 GRC/审计系统对接；
7. 基于真实结果校准规则和置信度，但不让模型自动升级事实。

---

## 12. 必须建立的行业基准

现有仓库用 72 节点/95 关系的样例验证了可重复图快照，但不足以支持市场声明。建议
建立公开或可复现的 `Requirement-to-Code Assurance Benchmark`。

### 12.1 事实抽取

| 指标 | 说明 |
|---|---|
| Entity Precision/Recall | 类型、方法、参数、API、Schema、表、列、Topic、配置 |
| Relation Precision/Recall | 调用、引用、读写、实现、序列化、持久化、覆盖 |
| Binding Accuracy | 重载、继承、泛型、跨模块、生成代码 |
| Cross-language Link Accuracy | HTTP、gRPC、消息、JNI/FFI 等 |
| Freshness | 修改后多久可查询到正确图 |

### 12.2 需求到代码

| 指标 | 说明 |
|---|---|
| IR Completeness | 明示项、隐含项、未决项是否完整 |
| Alignment Recall@K / MRR | 真实实现实体是否在候选前 K |
| False Confirmation Rate | AI 错误映射被自动升级的比例，目标必须为 0 |
| Reviewer Effort | 完成确认需要的点击/分钟 |

### 12.3 变更和影响

| 指标 | 说明 |
|---|---|
| Change Item Accuracy | 对真实语义变化分类正确率 |
| Impact Precision/Recall | 受影响实体、测试、Owner |
| Path Explanation Accuracy | 每条路径关系和规则是否真实 |
| Containment Accuracy | Adapter/Mapper/Serializer 是否正确吸收变化 |
| Cross-repo Contract Recall | Consumer 是否遗漏 |

### 12.4 实现和发布

| 指标 | 说明 |
|---|---|
| Reconciliation Accuracy | Missing/Unexpected/Deviated 分类 |
| Test Selection Recall | 会失败的测试被选中的比例 |
| Agent Policy Escape Rate | 越权编辑/命令/网络是否被阻止 |
| False Release Pass | 有真实偏差却允许发布的比例，目标必须接近 0 |
| Evidence Reproducibility | 同 Revision/规则版本能否重放同结论 |

### 12.5 性能与成本

- 10 万、100 万、1,000 万 LOC 首扫时间；
- 单文件、单模块和跨仓增量更新时间；
- 图存储大小、峰值内存、并发查询 P50/P95/P99；
- 每次 Requirement Workflow 的 Agent Token/时间/失败重试成本；
- MCP 单次响应 Token、工具调用数和答案质量；
- 长时间运行后的索引漂移和恢复。

---

## 13. 采购/选型建议

如果用户的真实目标是：

| 主要目标 | 优先考察 |
|---|---|
| 多技术遗留系统理解、可视化和现代化 | CAST Imaging |
| 跨域系统工程、DSM、UML/SysML 与需求影响 | Lattix |
| 架构规则、依赖循环和 CI Gate | Sonargraph |
| 海量跨仓确定性迁移 | Moderne/OpenRewrite |
| 全公司代码搜索、导航和 Agent 上下文 | Sourcegraph；也可评估 Augment |
| 行为热点、技术债和组织风险 | CodeScene |
| 安全数据流和程序切片 | CodeQL、Joern、Semgrep |
| 正式需求、合规和生命周期追踪 | DOORS Next、Jama、Polarion |
| 本地 Agent 代码图、快速试用 | CodeGraph、CodeGraphContext、Codebase-Memory |
| 测试影响与测试时间优化 | SeaLights、Develocity、Launchable |
| 服务所有权和运行目录 | Backstage、Cortex、Port、Datadog |
| **需求批准到实际实现的独立保证与对账** | **继续建设本项目，并集成上述工具** |

对于本项目团队，建议采购/试用顺序：

1. **CAST Imaging PoC**：用同一个 Java/Spring + API/DB/Kafka 仓对比事实和影响；
2. **Lattix 试用**：验证需求/模型/代码跨域 Trace 的真实深度；
3. **Moderne/OpenRewrite PoC**：把一个 Approved Change 编译成 Recipe；
4. **SCIP Java PoC**：测量对当前 Tree-sitter 图的 Precision/Recall 提升；
5. **DOORS/Jama 沙箱**：验证上游 Requirement/Baseline/Approval 摄取；
6. **Codebase-Memory/CodeGraphContext 基准**：比较 MCP Token、调用数和答案质量。

---

## 14. 最终结论

### 14.1 行业判断

行业正在从三类孤立工具：

```text
需求追踪
代码分析
AI 编码
```

走向同一个交叉点：

```text
结构化软件上下文
+ Agent 执行
+ 变更影响
+ 企业治理
```

代码图谱和 MCP 会成为基础设施，GraphRAG 会成为常见交互，Agent 会成为可替换执行者。
真正稀缺的是：**如何把自然语言意图变成经批准、可验证的变更合同，并证明实际实现
没有遗漏、越界或破坏兼容性。**

### 14.2 本项目的胜负手

本项目已经在架构上选择了正确而少见的位置，但必须完成三次转变：

1. 从“模型很完整”转向“关键结论可量化地正确”；
2. 从“单节点参考实现”转向“可接入现有企业工具链的保证层”；
3. 从“图谱工作台”转向“每项需求一个可签署、可重放的 Change Assurance Case”。

只要这三点落地，本项目不需要击败 CAST、Sourcegraph、DOORS、Moderne 或 GitHub；
它可以连接它们，并成为这些系统之间缺失的变更语义与责任边界。

---

## 附录 A：证据来源

以下优先列出官方资料。访问和核验时间均为 2026-07-31。

### A.1 企业代码智能与架构

1. [CAST Imaging Express Documentation](https://doc.castsoftware.com/imagingexpress/)
2. [CAST Imaging Components](https://doc.castsoftware.com/imaging/install/before-you-start/components/)
3. [CAST Imaging GraphRAG](https://doc.castsoftware.com/imaging/explore-results/use-ai-assistance/graphrag/)
4. [Lattix Products](https://www.lattix.com/products/)
5. [Lattix DSM Documentation](https://docs.lattix.com/lattix/userGuide/Working_with_the_Dependency_Structure_Matrix_DSM)
6. [Lattix Systems Engineering](https://www.lattix.com/solutions/systems-engineering/)
7. [Sonargraph User Manual 26.2](https://eclipse.hello2morrow.com/doc/standalone/)
8. [Sonargraph Architecture DSL](https://eclipse.hello2morrow.com/doc/standalone/content/architecture_definition.html)
9. [Sonargraph Architecture MCP Article](https://blog.hello2morrow.com/2026/07/sonargraph-mcp-2/)
10. [SciTools Understand](https://scitools.com/)
11. [CodeScene Hotspots](https://codescene.io/docs/guides/technical/hotspots.html)
12. [CodeScene Delta Analysis Terminology](https://codescene.io/docs/terminology/codescene-terminology.html)
13. [ArchGuard](https://github.com/archguard/archguard)

### A.2 代码搜索、重构和上下文

14. [Moderne Documentation](https://docs.moderne.io/)
15. [Moderne Licensing](https://docs.moderne.io/licensing/overview/)
16. [OpenRewrite LST](https://docs.openrewrite.org/concepts-and-explanations/lossless-semantic-trees)
17. [OpenRewrite Recipes](https://docs.openrewrite.org/concepts-and-explanations/recipes)
18. [Sourcegraph Documentation](https://sourcegraph.com/docs)
19. [Sourcegraph Precise Code Navigation](https://sourcegraph.com/docs/code-navigation/precise-code-navigation)
20. [Sourcegraph Cody Context](https://sourcegraph.com/docs/cody/core-concepts/context)
21. [Augment Context Engine](https://www.augmentcode.com/context-engine)
22. [GitHub Copilot Repository Indexing](https://docs.github.com/en/copilot/concepts/context/repository-indexing)
23. [Cursor Secure Codebase Indexing](https://cursor.com/blog/secure-codebase-indexing)

### A.3 开源代码图和程序分析

24. [CodeGraph](https://github.com/colbymchenry/codegraph)
25. [CodeGraphContext](https://github.com/CodeGraphContext/CodeGraphContext)
26. [GitNexus](https://github.com/nxpatterns/gitnexus)
27. [Codebase-Memory](https://github.com/DeusData/codebase-memory-mcp)
28. [OpenTology](https://github.com/Younkyum/opentology)
29. [Understand Anything](https://github.com/Egonex-AI/Understand-Anything)
30. [FalkorDB Code-Graph](https://github.com/FalkorDB/Code-Graph)
31. [Bevel code-to-knowledge-graph](https://github.com/Bevel-Software/code-to-knowledge-graph)
32. [Joern Code Property Graph](https://docs.joern.io/code-property-graph/)
33. [Code Property Graph Specification](https://cpg.joern.io/)
34. [CodeQL Overview](https://codeql.github.com/docs/codeql-overview/about-codeql/)
35. [CodeQL Path Queries](https://codeql.github.com/docs/writing-codeql-queries/creating-path-queries/)
36. [SCIP](https://github.com/scip-code/scip)
37. [Kythe Overview](https://www.kythe.io/docs/kythe-overview.html)
38. [Semgrep Pro Engine](https://semgrep.dev/products/pro-engine/)

### A.4 需求与生命周期

39. [IBM DOORS Next Traceability](https://www.ibm.com/docs/en/engineering-lifecycle-management-suite/doors-next/7.1.0?topic=requirements-traceability)
40. [IBM DOORS Next Cross-lifecycle Links](https://www.ibm.com/docs/en/engineering-lifecycle-management-suite/doors-next/7.1.0?topic=requirements-linking-development-design-test-requirement-artifacts)
41. [Jama Requirements-to-Test Traceability](https://help.jamasoftware.com/ah/en/getting-to-know-jama-connect-features/traceability-from-requirements-to-test.html)
42. [Siemens Polarion Requirements](https://www.siemens.com/de-ch/products/polarion/requirements/)
43. [Azure DevOps Requirements Traceability](https://learn.microsoft.com/en-us/azure/devops/pipelines/test/requirements-traceability)
44. [GitLab Requirements](https://docs.gitlab.com/user/project/requirements/)

### A.5 Agent、测试与服务目录

45. [GitHub Third-party Coding Agents](https://docs.github.com/en/copilot/concepts/agents/about-third-party-coding-agents)
46. [GitHub Agent Environment](https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/customize-cloud-agent/customize-the-agent-environment)
47. [GitHub Copilot Code Review](https://docs.github.com/en/copilot/concepts/agents/code-review)
48. [GitLab Duo Agent Platform](https://docs.gitlab.com/user/duo_agent_platform/)
49. [OpenHands Agents](https://docs.openhands.dev/openhands/usage/agents)
50. [OpenCode Agents](https://opencode.ai/docs/agents)
51. [SeaLights Test Impact Analysis](https://docs.sealights.co/sup/test-impact-analysis)
52. [Develocity Predictive Test Selection](https://develocity.ai/product/predictive-test-selection/)
53. [Launchable Predictive Test Selection](https://help.launchableinc.com/features/predictive-test-selection/)
54. [Backstage Software Catalog](https://backstage.io/docs/features/software-catalog/)
55. [Cortex Catalog](https://www.cortex.io/products/catalog)
56. [Port Standards and Compliance](https://docs.port.io/governance/standards-and-compliance/overview/)
57. [Datadog Dependency Management](https://docs.datadoghq.com/internal_developer_portal/use_cases/dependency_management/)

## 附录 B：新兴研究项目

这些项目暂不作为成熟产品计分，但揭示了行业方向：

- [RepoGraph](https://arxiv.org/abs/2410.14684)：用仓库级代码图增强 AI 软件工程；
- [CodePlan](https://arxiv.org/abs/2309.12499)：仓库级多步代码变更计划；
- [KGCompass](https://arxiv.org/abs/2503.21710)：知识图增强仓库级软件修复和定位；
- [Codebase-Memory](https://www.alphaxiv.org/abs/2603.27277)：Tree-sitter 图 + MCP 的成本/质量实验；
- [ReqToCode](https://arxiv.org/abs/2603.13999)：把需求追踪嵌入代码结构；
- [TraceDev](https://arxiv.org/abs/2607.18886)：需求追踪驱动的多 Agent 开发框架；
- [Repository Intelligence Graph](https://arxiv.org/abs/2601.10112)：面向 LLM 的确定性仓库架构图；
- [RepoDoc](https://arxiv.org/abs/2604.26523)：基于代码知识图的文档增量更新。

研究趋势与本报告结论一致：需求追踪、代码图、变更计划、Agent 和验证正在汇合，但
工业级事实精度、审批责任、生产集成和可重放证据仍是主要空白。
