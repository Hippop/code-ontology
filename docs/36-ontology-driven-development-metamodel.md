# 本体驱动开发元模型 2.0.0

2026-09-09：完成第一轮成熟化修订，不新增行为体系。类说明、引用、身份、关系上下文和草稿反例检查的具体变更，以及旧版本迁移注意事项，见 [2.0.0 优化说明](42-ontology-maturity-2.0.0.md)。旧项目数据不自动迁移；版本约束收紧后必须重新绑定和校验。

## 1. 核心命题与交付边界

本体驱动开发把业务意图转换为明确的实现义务，以版本化设计和转换规则产生代码，
再用实际采集、验证证据和满足性判断证明代码在声明范围内满足契约。

本版本交付机器可读的类/关系、约束、实例、查询和反例回归；不是只增加概念说明。
它复用总体架构的七层对象，补全贯穿开发过程的元模型。

元模型定义现已接入只读目录 API、前端元模型中心、项目草稿版本绑定及基础动态表单。
绑定的 JSON 模型投影为 RDF，在分析、生成和提交门禁入口执行 SHACL 校验。
包发布、多版本迁移和复杂约束可视化编辑尚未实现。当前新增一个明确受限的
`TransformationRule` 执行适配器：把带枚举/默认值/行为条款的业务属性设计生成
Python 数据类及边界校验；其他规则不会被自动解释。详见 [运行时接入与操作指南](37-metamodel-center-runtime.md)。

## 2. 三个独立维度

| 维度 | 内容 | 表达方式 |
| --- | --- | --- |
| 语义分类 | 代码结构、依赖数据、契约入口、验证、业务、交付运行、变化影响 | 保留 code/biz 类体系；`dev:semanticLayer` 展示锚点 |
| 定义层级 | 通用元模型、领域扩展、项目模型实例、执行与证据 | OWL 定义、包修订、项目配置、实例的 `rdf:type` |
| 生命周期 | Current、Business、Desired、Proposed、Approved、Actual、Impact | `GraphRevision.graphSpace`，不作为业务实体类型 |

知识图、变更图和影响图以 `graphRole` 区分。图角色与生命周期独立，例如
Desired 和 Actual 均可承载知识图，但来源、版本及事实性质不同。

`rdf:type` 表示实例归属；`rdfs:subClassOf` 表示定义扩展。不再新增功能相同的
`instanceOf`/`specializes` 属性。SHACL 负责符合性；RDFS domain/range 不能替代验证。

## 3. 资产布局与依赖

| 文件 | 职责 |
| --- | --- |
| `ontology/ontology-driven-development.ttl` | `dev:` 类、属性、注释、继承及七层展示锚点 |
| `shapes/ontology-driven-development-shapes.ttl` | 结构、生命周期、版本一致性和工程闭包约束 |
| `models/development-metamodel.package.json` | 仓库内包清单、依赖、示例与运行时边界 |
| `examples/development-task-priority.ttl` | 任务领域扩展和完整演示链 |
| `examples/development-code-ontology.ttl` | 平台自身“元模型查询”功能的待开发模型 |
| `queries/development/*.rq` | 六项能力问题的可执行查询 |
| `tests/test_development_metamodel.py` | 合法路径、错误模型和查询回归 |

命名空间：`https://example.org/code-ontology/development#`；
版本 IRI：`https://example.org/code-ontology/development/2.0.0`。
保留仓库现有 example.org 命名空间，避免无迁移地改变全部实体标识。

本包引用 code、biz、eng、plan。已有依赖没有完整版本 IRI，因此生产消费方还应
固定仓库 commit 和文件内容摘要；包清单明确说明此限制，不能仅记录 `latest`。
加载器应从本地清单解析依赖，不进行任意网络 `owl:imports` 拉取。

### 与旧定义的兼容

- `dev:Requirement` 继承 `eng:EngineeringRequirement`，保留能力归属和契约单一所有权。
- `dev:SemanticContract` 继承 `eng:SemanticContract`，允许多个需求引用同一语义契约。
- `dev:BusinessConcept/BusinessAttribute/BusinessRule` 继承 biz 定义，保留 canonicalId。
- `dev:ImplementationSlice` 继承 biz 切片，保留主要业务步骤和技术入口约束。
- `dev:Evidence` 继承 eng 证据，必须关联可审计 Artifact。
- `dev:CodeArtifact` 继承 `code:SourceFile`，表达实际文件修订。
- dev 的计划/执行记录用于跨模型闭环，不直接继承约束语义不同的 plan 提案类型；
  集成既有编排服务时应显式映射，并保留双方标识与来源。

