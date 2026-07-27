# 代码本体与波及分析设计文档

本目录是 `code-ontology` 的正式设计基线。文档不是概念速览，而是面向实现、评审和长期演进的完整建模说明。

## 推荐入口

- [需求到代码智能平台完整系统设计](21-complete-requirement-to-code-intelligence-platform.md)
- [可执行 Agent Gateway 与规划规则 MVP](22-executable-agent-gateway-mvp.md)
- [完整智能平台符合性审计](23-complete-platform-compliance-audit.md)
- [核心功能完成矩阵](24-core-function-completion-matrix.md)
- [总体架构](00-overall-architecture.md)
- [OpenCode Agent + Skill AI 辅助架构](20-opencode-agent-skill-architecture.md)

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
18. [业务语义建图完整设计](17-business-semantic-graph.md)
19. [业务图与代码图关联完整设计](18-business-code-graph-linkage.md)
20. [新增需求详细设计到代码图变更](19-requirement-design-to-code-graph-change.md)
21. [OpenCode Agent + Skill AI 辅助架构](20-opencode-agent-skill-architecture.md)
22. [需求到代码智能平台完整系统设计](21-complete-requirement-to-code-intelligence-platform.md)
23. [可执行 Agent Gateway 与规划规则 MVP](22-executable-agent-gateway-mvp.md)
24. [完整智能平台符合性审计](23-complete-platform-compliance-audit.md)
25. [核心功能完成矩阵](24-core-function-completion-matrix.md)

## 业务语义与需求规划资产

- [业务语义与代码图桥接本体](../ontology/business-code-linkage.ttl)
- [SDN 网络管理业务领域本体](../ontology/sdn-business-ontology.ttl)
- [需求设计到代码图变更规划本体](../ontology/requirement-change-planning.ttl)
- [业务图与代码图 SHACL 约束](../shapes/business-code-linkage-shapes.ttl)
- [需求变更规划 SHACL 约束](../shapes/requirement-change-planning-shapes.ttl)
- [需求变更规划规则模板](../rules/requirement-change-planning-rules.yaml)
- [SDN 网络策略部署实例图](../examples/sdn-network-policy-deployment.ttl)
- [SDN 需求到代码图变更实例](../examples/sdn-requirement-to-code-change-plan.ttl)

## OpenCode Agent 与 Skill 资产

- [OpenCode 项目配置](../opencode.json)
- [Agent 定义](../.opencode/agents/)
- [Skill 定义](../.opencode/skills/)
- [代码本体平台自定义工具](../.opencode/tools/ontology.ts)

Agent 负责角色化执行与编排，Skill 负责稳定工作流与输出契约，自定义 Tool/MCP 负责受控事实访问和草案写入。AI 结果必须保存 Agent、Skill 版本、上下文 Hash、证据、假设和人工 Gate。

## 统一写作结构

每个专题包含：为什么需要这一层、核心设计思想、最终类与关系、传播或转换语义、证据来源、示例、常见误区和实现注意事项。

## 图空间分离

完整系统明确区分：

- **Current Knowledge Graph**：长期存在且可验证的代码、契约、数据、业务和部署事实；
- **Desired Design Graph**：需求和详细设计描述的期望业务与技术状态；
- **Proposed Change Graph**：从当前状态到目标状态的候选与批准变更计划；
- **Actual Graph After Implementation**：代码实现后由解析器重新抽取的实际事实；
- **Impact Graph**：针对实际或提议变化生成的候选、确定影响、吸收点、证据、测试和风险结论。

这些图空间分离，是保证事实纯净、设计可评审、变更可重算和实现可对账的基础。

前端 Graph Explorer 已把 Business 和 Approved 补入可视图空间，当前统一支持
Current、Business、Desired、Proposed、Approved、Actual、Impact 七类图的版本
选择、过滤、路径查询和证据检查。核心功能逐项状态见
[智能代码本体平台核心功能完成矩阵](24-core-function-completion-matrix.md)。
