# Code Ontology

面向代码知识图谱、语义变更识别、需求变更规划、OpenCode Agent 辅助实现与全链路波及分析的本体和系统设计。

本仓库建立从源码、调用、类型、字段数据流、数据库、API、消息、配置、测试、业务语义，到需求详细设计、Agent 实现、构建、部署和运行版本的统一模型。设计目标不是进行无约束图遍历，也不是让设计文档或 AI 候选直接污染当前代码事实，而是根据变更类型、关系语义、兼容边界、运行证据和规划规则，生成可解释、可评审、可实现、可对账的变更结论。

## 系统总入口

- [需求到代码智能平台完整系统设计](docs/21-complete-requirement-to-code-intelligence-platform.md)
- [正式设计文档目录](docs/README.md)
- [总体架构](docs/00-overall-architecture.md)

完整系统闭环：

```text
现存代码库和运行事实
→ Current Knowledge Graph

特性与详细设计文档
→ Requirement IR
→ Desired Design Graph

Current + Desired
→ Semantic Graph Diff
→ Proposed Change Graph
→ 人工 Gate
→ Approved Change Graph

Approved Change
→ OpenCode Agent + Skill
→ 代码和测试 Patch
→ Actual Graph
→ Reconciliation
→ Impact Analysis
→ Release Verification
```

## 专题文档

- [业务语义建图完整设计](docs/17-business-semantic-graph.md)
- [业务图与代码图关联完整设计](docs/18-business-code-graph-linkage.md)
- [新增需求详细设计到代码图变更](docs/19-requirement-design-to-code-graph-change.md)
- [OpenCode Agent + Skill AI 辅助架构](docs/20-opencode-agent-skill-architecture.md)
- [影响传播规则](docs/14-impact-propagation-rules.md)
- [RDFS、OWL、SHACL 与规则引擎边界](docs/15-rdfs-owl-shacl.md)
- [实现架构与数据管道](docs/16-implementation-architecture.md)

## 本体、规则与示例

- [核心代码本体](ontology/code-ontology.ttl)
- [业务语义与代码图桥接本体](ontology/business-code-linkage.ttl)
- [SDN 网络管理业务领域本体](ontology/sdn-business-ontology.ttl)
- [需求设计到代码图变更规划本体](ontology/requirement-change-planning.ttl)
- [业务图与代码图 SHACL 约束](shapes/business-code-linkage-shapes.ttl)
- [需求变更规划 SHACL 约束](shapes/requirement-change-planning-shapes.ttl)
- [需求变更规划规则模板](rules/requirement-change-planning-rules.yaml)
- [SDN 网络策略部署实例图](examples/sdn-network-policy-deployment.ttl)
- [SDN 需求到代码图变更实例](examples/sdn-requirement-to-code-change-plan.ttl)

## OpenCode Agent + Skill

- [OpenCode 项目权限与 MCP 配置](opencode.json)
- [Agent 定义](.opencode/agents/)
- [Skill 定义](.opencode/skills/)
- [代码本体平台受控工具](.opencode/tools/ontology.ts)

AI 层采用：

```text
OpenCode Agent
→ 按角色编排任务

SKILL.md
→ 定义稳定、可复用、可审计的工作流和输出契约

Custom Tool / MCP
→ 查询 Current / Desired / Proposed / Actual / Impact 图并写入草案 Artifact

人工 Gate
→ 确认业务语义、关键映射、架构方案、破坏性变化、合并和发布
```

项目提供需求编排、需求文档分析、代码图对齐、变更规划、独立架构复核、批准后实现和实现对账 Agent。实现 Agent 只能在 Approved Change、独立 Worktree 和文件白名单存在时编辑代码，且禁止 Git Commit、Push、Merge 和生产部署。

## 核心原则

1. 编译器、Schema Parser 和平台连接器负责抽取事实，语义技术不替代静态分析。
2. 结构、调用、类型、数据流、契约、配置、业务和部署关系分层建模。
3. Java 类型与外部 Schema、实体与表、服务与镜像等概念保持独立，通过语义关系连接。
4. 图上可达只产生候选，真实影响由 ChangeType、上下文和规则决定。
5. Current Knowledge、Desired Design、Proposed Change、Actual Implementation 和 Impact 图空间分离。
6. 需求详细设计先转换为 Requirement IR，再生成目标图和可评审变更提案，不能直接写入当前事实图。
7. 所有实体对齐和变更提案保存证据、置信度、替代方案、规则版本和人工决策。
8. 传播支持 Confirmed、Contained、Rejected 和 Unresolved，识别 Mapper、Adapter、Serializer 等变化吸收点。
9. 影响结果最终连接到测试、业务能力、责任团队、构建产物、发布顺序和运行版本。
10. 业务图、代码图和项目级映射保持独立，通过 ImplementationSlice、稳定业务 ID、证据和版本化映射连接。
11. 通用业务元模型与 SDN 领域本体分层，避免把项目代码结构固化为领域语义。
12. 实现完成后必须重新抽取实际代码图，并与 Approved Change Graph 做设计—实现对账。
13. Agent 负责角色化执行，Skill 负责稳定流程，Tool/MCP 负责受控事实访问，人工负责需要承担责任的决策。
14. AI 未确认候选不得写入 Current Graph；Approved Change 不得复制为 Actual Graph。
15. 机器负责可证明事实，AI 负责候选和解释，人负责需要承担责任的决定。

## 仓库方向

后续实现目录将围绕 `ontology/`、`shapes/`、`rules/`、`extractors/`、`queries/`、`examples/`、`.opencode/`、Agent Gateway 和分析服务展开。
