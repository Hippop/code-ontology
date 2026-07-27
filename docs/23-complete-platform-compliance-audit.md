# 完整智能平台符合性审计

审计基线：`21-complete-requirement-to-code-intelligence-platform.md`
复核日期：2026-07-27
判定对象：本仓库的可执行单节点参考平台

## 1. 结论

第 31 章的 13 条功能验收标准均已有可执行实现和验证证据。平台不再是只有本体、Agent 配置和 API 壳的 MVP，而是形成了以下真实闭环：

```text
Java/Spring Repository Snapshot
→ Current Graph
→ Design Revision
→ Requirement IR / Desired Graph
→ Persistent Multi-Agent Workflow / Human Gates
→ Alignment / ImplementationSlice
→ Semantic Diff / Change Plan
→ Human Gates / Approved Graph
→ OpenCode Agent + Skill / Isolated Worktree / Patch
→ Independent Test Execution
→ Actual Graph / Reconciliation
→ Impact Graph / Test Selection / Release Plan
→ Runtime Evidence / Hash-chained Replay
```

这里的“通过”表示单节点参考实现达到功能验收，不表示已经完成生产规模化替换。设计中 PostgreSQL、Fuseki、Neo4j、对象存储、Kubernetes Worker Pool 和企业身份系统仍是生产部署演进项；当前 SQLite 图快照和同步 Worker 保持同一领域边界与 API 契约。

## 2. 最终验收标准逐项复核

| # | 设计验收项 | 判定 | 可执行证据 |
|---|---|---|---|
| 1 | 从真实 Java/Spring 仓库生成版本化代码知识图 | 通过 | `repository_scan.py` 使用 Tree-sitter Java AST，解析 Maven、Spring MVC、JPA、Kafka、OpenAPI、SQL、配置和测试；固定提交与脏工作区有不同 Revision；示例证明 Controller→Service→Repository→Table |
| 2 | 加载和校验 RDF/OWL/SHACL | 通过 | `semantic_validation.py` 合并 4 份本体与 2 份 Shape，对 2 份 Turtle 实例执行 RDFS + SHACL；自动化回归通过 |
| 3 | 建立业务流程、规则和代码实现切片 | 通过 | Requirement IR 生成 BusinessProcess、BusinessProcessStep、BusinessRule；Desired Graph 保存 `containsStep`/`nextStep`；确认 Alignment 后生成带图邻域和证据的 ImplementationSlice |
| 4 | 详细设计转换为 Requirement IR 和 Desired Graph | 通过 | Markdown/Front Matter 摄取、Document Hash、章节/行号证据、Explicit/Suggested/Unresolved 分类、Draft/Confirm Gate 和版本化 Desired Graph |
| 5 | 生成带证据、置信度和替代方案的对齐候选 | 通过 | 类型、词法、显式设计 Token 和实现建议评分；每个 Desired Entity 最多 5 个候选，保存分数分解、Evidence、Model Version；Confirm/Reject API |
| 6 | 自动计算 Current/Desired Semantic Diff | 通过 | 确认 Alignment 后确定性生成 Add/Modify Semantic Difference，绑定 Current、Desired、Alignment、Confidence 和 Evidence；Diff ID 与引擎版本稳定 |
| 7 | 生成覆盖全部工程层的变更提案 | 通过 | YAML 规则与 Generic Fallback 生成行为代码、API 契约、数据库、消息 Schema/Producer/Consumer、配置、测试和部署提案，同时生成兼容评估、Verification Obligation 和 Task DAG |
| 8 | 通过人工 Gate 形成 Approved Change | 通过 | Requirement、Alignment、Architecture、Security/Data 和 Change Approval 状态机；不能跳过架构评审；批准时固化 Allowed/Forbidden Files、Required Tests 并发布 Approved Graph |
| 9 | OpenCode Agent + Skill 在白名单内生成 Patch | 通过 | 持久化 Orchestrator 用真实 OpenCode 1.18.5 调度需求、代码图、规划、架构、实现和验证角色；`implementation-agent` 在 detached worktree 中生成白名单 Java 与测试 Patch |
| 10 | 阻止 Commit/Push/Merge/生产部署 | 通过 | OpenCode Inline Permission 最高优先级拒绝 Git 写操作、kubectl、helm、terraform；平台测试命令仅允许 Maven/Gradle；运行后验证 Worktree HEAD 等于 Base Commit，越界文件进入 PolicyViolation |
| 11 | 重新生成 Actual Graph 并进行对账 | 通过 | 完成的 Agent Run 回扫同一 worktree，发布 Actual Graph；对 Current/Actual 节点、关系和 Source Hash 求 Delta；逐 Proposal 和 Verification Obligation 分类 Conformed/Missing/Unexpected/Failed |
| 12 | 生成 Impact Graph、测试选择和发布建议 | 通过 | 从 Actual Delta 沿有类型的关系按衰减置信度传播 Direct/Propagated/Contained/Unresolved；选择受影响测试与批准命令；输出 Standard/Canary/Blocked、回滚触发器和人工 Release Gate |
| 13 | 事实、候选、规则、Agent 输出和人工决定可审计重放 | 通过 | Audit Event 带 Tenant、Actor、Correlation、Repository、Revision、前序 Hash 和 Event Hash；Replay Package 汇总持久化 Workflow、IR、Alignment、Plan、Reviews、Agent Artifacts、Reconciliation、Impact、Runtime Evidence 与所有引擎/规则版本 |

