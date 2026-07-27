# 可执行 Agent Gateway 与规划规则 MVP

> 历史阶段文档：本文件记录最初纵向切片，不再代表当前实现边界。完整实现与最新验收证据见 [完整智能平台符合性审计](23-complete-platform-compliance-audit.md)。

## 1. 文档梳理结论

现有设计已经完整定义了长期平台的语义边界和七阶段建设路线，仓库也已包含本体、SHACL、规划规则、OpenCode Agent、Skill 和工具声明。实现前的主要缺口不是模型，而是工具声明所依赖的运行时：

- `.opencode/tools/ontology.ts` 调用的 HTTP API 尚不存在；
- Current、Desired、Proposed、Approved、Actual、Impact 图空间没有可执行的隔离层；
- Candidate 和 Draft 写入没有状态守卫、Schema 校验、幂等和审计；
- `requirement-change-planning-rules.yaml` 只有规则声明，没有确定性执行器；
- 没有可运行示例和自动化测试。

本次实现选择一个跨越阶段四和阶段五的纵向切片，先让现有 Agent/Skill/Tool 契约真正可运行。完整 Java 21、Jena、Neo4j、PostgreSQL 生产架构保持不变；当前 Python/SQLite 实现是接口兼容、可测试的参考运行时，用于在引入重型基础设施前验证领域约束。

## 2. 已实现能力

代码位于 `src/code_ontology_platform/`，包含：

```text
HTTP API
  → 请求边界、错误模型、大小限制、Correlation ID

Platform Service
  → Stage/GraphSpace/QueryType 白名单
  → Candidate/Draft 状态守卫
  → Artifact 输出契约校验

SQLite Store
  → 阶段化 Requirement Context
  → 六类图空间的版本快照
  → Agent Artifact
  → Idempotency Record
  → Audit Event

Planning Rules
  → YAML 规则加载和自校验
  → Semantic Difference 精确匹配
  → Proposal、Assessment、Alignment Search 和人工 Gate 展开

Semantic Validation
  → Turtle 语法解析
  → 合并本体和 Shape
  → 对每个示例执行 RDFS + SHACL 校验
```

关键设计约束已落到代码：

1. 图查询必须指定 GraphSpace，只读取该空间和 Revision；
2. QueryType 使用固定枚举，遍历深度最多 6，节点最多 500；
3. Agent 写接口只能创建 `Candidate`、`Draft` 或只读审计 Artifact；
4. 同一写接口和 Idempotency-Key 的相同请求返回原结果；
5. 同一 Idempotency-Key 的不同请求返回 409，不能覆盖原 Artifact；
6. Context 精确绑定 Requirement、DesignRevision 和 Stage，并生成 `contextHash`；
7. 规则提案 ID 由规则版本、规则 ID、Difference ID 和序号确定性生成；
8. 缺少必要设计属性、触发兼容条件或存在架构决策时自动进入人工 Gate。

## 3. API 契约

已实现 `.opencode/tools/ontology.ts` 使用的接口：

```http
GET  /api/agent-context/requirements/{requirementId}
POST /api/agent-context/graph-query
POST /api/alignments/agent-candidates
POST /api/change-plans/agent-drafts
GET  /api/reconciliation-runs/{runId}/agent-context
POST /api/agent-artifacts
```

同时提供：

```http
GET  /api/agent-runs/{runId}/artifacts
POST /api/change-plans/expand
GET  /health
```

写接口必须携带长度至少为 8 的 `Idempotency-Key`。服务会返回 `X-Correlation-ID`；幂等重放还会返回 `X-Idempotent-Replay: true`。

## 4. 本地运行

要求 Python 3.11+。

```bash
python3 -m venv .venv
.venv/bin/pip install -e .

code-ontology-platform init
code-ontology-platform seed examples/agent-gateway-seed.json
code-ontology-platform plan examples/api-field-difference.json
code-ontology-platform validate
code-ontology-platform serve
```

不安装包也可以直接运行：

```bash
PYTHONPATH=src python3 -m code_ontology_platform init
PYTHONPATH=src python3 -m code_ontology_platform \
  seed examples/agent-gateway-seed.json
PYTHONPATH=src python3 -m code_ontology_platform validate
PYTHONPATH=src python3 -m code_ontology_platform serve
```

默认监听 `127.0.0.1:8080`，与 `.opencode/tools/ontology.ts` 的默认地址一致。数据库默认写入 `data/code-ontology.db`，可通过 `--database` 或 `CODE_ONTOLOGY_DB` 修改；规则路径可通过 `--rules` 或 `CODE_ONTOLOGY_RULES` 修改。

设置 `CODE_ONTOLOGY_API_TOKEN` 后，除 `/health` 外的 API 都要求 `Authorization: Bearer <token>`。该环境变量与 `.opencode/tools/ontology.ts` 已有的 Token 支持直接对应。

## 5. 验证

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

测试覆盖：

- Context 的 Requirement/Revision/Stage 精确隔离；
- Current 与 Desired 图空间不串读；
- CALL_PATH 的有向、限深查询；
- Candidate Artifact 幂等重放；
- Idempotency-Key 冲突拒绝；
- Draft 接口不能越权写入 Approved 状态；
- API 字段变化的规则展开和人工 Gate；
- 四份本体、两份 Shape 和两份 Turtle 示例的解析与 SHACL 一致性；
- 可选 Bearer Token 保护；
- OpenCode `requirement_context` 的真实 HTTP 契约。

## 6. 当前边界与后续主线

这个切片不伪装成最终生产平台。以下能力仍按正式路线图继续演进：

- 编译器级 Java/Spring、Schema、数据库、配置和部署 Extractor；
- Jena/TDB2 的 RDF、SHACL、Named Graph 和 RDFS；
- Neo4j 图投影及大规模路径预算；
- 文档摄取、Requirement IR 自动提取和实体解析；
- 审批工作流、权限模型和隔离 Worktree；
- Actual Graph 重新抽取、设计实现对账、影响和发布计划；
- PostgreSQL、对象存储、消息任务和生产可观测性。

当前接口层和领域约束可以直接作为后续 Java/Spring 模块的验收契约，SQLite Store 则替换为 PostgreSQL、Jena 和 Neo4j Adapter，不改变 Agent 工具调用方式。
