# 本体建模完整性审查与成熟化整体设计

> 文档状态：待评审设计，不是已实施说明。审计日期：2026-09-09。
> 本轮仅输出审查和设计文档，不修改本体、SHACL、服务、前端或生成代码。
> 范围约束：不新增业务动作、动作执行、业务函数或运行权限等行为体系；已有流程、状态、行为条款保持兼容。

## 0. 结论与阅读方式

当前本体已经具备业务、需求、契约、设计、代码、验证和工程治理的概念骨架，以及一条可执行的受限开发闭环，但尚不能认定为完整、统一、可持续演进的通用建模平台。

主要问题不是“类不够多”，而是：

1. 定义引用没有完全闭合，旧定义的机器可读说明缺失。
2. 语义定义、SHACL、JSON 建模格式、前端展示与运行时之间存在表达差异。
3. 身份唯一性、关系端点、跨模型上下文、版本治理的约束尚不完整。
4. 正例通过与已有测试通过，不能证明约束能够拦住所有应拒绝模型。
5. 当前目录、通用项目草稿、专用切片、旧工程引擎各自具备部分能力，尚未形成一套统一的版本化模型资产管理机制。

本设计的目标是：**先把现有对象、属性、关系、约束、版本和映射做成可靠的建模基础，再考虑扩展行为能力。**

阅读建议：第 1—3 节用于评审现状；第 4—11 节定义模型与数据规范；第 12—16 节定义服务、前端和实施；第 17—19 节提供验证、案例和交付条件。

配套文件：[611 项当前定义逐项审计清单](41-ontology-definition-audit-inventory.md)。该清单覆盖全部类、对象属性和数据属性，而非仅列出新增 dev 类型。

## 1. 审计基线与证据范围

### 1.1 基线

| 项目 | 本次审计值 |
|---|---|
| Git HEAD | `cdb00388472cd45fa20b2527733950d728b9c2db` |
| 工作树 | 包含此前未提交修改及未跟踪资产；HEAD 不能单独代表本次读取内容 |
| 元模型版本 | `1.0.0` |
| 包 ID | `https://example.org/code-ontology/development` |
| 定义绑定 SHA-256 | `da239c22fe1e7a661488ea9beb452dfcc4b38646419a199ef8dc0cfc9ea4629d` |
| 定义范围 | 包清单中的 5 个 ontology 文件、4 个 shapes 文件 |
| 示例范围 | 包内 2 个开发示例；CLI 另检查全仓库共 5 个 TTL 示例 |
| 环境 | Python 3.13.13、rdflib 7.6.0、pyshacl 0.40.1 |

上述摘要是当前 Registry 的定义绑定，不覆盖示例、查询、生成器和全部运行时代码。逐文件定义摘要见配套清单。因此，不能用该摘要声称完整软件构建可复现。

### 1.2 证据来源

| 编号 | 文件/入口 | 用途 |
|---|---|---|
| E01 | [包清单](../models/development-metamodel.package.json) | 正式加载范围、版本和运行时边界 |
| E02 | [总体架构](00-overall-architecture.md)、[业务语义设计](17-business-semantic-graph.md) | 设计意图与机器定义对照 |
| E03 | [dev 本体](../ontology/ontology-driven-development.ttl)、[dev 约束](../shapes/ontology-driven-development-shapes.ttl) | 开发闭环定义、上下文和证据约束 |
| E04 | [biz 本体](../ontology/business-code-linkage.ttl)、[biz 约束](../shapes/business-code-linkage-shapes.ttl) | 业务身份、对象、流程和映射 |
| E05 | [eng 本体](../ontology/engineering-semantics.ttl)、[eng 约束](../shapes/engineering-semantics-shapes.ttl) | 需求所有权、契约和验证继承 |
| E06 | [plan 本体](../ontology/requirement-change-planning.ttl)、[plan 约束](../shapes/requirement-change-planning-shapes.ttl) | 规划定义及引用闭合 |
| E07 | [Registry](../src/code_ontology_platform/metamodel_registry.py) | 目录、类型解析、JSON→RDF、查询与校验 |
| E08 | [Authoring](../src/code_ontology_platform/metamodel_authoring.py) | 草稿检查、候选约束与示例回归 |
| E09 | [元模型前端](../web/src/metamodel.tsx)、[项目工作台](../web/src/lifecycle.tsx) | 属性展示、关联选择和模型编辑 |
| E10 | [语义校验](../src/code_ontology_platform/semantic_validation.py)、[CLI](../src/code_ontology_platform/cli.py) | 校验加载范围和推理模式 |
| E11 | [运行时说明](37-metamodel-center-runtime.md)、[专用切片说明](38-task-priority-operational-slice.md) | 通用能力与任务专用能力的边界 |
| E12 | [开发元模型测试](../tests/test_development_metamodel.py)、[目录测试](../tests/test_metamodel_registry.py)、[草稿测试](../tests/test_metamodel_authoring.py) | 已有回归保障 |

本文将“直接执行发现”“源代码审查发现”“拟定设计”分别标明，不把设计建议当作既有事实。

## 2. 当前建模覆盖范围

### 2.1 定义规模与说明完整性

| 本体 | 类 | 对象属性 | 数据属性 | 术语总数 | 缺少自身 label/comment 的术语数 |
|---|---:|---:|---:|---:|---:|
| code | 81 | 127 | 11 | 219 | 219 / 219 |
| biz | 26 | 54 | 6 | 86 | 86 / 86 |
| eng | 22 | 17 | 1 | 40 | 40 / 40 |
| plan | 62 | 41 | 18 | 121 | 121 / 121 |
| dev | 49 | 57 | 39 | 145 | 0 / 0 |
| 合计 | 240 | 296 | 75 | 611 | 466 / 466 |

说明：统计对象仅为显式声明的 Class/ObjectProperty/DatatypeProperty；不计 ontology 头部标签和 `dev:semanticLayer` 注解属性。旧文档中存在说明，不等于各术语在 TTL 中有可供前端使用的 label/comment。

本包之外还有 SDN 领域本体。它由全仓库 CLI 装载，但没有进入当前 Registry 的开发包清单，不能混用这两种统计范围。

### 2.2 SHACL 覆盖

| 范围 | NodeShape 定义数 | 直接 targetClass 涉及的类数 | 沿上位类可命中类形状的类数 |
|---|---:|---:|---:|
| code | 无独立 code shapes 文件 | 0 / 81 | 0 / 81 |
| biz | 7 | 7 / 26 | 26 / 26 |
| eng | 7 | 7 / 22 | 20 / 22 |
| plan | 14 | 14 / 62 | 41 / 62 |
| dev | 50 | 43 / 49 | 49 / 49 |
| 合计 | 78 | 71 / 240 | 136 / 240 |

重要限定：

- “被类形状覆盖”不等于“业务约束完整”；例如仅继承 canonicalId 检查仍算命中。
- 未命中 targetClass 不等于完全无检查：关系形状、按谓词定位的约束和运行时代码仍可能检查部分数据。
- 371 个对象/数据属性中，有 143 个被简单 `sh:path` 直接引用；此统计不包括复杂路径、SPARQL 或运行时检查，不据此计算准确的约束覆盖率。
- dev 形状中有 27 个 SPARQL 约束节点；50 个 NodeShape 不是 50 条独立业务规则。

### 2.3 当前核心类的职责保留

本次成熟化保留现有 dev 49 类，不通过增加新行为类来解决基础质量问题。

