# code-ontology 平台自身业务：元模型驱动实施闭环

本轮对象是平台自身的代码开发管理业务，不再使用任务优先级代替平台业务。定义沿用开发元模型 2.0.0，不增加本体类、动作执行或行为 DSL。

## 1. 已落地的范围

新增工作台 `SELF · 平台自开发` 和服务端 `PlatformDevelopment`，提供：

1. 建立平台业务模型，并读取真实工作区文件摘要作为基线。
2. 将八个业务环节及追踪契约生成需求映射为 dev 类型实例和明确的关系。
3. 校验模型，保存不可覆盖版本；新版本通过 parentModelId 保留前一记录引用。
4. 由需求图生成 Python 追踪查询模块与 TypeScript 需求 IRI 类型，预览全部内容。
5. 独立批准操作固定模型摘要、源码基线、生成内容与执行配置。
6. 在新建受管理目录生成契约，并运行独立固定验收和已有平台回归测试。
7. 保存实际产物、报告、执行、满足性判断和义务关闭依据。
8. 查询记录时复核源码、定义、生成文件、模型及证据；漂移则返回 Stale，历史结果保留。

这是**平台固定回归基线的开发管理闭环第一版**。不等于完整项目需求管理、所有业务语义自动实现或生产交付平台已经完成。已有业务逻辑被复用，不是本轮重新生成。

## 2. 业务建模与实现职责

| 业务环节 | 需求含义 | 既有实现职责 | 固定验收 |
| --- | --- | --- | --- |
| 元模型治理 | 完整 IRI 查询、继承约束展示、版本摘要绑定 | metamodel_registry.py | test_metamodel_registry.py |
| 仓库基线 | 代码事实、查询与版本上下文 | repository_scan.py / code intelligence | test_code_intelligence.py |
| 需求契约 | 受治理工程意图、能力、契约与验收关联 | engineering_semantics.py | test_engineering_semantics.py |
| 语义对账 | Approved 与 Actual 对比及未解决影响 | verification_workflow.py | test_requirement_reconciliation.py |
| 计划执行 | 工作流人工确认、批准和执行限制 | workflow_orchestration.py | test_execution_workflow.py |
| 代码生成 | 明确转换规范及拒绝不支持输入 | development_codegen.py | test_development_codegen.py |
| 验证门禁 | 覆盖、义务与快照检查 | verification_workflow.py | test_precommit_verification.py |
| 平台审计 | 业务记录、阶段上下文和审计查询 | store.py / service.py | test_platform.py |
| 追踪契约 | 从需求图生成 Python/TS 类型与查询 | platform_development.py | platform_acceptance.py 中独立契约验收 |

每项均建立 BusinessConcept、Requirement、SemanticContract、Invariant、AcceptanceCriterion、TechnicalRepresentation、RealizationMapping、SemanticDelta、VerificationObligation、ImplementationTask 和 VerificationSpecification。

```text
BusinessGoal ─motivates→ Requirement ─hasAcceptanceCriterion→ AcceptanceCriterion
                              │                                  ↑
                        eng:constrainedBy                      verifies
                              ↓                                  │
                       SemanticContract                  VerificationSpecification
                              │                                  │
                           hasClause                        VerificationRun
                              ↓                                  │
                          Invariant                           produces
                              ↑                                  ↓
                           addresses                          Evidence
                              │                                  ↑
                   TechnicalRepresentation                   supportedBy
                                                                 │
                                                     SatisfactionAssessment
                                                                 │
                                                        义务 closedBy 引用
```

业务需求陈述与固定验收范围分开：测试成功支持当前规范内的条款与验收判断，不证明业务陈述所有可能语义均已满足。映射保持 Declared，不因为测试通过就自动宣称源码结构已经观察确证。

## 3. 数据、身份与版本

- 复用 SQLite `development_records`，使用 platform-model、platform-approval、platform-run 三种记录类型；不覆盖已有记录，不更改任务切片数据。
- 每个模型和执行都采用独立 UUID/IRI。需求节点使用 req_ 前缀，避免与 plan、baseline 等治理节点重名合并。
- 模型包含元模型 binding、Turtle、modelHash、baseline 文件摘要、需求列表和校验结果。
- 批准记录包含 approvalHash、模型 ID、理由与本地操作人；不是多人审查签名。
- parentModelId 只是版本追踪，目前没有自动语义差异合并或跨版本迁移。
- 文件摘要覆盖固定 src、tests、ontology、shapes、rules、models、examples、web/src 下的支持文件以及包清单；不是全磁盘、完整 Git 状态或已安装依赖锁定证明。新增/删除作用域内文件也会改变摘要。
- 定义绑定变动、源基线变动时，预览/批准/执行返回冲突，要求新版本重新审查。不得只替换旧摘要继续执行。

