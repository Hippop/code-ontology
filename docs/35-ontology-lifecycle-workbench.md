# 本体工程全流程工作台

## 目标

工作台把仓库事实、本体建模、需求意图、语义对齐、批准计划、代码生成、提交门禁和发布审计放入同一条可操作链路。每个阶段读取或产生受版本控制的工程语义资产，避免 UI 另建一套不可验证状态。

## 信息架构

| 阶段 | 主要输入 | 核心操作 | 输出或 Gate |
| --- | --- | --- | --- |
| 仓库基线 | Git 仓库 | 注册身份、选择工作仓库、进入图谱扫描 | repositoryId、HEAD 与 Current Graph |
| 本体构建 | Engineering Semantic Model | 新增实体/关系、JSON 高级编辑、上下文收集 | 一致性、覆盖率与显式规则影响 |
| 需求意图 | 设计文档 | 进入 Requirement Workflow，提取并确认 IR | Confirmed Requirement IR |
| 语义对齐 | Current + Desired | 图谱对比、实现切片、候选决策 | Confirmed Alignment |
| 批准计划 | 对齐结果与影响义务 | 检查生成契约和批准边界 | Approved Change Plan |
| 代码生成 | 已治理模型与仓库 | 预览产物；人工确认后才允许应用 | 内容 Hash、目标路径与工作树变更 |
| 提交门禁 | Git Diff、计划与验证结果 | Actual 映射、影响传播、计划对账 | ReadyToCommit 或结构化 Blocker |
| 发布审计 | Approved / Actual / Evidence | 对账、需求回放、证据核验 | 可审计发布决策 |

## 本体构建器

前端编辑的模型就是 `EngineeringSemanticModel` JSON：节点包含稳定 ID、类型、标签、可选代码路径与生成契约；边使用工程本体中定义的关系。草稿保存在浏览器本地，服务端只在明确请求时分析或生成，防止编辑动作隐式修改仓库。

一次分析请求同时返回：

- `validation`：所有权、契约、实现、验证与证据约束；
- `coverage`：叶子需求的实现、验证和执行证据覆盖率；
- `context`：选中实体的有界工程上下文；
- `impact`：从变更种子出发、由显式规则确认的影响路径。

## 代码生成与安全边界

`PREVIEW GENERATION` 永不写工作树，返回目标路径、源代码、内容 Hash 和 Planned / Unchanged / Updated 状态。`APPLY TO WORKTREE` 只有在用户勾选确认后才可用；后端仍强制执行注册仓库边界、相对 Python 路径、模型一致性、唯一需求所有者和覆盖策略。

## 提交门禁

门禁绑定精确 `workingTreeSnapshotHash`，并把 Git Diff 转换为 Actual Change Set。任何未建模且未纳入计划的路径都会产生 `UNEXPECTED_IMPLEMENTATION`；计划未实现、验证失败、模型无效和复核后快照漂移也会阻止提交。

## HTTP 契约

```text
GET  /api/engineering-workbench
GET  /api/repositories
POST /api/engineering-semantics/analyze
POST /api/ontology-code-generation/preview
POST /api/ontology-code-generation/apply
POST /api/precommit-verification
```

这些接口与既有 Requirement Workflow、Graph Compare、Graph Explorer 和 Requirement Trace 组合，构成从需求到发布审计的完整前端闭环。

## 运行

```bash
cd web
npm ci
npm run build
cd ..
code-ontology-platform serve --web-root web/dist
```

打开 `http://127.0.0.1:8080`，默认进入 `ONTOLOGY FLOW`。
