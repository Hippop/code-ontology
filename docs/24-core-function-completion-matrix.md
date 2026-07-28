# 智能代码本体平台核心功能完成矩阵

更新时间：2026-07-28

本矩阵只统计核心业务闭环。指标、告警、Tracing、运行监控等可观测性能力按当前
优先级暂缓，不以它们阻塞核心功能验收。

## 1. 图谱生产与查看

| 能力 | 后端 | 前端 | 验证结论 |
|---|---|---|---|
| 代码本体图（Current） | 已实现 Java/Spring/Maven/Kafka/OpenAPI/SQL/配置/测试扫描、版本快照和目录 API | 已实现 Current 图空间、Revision 选择、Cytoscape 展示和证据详情 | 已完成 |
| 业务本体图（Business） | 已从确认后的业务实体、关系和证据发布独立 Business Graph | 已实现 Business 图空间切换、类型/关系过滤和业务追踪 | 已完成 |
| 目标设计图（Desired） | 已由 Design Revision → Requirement IR 生成并版本化 | 已实现 Desired 图空间查看 | 已完成 |
| 变更草案图（Proposed） | 已把语义差异、Change Proposal、引用实体、任务和验证义务发布为实际图快照 | 已实现 Proposed 图空间查看和变更上下文查询 | 已完成 |
| 批准变更图（Approved） | 已在 Architecture/Security/Data Gate 后独立发布 | 已实现 Approved 图空间查看 | 已完成 |
| 实际实现图（Actual） | 已在 Agent 修改后重新扫描代码生成，不复制 Approved Graph | 已实现 Actual 图空间查看 | 已完成 |
| 波及图（Impact） | 已实现直接/传播/吸收/未决影响、路径、测试与发布建议 | 已实现 Impact 图空间、波及着色和路径查询 | 已完成 |
| 图版本目录 | `GET /api/graphs` 返回七类图空间、Revision、状态、节点/边数量和元数据 | Revision 下拉框消费真实目录 | 已完成 |
| 图谱文本持久化 | 所有图发布统一双写 SQLite 与规范化 JSON，文本包含 Schema、Metadata、稳定排序的节点/边、数量和内容 Hash | 图目录返回文本格式、相对路径和 Hash | 已完成 |
| 示例图谱回归基线 | 已提交 Java/Spring 示例的 72 节点、95 关系预期语义图；CLI 支持 generate/compare，`scan --expected-graph` 漂移时返回非零退出码 | 对比结果复用结构化 Added/Removed/Modified 摘要 | 已完成 |
| 有界图查询 | `GRAPH_OVERVIEW` 支持搜索、类型、关系、节点/边上限和截断标记 | 已实现对应筛选器、总量/可见量和截断状态 | 已完成 |
| 专项图查询 | 已实现邻域、实现切片、业务追踪、调用路径、契约消费者、数据依赖、变更上下文、波及路径 | 已提供统一查询入口、起止实体、深度和路径结果 | 已完成 |
| 图证据检查 | 节点与边返回完整属性、来源和证据 | 点击节点/关系显示只读 JSON 证据 | 已完成 |
| 跨图差异对照 | `POST /api/graphs/compare` 支持任意图空间/版本的节点、关系和字段级 Added/Removed/Modified/Unchanged 对比，并排除快照 Revision 等非语义漂移 | 已实现差异叠加、左右对照、状态/类型/关键字过滤、属性 Diff 和证据检查 | 已完成 |

## 2. 新增需求全流程

| 阶段 | 当前实现 | 结论 |
|---|---|---|
| 设计文档接入 | Design Revision、Requirement IR、流程/规则/契约/业务实体抽取 | 已完成 |
| 需求人工确认 | Requirement Review Gate 和不可变确认版本 | 已完成 |
| 代码—业务对齐 | 多候选 Alignment、置信度、证据、替代项、Implementation Slice | 已完成 |
| 语义差异和变更规划 | Semantic Diff、全层 Change Proposal、任务、风险和验证义务 | 已完成 |
| 架构审批 | Architecture/Security/Data Gate，未批准不能进入实现 | 已完成 |
| 隔离实现 | detached Worktree、文件/命令白名单、Patch 捕获、HEAD 不变 | 已完成 |
| 测试与实际图 | 独立测试、重新扫描 Actual Graph | 已完成 |
| 设计—实现对账 | Approved/Actual Reconciliation 和异常分类 | 已完成 |
| 波及分析与发布建议 | Impact Run、测试建议、发布顺序与 Release Advice | 已完成 |
| 真实模型自动完成 | 持久化 Orchestrator 已用真实 OpenCode 1.18.5 跑通需求分析、代码图分析、变更规划、架构复核、实现和验证；生成 Actual/Reconciliation/Impact。验收样例因真实设计偏差输出 `Release Blocked`，没有把流程完成误报为可发布 | 已完成 |

## 3. AI Agent 与 Skill

仓库提供一个需求编排角色和六个受限执行角色：需求分析、代码图分析、变更规划、
独立架构复核、批准后实现、实现验证。八个 Skill 分别覆盖编排、需求抽取、代码图
对齐、变更规划、独立架构评审、批准后实现、设计—实现对账和波及解释。

平台已实现持久化 Requirement Workflow 状态机：

```text
Extract / requirement-analyst
→ RequirementReview
→ Align / code-graph-analyst
→ AlignmentReview
→ Plan / change-planner
→ architecture-reviewer
→ ArchitectureReview
→ ChangeApproval
→ implementation-agent
→ Actual / Reconciliation / Impact
→ verification-agent
→ Completed
```

- 每个 Agent 固定 Skill、最小上下文、只读/可写权限和独立 Run 证据；
- Requirement、Alignment、Architecture、Change Approval 四个 Gate 必须人工恢复；
- `required`、`advisory`、`disabled` 三种 Agent Mode 均有明确失败语义；
- 失败状态和最后错误持久化，`POST .../retry` 只重试失败阶段，不从头重跑；
- 架构复核使用专用 `review-change-architecture` Skill，不再复用会写 Draft 的规划
  Skill；
- 真实 OpenCode 验收包含一次架构超时、安全中止、原地重试和完整终态，证明恢复
  链路可用。

## 4. 核心验收结论

1. 代码本体图、业务本体图、目标图、变更图、实际图和波及图均有后端快照与前端；
2. 任意两张图可做结构、关系和字段级对比；
3. 新增需求从文档到受控实现、Actual Graph、对账和波及分析形成完整状态机；
4. AI Agent 与 Skill 已实际接入，不只是静态设计；
5. 21 项自动化测试、前端生产构建和依赖审计通过；
6. 可观测性与生产规模化能力继续按当前优先级暂缓，不阻塞本轮核心业务验收。
