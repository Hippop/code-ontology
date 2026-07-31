# MCP 代码图谱 Server

## 1. 定位

本项目提供一个本地优先、只读的 MCP 代码图谱 Server。它参考
[CodeGraph](https://github.com/colbymchenry/codegraph) 的“一次探索返回源码上下文
和影响面”设计，以及 [GitNexus](https://github.com/nxpatterns/gitnexus) 的多仓库、
Context、Process、Community、变更检测、资源和 Prompt 设计，但继续使用本项目的
七图空间、业务语义、契约、数据库、配置、测试和需求变更模型。

两类图各司其职：

```text
平台 Current / Business / Desired / Proposed / Approved / Actual / Impact Graph
→ 业务、契约、数据、配置、测试、需求和变更事实

CodeGraph Sidecar
→ 多语言源码符号、源码探索、调用影响和受影响测试

只读 MCP Server
→ 把两类能力统一暴露给 Codex、Claude Code、Cursor 和 OpenCode
```

MCP 不提供扫描、索引、改码、审批、提交或部署工具。扫描和索引必须由人或 CI
显式执行。

## 2. 首次准备

```bash
python3 -m venv .venv
.venv/bin/pip install -e .

.venv/bin/code-ontology-platform \
  --database data/code-ontology.db \
  scan /absolute/path/to/repository \
  --repository-id repo-example

# 可选；启用 codegraph_explore、codegraph_impact 和 affected_tests
.venv/bin/code-ontology-platform \
  --database data/code-ontology.db \
  codegraph index /absolute/path/to/repository \
  --repository-id repo-example

.venv/bin/code-ontology-platform \
  --database data/code-ontology.db \
  doctor
```

同一个数据库可以连续注册和扫描多个仓库。多仓库查询应传 `repositoryId`，以绑定
到该仓库最新的 Current Graph Revision。

## 3. stdio 接入

stdio 是本地 Agent 的推荐接入方式：

```bash
/absolute/path/to/.venv/bin/code-ontology-platform \
  --database /absolute/path/to/data/code-ontology.db \
  --rules /absolute/path/to/rules/requirement-change-planning-rules.yaml \
  mcp
```

Codex CLI：

```bash
codex mcp add code-ontology -- \
  /absolute/path/to/.venv/bin/code-ontology-platform \
  --database /absolute/path/to/data/code-ontology.db \
  --rules /absolute/path/to/rules/requirement-change-planning-rules.yaml \
  mcp
```

Codex 项目级 `.codex/config.toml` 或用户级 `~/.codex/config.toml`：

```toml
[mcp_servers.code_ontology]
command = "/absolute/path/to/.venv/bin/code-ontology-platform"
args = [
  "--database",
  "/absolute/path/to/data/code-ontology.db",
  "--rules",
  "/absolute/path/to/rules/requirement-change-planning-rules.yaml",
  "mcp",
]
startup_timeout_sec = 30
tool_timeout_sec = 120
required = true
```

Codex 的 `command`、`args`、`startup_timeout_sec`、`tool_timeout_sec` 和 `required`
字段来自[官方配置参考](https://developers.openai.com/codex/config-reference)。

Cursor 或 Claude Desktop/Code 的 JSON 配置：

```json
{
  "mcpServers": {
    "code-ontology": {
      "command": "/absolute/path/to/.venv/bin/code-ontology-platform",
      "args": [
        "--database",
        "/absolute/path/to/data/code-ontology.db",
        "--rules",
        "/absolute/path/to/rules/requirement-change-planning-rules.yaml",
        "mcp"
      ]
    }
  }
}
```

OpenCode：

```json
{
  "mcp": {
    "code-ontology": {
      "type": "local",
      "command": [
        "/absolute/path/to/.venv/bin/code-ontology-platform",
        "--database",
        "/absolute/path/to/data/code-ontology.db",
        "--rules",
        "/absolute/path/to/rules/requirement-change-planning-rules.yaml",
        "mcp"
      ]
    }
  }
}
```

## 4. Streamable HTTP 接入

```bash
CODE_ONTOLOGY_API_TOKEN='replace-me' \
.venv/bin/code-ontology-platform \
  --database data/code-ontology.db \
  serve --host 127.0.0.1 --port 8080
```

MCP Endpoint 为 `http://127.0.0.1:8080/mcp`。Codex 可配置：

```bash
codex mcp add code-ontology-http \
  --url http://127.0.0.1:8080/mcp \
  --bearer-token-env-var CODE_ONTOLOGY_API_TOKEN
```

HTTP 实现校验 `Origin` 防止 DNS Rebinding，复用 REST Bearer Token，并支持当前
MCP `2025-11-25` 及前两版协议。无状态 Server 不建立 Session，也不提供 GET/SSE。

## 5. MCP 工具

| 工具 | 用途 |
|---|---|
| `list_repositories` | 发现已注册仓库 |
| `repository_context` | 仓库身份、Revision、索引新鲜度和能力 |
| `symbol_context` | 混合搜索加首选实体 360 度邻域 |
| `detect_changes` | Git Diff 到实体、流程和测试的映射 |
| `trace` | 两个实体之间的有向调用路径 |
| `graph_query` | 受控图概览、邻域、调用链、数据和影响查询 |
| `hybrid_search` | BM25、确定性语义向量、中心度和 RRF |
| `codegraph_explore` | CodeGraph 一次式源码探索 |
| `codegraph_impact` | CodeGraph 符号影响范围 |
| `affected_tests` | CodeGraph 受影响测试 |
| `index_status` | CodeGraph 索引新鲜度和 Provenance |
| `communities` | 确定性功能社区 |
| `processes` | API、事件和测试入口流程 |
| `contract_graph` | 跨仓 HTTP、事件和 Schema 契约 |

每个工具的 `inputSchema` 都设置 `additionalProperties=false`，Server 会在调用前做
类型、枚举、范围和必填字段校验。所有工具支持可选 `maxTokens`，按四个 UTF-8
字节约等于一个 Token 的确定性预算压缩超大结果，同时保持合法 JSON。

## 6. Resources 和 Prompts

固定资源：

```text
code-ontology://setup
code-ontology://repositories
code-ontology://graphs
code-ontology://schema
```

仓库资源模板：

```text
code-ontology://repositories/{repositoryId}/context
code-ontology://repositories/{repositoryId}/communities
code-ontology://repositories/{repositoryId}/processes
```

Prompt：

```text
detect_impact
generate_map
```

Agent 的推荐入口是先读 `code-ontology://setup` 和
`code-ontology://repositories`，再按仓库读取 Context。

## 7. 五轮优化结果

1. 增加可被主流 Agent 直接启动的 stdio MCP，同时保留 Streamable HTTP。
2. 增加多仓库发现、仓库 Revision 作用域、Context、Trace 和跨仓资源。
3. 增加 Git 变更映射、输入 Schema 校验、Token 预算、并发索引锁和路径安全。
4. 增加资源模板、Prompts、Doctor、客户端配置和接入说明。
5. 用协议、服务、HTTP、图分析、变更检测和完整平台回归进行最终审计。