不把 `code:BusinessCapability` 与 `biz:BusinessCapability` 强行声明成 sameAs 或
等价类。新工程需求沿用 eng 已采用的 code 能力类型，biz 流程继续采用 biz 类型。
项目若认为二者语义对应，应提供明确迁移或映射。运行时只取 localName 会丢失这一区别，
因此后续动态元模型 API 必须采用完整 IRI。

## 4. 核心节点与关系

### 4.1 模型治理

`MetamodelPackage` 收录 `definesTerm`，固定版本、来源、状态及 `dependsOnPackage`。
`DomainExtension` 是依赖通用定义的包；新领域类型使用 RDFS 继承。

`ProjectProfile` 锁定项目的包、`ConstraintSet`、`RuleSet`、`TechnologyProfile`；
`ModelRevision` 通过 `usesProfile` 使用该配置。项目实体通过 `inModel` 绑定修订。
`CodeSnapshot` 记录项目、仓库、commit、工作树内容摘要及采集范围。

`MigrationPlan` 声明源包、目标包、受影响配置与迁移依据。服务层后续须实现
发布后不可变、内容摘要重算、迁移执行与复核；单一 RDF 文件无法证明历史未被改写。

### 4.2 意图、需求与契约

```text
BusinessGoal --motivates--> Requirement
Requirement --eng:specifiesCapability--> code:BusinessCapability
Requirement --hasAcceptanceCriterion--> AcceptanceCriterion
Requirement --eng:constrainedBy--> SemanticContract --hasClause--> ContractClause
Requirement --eng:definesContract--> eng:RequirementContract
```

语义契约可复用；需求拥有的实现契约仍有且仅有一个需求所有者，两者不可混淆。

`BusinessConcept --hasAttribute--> BusinessAttribute`，`BusinessRule` 描述业务规则。
条款通过 `constrains` 指向业务对象、属性或需求，分为：

- `ValueConstraint`：XSD 数据类型、枚举、默认值、单位；类型和默认枚举由 SHACL 检查。
- `BehaviorClause`：前置条件、后置条件、失败行为。
- `Invariant`：在指定操作/状态范围内保持的约束。

条款是生成和验证逐项引用的责任单位。字段 `priority: str` 仅表达一种技术结构，
不证明默认值、枚举合法性或非法输入处理已经实现。
自然语言 `statement`、`precondition` 等是可读语义；执行其业务含义仍需规则适配器。

### 4.3 设计与业务—代码映射

```text
DesignElement --addresses--> Requirement / ContractClause / AcceptanceCriterion
DesignElement --decidedBy--> DesignDecision
TechnicalRepresentation --represents--> BusinessConcept / BusinessAttribute
ImplementationSlice --hasMember--> 设计 / 代码 / 接口 / 验证对象
```

`DesignDecision` 记录问题、候选、选择及理由；本体无法自行决定的架构选择成为显式输入。
API 字段、语言字段、数据库列是不同技术表示，不能与业务属性合并。

`RealizationMapping` 保存语义源、技术目标、角色、状态和依据。角色词表：
`Represents / Implements / Enforces / Verifies`；状态：`Declared / Observed / Stale / Rejected`。
Observed 必须指向实际 CodeArtifact，且由同快照成功的 ObservationRun 支持。
仅建立映射不推出 `Satisfied`。

### 4.4 差异、义务与计划

```text
SemanticDelta --baseline--> CodeSnapshot
SemanticDelta --targetModel--> ModelRevision
SemanticDelta --createsObligation--> ChangeObligation / VerificationObligation
ChangePlan --hasObligation--> Obligation
ChangePlan --hasTask--> ImplementationTask --fulfills--> Obligation
```

变化种类：Add、Modify、Remove、Reuse、ConstraintChange。义务状态：Open、InProgress、
Closed、Waived。`fulfills` 是任务承担责任的声明，不能直接关闭义务。
Closed 必须有对应语义目标的 Satisfied 判断；Waived 必须有明确批准及理由。
Ready 检查仍要求该模型中需求的全部验收条件满足，不以免除义务绕过验收条件。

