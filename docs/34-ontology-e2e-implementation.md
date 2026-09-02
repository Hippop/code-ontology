# 本体驱动需求到代码闭环：可执行实现

## 实现范围

本仓库现在提供一条可执行参考链：

```text
Design Document
→ Requirement IR
→ EngineeringRequirement / Capability / Contract / Verification Objective
→ Desired + Business Engineering Graph
→ Alignment + Change Plan + typed Engineering Context
→ Human Gates
→ isolated Agent code generation
→ deterministic Contract code generation
→ Working Tree Snapshot
→ ActualChangeSet + ActualImpactGraph
→ Plan/Actual Reconciliation + Verification Coverage
→ snapshot-bound Commit Gate
→ Actual Graph + Release Advice + Audit Replay
```

平台仍不执行 Git Commit、Push、Merge 或生产发布；Commit Gate 和 Release Gate
只返回受版本和证据约束的决定。

## 已落地模块

| 模块 | 作用 |
| --- | --- |
| `engineering_workflow.py` | Requirement IR 自动物化为 Capability、EngineeringRequirement、Contract、SemanticContract 和 Verification Objective |
| `engineering_semantics.py` | 所有权校验、三维 Coverage、白名单 Context 和 typed impact |
| `ontology_codegen.py` | 从 Requirement-owned generation contract 生成确定性、可编译、路径安全的 Python Artifact |
| `precommit_verification.py` | 完整 Working Tree Snapshot、ActualChangeSet、Impact Obligation、双向对账和 Commit Gate |
| `mcp_gateway.py` | 在统一只读 MCP 中暴露 engineering validate / coverage / collect / impact |
| `models/code-ontology.engineering-model.json` | 当前平台自身的工程语义模型 |
| `generated/engineering_registry.py` | 从当前项目自模型实际生成的 Requirement Registry |

Verification Evidence 采用生命周期约束：Planned Verification 可以尚无执行证据，
状态进入 Executed / Completed / Passed / Failed 后必须关联 Evidence；Evidence 必须
继续指向可审计 Artifact。

## 当前项目自模型

自模型覆盖 10 个核心 Capability / leaf Engineering Requirement：

1. Repository Fact Ingestion；
2. Graph Intelligence and Impact Analysis；
3. Semantic Governance；
4. Requirement Change Planning；
5. Governed Agent Execution；
6. Ontology-driven Code Generation；
7. Pre-commit Completeness Verification；
8. HTTP、MCP 和 Graph Workbench Access；
9. Implementation Reconciliation and Release Verification；
10. Audit and Requirement Replay。

模型把这些需求连接到 Requirement Contract、共享 Semantic Contract、实现模块、
Verification Objective、Test Verification、执行 Evidence 和测试 Artifact。

模型校验：

```bash
code-ontology-engineering validate models/code-ontology.engineering-model.json
code-ontology-engineering coverage models/code-ontology.engineering-model.json
```

当前基线：10/10 leaf Requirement 有实现，10/10 有验证，10/10 Verification Method
有 Evidence，三项 Coverage 均为 1.0。

## 代码生成

Dry run 默认不修改工作区：

```bash
code-ontology-generate \
  models/code-ontology.engineering-model.json \
  --output .
```

显式应用生成结果：

```bash
code-ontology-generate \
  models/code-ontology.engineering-model.json \
  --output . \
  --apply
```

生成器支持：

- `python-engineering-registry`；
- `python-dataclass`；
- `python-protocol`。

每个生成任务必须由唯一 Engineering Requirement 拥有的 Requirement Contract
声明。`targetPath` 必须是工作区内相对 `.py` 路径；禁止 `..` 和绝对路径；现有文件
内容不一致时默认拒绝覆盖；所有输出先经过 Python `compile()` 校验并返回输入 Hash、
内容 Hash、Contract ID 和 Requirement ID。

仓库中的
`src/code_ontology_platform/generated/engineering_registry.py` 已由自模型生成，并由
回归测试持续检查生成结果没有漂移。

## 提交前验证

```bash
code-ontology-precommit \
  --repository . \
  --model models/code-ontology.engineering-model.json \
  --planned /path/to/planned-changes.json \
  --verification-results /path/to/test-results.json
```

`planned-changes.json` 是数组，每项用 `planId` 加 `targetPath` 或 `targetEntityId`
声明批准目标。验证结果是带 `name` 和 `status` 的数组。

提交前结果包含：

```text
GitDiffSnapshot
ActualChangeSet
ActualImpactGraph
ImpactObligations
ImplementationReconciliation
VerificationCoverage
ModelValidation
PreCommit status: ReadyToCommit | BlockCommit
```

将首次结果的 `workingTreeSnapshotHash` 作为
`--reviewed-snapshot-hash` 再次验证。如果 Working Tree 发生任何 staged、unstaged、
untracked、rename、delete 或 binary patch 变化，返回 `STALE_REVIEW` 并阻断提交。

## Requirement IR 自动接线

文档抽取后，Desired Graph 不再只有普通 Requirement 节点。平台确定性生成：

```text
BusinessCapability
← specifiesCapability ← EngineeringRequirement
                         ├─ definesContract → SpecificationContract
                         └─ constrainedBy → SemanticContract → OntologyAsset

DesiredTestObligation
→ Planned TestVerification
→ VerificationObjective
→ EngineeringRequirement
```

Change Plan 保存 `ontologyVersion`，并把上述工程语义 Context 和 Coverage 放入
`requirementContext`。因此 Implementation Agent 的原有 Prompt 会连同 Approved
Proposal、Task、Verification Obligation 一起获得受白名单关系限定的工程上下文。

## 统一 MCP

原有 `code-ontology-platform mcp` 现在直接包含：

```text
engineering_validate
engineering_coverage
engineering_collect
engineering_impact
```

旧的 `code-ontology-engineering-mcp` 命令保留为兼容入口，但不再维护第二份 Tool
定义或算法。

## 验证标准

完整闭环的自动化测试覆盖：

- Requirement IR 到 Engineering Semantic Graph；
- SHACL 与生命周期 Evidence 规则；
- leaf Requirement 三维 Coverage；
- Ontology / Requirement / Contract / Code / Test typed impact；
- 统一 MCP 工具目录；
- 生成代码确定性、可编译、路径安全、幂等和自模型漂移；
- 完整 Working Tree Hash；
- Missing Implementation 和 Unexpected Implementation；
- Review 后变更触发 `STALE_REVIEW`；
- 原有四人工 Gate、Worktree Agent、Actual Graph、Reconciliation、Impact、Release
  Advice 和 Audit Chain 回归。
