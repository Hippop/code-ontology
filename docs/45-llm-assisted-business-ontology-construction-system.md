# 基于大模型的业务需求文档本体构建系统设计

> 文档定位：面向业务需求/特性文档，设计一套可审计、可验证、可人工干预、可持续演进的领域本体构建系统。目标不是“让 LLM 一次性输出 OWL”，而是建立从 Requirement 到 Competency Question、Candidate Ontology、Ontology Alignment、Formal Ontology、Validation、Release 的工程化闭环，并与现有 code-ontology 平台衔接。

---

## 1. 背景与问题

业务需求文档通常包含业务概念、能力、规则、状态、约束、角色、对象关系和行为，但它们以自然语言存在，存在以下问题：

1. 同一概念存在多个名称；
2. 同一个词在不同上下文中可能表达不同概念；
3. 文档中的名词并不天然等于本体 Class；
4. 文档中的动词并不天然等于 ObjectProperty；
5. 很多关键语义藏在约束、条件、状态变化和例外中；
6. LLM 容易产生文档中不存在的概念和关系；
7. 多批文档增量导入时容易重复建模；
8. 即使生成了 OWL，也无法证明该本体覆盖了业务需求；
9. 业务专家无法直接审查复杂 RDF/OWL；
10. 本体一旦进入下游代码生成、知识图谱和波及分析，就必须具备版本、来源和变更治理能力。

因此系统需要解决的不是简单的 `text → ontology`，而是：

```text
自然语言需求
  ↓
需求语义理解
  ↓
可验证的问题定义
  ↓
候选概念与关系发现
  ↓
与已有本体对齐和复用
  ↓
正式本体生成
  ↓
语法/语义/业务覆盖验证
  ↓
人工批准
  ↓
版本化发布
```

---

## 2. 系统目标

### 2.1 核心目标

系统最终需要做到：

```text
Requirement Documents
        ↓
Competency Questions
        ↓
Candidate Ontology
        ↓
Aligned Domain Ontology
        ↓
OWL + SHACL + Documentation
        ↓
CQ/SPARQL + Reasoner + Quality Gate
        ↓
Approved Ontology Release
```

并保证任意本体元素都可以回答：

```text
这个 Class/Property/Axiom 为什么存在？
    ↓
来自哪个 CQ？
    ↓
来自哪个 Requirement？
    ↓
来自哪份文档、哪一段原文？
```

### 2.2 非目标

第一阶段不追求：

- 全自动替代本体专家；
- 一次生成企业级完整本体；
- 仅靠向量相似度完成概念合并；
- 将所有需求名词都转成 Class；
- 将业务实例和领域类型混在一个阶段生成；
- 让 Agent 直接修改已发布本体且绕过人工 Gate。

系统原则是：

> LLM 负责候选生成和受约束语义判断；规则、Reasoner、SHACL、SPARQL 和人工 Gate 负责确定性验证与最终治理。

---

## 3. 总体架构