批准绑定计划对象及内容摘要。任务不能承担计划之外的义务；计划内每项义务必须由任务承担。
本版本交付就绪的闭包范围是一个目标模型中的全部需求；若只发布一个切片，应建立
范围明确的目标模型修订，不对整个项目模型给出局部 Ready 结论。

### 4.5 转换与执行

`TransformationRule` 记录输入模式、前提、输出模式、不支持情况和版本。
`GenerationSpecification` 固定输入设计、条款、规则、技术栈和目标路径。
`preserves` 是转换对语义的承诺，不是已验证的性质。
每项承诺条款必须有对应验证规范；是否已真实执行以及执行结果属于后续证据判断。

`ImplementationTask.mode` 区分 Template、Agent、Manual、Reuse。独立执行记录包括：

| 执行类型 | 必要上下文 | 产物 |
| --- | --- | --- |
| GenerationRun | 批准计划、任务、生成规范、执行器版本、输入摘要 | 目标路径 CodeArtifact |
| ObservationRun | 精确快照、采集范围、解析器版本 | 实际图与采集事实 |
| VerificationRun | 验证规范、模型修订、代码快照 | Evidence 和报告 |

生成规则和技术栈必须属于计划目标模型锁定的配置。输入设计和条款必须同模型，
生成产物必须属于同项目。所有执行记录区分 Operational 与 Illustrative。

目标设计与实际代码采用不同节点；不因生成完成而自动发布 Current/Actual 图。
对于既有代码变更，执行器应以补丁方式维护人工代码区域，重扫后再建立观察映射。

### 4.6 证据、满足性与影响

```text
VerificationSpecification --verifies--> AcceptanceCriterion / ContractClause
VerificationRun --usesSpecification--> VerificationSpecification
VerificationRun --produces--> Evidence --generatedBy--> VerificationRun
SatisfactionAssessment --assesses--> AcceptanceCriterion / ContractClause
SatisfactionAssessment --supportedBy--> Evidence
ReleaseAssessment --underPlan--> ChangePlan
ReleaseAssessment --includesAssessment--> SatisfactionAssessment
```

满足性状态：NotAssessed、Satisfied、PartiallySatisfied、NotSatisfied、InsufficientEvidence。
确定性判断必须有证据；Satisfied 的所有支持证据必须来自 Operational 成功执行。
证据与判断须同模型、同快照、同范围，且验证规范覆盖判断目标。
当前范围比较采用精确字符串相等；不同粒度范围的包含推理不在此版本内。

`ImpactRule` 记录匹配模式、传播前提和停止条件；`ImpactAssessment` 记录差异、对象、
规则、路径、证据及 Candidate/Confirmed/Contained/Rejected/Unresolved 状态。
查询返回的引用者仅是评审候选，不因可达而自动成为 Confirmed 影响。

## 5. 生命周期关键约束

| 约束标识 | 拦截的问题 |
| --- | --- |
| DEV_PACKAGE_CYCLE / DEV_PACKAGE_NOT_PUBLISHED | 包依赖成环，项目采用未发布依赖 |
| DEV_REQUIREMENT_CYCLE / DEV_TASK_CYCLE | 需求细化和任务依赖成环 |
| DEV_DEFAULT_OUTSIDE_ENUM / DEV_VALUE_DATATYPE | 默认值或枚举与值域不一致 |
| DEV_OBSERVED_MAPPING / DEV_FACT_GRAPH | 把设计声明当作代码事实 |
| DEV_MODEL_LINK / DEV_PROJECT_CONTEXT | 无依据地连接不同模型或项目版本 |
| DEV_PLAN_APPROVAL / DEV_TASK_SCOPE | 计划变化后继续用旧批准、遗漏义务或越界任务 |
| DEV_GENERATION_AUTHORITY / DEV_GENERATION_CONTEXT | 未批准生成、使用未锁定规则或技术栈 |
| DEV_PRESERVATION_VERIFICATION | 转换承诺保留某条语义却没有验证规范 |
| DEV_PATH / DEV_GENERATION_OUTPUT | 不安全的目标路径、成功执行无对应产物 |
| DEV_VERIFICATION_REPORT / DEV_EVIDENCE_VERSION | 失败执行不留报告、证据来源版本不一致 |
| DEV_ASSESSMENT_EVIDENCE / DEV_ASSESSMENT_SCOPE | 虚假通过、旧证据、错误目标或范围 |
| DEV_OBLIGATION_CLOSURE / DEV_RELEASE_CLOSURE | 无证据关闭义务、验收未满足即宣布交付 |