## 4. 生成与执行边界

固定转换从保存的 RDF Requirement 节点读取完整 IRI、名称、需求陈述及范围：

- `generated/platform_contract.py`：REQUIREMENTS 与按 IRI 查询函数。
- `generated/platform-contract.ts`：只读需求常量与 RequirementIRI 类型。

输出位于数据库旁 `platform-development-runs/<runId>/`。同时保存 model.ttl、report.json 与 evidence.ttl。此入口不覆盖平台源码，不将生成物自动安装到既有业务服务，不提交 Git，不推送 GitHub，不部署。

预览后必须独立批准；执行仅接受 approvalId。客户端不能提交命令、目标路径、验收脚本或任意 Turtle。固定验证器执行仓库中已有测试，这些测试属于受信仓库代码；独立进程有超时，但不是任意程序安全沙箱。

生成契约的独立验收检查九个领域 ID、模型与生成数据一致、已知/未知 IRI 查询、Python 与 TypeScript 数据一致。其他八项分别执行上表固定测试模块。零用例、跳过、失败、缺失领域、报告错误或源码漂移均不能得到 Ready。

## 5. 状态与证据

模型和批准不可变；同一批准可以显式再次执行，每次产生独立执行记录。当前尚未提供持久执行队列、取消、断线恢复和幂等执行令牌。

- `status`：执行结束时的历史结论，Ready 或 Blocked。
- `currentStatus`：重新读取文件与定义后的状态；发生变化为 Stale。
- `validation`：执行证据图的元模型约束检查。
- `report`：每个固定领域的实际用例数量、跳过数量、输出及成功/失败。

Ready 的范围仅为 `platform-regression-v1`。测试证据不替代真实浏览器验收、安全审计、全业务覆盖、依赖可复现构建或生产部署批准。失败采用保守策略：保留报告、所有义务保持 Open，不部分宣称整条链已经就绪。

## 6. 前端操作

1. 启动本地工作台，在 ONTOLOGY FLOW 中选择 `SELF · 平台自开发`。
2. 输入基线名称，建立平台业务模型与源码基线。
3. 逐项查看九个需求的语义链、声明源码位置和固定验收；展开完整 Turtle。
4. 点击“检查基线并预览生成”，查看 Python 与 TypeScript 产物。
5. 填写批准理由，点击“批准当前预览”。这一步不执行代码。
6. 点击“生成契约并执行平台固定验收”，等待数分钟。
7. 查看每组测试与证据图、当前状态；历史记录可在刷新后重新加载。
8. 代码修改后保存新版本并重新批准、执行；旧历史继续保留。

## 7. API

前缀 `/api/platform-development/`，沿用平台已有鉴权配置。

| 方法 | 操作 | 输入 |
| --- | --- | --- |
| GET | catalog | 无 |
| GET | models | 无 |
| POST | models | title、可选 parentModelId |
| GET | model | modelId |
| GET | preview | modelId |
| POST | approve | modelId、approvalHash、reason |
| POST | execute | approvalId |
| GET | history | modelId |
| GET | run | runId |

## 8. 后续还需完成

要从固定基线扩展到真正的任意平台需求开发，还需要：需求条款的服务端编辑与版本差异、对齐结果与 dev 映射的持久绑定、需求级独立验收设计、更多明确转换器、受控补丁应用、异步执行恢复及团队审批。当前不能把这些工作标为已完成。

## 9. 本次真实验证

- 新增 5 项平台自开发回归测试全部通过，覆盖模型身份与关系、显式批准、基线/定义变化阻断、失败/空报告、持久化与产物篡改失效。
- 工作台 TypeScript 与 Vite 构建通过；仍有主包超过 500 kB 的既有体积提示。没有执行真实浏览器交互验收。
- 真实运行 `109770b9-a08a-41d4-94a1-be966d2b6dd1`：9 组共 80 项检查通过，其中 75 项来自既有平台回归，5 项为独立生成契约检查；证据图 1243 条三元组，约束问题为 0。
- 运行对应模型 `f47459bd-e8c8-43f7-91f9-0732a4c84632`，批准 `c2ac68c1-f722-4b2c-bd79-55259144cee9`。这些是本次本地数据库记录，不是其他安装环境的预置数据。
- 产物目录 `data/platform-development-runs/109770b9-a08a-41d4-94a1-be966d2b6dd1/`；包含 Python/TS 代码、模型、报告和真实证据图。

历史 Ready 仍需通过读取接口复核 currentStatus。测试结果不是永久有效的项目完成声明。