```text
┌──────────────────────────────────────────────────────────────┐
│                    Requirement Sources                       │
│ Markdown / Word / PDF / Feature / User Story / Specification│
└────────────────────────────┬─────────────────────────────────┘
                             ↓
┌──────────────────────────────────────────────────────────────┐
│ 1. Document Ingestion & Requirement IR                       │
│ 文档解析、切片、来源定位、Requirement 单元化                 │
└────────────────────────────┬─────────────────────────────────┘
                             ↓
┌──────────────────────────────────────────────────────────────┐
│ 2. Ontology Requirement Engineering                          │
│ Requirement → Competency Question / Semantic Requirement     │
└────────────────────────────┬─────────────────────────────────┘
                             ↓
                    [Human Gate A: CQ]
                             ↓
┌──────────────────────────────────────────────────────────────┐
│ 3. Ontology Learning                                         │
│ Term → Type → Taxonomy → Relation → Constraint Candidate     │
└────────────────────────────┬─────────────────────────────────┘
                             ↓
                 Candidate Ontology Graph
                             ↓
┌──────────────────────────────────────────────────────────────┐
│ 4. Ontology Alignment & Reuse                                │
│ Meta Ontology / Common Ontology / Existing Domain Ontology   │
│ exact → lexical → semantic → structural → LLM judgement      │
└────────────────────────────┬─────────────────────────────────┘
                             ↓
                 [Human Gate B: Modeling]
                             ↓
┌──────────────────────────────────────────────────────────────┐
│ 5. Formalization                                             │
│ RDFS / OWL / SHACL / Annotation / Provenance                 │
└────────────────────────────┬─────────────────────────────────┘
                             ↓
┌──────────────────────────────────────────────────────────────┐
│ 6. Verification                                              │
│ Parse / SHACL / Reasoner / CQ→SPARQL / Coverage / Quality    │
└────────────────────────────┬─────────────────────────────────┘
                             ↓
                 [Human Gate C: Release]
                             ↓
┌──────────────────────────────────────────────────────────────┐
│ 7. Ontology Registry & Versioning                            │
│ Draft / Approved / Deprecated / Version / Diff / Provenance  │
└────────────────────────────┬─────────────────────────────────┘
                             ↓
┌──────────────────────────────────────────────────────────────┐
│ 8. Downstream Integration                                    │
│ Business KG / Code Ontology / Code Generation / Impact       │
└──────────────────────────────────────────────────────────────┘
```

---

## 4. 三层本体体系

为了避免每批需求都从零建模，系统将本体拆成三层。

### 4.1 L0：Meta Ontology

表达“业务建模本身”的通用类型：

```text
BusinessObject
Capability
Actor
Role
Service
Process
Event
State
Policy
Rule
Constraint
Resource
InformationObject
Relationship
```

它的作用不是描述具体网络设备，而是规定“领域本体可以使用哪些基本建模构件”。

### 4.2 L1：Common Business Ontology

跨多个业务域复用：

```text
Device
Organization
User
Location
Version
LifecycleState
Identifier
Configuration
Alarm
Task
```

### 4.3 L2：Domain Ontology

具体业务领域概念：

```text
NetworkDevice
Router
Switch
Interface
VLAN
RoutingPolicy
Link
```

继承示例：

```text
Resource
  └─ Device
      └─ NetworkDevice
          ├─ Router
          ├─ Switch
          └─ Firewall
```

系统必须优先执行：

```text
Reuse > Extend > Create
```

即：优先复用已有概念；无法复用时扩展；只有没有合适语义时才创建新概念。

---

## 5. 核心中间产物

本系统不允许 `Document → OWL` 直接跳跃。必须保留以下中间产物。

### 5.1 Requirement Unit

```yaml
id: REQ-001
source_document: network-feature.md
source_range: L120-L136
text: 核心路由器必须至少配置两条上联链路
context:
  feature: NetworkReliability
  section: Uplink
status: parsed
```

### 5.2 Competency Question

```yaml
id: CQ-001
requirement_ids:
  - REQ-001
question: 一个核心路由器至少需要多少条上联链路？
expected_answer_type: cardinality
priority: must
status: approved
```

CQ 是连接业务需求和本体设计的关键中间表示。

### 5.3 Semantic Requirement

```yaml
id: SR-001
source_requirement: REQ-001
semantic_type: cardinality_constraint
subject: CoreRouter
predicate: hasUplink
object: Link
operator: min
value: 2
confidence: 0.95
```

### 5.4 Candidate Concept

```yaml
id: CAND-CLASS-001
label: Router
kind: class
suggested_parent: NetworkDevice
definition: 能够执行三层数据包转发和路由选择的网络设备
source_requirements:
  - REQ-003
  - REQ-011
confidence: 0.93
```

### 5.5 Candidate Relation

```yaml
id: CAND-REL-001
label: hasInterface
domain: NetworkDevice
range: Interface
relation_type: object_property
source_requirements:
  - REQ-006
confidence: 0.91
```

### 5.6 Alignment Decision

```yaml
candidate: Router
existing: net:Router
decision: reuse
method:
  - exact_label
  - semantic_match
  - structural_match
confidence: 0.98
review_status: approved
```

可选 decision：