图校验不能证明实际报告存在、hash 真实、批准人身份真实或命令确实执行。
这些必须由后续可信执行器和审计存储验证。也不执行 OWL 完整一致性推理，
关键设计/事实互斥约束已另外编码成 SHACL。

## 6. 两个实例的阅读方式

### 任务优先级

从 `t:goal` 到 `t:requirement`、两个条款、设计决策、实现切片、差异、义务、批准计划、
转换规范、演示生成、采集、测试和最终判断，可遍历整个开发过程。

所有执行记录、报告、commit 和 hash 均为示例数据，`scenario=Illustrative`。
满足性为 InsufficientEvidence，交付为 Blocked。样例不代表真实 Task 应用已生成，
也不代表“优先调度”这一更大的业务目标已实现。将样例判断改成 Satisfied 会被拦截。

### 平台自建模

从 `p:goal` 阅读“按类 IRI 和版本查询元模型定义”的功能模型。平台提供元模型的角色，
与平台作为工程项目接受元模型约束的角色，通过 dev 定义命名空间和 p 实例命名空间分开。

该样例包含待实现 API 设计、转换规范与独立验收方法。计划为 Draft，义务 Open，
判断 NotAssessed；没有伪造生成、测试或已完成 UI。全项目能力分解继续参考
`models/code-ontology.engineering-model.json`，本例深入其中一条真实待开发纵向切片。

## 7. 元模型的六项可执行能力问题

| 查询 | 能回答什么 |
| --- | --- |
| 01-definition-catalog.rq | 类/属性定义、标签、继承、适用约束及七层归类 |
| 02-intent-to-artifact.rq | 一项代码产物的目标、需求、条款、决策、规则及执行来源 |
| 03-open-obligations.rq | 尚未完成的责任、源差异及承担任务 |
| 04-evidence-and-assessment.rq | 判断对象、结果、模型/快照、报告及演示/真实属性 |
| 05-package-to-project.rq | 哪些项目、模型和需求受某个定义包及其依赖影响 |
| 06-contract-change-candidates.rq | 条款改变后应复核哪些设计、规范、验证和映射 |

查询目录针对明确装载的本地图范围；生产查询服务需要保持包修订隔离和查询权限。
不要把所有包历史版本无选择合并后当成“指定版本查询”。

## 8. 校验与复现

在仓库根目录运行，现有 CLI 自动发现 ontology/shapes/examples 下的 Turtle 文件：

```bash
.venv/bin/python -m code_ontology_platform validate
.venv/bin/python -m unittest discover -s tests -p 'test_development_metamodel.py' -v
```

查询示例（读取文件，不修改仓库）：

```bash
.venv/bin/python - <<'PY'
from pathlib import Path
from rdflib import Graph

graph = Graph()
for directory in ('ontology', 'shapes'):
    for path in Path(directory).glob('*.ttl'):
        graph.parse(path, format='turtle')
graph.parse('examples/development-task-priority.ttl', format='turtle')
query = Path('queries/development/03-open-obligations.rq').read_text()
for row in graph.query(query):
    print(row.asdict())
PY
```

测试覆盖合法实例、字典完整性、查询结果、枚举、类型/事实互斥、单一契约所有者、
依赖环、批准摘要、上下文锁定、路径、执行报告、旧证据、范围、义务关闭和交付。
测试构造的 Operational 数据仅用于验证允许路径，不产生真实业务执行报告。

## 9. 后续运行时接入契约

1. 元模型中心按包加载完整 IRI、继承、属性、SHACL 和来源；用查询 01 建目录。
2. 项目模型服务保存 ProjectProfile 与 ModelRevision，采用元模型驱动表单。
3. 事实采集服务产生 CodeSnapshot/ObservationRun/Actual 图，不接受生成器自报事实。
4. 对齐服务维护 RealizationMapping 和 ImplementationSlice 的状态、版本与证据。
5. 规划器把差异转成义务及任务；生成服务绑定规则版本和明确批准。
6. 执行器真实采集时间、hash、报告，测试失败同样产生证据。
7. 判断服务按模型范围聚合义务、验收与精确快照，服务端验证后才接受 Ready。

本体提供这些服务共享的语义契约与可执行校验基线；服务实现进度与模型定义完整性
分别报告，不能以类和边已建齐替代功能已完成。