当前判定：

```text
通过       13 / 13
部分实现    0 / 13
未实现      0 / 13
```

## 3. 关键安全与失败语义

平台不会把“Agent 写了文件”等价为“实现完成”：

- OpenCode 进程超时会调用 Session Abort；
- 超时期间已经产生的 Patch 仍被捕获、计算 Hash 和校验路径，但 Run 状态为 `TimedOut`，不能进入 Reconciliation；
- Worktree HEAD 改变或文件越界时状态为 `PolicyViolation`，批准测试不会执行；
- 只有 `Completed + Path Policy Passed + Required Tests Passed` 才发布 Verify Context；
- Agent Run 完成后 Worktree 再次漂移会阻断 Actual Graph；
- Reconciliation 有 Missing、Unexpected、测试失败或抽取不完整时 Release Plan 为 `Blocked`；
- 生产 Runtime Evidence 必须引用未被阻断的 Release Plan、人工 Release Approval 和全部通过的 Verification Check；
- 配置和运行证据中的 password、secret、token 等字段只保存 Redaction 与 Value Hash。

## 4. 验证证据

自动化套件：

```bash
python3 -m ruff format src tests
python3 -m ruff check src tests
python3 -m unittest discover -s tests -v
cd web && npm ci && npm run build
npm audit --package-lock-only --audit-level=high
CODE_ONTOLOGY_API_TOKEN=validation-token REPOSITORY_ROOT=/tmp \
  docker compose -f deploy/docker-compose.yml config --quiet
```

最终复核结果：Python 格式与静态检查通过，19 项自动化测试全部通过；Web 生产构建成功，锁文件依赖审计为 0 漏洞；Compose 配置展开成功。CLI 复核中 4 份本体、2 份 Shape 和 2 份 RDF 实例全部 conform，Java/Spring 样例 9/9 文件解析成功并生成 72 个节点、95 条边、0 个未解析调用。

覆盖点包括：

- 真实 Java/Spring/Maven/Kafka/OpenAPI/SQL/配置/测试抽取；
- 版本漂移与敏感配置脱敏；
- Requirement IR、流程步骤、Desired Graph 和人工确认；
- 多候选 Alignment、ImplementationSlice、Semantic Diff 和全层 Proposal；
- 不可跳过的 Architecture/Security/Data Gate；
- detached worktree、HEAD 不变、文件白名单和命令白名单；
- 正常 Patch、越权 Patch、独立测试、Actual Graph、Reconciliation、Impact 和 Release Advice；
- Runtime Evidence 脱敏与生产阻断；
- 审计链完整性和 Requirement Replay Hash；
- HTTP Bearer Token、幂等冲突和图空间隔离；
- 任意双图 Compare、字段级 Diff 与快照 Revision 非语义漂移过滤；
- 多角色 Requirement Workflow、四个人工 Gate、失败阶段原地重试；
- 4 份本体、2 份 Shape、2 份 RDF 实例的 SHACL 一致性。