```text
reuse
subclass_of
superclass_of
equivalent_to
related_to
create_new
reject
needs_review
```

### 5.7 Formal Ontology Change Set

```yaml
change_set: ONT-CHG-017
base_version: 1.4.0
adds:
  classes:
    - CoreRouter
  properties: []
  axioms:
    - CoreRouter SubClassOf Router
    - CoreRouter SubClassOf hasUplink min 2 Link
updates: []
deprecates: []
trace:
  - CQ-001
  - REQ-001
```

### 5.8 Validation Report

```yaml
syntax_valid: true
shacl_valid: true
reasoner_consistent: true
cq_coverage: 0.94
requirement_traceability: 1.0
orphan_concept_ratio: 0.03
unresolved_alignment_count: 2
release_recommendation: review
```

---

## 6. Agent 设计

Agent 数量应保持较少，职责按“语义阶段”划分，而不是每个小步骤都创建一个 Agent。

### 6.1 Ontology Orchestrator

负责整个流程状态机，不负责具体领域判断。

职责：

```text
创建 ontology construction run
组织各阶段执行
检查阶段产物是否满足 schema
触发 Human Gate
失败重试
保存审计记录
发布最终结果
```

输入：文档集合、目标领域、已有本体版本。

输出：Ontology Construction Run。

### 6.2 Requirement & CQ Analyst

合并 Requirement 理解和 CQ 生成两个职责。

职责：

```text
Requirement Chunking
Requirement IR
Semantic Requirement 提取
Competency Question 生成
CQ 去重和覆盖分析
```

参考思想：IDEA2 / CQ-driven ontology engineering。

### 6.3 Ontology Modeling Agent

合并 Ontology Learning、Alignment 和 Formalization 的语义判断能力。

职责：

```text
Term Discovery
Term Typing
Taxonomy Discovery
Relation Discovery
Constraint Discovery
Existing Ontology Retrieval
Reuse / Extend / Create 判断
Ontology Change Set 生成
OWL / SHACL Formalization 建议
```

参考思想：LLMs4OL、LABKAG、OntoExtend、CQ4OE。

### 6.4 Ontology Verification Agent

负责“解释验证结果”和“定位问题”，确定性校验本身交给工具。

职责：

```text
分析 SHACL violation
分析 Reasoner inconsistency
分析 CQ coverage gap
发现 orphan / duplicate / suspicious concept
生成修复建议
决定回退到哪个阶段
```

因此系统只需要 **4 个 Agent**：

```text
Ontology Orchestrator
Requirement & CQ Analyst
Ontology Modeling Agent
Ontology Verification Agent
```

---

## 7. Skill 设计

Skill 应封装稳定的领域方法，而不是封装数据库 CRUD。

### Skill 1：`extract-ontology-requirements`

目标：从需求中产生可审查的本体需求。

内部步骤：

```text
Document
→ Requirement Unit
→ Semantic Requirement
→ Competency Question
```

强制规则：

- 每个 CQ 必须追溯到至少一个 Requirement；
- 不允许生成没有来源的业务事实；
- 区分类型定义、实例事实、行为规则和约束；
- 不将 UI/实现细节默认升级为领域概念。

### Skill 2：`build-domain-ontology`

目标：从批准的 CQ 和 Semantic Requirement 生成候选本体并完成对齐。

内部步骤：

```text
Term
→ Type
→ Taxonomy
→ Relation
→ Constraint
→ Existing Ontology Retrieval
→ Alignment
→ Change Set
```

强制规则：

```text
Reuse > Extend > Create
Evidence before assertion
Candidate != Approved
Class != Instance
Concept != term
Constraint != relationship
```

### Skill 3：`verify-ontology-release`

目标：判断本体是否具备发布条件。

内部步骤：

```text
OWL parse
→ SHACL
→ Reasoner
→ CQ/SPARQL
→ Traceability
→ Quality Metrics
→ Release Advice
```

最终只保留 **3 个核心 Skill**，减少 Agent 上下文切换。

---

## 8. MCP / Tool 设计

MCP Tool 必须尽量是确定性的，不把“让 LLM 判断”包装成 Tool。