| 组 | 保留的完整类集合 | 核心责任 |
|---|---|---|
| 治理，12 类 | Entity、VersionedAsset、MetamodelPackage、DomainExtension、ConstraintSet、RuleSet、Project、ProjectProfile、ModelRevision、CodeSnapshot、GraphRevision、MigrationPlan | 身份、配置、包、模型和快照边界 |
| 意图与契约，11 类 | BusinessGoal、BusinessConcept、BusinessAttribute、BusinessRule、Requirement、AcceptanceCriterion、SemanticContract、ContractClause、Invariant、BehaviorClause、ValueConstraint | 业务含义与可验证责任 |
| 设计与计划，11 类 | DesignDecision、DesignElement、TechnicalRepresentation、ImplementationSlice、RealizationMapping、SemanticDelta、Obligation、ChangeObligation、VerificationObligation、ChangePlan、Approval | 目标表示、映射、差异及责任安排 |
| 转换与执行，9 类 | TechnologyProfile、TransformationRule、ImpactRule、GenerationSpecification、ImplementationTask、ExecutionRun、GenerationRun、ObservationRun、CodeArtifact | 现有开发执行记录和规则绑定 |
| 证据与判断，6 类 | VerificationSpecification、VerificationRun、Evidence、SatisfactionAssessment、ImpactAssessment、ReleaseAssessment | 证据来源、结论及交付边界 |

BusinessProcess、BusinessProcessStep、StateTransition 等继续来自 biz；代码、API、数据结构继续来自 code。已有 BehaviorClause 保留，不新增 action 属性或可执行行为 DSL。其注释提到“动作”而结构属性未定义动作，应在后续文档一致性修订中澄清，而不是本轮扩展功能。

## 3. 完整性问题清单

优先级定义：P0 为发布“成熟建模基线”前必须解决；P1 为通用建模开放使用前必须解决；P2 为质量、可用性或后续治理增强。不等同于已确认的生产安全事故等级。

| ID | 优先级 | 发现与证据 | 影响 | 拟解决位置 |
|---|---|---|---|---|
| A01 | P0 | `a` 与 `urn:engineering-node:a` 两个 JSON ID 通过唯一性检查后被投影为同一 IRI；实测只剩 1 个 type 三元组（E07） | 静默合并实体，破坏身份 | §5、§9 |
| A02 | P0 | plan 的两个 range 和两处 SHACL 引用未声明的 `biz:Requirement`；SDN 示例也使用它（E06） | 目录不可查，JSON 无法选择，语义引用不闭合 | §4.3 |
| A03 | P0 | 将 dev shapes 草稿替换为仅含前缀的空约束文档，Authoring 仍返回 conforms=true（E08，实测） | 删除约束仍能通过正例检查，不能充当发布门禁 | §8、§11 |
| A04 | P1 | 466 个旧术语缺少自身 label/comment（定义统计） | 前端无法完整中文解释；术语边界难以评审 | §4.2 |
| A05 | P1 | 有 28 组同名术语；Registry 已拒绝歧义短名，但不同引擎和展示仍有 localName 使用（E07、E09） | 同名概念和状态可能被误读或错配 | §4.3、§12 |
| A06 | P0 | 把 goal 或 task 概念移动到另一 ModelRevision，跨模型 motivates/hasAttribute 仍校验通过（E03，实测） | 业务意图、对象和属性可静默串版 | §7.2 |
| A07 | P1 | 两个 BusinessAttribute 在同模型使用相同 canonicalId 仍通过（E04，实测） | 稳定业务身份不唯一 | §5.2 |
| A08 | P1 | constrains 和 mappingSource 指向不存在的 IRI 仍通过（E03，实测） | 关键责任关系悬空 | §7、§8 |
| A09 | P1 | 不含允许值/默认值的 ValueConstraint 可引用任意未注册 datatype IRI（E03，实测） | 结构合法但无法一致解释或生成 | §6.2 |
| A10 | P1 | 绑定 JSON 不支持外部 IRI 端点、示例领域类型和 type 数组（E07，实测） | TTL 能表达的模型无法从通用表单完整建立 | §9 |
| A11 | P1 | detail.relations 主要依据 domain/range；GenerationSpecification 的核心出边未出现在关联列表（E07，实测） | 图上“没显示”被误读成“没定义” | §12、§13 |
| A12 | P1 | 只提交 eng:contractDefinedBy 逆边而不提交 definesContract 正边，原合法示例不通过所有权约束（E05、E07，实测） | OWL 逆关系与当前 rdfs 推理模式不一致 | §8.3 |
| A13 | P1 | 空 RDF 数据图、未知 dev 谓词通过普通 SHACL 检查（实测） | 符合性被误当成完整性；拼写错误可能隐藏 | §8.1 |
| A14 | P1 | code 81 类没有目标类形状；eng/plan 也有类未命中类形状（统计） | 通用目录可创建的对象并不都有建模质量约束 | §6、§8 |
| A15 | P1 | CLI 装载目录通配文件；Registry 按清单加载；查询 01 仅筛选 dev（E07、E10、查询目录） | 相同“校验/目录”称呼可能指不同语义闭包 | §10、§12 |
| A16 | P1 | 当前只有一个安装版本；查询和 usage 主要读取两个包内示例（E07） | 无法查询通用项目真实使用范围及历史定义 | §10—§12 |
| A17 | P1 | GraphRevision 用 containsEntity 表达成员，但当前 Graph 合并不等于 RDF Dataset 的命名图隔离（E03、E07） | 多修订事实和边的来源边界不足 | §10.2 |
| A18 | P2 | 已有测试通过，但出现 SQLite 连接未关闭 ResourceWarning；文档存在不同阶段能力说明并列 | 维护噪声，容易混淆专用与通用能力 | §15、§17 |

### 3.1 不应误报为缺陷的情况

- `Declared` 映射可以先声明一个已有实际文件为候选目标；只要不冒充 Observed/Satisfied，这不必被禁止。本次替换目标为实际产物后通过校验，是可接受的对照结果。
- 空图通过一般 SHACL 属于目标节点未命中时的正常结果；真正缺口是产品没有单独的项目完整性判定。
- 缺少 domain 不必然是错误。为多种类共用的关系强行添加多个 domain 会产生交集语义，不能用这种方式修复展示。
- RDFS/SHACL 未进行完整 OWL 一致性推理是已知边界，不能把语法通过说成完整本体一致性已证明。
- 文件 hash 格式合法不代表文件存在或内容真实。源真实性属于运行时验证，不应全部塞进 SHACL。

## 4. 目标架构与术语规范

### 4.1 保留五套本体，建立统一建模契约

```text
仓库定义：code / biz / eng / plan / dev + 领域扩展
  → 包解析与版本锁定
  → 统一定义目录：类型、属性、关系、继承、约束、来源
  → 项目模型工作区：业务模型 / 代码事实 / 映射 / 工程记录
  → 身份与引用预检 → 规范化 → SHACL → 完整性评估
  → 不可变模型修订、定义使用索引、图谱查询
  → 现有分析与受限生成器（必须经过明确适配）
```

不要再创建一套与 OWL 平行的 ObjectType/PropertyType 自定义本体。类型定义优先使用 owl:Class，关系使用 owl:ObjectProperty，值字段使用 owl:DatatypeProperty。目录中的 JSON 描述符是这些定义和 SHACL 的投影，不是第二份人工维护的真相。

### 4.2 每项术语必须具备的定义卡

| 字段 | 规范 | 权威来源 |
|---|---|---|
| IRI | 全局明确、不可通过中文名或 localName 替代 | TTL |
| kind | Class/ObjectProperty/DatatypeProperty/AnnotationProperty | rdf:type |
| label | 至少中文名称；英文显示名可选 | rdfs:label |
| definition | 一句明确含义，说明“不是什么”或适用边界 | rdfs:comment |
| package/version | 所属包、精确修订、文件摘要 | 包清单/锁文件 |
| hierarchy | 上位类、子类、上位属性；展示直接与继承来源 | RDFS |
| applicability | 哪类节点能使用该属性，哪些上下文合法 | SHACL + 关系规范 |
| cardinality | 最小/最大值数、条件必填、缺失含义 | SHACL |
| provenance | 定义文件、形状、规则 ID、设计文档章节 | 索引与目录描述符 |
| examples | 最小合法例、最小非法例、预期规则 ID | 测试数据 |
| lifecycle | 引入、弃用、替代、兼容策略 | 版本清单与迁移记录 |

