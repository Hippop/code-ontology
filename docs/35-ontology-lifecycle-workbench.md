# 本体工程全流程工作台

## 目标

工作台把仓库事实、本体建模、需求意图、语义对齐、批准计划、代码生成、提交门禁和发布审计放入同一条可操作链路。每个阶段读取或产生受版本控制的工程语义资产，避免 UI 另建一套不可验证状态。

## 信息架构

| 阶段 | 主要输入 | 核心操作 | 页面输出或 Gate |
| --- | --- | --- | --- |
| 01 仓库与存储接入 | 代码库路径、图谱保存路径（选填，默认生成 `.code-ontology`） | 注册代码库、初始化图谱存储空间、一键触发图谱扫描 | 绑定状态卡片、存储空间状态、HEAD 修订号 |
| 02 图谱扫描基线 | 目标仓库、触发扫描指令 | 静态 AST 解析、事实抽取、图谱快照落盘 | 节点与关系统计指标、Current Graph 快照路径（`.code-ontology/graphs/current/`） |
| 03 项目本体建模 | 实体/关系草案、影响分析种子、JSON 模型 | 关联元模型、新增实体与契约、执行 SHACL 约束校验与显式波及分析 | 拓扑图画布、CONFORMS 判定与约束违规清单、波及影响雷达 |
| 04 需求意图 IR | 自然语言需求描述、PRD 片段、能力归属 | 运行意图抽取引擎、识别期望实体与业务规则 | 结构化 Requirement IR、RequirementReview 门禁 |
| 05 语义对齐裁决 | 对齐分析触发、候选动作人工裁决（复用/扩展/修改/替换/新建） | 双图差异比对、消除歧义决策、生成变更草案 | Current ↔ Desired 对照视图、Proposed Graph 快照 |
| 06 批准计划契约 | 审查变更集、配置生成契约（RequirementContract）、设定影响测试义务 | 签署并锁定变更范围与安全边界 | Approved Change Plan、不可变 Plan Hash 签名 |
| 07 代码生成应用 | 覆盖选项勾选、审查预览 Diff、工作树写入确认 | 确定性代码生成、Diff 审查、安全写入 Git 工作树 | 产物明细清单、语法高亮 Diff 查看器、工作树变更日志 |
| 08 提交门禁核验 | 触发门禁复核、可选导入自动化测试执行证据 | 工作树 Git 快照核验、计划对账、影响义务闭环与防漂移检查 | ReadyToCommit 或 BlockCommit 判定、Blockers 违规清单 |
| 09 发布就绪审计 | 选定需求 ID 或发布 Commit 标签 | 聚合因果链、验证密码学签名、最终对账核验 | 全因果溯源时间线、不可篡改证据包（Evidence Package） |

## 图谱工作空间约定：.code-ontology

每个受管辖代码库默认拥有专属图谱与语义工作空间，结构如下：
```text
<repository_path>/.code-ontology/
├── config.json              # 仓库图谱治理配置（分支、语言、扫描规则）
├── .gitignore               # 自动化保护规则（忽略 *.tmp 与 scratch/）
├── models/
│   └── engineering-model.json  # 项目工程本体模型（实体、关系、生成契约）
├── graphs/
│   ├── current/             # 扫描提取的代码本体图谱快照
│   ├── proposed/            # 变更草案图谱快照
│   └── approved/            # 批准生效的图谱快照
├── baselines/               # 结构化图谱基线与差异对比记录
└── audit/                   # 门禁凭证与发布审计追踪链
```
用户在接入代码库时可自定义此路径；若留空，系统自动在源码根目录下创建并维护 `.code-ontology` 目录。系统已在扫描器遍历与 Git 快照检查中对 `.code-ontology` 进行了防漂移隔离保护。


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