### 8.1 文档工具

```text
document.list
读取输入文档列表

document.read
读取指定段落并保留 source locator

document.search
按关键词或语义搜索需求原文
```

### 8.2 Requirement 工具

```text
requirement.create_ir
创建结构化 Requirement IR

requirement.trace
返回 Requirement → Document Source

requirement.coverage
统计 Requirement 是否被 CQ / ontology element 覆盖
```

### 8.3 Ontology Registry 工具

```text
ontology.get_version
获取指定 ontology/version

ontology.search_elements
搜索已有 Class / Property / Shape / Axiom

ontology.get_neighborhood
查询某概念上下游结构

ontology.diff
比较两个本体版本

ontology.propose_change_set
保存 Candidate Change Set

ontology.publish
只允许批准状态进入 registry
```

### 8.4 Ontology Validation 工具

```text
ontology.parse
RDF/Turtle/OWL 语法校验

ontology.shacl_validate
运行 SHACL

ontology.reason
运行 OWL Reasoner

ontology.detect_duplicates
标签、IRI、语义和结构重复检查

ontology.detect_orphans
发现孤立 Class / Property
```

### 8.5 CQ 工具

```text
cq.store
保存 CQ

cq.generate_sparql_template
将批准 CQ 转换为 SPARQL 测试模板

cq.execute
针对 sample ABox / fixture 执行

cq.coverage
统计 CQ coverage
```

### 8.6 Provenance 工具

```text
provenance.link
建立 Requirement/CQ/OntologyElement 追溯关系

provenance.trace
双向查询来源
```

---

## 9. Human Gate 设计

人工不应参与每一步，只参与高价值决策。

### Gate A：CQ Approval

业务专家审查：

```text
需求理解是否正确？
CQ 是否覆盖核心业务问题？
是否漏掉规则、状态、异常和约束？
是否混入实现细节？
```

### Gate B：Ontology Modeling Approval

领域专家/本体专家重点审查：

```text
概念边界
Class vs Instance
Taxonomy
Relation 方向
Existing Ontology reuse
同义概念合并
Constraint 是否正确
```

### Gate C：Release Approval

只审查最终 diff，而不是重新阅读全部需求：

```text
Added Class
Added Property
Changed Axiom
Deprecated Element
CQ Coverage Delta
Validation Result
Breaking Change
```

---

## 10. 端到端执行流程

### Phase 0：Run 初始化

输入：

```yaml
domain: network-management
source_documents:
  - feature-a.md
  - feature-b.md
base_ontology: network-ontology@1.3.0
mode: incremental
```

输出：

```text
OntologyConstructionRun
```

### Phase 1：文档解析

```text
Document
→ section/chunk
→ Requirement Unit
→ source locator
```

切片原则：

- 优先保持 requirement / scenario / rule 完整；
- 不按固定 token 粗暴切割；
- 保留章节、标题、表格和上下文；
- 每个结构化结果必须携带 provenance。

### Phase 2：CQ 和 Semantic Requirement

针对每个 Requirement 识别：

```text
Concept Definition
Relationship
Behavior
State Transition
Constraint
Cardinality
Policy
Exception
Precondition
Postcondition
```

然后生成 CQ。

例：

```text
Requirement:
核心路由器必须至少配置两条上联链路。
```

得到：

```text
Semantic Requirement:
CoreRouter --hasUplink--> Link
minCardinality = 2

CQ:
一个核心路由器至少需要配置多少条上联链路？
```

Gate A 批准后进入下一阶段。

### Phase 3：Ontology Learning

按照 LLMs4OL 思路分阶段执行：

```text
Terminology Discovery
       ↓
Term Typing
       ↓
Taxonomy Discovery
       ↓
Non-taxonomic Relation Discovery
       ↓
Constraint / Axiom Candidate Discovery
```

必须保留 candidate confidence 和 evidence。

### Phase 4：Ontology Alignment

对每个 Candidate Concept：

```text
1. IRI exact match
2. normalized label match
3. synonym match
4. embedding retrieval
5. taxonomy neighborhood match
6. property signature match
7. LLM constrained judgement
```