不是每一类必须单独写 Shape：继承可复用约束，但必须显式说明该类自身还有无额外约束。不能把“无附加约束”与“遗漏设计”混为一谈。

### 4.3 同名概念与兼容策略

| 问题族 | 拟定规范 |
|---|---|
| code:Requirement → eng:EngineeringRequirement → dev:Requirement | 保留现有继承；通用项目正式需求优先使用 dev，旧工程实例不自动升级 |
| 未声明 biz:Requirement | 推荐补全历史业务需求类声明并令其继承 biz:BusinessEntity；因此继承 canonicalId。先修订 SDN 示例与迁移清单，不直接 sameAs 到 eng/dev |
| code/biz:BusinessCapability | 保留各自语义；工程 owner 继续使用 eng 规定的 code 类型；业务能力对应关系通过明确适配记录，不自动判等 |
| code/biz/dev:AcceptanceCriterion | dev 保留现有 code 继承；biz 旧验收采用显式迁移/关联，不能仅改前缀 |
| biz:BusinessObject 与 dev:BusinessConcept | 后者是受模型修订管理的业务概念节点；保持既有继承，说明与运行业务记录的区别 |
| eng:RequirementContract 与 dev:SemanticContract | 前者有单一需求所有者；后者可被多个需求引用；不合并 |
| plan/dev:DesignDecision、ImplementationTask、VerificationObligation | 保留来源标识、上下文和转换报告；逐字段适配，不宣称等价类 |
| biz:ConfirmedMapping 与 dev:Observed 映射 | 前者状态不能直接升级为后者；需要同快照采集来源，亦不等于验收满足 |

补全 `biz:Requirement` 是修复已使用但未声明的静态术语，不属于增加新的行为体系。它将改变类数量和约束要求，实施时必须重新统计并执行兼容迁移，不沿用当前“240 类”的宣传数字。

### 4.4 定义层、模型层、运行记录层

- 定义层：通用类、领域子类、属性、形状、规则版本。
- 项目模型层：本项目的业务概念、业务属性、需求、设计与验收定义节点。
- 事实/执行层：某个代码快照的文件、方法、采集结果、测试报告及判断。
- 业务生产记录：例如用户真实创建的 Task-1001，本轮不扩展通用对象存储与业务运行能力；不得混入“Task 业务概念”节点。

同一逻辑业务概念在模型 r1/r2 中使用不同修订节点 IRI，以稳定 canonicalId 关联其逻辑身份。不能在一个合并 Graph 中给同一节点添加两个 inModel 来表示历史版本。

## 5. 身份、唯一性和版本规范

### 5.1 IRI 处理

新模型格式采用绝对 IRI；CURIE 只在输入边界按显式前缀表展开。展开后再次执行唯一性检查，禁止沿用“字符串含冒号即有效”的简化判断。

规则：

1. 明确 URI 解析规则，拒绝空白、非法编码及相对节点 ID。
2. 不擅自改写 IRI 大小写或解码保留字符；稳定身份不是任意字符串规范化。
3. 导入旧 ID 时先生成映射表，再检查是否多对一；出现 A01 的情况必须拒绝或交由用户显式合并。
4. 展示名称可以修改，IRI 不因改中文名称而变化。
5. 代码重命名或移动产生新定位；通过既有对齐/映射记录表示对应候选，不使用 sameAs 自动合并。

建议标识形式（命名策略，不是已存在的新术语）：

| 资产 | 例 |
|---|---|
| 项目 | `urn:co:project:task-demo` |
| 模型修订 | `urn:co:model:task-demo:r1` |
| 修订内概念 | `urn:co:model:task-demo:r1:concept:task` |
| 修订内属性 | `urn:co:model:task-demo:r1:attribute:priority` |
| 逻辑业务 ID | `task.attribute.priority`，通过 biz:canonicalId 记录 |
| 代码节点 | 包含 repositoryId、snapshotId、规范化符号定位的绝对 IRI |

### 5.2 唯一性边界

| 对象 | 唯一性要求 |
|---|---|
| 定义术语 | 在已解析包闭包中 IRI 唯一；不同包不能静默提供冲突定义 |
| 项目模型节点 | 一个模型修订内，规范化 IRI 唯一 |
| 业务节点 | 同模型内 canonicalId 唯一；跨模型修订允许相同 canonicalId |
| 独立领域资产 | canonicalId 唯一性按明确资产包/作用域检查，不能因为没有 inModel 就不检查 |
| 代码文件 | 同 repository + snapshot 内，规范化路径唯一 |
| 成员符号 | 同 snapshot 内签名标识唯一；重载方法不能只用方法名 |
| 修订 | 相同修订 IRI 不允许对应两个不同内容摘要 |

### 5.3 三种摘要分开

| 摘要 | 覆盖范围 | 用途 |
|---|---|---|
| definitionHash | 清单、术语、形状、推理配置 | 模型绑定、定义兼容性 |
| modelHash | 规范化实例断言、命名图元数据、定义绑定 | 草稿版本、校验结果适用性 |
| executionInputHash | 模型摘要、代码快照、规则/生成器/验证器版本及参数 | 生成和验证复现 |

以上为拟定存储契约。现有 metamodelRef.contentHash 保留为旧 definitionHash 的兼容投影。具体规范化算法须版本化：本体文件可保留字节 hash；实例图按固定 RDF 规范化策略计算，不能随空白节点编号或 JSON 键序漂移。

## 6. 对象与属性的建模规范

### 6.1 对象的最小定义与建模边界

| 类型/类型族 | 当前基础 | 成熟化补强规则 |
|---|---|---|
| Project/Profile/ModelRevision | 已有配置、版本、范围关系 | 项目解析闭合；已发布修订不可变；实例实际使用术语必须属于绑定闭包 |
| BusinessConcept | inModel、statement、canonicalId | 必须说明概念边界；属性通过 hasAttribute；同模型身份唯一 |
| BusinessAttribute | inModel、statement、canonicalId | 成熟项目中必须有所属概念或明确共享属性用途；不得悬空 |
| BusinessRule | 已有规则节点及陈述 | 必须关联被约束对象/属性或明确业务范围；不扩展执行语义 |
| Requirement | 目标来源、验收、语义契约及继承的能力归属 | 目标/父需求/验收/契约必须处于允许上下文；区分直接 owner 与经既有 eng 链继承 owner |
| SemanticContract/Clause | 条款集合与被约束对象 | 条款目标可解析，使用类型与值类型一致；引用外部契约必须有固定导入 |
| DesignElement/TechnicalRepresentation | 责任目标、决策、业务表示 | 目标表示与事实节点分离；技术表示有明确种类与定位，不把文件路径冒充业务身份 |
| ImplementationSlice | 一个主要业务步骤和技术入口 | 明确目标模型、成员范围；事实成员另带 snapshot；不强行要求所有成员同一种类型 |
| CodeSnapshot/CodeArtifact | 仓库、摘要、范围、路径 | 文件定位与所属仓库一致；读取真实代码后确认摘要；代码成员需可追溯到文件与快照 |
| Mapping | 源、目标、角色、状态、理由 | 按角色限制端点；声明与观察来源区分；失效保留历史 |
| Plan/Obligation/Assessment | 已有责任、审批、证据规则 | 计划与义务来源、目标模型及判断范围不能串联到不相关上下文 |

对于 code 结构，先对当前采集器支持的 Repository、Module、SourceFile、Type、Callable、Field、Parameter 补充约束；其他类标明“定义可查、结构检查有限”，不得一刀切要求不存在的解析能力。

代码结构可以检查“成员有声明容器、文件路径归属仓库、参数位置合法”；不能要求调用图无环，因为递归合法，也不能要求业务/代码图整体无环。

### 6.2 属性类型、缺失与复用

业务属性节点与实际值必须区分：`priority` 是 BusinessAttribute；`medium` 是 ValueConstraint 的默认字面量，不是同层级的业务概念。

