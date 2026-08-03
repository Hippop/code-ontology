# 本地 Codex 需求到代码图谱闭环

## 目标与结论

平台同时支持本地 Codex CLI 和 OpenCode。`auto` 模式优先选择已安装的
Codex，容器内没有 Codex 时继续使用已打包的 OpenCode。两种运行时共用同一套
Requirement IR、图空间、人工 Gate、受控 Worktree、Patch、测试、Actual Graph、
Reconciliation、Impact 和审计协议。

本地 Codex 使用官方的非交互 `codex exec` JSONL 模式。平台通过 stdin 传入提示，
启用 ephemeral session，固定 `approval_policy=never`，并忽略用户级配置，避免
无关 Connector、MCP 或个人指令进入受控运行。命令契约参考
[Codex non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode)。

## 运行时选择

```bash
export CODE_ONTOLOGY_AGENT_RUNTIME=auto
# 可选：codex 或 opencode

export CODEX_BINARY=/absolute/path/to/codex
export CODE_ONTOLOGY_CODEX_MODEL=optional-model-name
export CODE_ONTOLOGY_CODEX_SANDBOX=workspace-write

code-ontology-platform doctor
```

`doctor` 的 `agentRuntime` 会返回运行时、可用性、二进制、版本、Sandbox 和
JSONL API 版本。`auto` 的选择顺序是 Codex、OpenCode；两者都不存在时仍返回
Codex Adapter，并在真正执行时给出 `CODEX_UNAVAILABLE`，不会静默使用测试替身。

实际 Codex 子进程等价于：

```text
codex exec
  --ignore-user-config
  --ephemeral
  --sandbox <mode>
  -c approval_policy="never"
  --json
  -
```

## 安全边界

- requirement、graph、planning、architecture 和 verification 五个只读角色各自
  使用一次性 detached Git Worktree；任何文件或 HEAD 变化都会使结果被拒绝，
  随后强制清理隔离目录。
- implementation 只在平台创建的独立 Worktree 中运行。完成后平台重新计算
  binary patch 和 patch hash，验证 HEAD、文件白名单、禁止路径和 Maven/Gradle
  测试。
- 未跟踪的 `.gradle/`、`build/`、`out/`、`target/` 只被排除出补丁输入；
  同名的已跟踪文件仍参与差异，不会被隐藏。
- Codex 不获得交互批准。提示还禁止 Web、Connector、子 Agent、Commit、Push、
  Merge、Rebase、Tag 和部署。
- 只有 Requirement、Alignment、Architecture 和 Change Approval 四个人工 Gate
  可以放行对应状态。发布始终保留人工 release gate。

在部分 WSL 环境中，Codex 的 `workspace-write` 依赖的 `bwrap` 可能不存在。
默认仍应使用 `workspace-write`。只有在一次性仓库、受控 Worktree、无生产凭据
且调用方明确承担风险时，才可临时选择 `danger-full-access`；平台的路径和 Patch
校验不是操作系统 Sandbox 的替代品。

## 完整运行

脚本默认停在第一个人工 Gate。只有显式传入 `--approve-gates` 才会为演示模拟
四次人工决定：

```bash
python3 scripts/run_codex_requirement_workflow.py \
  --repository /absolute/path/to/clean/repository \
  --design examples/designs/sdn-minimum-bandwidth.md \
  --database /tmp/code-ontology-workflow.db \
  --worktree-root /tmp/code-ontology-worktrees \
  --rules rules/requirement-change-planning-rules.yaml \
  --workflow-id sdn-codex-e2e \
  --approve-gates \
  --required-test "mvn test" \
  --report /tmp/code-ontology-workflow-report.json
```

脚本会先验证 repository、design 和 rules 路径。最终报告包含所有状态机步骤、
角色运行时、实现 Worktree、Changed Files、Patch Hash、路径策略、测试报告、
Reconciliation、Impact 和审计链；失败时也包含 `error` 与 `nextActions`。

## 五轮优化证据

| 轮次 | 真实运行发现 | 修正 |
| --- | --- | --- |
| 1 | 本地 Codex 需要稳定的无交互协议和只读隔离 | JSONL Adapter、stdin prompt、ephemeral、忽略用户配置、detached Worktree |
| 2 | Maven 生成的 `target/` 使 Agent 完成后的 Patch Hash 漂移；失败时 agentRunId 未及时持久化 | 仅过滤未跟踪构建产物；Implementation/Reconciliation 分阶段持久化和可重试 |
| 3 | “不新增数据库表”被反向抽成迁移需求；Agent 看不到 proposal 对应的需求原文 | 非变更语句进入 scope；proposal 携带 desiredEntity、需求范围和逐项状态契约 |
| 4 | 已通过的验收测试、消息 Schema 和消息契约测试仍被误报；粒度子节点被视为意外变更 | obligation 关联、design token 匹配、changed-node 图关系闭包和显式 claimCoverage |
| 5 | 部署动作被错误要求出现在代码图；删除签名被当成 Unresolved；平行关系产生重复 Impact Edge | DeferredToReleaseGate、Removed 直接影响、Impact Edge 合并并保留 sourceRelations |

最终独立运行 `sdn-codex-final-e2e` 的持久化结果：

- 六个角色全部由本地 Codex 完成；
- implementation 修改 17 个批准路径内文件，Maven 6 个测试通过；
- 路径策略通过，源仓库保持干净；
- Reconciliation 为 `Conformed`：18 个 proposal 为 `Conformed`，2 个部署
  proposal 为 `DeferredToReleaseGate`，0 deviations；
- Impact 为 140 Direct、18 Propagated、13 Contained、0 Unresolved；
- Release Decision 为 `Canary / High`，继续要求人工 release gate；
- 失败阶段通过正式 `RetryFailedStage` 恢复，审计事件和资源 ID 保持连续。

最终仓库回归还验证了：

- Python、MCP、HTTP、Codex Adapter、状态机和图谱分析共 40 个测试全部通过；
- Java/Spring 样例在 Java 17 和 Spring Boot 4.1.0 下完成 Maven 构建；
- Java 抽取器 0.2.0 生成 71 nodes、97 edges、0 unresolved calls，图谱基线
  `Matched`；
- TypeScript 类型检查、Vite 生产构建以及 RDF/SHACL 全部通过；
- 持久化端到端运行的审计链为 `Verified`，40 个事件、0 failures。

## 与 MCP 图谱工具的关系

Codex/OpenCode 负责角色执行；MCP 只提供图谱事实读取。可通过 stdio：

```bash
code-ontology-platform mcp
```

或 Streamable HTTP：

```text
POST http://127.0.0.1:8080/mcp
Authorization: Bearer <CODE_ONTOLOGY_API_TOKEN>
```

MCP 暴露图谱概览、符号探索、影响、受影响测试、混合检索、社区、流程、跨仓契约
和索引新鲜度等只读工具。它不允许索引、审批、改码或提交，因此可以接入 Codex、
OpenCode 和其他 MCP Client，而不扩大写权限。