例如：

```text
candidate: Router
retrieved:
  net:Router            0.97
  common:NetworkDevice  0.82
  infra:Node            0.55
```

Agent 不能只根据 embedding score 决策，而应综合：

```text
definition
parent class
relations
domain/range
usage context
CQ intent
```

### Phase 5：Formalization

从批准的 Candidate Graph 生成：

```text
RDFS taxonomy
OWL object/datatype properties
OWL restrictions
SHACL operational constraints
annotations
provenance
```

OWL 与 SHACL 分工：

```text
OWL：表达领域真理、可推理语义
SHACL：表达数据/模型必须满足的工程约束
```

不要把所有约束都塞进 OWL。

### Phase 6：Validation

分五层验证。

#### V1 Syntax

```text
RDF parse
IRI validity
namespace consistency
```

#### V2 Structural

```text
Class parent validity
Property domain/range
cycle detection
orphan element
undefined reference
```

#### V3 Semantic

```text
OWL consistency
unsatisfiable class
contradictory restriction
```

#### V4 Constraint

```text
SHACL validation
```

#### V5 Business Coverage

```text
Requirement → CQ coverage
CQ → ontology elements coverage
CQ → SPARQL answerability
```

这一层才是“本体是否真正满足需求”的核心。

### Phase 7：Release

发布前生成 Ontology Change Set：

```text
Base v1.3.0
      ↓
Candidate v1.4.0

Added
Changed
Deprecated
Breaking
Coverage Delta
Validation Result
```

Gate C 批准后：

```text
Draft → Approved → Released
```

---

## 11. 可追溯模型

建议形成如下主链：

```text
DocumentFragment
    ↓ contains
Requirement
    ↓ motivates
CompetencyQuestion
    ↓ requires
SemanticRequirement
    ↓ supportedBy
OntologyElement
    ↓ materializedAs
OWL / SHACL Artifact
    ↓ verifiedBy
ValidationCase
    ↓ produces
ValidationEvidence
```

任意 OntologyElement 必须至少记录：

```text
iri
label
definition
kind
status
introduced_in_version
source_requirements
source_cqs
evidence
confidence
approved_by
```

对于自动生成但没有 provenance 的 ontology element，Release Gate 默认失败。

---

## 12. 图空间设计

为了避免 Candidate 污染正式本体，应明确区分多个图空间：

```text
Current Ontology Graph
    当前已发布事实

Candidate Ontology Graph
    LLM 新发现但未批准的元素

Aligned Ontology Graph
    与已有本体完成对齐的候选

Proposed Ontology Graph
    准备提交人工审批的目标图

Approved Ontology Graph
    已通过 Gate B

Released Ontology Graph
    正式版本

Validation Graph
    CQ、测试、Evidence、Violation
```

原则：

> Candidate、Proposed、Approved、Released 绝不能通过原地覆盖表达状态变化。

---

## 13. 质量指标

### 13.1 Requirement Coverage

```text
有 CQ 覆盖的 Requirement / 需要本体表达的 Requirement
```

### 13.2 CQ Coverage

```text
可由 ontology 支持回答的 CQ / Approved CQ
```

### 13.3 Traceability Coverage

```text
具有 Requirement/CQ provenance 的 ontology elements / 全部新增 ontology elements
```

目标应为 100%。

### 13.4 Reuse Ratio

```text
复用已有元素数量 / 本次涉及元素总量
```

用于监测 LLM 是否不断重复造概念。

### 13.5 Duplicate Ratio

```text
潜在重复概念 / 总概念
```

### 13.6 Orphan Ratio

```text
没有 taxonomy/relation/CQ 支持的孤立元素 / 总元素
```

### 13.7 Human Rejection Rate

```text
被人工拒绝的 candidate / 全部 candidate
```

长期可以作为 Prompt、模型和规则优化信号。

### 13.8 Hallucination Rate

没有 Requirement、CQ 或 approved external ontology evidence 支持的生成断言比例。

---

## 14. 评测体系

系统上线前需要建立固定 benchmark，而不是只看几个 demo。