| 项目 | 拟定规范 |
|---|---|
| 值类型 | datatype IRI 必须来自包内固定的允许词表；初期支持 xsd:string/boolean/integer/decimal/date/dateTime/anyURI 等明确类型 |
| 自定义 datatype | 需登记验证器及版本；未登记可保存草稿但不能视为可验证或可生成 |
| 枚举 | 由 allowedValue 声明；字面量实际类型匹配 datatype |
| 默认值 | 最多一个；有枚举时必须属于枚举；不自动推出运行时缺省赋值已实现 |
| 单位 | 当前保留 unit；给出项目约定的规范名称，不把不同单位的数值直接当成同义 |
| 缺失 | 未提供、空字符串、显式 null 不等价；JSON v2 不将 null 偷换为字符串或空值 |
| 多值 | 保留 RDF 集合语义；如需有序序列，使用明确支持的 RDF 列表/表达形式，不能靠 JSON 数组顺序推断 |
| 共享属性 | 可由多个概念关联同一属性定义，但要明确它表示共享语义；每个用途的约束作用域必须可识别 |

枚举/默认值不足以覆盖全部静态类型约束。长度、正则、数值上下限、必填、唯一性优先用已有 SHACL 词汇及类/属性形状表达，不创建重复的 dev:minValue、dev:pattern 等词汇。只有确有业务责任追溯要求时才把约束作为条款节点，并建立与形状的明确定位记录。

## 7. 关系建模与上下文闭合

### 7.1 关系定义卡

每条公开关系都应提供：IRI、中文语义、自然方向、允许源/目标、目标类别（模型节点/定义术语/datatype）、基数、是否有逆关系、是否允许跨模型、证据要求、使用示例。

不要把自然方向当成影响传播方向；不要把所有关系声明为传递属性。允许多种源类型时，采用形状的 sh:or 或明确上位类，不能添加多个 domain 误造交集。

核心关系规范（箭头按当前定义方向）：

| 关系 | 源 → 目标 | 基数/边界设计 |
|---|---|---|
| motivates | BusinessGoal → Requirement | 需求至少有一个目标来源；默认同模型 |
| refines | 子 Requirement → 父 Requirement | 无环；默认同模型；与 eng 父子关系映射需显式规范化 |
| hasAttribute | BusinessConcept → BusinessAttribute | 0..N；每个属性至少一个有效归属或共享用途；同模型 |
| hasAcceptanceCriterion | Requirement → AcceptanceCriterion | 1..N；同模型 |
| hasClause | SemanticContract → ContractClause | 1..N；同模型或显式固定契约导入 |
| constrains | Clause/BusinessRule → 业务概念、属性或需求 | 条款 1..N；目标必须可解析且类型合法 |
| represents | TechnicalRepresentation → BusinessConcept/BusinessAttribute | 1..N；同模型 |
| addresses | 设计/决策/义务 → 语义责任 | 依源类型确定目标集合；义务当前仅指条款或验收条件，不笼统放宽为任意需求 |
| decidedBy | DesignElement → DesignDecision | 1..N；同模型 |
| mappingSource | RealizationMapping → 业务/需求/条款等语义源 | 恰一个；按 mappingRole 验证类型，不接受任意 IRI |
| mappingTarget | RealizationMapping → DesignElement/CodeArtifact | 恰一个；Observed 必须是同快照事实产物 |
| observedBy | 映射/事实图 → ObservationRun | 已观察对象必须能证明在对应采集范围内 |
| containsEntity | GraphRevision → 图内成员 | 1..N；成员索引不替代边的命名图来源 |
| hasMember | ImplementationSlice → 设计/事实/验证对象 | 允许异构；分别检查模型与快照上下文 |
| valueDatatype | ValueConstraint → 已注册 datatype IRI | 恰一个；目标不是人为创建的业务节点 |
| definesTerm | MetamodelPackage → 已声明类或属性 IRI | 1..N；目标必须由包定义/依赖策略解释 |
| targetModel / baseline | Delta/Plan → ModelRevision / CodeSnapshot | 各恰一个；项目一致 |
| createsObligation / causedBy | Delta → Obligation / Obligation → Delta | 责任来源双方一致；按规范化规则处理双向表达 |
| usesSpecification | Task/Run → 生成或验证规范 | 依源类型判定，不允许混用规范种类 |
| preserves | GenerationSpecification → ContractClause | 1..N；同模型且存在对应验证规范 |
| evaluatesModel / evaluatesSnapshot | 证据/判断/验证记录 → 修订/快照 | 各恰一个；同项目并保持证据链一致 |

完整现有属性目录见配套清单。上表是拟加强的建模契约，不能误读为这些约束今天已全部实现。

### 7.2 跨模型策略

将关系分成三组，而非统一禁止跨图连接：

1. **模型内语义关系**：motivates、refines、hasAttribute、hasAcceptanceCriterion、hasClause、constrains、addresses、represents、decidedBy、mappingSource。默认同 ModelRevision；外部共享语义必须显式导入固定修订。
2. **定义引用关系**：usesPackage、dependsOnPackage、definesTerm、valueDatatype。允许指向绑定闭包中的外部定义 IRI，不要求伪装为项目节点。
3. **设计—事实关联**：mappingTarget、hasMember、produces 等。允许从模型关联代码快照，但必须校验项目、仓库、图角色和快照范围。

跨模型合法导入至少记录来源模型 IRI、修订摘要、授权可见范围和本地引用位置。当前阶段先支持只读固定导入，不支持隐式引用 latest 或任意远端内容。

对发布模型，目标缺失不能仅因 nodeKind=IRI 就通过。草稿可以暂存缺失引用，但要显示明确未闭合问题。

## 8. 分层校验与成熟度判定

### 8.1 不再只有 conforms 一个结论

拟将结果分为：

| 层 | 检查对象 | 典型问题 |
|---|---|---|
| L0 语法 | Turtle/JSON/SHACL 元语法 | 无法解析、非法 literal |
| L1 定义闭合 | 类型、谓词、引用的术语与包 | 未声明 biz:Requirement、未知 dev 谓词 |
| L2 身份引用 | IRI、canonicalId、目标解析 | ID 合并、同模型重号、悬空关系 |
| L3 结构符合 | SHACL 类型、基数、值域、互斥 | 缺必填、错误端点、默认值越界 |
| L4 上下文 | 模型、项目、快照、图空间 | 跨模型 hasAttribute、错误代码版本 |
| L5 建模完整性 | 指定用途的最小闭包 | 空模型、无业务范围、无验收链 |
| L6 运行时可用性 | 现有执行器适配能力 | 模型合法但规则无适配器 |

开发者可保存 L0 尚未通过的草稿；但不得让其参与正式分析或发布。`conforms=true` 仅表示本次选择的符合性检查通过，不等于“模型完整”“生成受支持”或“需求满足”。

拟定 validationProfile：

- `Draft`：允许未完成，返回缺口，不发布。
- `BusinessModel`：检查业务概念、属性、范围、关系与语义约束，不要求已有代码。
- `CodeSnapshot`：检查已声明采集范围内的代码事实结构与来源，不要求完整业务需求。
- `DevelopmentModel`：检查需求—契约—设计—计划链，以及当前 dev 必填约束。
- `ReleaseAssessment`：使用现有证据和交付闭包要求，不降低 Ready 条件。

这些是校验配置名，不是新增业务实体状态。第一阶段可在既有组合校验上增加前置检查和完整性报告，不能为适配新 Profile 悄悄停用旧强约束。

### 8.2 拟新增/加强的规则目录

