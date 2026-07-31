# 图谱文本快照与预期基线

## 1. 目标

平台中的 Current、Business、Desired、Proposed、Approved、Actual 和 Impact 图不能
只存在于数据库中。每次图发布必须同时形成：

1. SQLite 中可查询的实体、关系和元数据；
2. 文件系统中可阅读、可归档、可计算 Hash 的 JSON 文本快照；
3. 对示例代码库可跨机器、跨 Commit 比较的预期语义图基线。

精确文本快照和预期基线用途不同，不能混为一类：

- 精确快照保存某次发布的完整事实，包括 Revision 和发布 Metadata；
- 预期基线排除 Revision、时间戳、绝对路径和 Git Checkout 状态，只保存应稳定的
  代码语义。

## 2. 精确文本快照

`SQLiteStore.replace_graph` 是所有图空间的统一发布入口。它在数据库写入之外生成：

```text
<graph-text-root>/
└── <graph-space>/
    └── <readable-revision>--<revision-hash>.graph.json
```

默认 `graph-text-root` 为 `<database-stem>.graphs`，例如：

```text
data/code-ontology.db
data/code-ontology.graphs/current/main--a1b2c3d4.graph.json
```

可以设置：

```bash
export CODE_ONTOLOGY_GRAPH_TEXT_ROOT=/var/lib/code-ontology/graphs
```

文本格式：

```json
{
  "schemaVersion": "code-ontology-graph-snapshot/v1",
  "graphSpace": "current",
  "revision": "commit-or-workspace-revision",
  "metadata": {},
  "summary": {
    "nodeCount": 72,
    "edgeCount": 95
  },
  "nodes": [],
  "edges": [],
  "contentHash": "sha256:..."
}
```

节点按 `id` 排序，关系按 `source/relation/target` 排序。同一输入不受调用方列表顺序
影响。写文件使用同目录临时文件、`fsync` 和原子替换；读取时重新计算 Hash，损坏
或人工篡改会被拒绝。

`GET /api/graphs` 的 Revision Metadata 包含：

```json
{
  "textSnapshot": {
    "format": "application/json",
    "schemaVersion": "code-ontology-graph-snapshot/v1",
    "relativePath": "current/...",
    "contentHash": "sha256:..."
  }
}
```

## 3. 示例预期图谱

仓库提交以下基线：

```text
examples/expected-graphs/java-spring-sample.current.graph.json
examples/expected-graphs/java-spring-sample.codegraph-1.5.0.graph.json
examples/expected-graphs/java-spring-sample.codegraph-1.5.0.comparison.json
```

当前基线覆盖：

```text
Repository: repo-sdn-sample
Nodes:      72
Edges:      95
Java:       9 / 9 parsed
Calls:      0 unresolved
```

基线保留类、方法、字段、调用、API、Schema、数据库、配置、消息、测试和构建依赖，
但删除下列环境噪声：

```text
revision / revisionId
createdAt / updatedAt / scannedAt
absolutePath / workspacePath
Repository branch / remote / dirty
绝对 path
```

源文件 Hash、相对证据位置和业务属性仍保留，因此真实代码变化会导致漂移。

CodeGraph 快照是使用 1.5.0 对同一示例执行真实索引得到的 66 节点、70 关系结果；
Comparison 文件保存它与平台 72/95 语义基线的稳定节点映射、类型覆盖、关系覆盖和
差异清单。它们用于验证 Sidecar 适配器和模型边界，不替代平台预期语义图。

## 4. CLI

生成或显式更新基线：

```bash
code-ontology-platform baseline generate \
  examples/java-spring-sample \
  examples/expected-graphs/java-spring-sample.current.graph.json \
  --repository-id repo-sdn-sample
```

只比较、不写数据库：

```bash
code-ontology-platform baseline compare \
  examples/java-spring-sample \
  examples/expected-graphs/java-spring-sample.current.graph.json
```

扫描、发布 Current Graph 并同时比较：

```bash
code-ontology-platform scan examples/java-spring-sample \
  --repository-id repo-sdn-sample \
  --expected-graph examples/expected-graphs/java-spring-sample.current.graph.json
```

匹配时退出码为 `0`，漂移时退出码为 `1`。结构化结果分别统计 Nodes 和 Edges 的
Added、Removed、Modified、Unchanged，并返回字段级变化。

## 5. 基线更新规则

预期基线不是每次测试自动覆盖的 Golden File。只有确认以下条件后才允许执行
`baseline generate` 并提交新文件：

1. 示例源码变化是预期需求；
2. 抽取器 Schema 或语义发生受评审的版本变化；
3. Diff 中新增、删除和修改的实体关系均已人工确认；
4. 自动化比较和全量平台测试通过。

这样可以避免抽取器回归通过“自动更新预期结果”被掩盖。
