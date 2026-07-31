# CodeGraph Sidecar 与图智能增强

## 1. 边界和取舍

本实现把 [CodeGraph](https://github.com/colbymchenry/codegraph) 作为可替换的只读
Sidecar，而不是平台事实模型的唯一来源。CodeGraph 1.5.0 负责源码符号、引用、
调用、探索、符号影响和受影响测试；平台扫描器继续负责 Java/Spring、OpenAPI、
数据库、配置、消息、构建依赖、业务图和需求变更图。

[GitNexus](https://github.com/nxpatterns/gitnexus) 的混合检索、Community、
Process 和跨仓契约思路由本项目独立实现，没有复制其源码。这样既保留适合当前
产品的图智能能力，也不把 PolyForm Noncommercial 代码引入可商用核心。CodeGraph
为 MIT License，容器固定安装 `@colbymchenry/codegraph@1.5.0`。

可观测性、指标、Tracing 和告警不属于本轮范围。

## 2. Java 示例的真实对比

在 Node 24.18.1、CodeGraph 1.5.0 上对
`examples/java-spring-sample` 的真实索引结果为：

| 模型 | 节点 | 关系 |
|---|---:|---:|
| 平台预期 Current Graph | 72 | 95 |
| CodeGraph 1.5.0 | 66 | 70 |
| 数量差 | -6 | -25 |

数量接近不代表模型等价。稳定 ID、类型和证据归一后，35 个平台节点能与 35 个
CodeGraph 节点对齐，覆盖平台预期节点的 48.61%；24 条平台关系能语义对齐，
覆盖预期关系的 25.26%。

CodeGraph 的优势是 Namespace、Import、源码符号、引用和调用；平台多出的重点是
Parameter、Maven Artifact、配置、OpenAPI Schema、表/列、事件和业务/变更语义。
因此 Sidecar 只能补充探索和影响证据，不能替换平台的 Current Graph。

固定验收资产：

```text
examples/expected-graphs/
├── java-spring-sample.current.graph.json
├── java-spring-sample.codegraph-1.5.0.graph.json
└── java-spring-sample.codegraph-1.5.0.comparison.json
```

重新生成真实 CodeGraph 基线：

```bash
python3 scripts/generate_codegraph_baseline.py \
  <带 .codegraph/codegraph.db 的示例仓库> \
  examples/expected-graphs/java-spring-sample.current.graph.json \
  examples/expected-graphs/java-spring-sample.codegraph-1.5.0.graph.json \
  examples/expected-graphs/java-spring-sample.codegraph-1.5.0.comparison.json
```

## 3. Sidecar 接口

CLI：

```bash
code-ontology-platform codegraph index <repository>
code-ontology-platform codegraph status <repository>
code-ontology-platform codegraph explore <repository> "PolicyService deploy"
code-ontology-platform codegraph impact <repository> PolicyService --depth 3
code-ontology-platform codegraph affected <repository> \
  src/main/java/org/example/sdn/PolicyService.java
code-ontology-platform codegraph compare <repository> \
  examples/expected-graphs/java-spring-sample.current.graph.json
```

默认命令为 `codegraph`，可通过
`CODE_ONTOLOGY_CODEGRAPH_COMMAND` 指定完整命令。子进程使用参数列表执行，不经过
Shell。查询接口只读；只有显式 `index` 会更新仓库内的 `.codegraph` 索引。

REST：

```text
POST /api/repositories/{repositoryId}/codegraph/index
GET  /api/repositories/{repositoryId}/codegraph/status
POST /api/repositories/{repositoryId}/codegraph/explore
POST /api/repositories/{repositoryId}/codegraph/impact
POST /api/repositories/{repositoryId}/codegraph/affected-tests
POST /api/repositories/{repositoryId}/codegraph/compare
```

## 4. 索引陈旧协议

每次索引记录 Provider、版本、Repository Revision、索引路径、文件 Manifest
Fingerprint、文件数和更新时间。状态计算比较：

```text
CodeGraph files.content_hash
↔ 当前仓库对应文件 SHA-256
↔ 已记录 Repository Revision
```

状态：

- `Missing`：没有 `.codegraph/codegraph.db`；
- `Fresh`：索引文件内容和 Repository Revision 一致；
- `Stale`：存在变更、删除、新增的受支持文件，或 Revision 已变化；
- 索引损坏、命令不可用和超时使用独立错误码。

`explore`、`impact`、`affected-tests` 和图快照默认在 `Stale` 时返回
`409 CODE_INDEX_STALE`。只有调用方显式传入 `allowStale: true` 才可读取，并且
响应仍携带完整 Index Provenance。MCP 默认不绕过该保护。

索引完成后还会把 CodeGraph 的完整 Nodes/Edges 以
`codegraph-snapshot/v1` 写入 `CODE_ONTOLOGY_GRAPH_TEXT_ROOT/codegraph/`。文本按
稳定 ID 排序并保存内容 Hash；索引状态记录该文件的相对路径和 Hash。因此 Sidecar
图同样不是只留在 `.codegraph/codegraph.db`。

## 5. 只读 MCP Gateway

`code-ontology-platform mcp` 实现 stdio JSON-RPC，`POST /mcp` 实现无状态
Streamable HTTP JSON-RPC。当前协议版本为 `2025-11-25`，同时兼容
`2025-06-18` 和 `2025-03-26`。Server 支持 `initialize`、`ping`、
`tools/list`、`tools/call`、Resources、Resource Templates 和 Prompts。HTTP
通知返回 202。

只读工具：

```text
list_repositories
repository_context
symbol_context
detect_changes
trace
graph_query
hybrid_search
codegraph_explore
codegraph_impact
affected_tests
index_status
communities
processes
contract_graph
```

所有工具声明 `readOnlyHint=true`、`destructiveHint=false` 和
`idempotentHint=true`。索引、草案写入、审批、代码编辑、提交和部署均不进入 MCP
工具面。Gateway 复用 REST Bearer Token，并校验 `Origin` 必须与 `Host` 匹配；
额外可信 Origin 通过 `CODE_ONTOLOGY_ALLOWED_ORIGINS` 配置。无状态服务不提供
GET/SSE。完整接入配置见
[MCP 代码图谱 Server](27-mcp-code-graph-server.md)。

## 6. 独立图智能算法

### 6.1 混合检索

`POST /api/graph-analysis/hybrid-search` 融合：

1. 节点属性 BM25；
2. 标识符 Token 与字符三元组的确定性 Feature Hashing Cosine；
3. 节点度中心性；
4. Weighted Reciprocal Rank Fusion。

实现不依赖外部 Embedding 服务，同一图和查询得到稳定排序，并返回每种分数和命中
字段。未来可把语义通道替换成正式 Embedding，而不改变返回契约。

### 6.2 Community

`POST /api/graph-analysis/communities` 使用按关系语义加权的确定性局部模块度移动。
调用、实现、事件关系权重大于声明和容器关系。社区 ID 由稳定成员 ID 计算，结果
包含成员、关键字、内部/边界关系、凝聚度和跨社区关系。

### 6.3 Process

`POST /api/graph-analysis/processes` 从 `APIOperation`、`EventType` 和测试节点开始
有界遍历。API 反向找到 `implementsOperation` 方法，事件反向找到消费者，测试从
`verifies` 进入被测行为；随后沿调用、数据、配置、表读写和 Payload 关系展开。
每个步骤保留来源关系和 Community ID，能够标记跨社区流程。

### 6.4 跨仓 Contract Graph

`POST /api/graph-analysis/contracts` 聚合各仓库最新 Current Graph，以
HTTP Method/Path、Event Channel 和 Schema Name 形成稳定契约键，再连接 Provider
与 Consumer。结果包含契约定义、仓库 Revision、使用证据和跨仓链接。Current
Graph Metadata 现在显式保存 `repositoryId`，避免跨仓聚合时依赖节点 ID 猜测。

## 7. 结论

最终职责划分：

```text
CodeGraph Sidecar
→ 快速源码探索、符号影响、受影响测试、额外引用证据

平台 Current / Business / Change / Actual / Impact Graph
→ 完整业务、契约、数据、配置、构建、需求和变更事实

平台图智能层
→ 混合检索、社区、流程、跨仓契约

只读 MCP Gateway
→ 向 Agent 暴露受控查询，不暴露写操作
```