| 规则 ID | 检查 | 级别与反例 |
|---|---|---|
| MM_TERM_DECLARED | 项目自有命名空间中的类型/属性均已声明 | Error：biz:Requirement 未定义 |
| MM_TERM_DOCUMENTED | 公开术语有中文名、定义和来源 | 发布 Error：只有英文 localName |
| MM_PACKAGE_CLOSURE | 所用术语属于锁定依赖闭包 | Error：引用未安装领域类 |
| MM_NORMALIZED_ID_UNIQUE | IRI 展开后不重复 | Error：a 与 urn:engineering-node:a |
| MM_CANONICAL_ID_UNIQUE | 作用域内业务 ID 唯一 | Error：同模型两属性同 ID |
| MM_REFERENCE_RESOLVED | 内部引用存在、外部引用可解析 | Error：不存在的 constrains 目标 |
| MM_REFERENCE_KIND | 区分节点/术语/datatype 引用 | Error：把 datatype 伪装成业务节点 |
| MM_DATATYPE_REGISTERED | 值类型有固定语义和验证器 | Error：任意未知 datatype |
| MM_RELATION_ENDPOINT | 按源类型和角色检查端点 | Error：映射源为仓库节点 |
| MM_MODEL_CONTEXT | 同模型关系不能串版 | Error：r1 的目标驱动 r2 的需求 |
| MM_FACT_CONTEXT | 事实成员匹配项目/仓库/快照 | Error：r1 事实图收录 r2 文件 |
| MM_ATTRIBUTE_OWNERSHIP | 属性有归属或声明共享用途 | BusinessModel Error：孤立属性 |
| MM_HIERARCHY_POLICY | 类型/属性层级按声明策略检查 | Error：无意的继承环；合法等价需显式声明 |
| MM_INVERSE_NORMALIZATION | 指定逆关系的两种输入结果一致 | Error：仅逆边导致丢失所有者 |
| MM_SHAPE_COVERAGE | 每个支持建模类型有覆盖说明 | 发布 Error：新增类型无规则也无豁免理由 |
| MM_NEGATIVE_REGRESSION | 必须拒绝既定反例 | 发布 Error：删除 Shape 后仍放行 |
| MM_PROFILE_COMPLETENESS | 用途所需根节点与链闭合 | Error：空图冒充 DevelopmentModel |
| MM_REVISION_IMMUTABLE | 已发布 IRI 和摘要不可改写 | 发布 Error：同版本不同内容 |
| MM_MODEL_ROUNDTRIP | JSON→RDF→JSON 语义无损 | Error：丢类型、literal 类型或外部引用 |
| MM_QUERY_CONTEXT | 查询固定模型与定义修订 | Error：混合历史定义后称单版本结果 |

既有 DEV_* 规则继续保留。上述规则 ID 是待实现的设计标识，尚未加入仓库验证器。

### 8.3 推理与闭合边界

当前校验采用 `inference="rdfs"`，因此不能假设所有 `owl:inverseOf` 都已物化。建议初期采用：

1. RDFS 类型/属性继承继续使用现有模式。
2. 对已审查的逆关系建立明确白名单，在规范化视图中补出对应方向；保留原始输入和推导来源。
3. 类/属性语义相同与否不得通过 localName 猜测；不启用不受控 sameAs 合并。
4. 类型互斥、唯一性、基数和上下文仍由 SHACL/预检承担。
5. 若未来启用 OWL RL，必须独立版本化推理配置，并重新跑所有正反例，不直接修改全局 inference 开关。

多类型应显式保留。需要严格端点声明的配置，检查原始类型或经允许的 subclass 继承，不能仅因关系的 domain/range 推导出了期望类型就声称输入声明正确。

## 9. 统一模型交换格式

### 9.1 当前格式的限制

当前 `nodes[].type` 是单字符串；所有边两端必须在 nodes 中；properties 只接受已登记的数据属性。它不能完整表达：

- 示例中 `t:TaskConcept` 等只在扩展示例定义、未安装到目录的类型。
- `dev:valueDatatype → xsd:string` 这样的外部类型引用。
- `dev:definesTerm → owl:Class` 对应的定义术语节点引用。
- 合法多类型实例。

不能通过给 xsd:string 或类 IRI 创建假的业务节点来绕过这些限制。

### 9.2 拟定 model-json/2

以下是结构片段，不是可直接通过全部 SHACL 的完整项目。示例中的领域包、其他必需节点和关系必须先按锁定闭包提供。

```json
{
  "schemaVersion": "model-json/2",
  "modelIri": "urn:co:model:task-demo:r1",
  "projectIri": "urn:co:project:task-demo",
  "definitionBinding": {
    "packageId": "https://example.org/code-ontology/development",
    "version": "<固定版本>",
    "definitionHash": "<64位摘要>",
    "lockHash": "<依赖闭包摘要>"
  },
  "nodes": [
    {
      "id": "urn:co:model:task-demo:r1:attribute:priority",
      "types": ["https://example.org/code-ontology/development#BusinessAttribute"],
      "labels": [{"value": "任务优先级", "language": "zh"}],
      "properties": {
        "https://example.org/code-ontology/business#canonicalId": [
          {"value": "task.attribute.priority", "datatype": "http://www.w3.org/2001/XMLSchema#string"}
        ]
      }
    }
  ],
  "references": [
    {"iri": "http://www.w3.org/2001/XMLSchema#string", "kind": "DatatypeRef"}
  ],
  "edges": [
    {
      "source": "urn:co:model:task-demo:r1:clause:priority-values",
      "relation": "https://example.org/code-ontology/development#valueDatatype",
      "target": "http://www.w3.org/2001/XMLSchema#string",
      "targetKind": "DatatypeRef"
    }
  ]
}
```

约定：

- `types` 为非空完整 IRI 数组；displayPrimaryType 仅用于展示，不删除其他类型。
- `NodeRef` 指向当前模型或显式导入修订内的实例；`TermRef` 指向定义闭包；`DatatypeRef` 指向允许词表。
- references 是白名单引用目录，不授予任意网络读取权限，也不允许客户端自行把未知词声明为可信类型。
- literal 的值、datatype、language 保真；datatype 与 language 互斥。
- 包含纯字面量列表时采用无序集合语义；不同数据类型的相同文本不得合并。
- 原始 Turtle 可单独导入；实例入口禁止混入未审查的 Class/Shape 定义，扩展定义必须走定义包入口。
- 原始图、规范化图和校验报告分开保存，避免将推理事实误称为用户显式声明。

### 9.3 旧格式迁移

按“解析旧词汇 → 生成完整 IRI → 检查规范化碰撞 → 明确类型适配 → 生成 v2 → 双向对照 → 校验”执行。

迁移报告列出：输入格式、适配器版本、节点/边数量变化、ID 映射、丢失或无法表达字段、未解决引用、语义变化与输出摘要。只要发生丢字段或歧义就不能静默成功。

## 10. 定义包、图空间与模型资产存储

### 10.1 统一解析范围

定义一个 PackageResolver，为 CLI、Registry、Authoring、查询、分析和生成提供相同的解析结果。结果至少包含：包版本列表、文件摘要、术语所属包、形状列表、推理配置、允许外部词表。

CLI 保留“全仓库校验”模式，但必须显式称为 repository-wide；项目校验只使用 selected-package-closure，响应中回传实际文件列表和摘要。

SDN 本体与 TaskConcept 等领域定义应独立登记为领域包；不能因为放在 ontology 文件夹或示例中，就自动变为项目可用定义。测试 fixtures 中的 Published 不代表真实包已发布。

### 10.2 图的隔离与来源

保留 graphRole（Knowledge/Change/Impact）和 graphSpace（Current/Business/Desired/Proposed/Approved/Actual/Impact）两个独立维度，不新增状态词来代替版本。

拟采用 RDF Dataset/等价命名图存储：

- 一个图修订 IRI 对应明确的一组断言和内容摘要。
- 元数据记录 projectId、modelRevisionId、snapshotId（如适用）、graphRole、graphSpace、采集来源、definitionHash。
- 同一关系在不同图中的断言分别保留；containsEntity 只是成员索引，不能替代断言 provenance。
- 查询先选择允许图集合，再构建视图；禁止默认将所有历史模型和事实混合。
- 设计与事实互斥规则继续执行；跨图映射是允许且必须受控的关系。