### 14.1 Gold Dataset

人工准备小规模高质量样本：

```text
Requirement Documents
Gold CQ
Gold Classes
Gold Taxonomy
Gold Relations
Gold Constraints
Gold Alignment
Gold OWL/SHACL
```

### 14.2 Pipeline 分段评测

分别评测：

```text
Requirement → CQ
Term Extraction
Term Typing
Taxonomy
Relation
Constraint
Alignment
Formalization
CQ Answerability
```

否则端到端失败时无法定位是哪一步的问题。

### 14.3 对比实验

至少支持：

```text
Baseline A: One-shot LLM Document → OWL
Baseline B: Multi-step without reuse
Baseline C: Full pipeline with reuse + gates
```

比较：

```text
precision
recall
CQ coverage
reuse ratio
hallucination rate
expert correction count
cost
time
```

---

## 15. 开源项目的吸收方式

系统不建议直接绑定某一个开源项目，而是按能力吸收。

| 开源方向 | 吸收能力 | 系统位置 |
| --- | --- | --- |
| LLMs4OL | Term Typing、Taxonomy、Relation、Ontology Learning 分解 | Phase 3 |
| LABKAG-LLMs4OL | Text2Ontology pipeline 和实现参考 | Phase 3 |
| IDEA2 | Requirement → CQ、expert-in-the-loop、provenance | Phase 2 |
| CQ4OE / MASEO | CQ → Ontology、Multi-Agent ontology generation、evaluation | Phase 5/6 |
| OntoExtend | Existing ontology retrieval、reuse-first、OWL/SHACL extension | Phase 4 |
| OntoGPT | Schema-driven extraction；后续可用于 Ontology Population | 下游 ABox |
| Automated Ontology Generation | LangGraph 多 Agent pipeline 设计参考 | Orchestration |

推荐策略：

```text
借鉴算法和 pipeline
> 封装适配层
> 保持内部 IR 稳定
> 不让任何单一开源项目成为平台数据模型
```

这样未来更换 LLM、embedding、reasoner 或 ontology learner 不影响核心工作流。

---

## 16. 与现有 code-ontology 平台的集成

本方案不是替换现有 code-ontology，而是补齐它的“业务领域本体从哪里来”。

目标集成链：

```text
Business Requirement Documents
        ↓
本方案
        ↓
Approved Domain Ontology
        ↓
Business Semantic Graph
        ↓
Engineering Semantics
        ↓
Requirement / Contract / Verification
        ↓
Code Ontology / Code Graph
        ↓
Change Planning
        ↓
Code Generation
        ↓
Pre-commit Impact Verification
```

现有仓库能力可复用：

```text
document_ingestion.py
用于 Requirement 文档摄取，可扩展 Ontology Requirement IR

metamodel_registry.py
可扩展为 Meta/Common/Domain Ontology Registry

metamodel_authoring.py
可作为人工建模/修订入口

metamodel_quality.py
可扩展为 ontology quality evaluator

ontology_codegen.py
继续承担已批准本体到确定性代码模型的下游生成

semantic_validation.py
扩展 OWL/SHACL/CQ validation

mcp_gateway.py
增加 ontology construction 只读/受控工具入口

store.py
保存 run、candidate、alignment、gate、evidence、version
```

不建议第一阶段直接修改上述模块，而应先新增独立 ontology-construction domain service，验证模型后再融合。

---

## 17. 推荐代码模块边界

未来实现可采用：

```text
src/code_ontology_platform/
  ontology_construction/
    models.py
    ingestion.py
    requirement_analysis.py
    cq.py
    learning.py
    alignment.py
    formalization.py
    validation.py
    provenance.py
    registry.py
    workflow.py
```

其中：

```text
models.py
内部稳定 IR

ingestion.py
Document → Requirement Unit

requirement_analysis.py
Semantic Requirement

cq.py
CQ lifecycle / coverage / SPARQL template

learning.py
Term / Type / Taxonomy / Relation / Constraint Candidate

alignment.py
Existing ontology retrieval + alignment decision

formalization.py
Candidate → OWL / SHACL

validation.py
Parse / Reasoner / SHACL / CQ Coverage

provenance.py
Requirement ↔ CQ ↔ OntologyElement

registry.py
Draft / Approved / Released ontology version

workflow.py
阶段状态机 + Gate
```