真实 OpenCode 全流程验收：

```text
OpenCode version:           1.18.5
requirement-analyst:        Completed
code-graph-analyst:         Completed
change-planner:             Completed
architecture-reviewer:      TimedOut → dedicated Skill retry → Completed
implementation-agent:       Completed
verification-agent:         Completed
Changed files:              PolicyService.java, PolicyServiceTest.java
Path policy / tests:        Passed / Passed
Worktree HEAD unchanged:    true
Actual / Reconciliation:    Generated / Deviated
Impact / Release advice:    Generated / Blocked + Human Gate
```

第一次架构复核复用了规划 Skill，在 Deadline 内没有结束；平台安全 Abort 并持久化
失败。拆分专用 `review-change-architecture` Skill 后，同一 Workflow 通过
`POST /api/requirement-workflows/{id}/retry` 只重试该阶段并继续完成。实现 Agent
随后生成受控 Patch，通过路径策略和测试；平台重新抽取 Actual Graph。确定性对账
识别到设计偏差，因此流程状态为 Completed，但发布建议保持 Blocked 并要求人工
Release Gate。这验证了“工作流执行完毕”与“允许发布”是两个不同状态。

## 5. 产品与部署

`web/` 提供 React + TypeScript 工作台：

- Graph Explorer 通过 Cytoscape.js 展示代码本体、业务本体、Desired、Proposed、
  Approved、Actual 和 Impact 七类版本化图空间；
- Graph Compare 支持任意两个图空间/Revision 的差异叠加、左右对照、字段 Diff、
  状态筛选和证据检查；
- Workflow Control 支持创建/装载完整需求流程、提交四类 Human Gate，以及从失败
  Agent 阶段原地重试；
- 支持图谱总览、实体/关系/关键字过滤、邻域与路径类查询以及节点/边证据检查；
- Requirement Trace 展示 Requirement→Alignment→Plan→Agent→Reconcile→Impact；
- 自包含只读 JSON Inspector 查看不可变 Artifact，不依赖外部 CDN；
- 显示 Audit Chain、Replay Hash、阶段状态与 Human/Machine Events；
- API Token 只保存在当前浏览器内存。

`Dockerfile` 和 `deploy/docker-compose.yml` 提供 API、工作台、SQLite 持久卷和 OpenCode 运行时的单节点容器部署。当前验证环境没有运行中的 Docker daemon，因此完成了 Dockerfile/Compose 静态检查和 Web 生产构建，未声称已在本机启动容器。

真实浏览器像素级验收受当前 WSL 宿主限制：应用内浏览器连接器不能接受包含中文的 WSL 工作区 URI，Playwright WebKit 又缺少宿主 GUI 动态库。已完成七类真实图快照的 HTTP 查询、静态入口、指纹资源、CSP、安全响应头和前端生产构建检查，但不把这些替代项误报为像素级浏览器验收。前端构建仍有主 Chunk 的性能提示，属于后续代码分包优化项。

## 6. 生产化边界

以下不是第 31 章功能验收缺口，但在企业生产前必须继续：

1. 将 SQLite Adapter 替换为 PostgreSQL，把 RDF 投影到 Fuseki/TDB2，把大图遍历投影到 Neo4j；
2. 把同步抽取、Agent 和分析调用迁移到可恢复队列与隔离 Worker/Job；
3. 使用 OIDC/RBAC、密钥托管、Tenant 强隔离和审批职责分离；
4. 增加对象存储、Artifact 保留策略、审计导出和灾难恢复；
5. 增加大仓库性能基准、增量抽取、编译器 Binding Resolution 和跨仓库解析；
6. 通过 Kubernetes NetworkPolicy、seccomp/AppArmor 和无特权沙箱强化 Agent 进程边界；
7. 接入真实 CI、Staging 和 Production Deployment/Runtime Connector。

这份边界说明防止把“功能完整的参考平台”误写成“已经生产规模化上线的平台”。