不要求本阶段立即迁移到大型图数据库。可以先在现有 SQLite 保存不可变规范化 RDF 内容及索引，在请求范围内构造 Dataset；存储后端替换不能改变语义契约。

### 10.3 拟定持久化实体

| 存储表/集合 | 关键字段与约束 |
|---|---|
| definition_packages | packageId、version、revisionHash、status、manifest；发布修订不可覆盖 |
| package_dependencies | sourceRevision、targetRevision；固定依赖且无环 |
| model_workspaces | workspaceId、projectId、headDraftRevision；乐观并发 |
| model_revisions | modelIri、definitionLockHash、modelHash、sourceFormat、canonicalRdf、createdAt、createdBy；不可变 |
| graph_revisions | graphIri、modelIri、role、space、snapshotId、contentHash |
| term_usage | termIri、definitionRevision、modelIri、node/edge位置、使用方式；支持类型、谓词、datatype 及继承影响 |
| validation_reports | reportId、modelHash、definitionHash、profile、validatorVersion、issues、coverage |
| migration_records | from/to binding、ID 映射、差异、审批、结果摘要 |

这些为拟定平台存储对象，不是本次新增的 OWL 类。现有草稿表与专用切片表可复用或适配；不能把它们当前已有的存在等同于上述通用能力已实现。

## 11. 定义修订、兼容性与发布设计

### 11.1 发布门禁

候选定义从 Draft 到 Published，必须依次完成：

1. Turtle/SHACL 元语法检查。
2. 术语引用闭合、标签说明、类型层级和冲突检查。
3. 与基线的语义差异比较：新增/删除类型、范围收紧、必填增加、基数变化、枚举缩小等。
4. 全部正例符合性回归。
5. 全部反例继续被正确规则拒绝；专门测试删除或禁用关键 Shape 的情况。
6. 已登记项目使用索引查询和实例迁移试运行。
7. 按兼容策略选择版本并固定依赖锁。
8. 审查确认、写入不可变发布记录，再切换项目绑定。

`Authoring.check` 当前只是候选语法与正例回归，界面应称“草稿检查通过”，不能称“发布验证通过”。

### 11.2 版本变更分类

| 变化 | 默认处理 |
|---|---|
| 补充 label/comment | 通常补丁级；仍生成新内容摘要 |
| 增加可选静态属性/类型 | 评估后通常兼容；检查对工具/枚举选择影响 |
| 增加必填、收紧基数、缩小枚举、限制旧合法关系 | 破坏性，必须迁移并升级不兼容版本 |
| 删除或修改 IRI 语义 | 破坏性；弃用、替代映射、迁移报告，不直接覆盖 |
| 放宽或删除约束 | 同样需要评审；可能破坏质量保证，而非天然安全 |
| 修改推理配置/标准化方式 | 作为语义变更，完整重跑测试与实例 |

不要因为本次修订被称为“成熟化”就预先保证版本只升为 1.1.0；应根据实际兼容差异确定。保留旧绑定的读取与导出，禁止强制自动迁移所有项目。

## 12. 服务与 API 设计

以下为目标接口。除明确标为当前已有外，其余尚未实现。