---

## 18. 数据存储建议

第一阶段不必引入复杂基础设施。

```text
SQLite/PostgreSQL
保存 workflow metadata、candidate、gate、audit、version

RDFLib / Oxigraph / Jena
保存和处理 RDF/OWL

FAISS / pgvector
Existing ontology semantic retrieval

Git
保存 ontology artifact、SHACL、CQ fixture 和版本 diff
```

内部权威数据建议：

```text
Workflow state → relational DB
Ontology semantics → RDF graph
Large document → file/object storage
Versioned artifact → Git
Embedding → vector index
```

---

## 19. MVP 设计

不要一开始实现完整平台。MVP 只做一个垂直闭环。

### MVP 输入

```text
10~30 份业务需求 Markdown
已有一个小型 Meta Ontology
```

### MVP 输出

```text
requirements.json
competency-questions.yaml
candidate-ontology.yaml
alignment-decisions.yaml
domain-ontology.ttl
domain-shapes.ttl
validation-report.json
traceability.json
```

### MVP 只实现三个 Skill

```text
extract-ontology-requirements
build-domain-ontology
verify-ontology-release
```

### MVP 只实现四个 Agent

```text
Ontology Orchestrator
Requirement & CQ Analyst
Ontology Modeling Agent
Ontology Verification Agent
```

### MVP 必须打通的测试

```text
Requirement → CQ
CQ → Concept/Relation
Candidate → Existing Ontology Alignment
Approved Candidate → TTL
TTL → Parse
TTL → SHACL
CQ → coverage
OntologyElement → Requirement trace
```

如果这条链稳定，再增加复杂 Reasoner、外部 ontology reuse、ABox population 和 UI。

---

## 20. 分阶段实施路线

### Stage 1：Ontology Requirement Pipeline

目标：

```text
Document → Requirement → CQ → Semantic Requirement
```

完成标准：

- 100% provenance；
- Human Gate A 可执行；
- CQ coverage 可计算。

### Stage 2：Ontology Learning

目标：

```text
CQ + Requirement → Candidate Class/Relation/Taxonomy/Constraint
```

完成标准：

- candidate schema 固定；
- 每个 candidate 有 evidence/confidence；
- 可建立 gold dataset 做 precision/recall。

### Stage 3：Ontology Reuse & Alignment

目标：

```text
Candidate + Existing Ontology → Reuse/Extend/Create
```

完成标准：

- 支持多策略 retrieval；
- 形成 Alignment Decision；
- Human Gate B 可执行；
- Reuse Ratio 可统计。

### Stage 4：Formalization & Verification

目标：

```text
Approved Model → OWL/SHACL → Validation
```

完成标准：

- RDF parse；
- SHACL pass；
- Reasoner consistency；
- CQ coverage；
- traceability 100%。

### Stage 5：Registry & Incremental Evolution

目标：

```text
v1.0 + New Requirement → Ontology Change Set → v1.1
```

完成标准：

- ontology diff；
- breaking change detection；
- deprecation；
- release history；
- incremental alignment。

### Stage 6：Integration with Code Ontology

目标：

```text
Domain Ontology
→ Business Semantic Graph
→ Engineering Semantics
→ Code Graph
```

使业务概念真正参与：

```text
代码生成
需求到代码追溯
波及分析
架构约束
测试覆盖分析
变更完整性验证
```

---

## 21. 一个最小示例

输入需求：

```text
网络设备具有多个接口。
路由器是一种网络设备。
核心路由器必须至少有两条上联链路。
接口可以绑定一个 VLAN。
```

### Requirement IR

```text
REQ-1 NetworkDevice has Interface
REQ-2 Router is NetworkDevice
REQ-3 CoreRouter hasUplink min 2 Link
REQ-4 Interface boundTo VLAN
```

### CQ