| 接口 | 当前情况 | 目标语义 |
|---|---|---|
| GET /api/metamodel/catalog | 已有单版本目录 | 增加定义闭包、覆盖状态、分页和过滤；完整 IRI |
| GET /api/metamodel/term | 已有定义详情 | 同时返回 declaredRelations、effectiveConstraints、applicableRelations、推断依据和来源 |
| GET /api/metamodel/example | 已有白名单示例 | 保留示例属性，不能冒充项目真实实例 |
| POST /api/metamodel/validate | 已有 Turtle/JSON 校验 | 增加 profile 和分层结论，保持旧 conforms 的兼容含义 |
| POST /api/metamodel/query | 已有白名单示例查询 | 增加受权 modelRevision/graphRevision 上下文；查询模板有版本 |
| /api/metamodel/drafts/* | 已有定义草稿历史和检查 | 增加语义 diff、正反例摘要、兼容性报告 |
| GET /api/metamodel/term/usage | 拟新增 | 指定术语修订的真实项目使用索引，区别显式/继承使用 |
| POST /api/model-workspaces | 拟新增 | 创建通用项目建模工作区，绑定固定闭包 |
| GET/PUT /api/model-workspaces/{id} | 拟新增 | 获取/保存草稿；If-Match 或 revision 乐观并发 |
| POST /api/model-workspaces/{id}/validate | 拟新增 | 校验精确草稿摘要；旧报告自动标记不适用 |
| POST /api/model-workspaces/{id}/revisions | 拟新增 | 形成不可变项目模型修订；不表示软件已交付 |
| POST /api/metamodel/packages/{id}/publish | 拟新增 | 执行完整发布门禁与审计，而非上传任意文件 |

### 12.1 关系目录不能只靠 domain/range

`applicableRelations` 的来源应取并集并保留区别：

- 属性显式 domain/range，以及允许的继承关系。
- 类形状上的 sh:path、sh:class、sh:or、sh:in、inversePath。
- 复杂约束中由已审查规则描述符给出的适用关系。

不从任意 SPARQL 字符串猜测一个确定的基数。无法解释的约束保留“复杂规则，后端校验”，而非不显示。

例如 GenerationSpecification 页面必须能够显示 appliesRule、inputDesign、usesTechnology、preserves、targetPath；ValueConstraint 必须显示 constrains、valueDatatype、allowedValue、defaultValue。修复展示不能靠篡改本体 domain。

### 12.2 校验响应

```json
{
  "conforms": false,
  "profile": "DevelopmentModel",
  "definitionHash": "<hash>",
  "modelHash": "<hash>",
  "completeness": {"status": "Incomplete", "checked": 20, "failed": 1},
  "issues": [{
    "ruleId": "MM_MODEL_CONTEXT",
    "severity": "Error",
    "entityId": "urn:co:model:task-demo:r1:concept:task",
    "path": "https://example.org/code-ontology/development#hasAttribute",
    "value": "urn:co:model:task-demo:r2:attribute:priority",
    "sourceShape": "<shape-iri>",
    "message": "对象与属性不属于同一模型修订，且未声明固定导入",
    "suggestion": "选择本模型属性，或建立显式版本化导入"
  }]
}
```

状态码：输入语法/模式错误 400；未认证 401；不具备对应资源访问权 403；不存在 404；版本/并发冲突 409。合法校验请求发现语义问题可保持 200 + conforms=false；执行入口对不合格模型继续拒绝，不因为校验 API 返回 200 就执行。

## 13. 前端完整建模辅助设计

本节是设计，不是新网站或界面实现。本轮不引入业务 Action 编辑器。

### 13.1 页面结构

| 页面 | 必须能完成的事情 |
|---|---|
| 定义总览 | 查看五套本体、领域包、版本、术语数、说明覆盖和约束覆盖；显示审计范围 |
| 类型目录/详情 | 查类定义、继承、允许属性/关系、直接及继承约束、正反例、项目引用 |
| 关系目录/详情 | 查方向、源目标、基数、外部引用类型、上下文和证据要求 |
| 属性/值约束 | 编辑字面量类型、枚举、默认值、现有单位及 SHACL 静态约束 |
| 定义草稿与比较 | 原文编辑、保存修订、语义 diff、正反例结果；明确未发布 |
| 项目模型工作区 | 选择已安装类型，建立对象/属性/需求/设计及关联，导入导出 |
| 图谱与问题列表 | 按模型和图空间浏览节点与边；问题定位；查看来源和证据 |
| 模型版本与引用 | 比较修订、检查旧绑定、查询术语使用、迁移预览 |

### 13.2 图谱交互

图谱以选定模型和修订为根。初始显示业务概念、属性、需求、契约、设计与代码的主干，按需展开，不一次显示 611 个定义。

交互规范：

- 节点点击：基本定义、当前实例、属性、入/出关系、约束问题、来源六个面板。
- 关系点击：完整 IRI、自然方向、所属图、声明/观察状态、模型/快照上下文。
- 展开“定义”：跳转类型视图但保留当前实例位置。
- 连线：先选择允许关系，再过滤合法目标；外部定义/datatype 走独立选择器。
- 层级和图空间有图例；颜色之外还用文字/图标标识，避免仅靠颜色传达状态。
- 没有发现关系，显示“当前选定范围内未发现”，不宣称系统不存在该关系。

### 13.3 表单规则

简单 SHACL 属性形状生成表单：string 文本、enum 下拉、boolean 开关、日期控件、数值输入、多值列表、对象引用选择器。

继承约束合并采用约束交集：minCount 取更严格下限、maxCount 取更严格上限；检测冲突而不是后读取的定义覆盖先读取的定义。sh:or 是备选分支，不能误合并成同时必填。

复杂路径和 SPARQL 约束必须展示来源与说明，并允许受控原文/JSON 编辑。无法自动生成表单不等于不执行校验。

编辑后 modelHash 变化，旧校验结果显示“已过期”；保存草稿与形成不可变修订是不同按钮。术语目录仍可显示无实例的类型，但应提示约束支持程度。

## 14. 与现有代码生成流程的关系

本次不是扩充生成器。成熟建模层首先保证生成输入不丢信息、不串版本、不误解类型。

生成前必须形成：

1. 固定定义闭包、模型修订及校验报告。
2. 明确的输入设计、技术栈和转换规则。
3. 每项条款的责任追溯和验证规范。
4. 规则适配器支持性结果；不支持必须明示，不能换成任意代码生成。
5. 当前已有批准与路径安全要求。

旧 eng 生成器与受限 dev Python 数据类适配器继续区分。SHACL 合格不代表代码可生成；代码生成成功不代表实际图已采集；测试关联不代表满足性证据。

在不增加行为的前提下，可先提升静态结构建模质量：对象、属性、类型、关系、枚举、必填和技术映射。这些信息可为现有/后续结构生成提供可靠输入，但本轮不承诺新增数据库、前后端或任意业务生成能力。

## 15. 文件与组件变更蓝图

以下全部为后续实施清单，本轮没有对这些文件进行修改。

| 位置 | 拟改动 | 保护条件 |
|---|---|---|
| ontology/business-code-linkage.ttl | 补 biz:Requirement 与旧术语定义说明 | 修订相关示例、canonicalId 和版本；不 sameAs 合并 |
| ontology/code-ontology.ttl、engineering-semantics.ttl、requirement-change-planning.ttl | 补标签、定义、边界，核查引用 | 不悄悄更改旧关系含义 |
| ontology/ontology-driven-development.ttl | 澄清现有类注释和上下文；不新增行为体系 | 保持现有 dev 类型兼容，语义变更须版本化 |
| shapes/ontology-driven-development-shapes.ttl | 补跨模型、端点、datatype 等缺口 | 既有 DEV_* 正反例全部保留 |
| shapes/business-code-linkage-shapes.ttl | 身份/归属策略及缺失需求类约束 | 分清草稿、领域资产、项目模型作用域 |
| 新 code 结构 shapes | 对支持的代码类型补结构约束 | 不把递归/合法共享关系误判为环错误 |
| models/development-metamodel.package.json | 精确依赖、校验配置和资产登记 | 旧 binding 可查，不能静默重绑定 |
| PackageResolver（拟增） | 统一加载闭包、外部词表、版本锁 | 不在线执行任意 imports |
| metamodel_registry.py | JSON v2、唯一性、引用、关系投影、分层校验 | v0/v1 通过明确适配器兼容 |
| metamodel_authoring.py | 语义 diff、负例/削弱约束回归、发布检查分离 | 保存无效草稿仍允许，发布不得放行 |
| store.py、service.py、http_api.py | 通用修订、使用索引、接口与权限边界 | 复用现有设施，明确迁移，保留用户数据 |
| web/src/metamodel.tsx、lifecycle.tsx | 定义详情、类型/端点过滤、引用选择、多类型和问题定位 | localName 只用于显示，不参与身份解析 |
| tests 与 fixtures | 核心正反例、格式往返、版本失效、削弱约束测试 | 不以全通过代替新增能力的验收 |
| docs/00、17、36、37 与文档索引 | 同步机器基线、运行范围和支持矩阵 | 区分“已实现”“设计中”“兼容保留” |

## 16. 实施阶段与退出标准

不按主观百分比宣称成熟度，按可验证门槛推进。

| 阶段 | 内容 | 退出标准 |
|---|---|---|
| M0 定义基线整理 | 术语清单、引用闭合、labels/comments、同名矩阵 | 611 项现有术语有处理结论；未声明引用为 0；类数随修复重新统计 |
| M1 校验可信 | 身份、端点、跨模型、值类型、正反例与删除约束测试 | A01/A03/A06 被对应规则拒绝；已知合法例仍通过 |
| M2 表达统一 | 领域包解析、JSON v2、外部 IRI、多类型、逆边规范化 | 当前两开发示例的模型数据可在已安装定义闭包下语义往返 |
| M3 可视化建模 | 类型/关系/值表单、图谱、问题定位、使用索引 | 用户无需手工伪造 RDF 节点即可完成静态业务到设计建模 |
| M4 生命周期治理 | 通用服务端草稿、不可变修订、兼容 diff、迁移预览 | 旧模型可重现；冲突写入被拒绝；破坏性变更不得自动发布 |

依赖关系：M0 → M1 → M2 → M3；M4 的存储设计可提前，但发布功能必须依赖 M1 的可信门禁。本轮只交付这些阶段的设计，不执行阶段内实现。

## 17. 本次实际验证与后续验收用例

### 17.1 已执行结果

| 检查 | 命令/方式 | 结果 |
|---|---|---|
| 全量现有测试 | `.venv/bin/python -m unittest discover -s tests -v` | 112 tests，148.973 秒，OK |
| 全仓库 TTL/SHACL | `.venv/bin/python -m code_ontology_platform validate` | 6 个 ontology 文件、4 个 shapes 文件、5 个示例全部 conforms=true |
| CLI 图规模 | 上述命令 | ontology 1942 triples，shapes 1431 triples；含 SDN，不是仅开发包统计 |
| 包内开发示例 | Registry/完整校验 | 平台示例 201 triples、任务示例 373 triples，均通过 |
| 静态清单 | rdflib 遍历显式声明、继承和形状 | 得到 §2 与逐项清单 |
| 内存反例 | 原始示例副本经单点修改后调用当前 Registry | 结果见下表 |

测试过程出现 SQLite 连接未关闭 ResourceWarning；不影响此次测试结果，但需要独立维护。初次尝试 pytest 发现环境未安装，随即使用项目现有 unittest，不安装新依赖。

本次未运行前端浏览器交互验收或构建；前端结论来自源码检查。112 项通过不代表本报告新增缺口已经修复。

### 17.2 反例执行结果与目标

| 实验 | 当前结果 | 成熟化目标 |
|---|---|---|
| 未修改任务示例 | 通过 | 继续通过，并保留 Illustrative/Blocked 语义 |
| 空数据图 | 通过 | 普通 SHACL 可通过；项目完整性明确 Incomplete |
| 插入 dev:misspelledProperty | 通过 | 严格项目定义检查拒绝未知谓词 |
| goal.inModel 改为另一有效模型 | 通过 | MM_MODEL_CONTEXT 拒绝跨模型 motivates |
| task.inModel 改为另一有效模型 | 通过 | MM_MODEL_CONTEXT 拒绝跨模型 hasAttribute |
| constrains 指向不存在的 IRI | 通过 | 发布模型拒绝；草稿标记未解析引用 |
| mappingSource 指向不存在的 IRI | 通过 | 同上，并验证 mappingRole 对应类型 |
| 同模型新增重复 canonicalId 属性 | 通过 | MM_CANONICAL_ID_UNIQUE 拒绝 |
| 去掉枚举/默认值并设置未知 datatype | 通过 | MM_DATATYPE_REGISTERED 拒绝或标为不支持，不能假定可执行 |
| Declared 映射目标改为实际文件 | 通过 | 可继续通过，不升级为 Observed/Satisfied |
| JSON 外部 xsd:string 引用 | 输入被拒绝 | v2 允许合法 DatatypeRef |
| JSON 使用示例 TaskConcept 类型 | 输入被拒绝 | 正式安装领域包后允许；未安装仍拒绝 |
| JSON type 为数组 | 输入被拒绝 | v2 types 支持合法多类型 |
| 所有权仅用 OWL 已声明逆边 | SHACL 拒绝 | 受控规范化后与正边语义一致 |
| dev shapes 草稿清空，只留前缀 | 草稿检查通过 | 发布门禁因负例失守/约束删除拒绝 |
| 两个原始 ID 投影到同一 IRI | 通过，合并为 1 triple | 输入阶段拒绝，不产生模型修订 |

### 17.3 必须加入的验收矩阵

每条 MM/DEV 规则至少包含：最小合法例、最小非法例、继承例、缺字段例；涉及版本时增加跨模型/跨快照例。属性约束还应覆盖字面量类型、空值和多值。

额外测试：

- 反例不能只断言 conforms=false，还应命中预期 ruleId，避免被无关错误“碰巧拦住”。
- 删除 Shape、修改 targetClass、扩大枚举等变异必须被发布回归发现。
- 规范化碰撞必须在 RDF 合并前被发现。
- JSON↔RDF 使用图同构/规范化摘要检查，不用文本顺序比较。
- 草稿保存、模型修订、包发布三条通路不得混用状态。
- 同一份模型由 CLI/API 得到同绑定闭包和一致违规集合。
- 查询显式断言与继承结果要分栏；模型 r1 的查询不混入 r2。
- 新规范不能把原合法演示数据误称为真实成功证据。

## 18. 不增加行为的完整建模案例

采用“任务优先级静态语义与技术表示”，不增加完成任务、分配任务等动作。

### 18.1 建模步骤与结果

| 步骤 | 操作 | 形成的资产 | 必须检查 |
|---|---|---|---|
| 1 | 选择基础包和已安装任务领域包 | 固定 Profile/定义锁 | 依赖版本、术语可解析 |
| 2 | 建项目及模型 r1 | Project、ModelRevision | 绝对 IRI、范围与版本 |
| 3 | 建“任务”概念 | BusinessConcept 或领域子类实例 | 与生产 Task 记录分离 |
| 4 | 建“优先级”属性并连接任务 | BusinessAttribute、hasAttribute | 同模型、canonicalId 唯一 |
| 5 | 建业务目标和需求 | BusinessGoal、Requirement | motivates、能力归属和范围 |
| 6 | 建语义契约与值条款 | SemanticContract、ValueConstraint | XSD 类型、low/medium/high、默认 medium |
| 7 | 建验收条件 | AcceptanceCriterion | 与需求关联；并非已经验证通过 |
| 8 | 建设计决策及表示 | DesignDecision、TechnicalRepresentation | 表示 priority，承接值条款，同模型 |
| 9 | 绑定已有仓库和代码快照 | Repository、CodeSnapshot | 来源、范围、真实摘要 |
| 10 | 建声明映射；采集后建立观察映射 | RealizationMapping | Declared 与 Observed 的证据边界 |
| 11 | 分层校验并保存模型修订 | 报告、不可变 r1 | 符合性、完整性、支持性分别显示 |
| 12 | 将枚举增加 urgent 形成 r2 | 新模型修订及差异报告 | 不修改 r1；列出受影响设计、映射和验证规范 |

如使用现有生成适配器，其原有 BehaviorClause 等必需输入继续按既有案例提供，本轮既不删除它，也不设计新的行为语义。纯静态模型的成熟化验收不以新生成能力为前提。

### 18.2 图谱必须回答的具体查询

1. priority 属性由哪个元模型/领域类定义，绑定哪一版本？
2. 它属于哪个业务概念，受哪些值约束约束？
3. 哪个需求和验收条件要求它存在？
4. 哪些目标表示承接它，设计理由是什么？
5. 哪些映射只是声明，哪些由采集证实？
6. 当前图中的代码事实属于哪个仓库和快照？
7. 该属性在 r1/r2 的约束有什么差异？
8. 哪些设计/验证需要复核，依据是显式使用还是继承依赖？
9. 当前还有哪些未解析引用、跨版本边或缺失约束？
10. 查询结果属于示例、项目草稿、正式修订还是实际代码事实？

这些问题应有固定查询模板和预期结果，作为建模完整性的能力问题，而不是仅展示节点总数。

## 19. 整体完成定义

满足以下条件后，才能宣布“当前本体建模基础成熟”：

- 当前范围的术语全部可查询、可解释、可定位到版本与来源。
- 所有定义引用闭合，同名术语有明确兼容策略。
- 类型、属性、关系、值约束与前端/JSON 表达一致，没有静默信息丢失。
- 项目节点身份、业务 ID、代码定位、模型修订不冲突。
- 关键关系不存在未声明的跨模型连接或悬空目标。
- 正例、反例、削弱约束回归和模型往返均通过。
- 草稿、定义发布、模型修订、代码事实和验收结论严格区分。
- CLI/API/前端使用同一固定定义闭包，查询有明确图范围。
- 能用界面完整建立并检查 §18 的静态建模案例。
- 不通过新增行为概念、扩大生成承诺或放松现有证据门禁来掩盖基础缺口。

最终原则：**本体的成熟度不取决于画出了多少节点，而取决于每个概念是否有明确含义、每条关系是否有合法边界、每份模型是否可验证和可复现，以及工具是否忠实表达了这些定义。**

## 附录 A：关键反例复现方式

在仓库根目录执行以下只读内存检查，不写回实例或定义。输出为当前校验结果；实施修复后应更新预期与回归测试。

```python
from rdflib import Graph, Literal, Namespace
from code_ontology_platform.metamodel_registry import MetamodelRegistry, DEV
from code_ontology_platform.metamodel_authoring import MetamodelAuthoring

r = MetamodelRegistry('.')
t = Namespace('urn:example:task-priority:')
g = Graph().parse('examples/development-task-priority.ttl')

# 反例：目标跨模型，其他结构保持有效。
for p, o in list(g.predicate_objects(t.model)):
    g.add((t.otherModel, p, o))
g.set((t.goal, DEV.inModel, t.otherModel))
print(r._validate_graph(g)['conforms'])  # 当前 True；成熟基线应拒绝。

# 反例：原始 ID 不同，但规范化后碰撞。
model = {
    'metamodelRef': r.ref,
    'nodes': [
        {'id': 'a', 'type': 'code:Repository'},
        {'id': 'urn:engineering-node:a', 'type': 'code:Repository'}
    ],
    'edges': []
}
print(r.validate_model(model))  # 当前 conforms=True，tripleCount=1。

# 反例：清除 dev 约束，只有正例回归仍能通过。
# check 不使用 store，不保存草稿。
a = MetamodelAuthoring(r, None)
draft = a.template()
draft['shapes'] = '@prefix sh: <http://www.w3.org/ns/shacl#> .'
print(a.check(draft)['conforms'])  # 当前 True；不能据此允许发布。
```

## 附录 B：与前次参考方向的关系

前次讨论中借鉴的对象、属性、关系、定义与实例分离、对象中心查询等思路，落实为本文的定义卡、静态建模工作区与版本化图谱。当前明确搁置 Actions/Functions/Interfaces 等行为能力扩展，不因参考外部产品而改变本轮范围。

本设计的决策依据以当前仓库定义、实际校验与反例为主；不是对外部产品能力的复制或兼容声明。