```text
CQ-1 一个网络设备有哪些接口？
CQ-2 路由器属于哪类设备？
CQ-3 一个核心路由器至少需要多少条上联链路？
CQ-4 一个接口可以绑定什么？
```

### Candidate Ontology

```text
Class:
NetworkDevice
Router
CoreRouter
Interface
Link
VLAN

Taxonomy:
Router subClassOf NetworkDevice
CoreRouter subClassOf Router

Relation:
NetworkDevice hasInterface Interface
Router hasUplink Link
Interface boundTo VLAN

Constraint:
CoreRouter hasUplink min 2 Link
```

### Alignment

假设已有：

```text
common:Device
common:NetworkInterface
```

则可能得到：

```text
NetworkDevice subClassOf common:Device
Interface equivalentTo common:NetworkInterface
Router create_new
CoreRouter create_new
```

### Formal Ontology

```turtle
:Router rdfs:subClassOf :NetworkDevice .
:CoreRouter rdfs:subClassOf :Router .

:hasInterface a owl:ObjectProperty ;
    rdfs:domain :NetworkDevice ;
    rdfs:range :Interface .

:CoreRouter rdfs:subClassOf [
    a owl:Restriction ;
    owl:onProperty :hasUplink ;
    owl:minQualifiedCardinality "2"^^xsd:nonNegativeInteger ;
    owl:onClass :Link
] .
```

最终所有元素都能追溯：

```text
CoreRouter
  ← CQ-3
  ← REQ-3
  ← network-feature.md#uplink
```

---

## 22. 关键设计决策

### ADR-1：不用 One-shot Document → OWL

原因：不可解释、不可分段评测、容易 hallucination、难以增量复用。

### ADR-2：CQ 作为业务需求与本体之间的一级对象

原因：CQ 同时承担 scope、validation 和 traceability。

### ADR-3：Candidate Graph 与 Released Graph 隔离

原因：LLM 输出永远是 proposal，不应直接成为事实。

### ADR-4：Reuse before Create

原因：企业本体长期演化最大的风险之一是同义概念膨胀。

### ADR-5：OWL 与 SHACL 分工

原因：领域语义与工程验证约束属于不同关注点。

### ADR-6：Agent 少而稳定，Tool 多而确定

原因：语义判断集中在 Agent；解析、查询、Reasoner、SHACL、diff 等应保持 deterministic。

### ADR-7：所有生成结果必须带 provenance

原因：没有来源就无法审查、修复、演化和用于下游代码决策。

---

## 23. 最终系统形态

系统成熟后，用户体验应是：

```text
上传业务需求文档
      ↓
系统识别 Requirement
      ↓
自动生成 CQ
      ↓
业务专家批量确认
      ↓
自动发现概念、层级、关系、约束
      ↓
自动与企业已有本体对齐
      ↓
专家只处理低置信度冲突
      ↓
自动生成 OWL + SHACL
      ↓
自动执行 Reasoner / SHACL / CQ Test
      ↓
展示 Ontology Diff 和 Coverage
      ↓
人工批准 Release
      ↓
领域本体进入业务图谱和代码开发链
```

核心价值不是“把文本变成 TTL”，而是建立：

> **Requirement → CQ → Ontology → Verification → Code**

之间长期可追溯、可验证、可增量演进的语义主轴。

---

## 24. 推荐的下一步

实施顺序建议严格按下面推进：

```text
1. 固化 Requirement/CQ/Candidate/Alignment IR
2. 做 Requirement → CQ
3. 做 Candidate Ontology Learning
4. 做 Existing Ontology Alignment
5. 做 OWL/SHACL Formalization
6. 做 CQ Coverage + Reasoner + SHACL
7. 做 Ontology Version / Diff / Release
8. 最后接入现有 code-ontology 全链路
```

第一阶段真正应该验证的不是“LLM 能不能生成一个漂亮的 ontology”，而是三个指标：

```text
A. Requirement 是否被正确理解？
B. Ontology 是否能够回答 Approved CQ？
C. 新增 OntologyElement 是否都能追溯到需求证据？
```

只有这三条稳定之后，自动本体构建才具备进入代码生成、波及分析和工程治理链路的基础。
