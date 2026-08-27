# 工程语义闭环：Capability → Requirement → Contract → Code → Verification

## 1. 目标

本实现把现有 `code-ontology` 的代码事实图、需求规划图和影响图连接成一条可执行的工程语义链：

```text
Capability
    ↓ specifies
EngineeringRequirement
    ├─ defines → RequirementContract
    ├─ constrainedBy → SemanticContract → OntologyAsset
    ├─ implementedBy ← Code Entity
    └─ verifiedBy ← VerificationMethod → VerificationEvidence → Test/Proof/Report
```

它不是复制 Reqvire，而是吸收其最有价值的工程语义：**显式所有权、契约、验证、证据、覆盖率和 typed impact**，再与本仓库已有的 Method / Field / Call / DataFlow / API / Test 图连接。

本层采用渐进式治理。现有 `code:Requirement` 不被新规则强制改造；需要进入严格闭环的需求使用 `eng:EngineeringRequirement`，它是 `code:Requirement` 的子类。

## 2. 新增资产

- `ontology/engineering-semantics.ttl`：工程语义本体。
- `shapes/engineering-semantics-shapes.ttl`：所有权和验证闭环 SHACL 约束。
- `src/code_ontology_platform/engineering_semantics.py`：确定性 validation、coverage、context collect 和 typed impact 引擎。
- `src/code_ontology_platform/engineering_mcp_gateway.py`：在现有只读 MCP Gateway 上扩展工程语义工具。
- `examples/engineering-semantic-closed-loop.ttl`：RDF 示例。
- `examples/engineering-semantic-closed-loop.graph.json`：平台 JSON Graph 示例。
- `tests/test_engineering_semantics.py`：传播与约束回归测试。

## 3. 核心节点和关系

### EngineeringRequirement

顶层 `EngineeringRequirement` 必须显式指定且只能指定一个 Capability；子需求可以通过 `eng:derivesRequirement` 从父 Requirement 继承 ownership。

### RequirementContract

Requirement-owned Contract 精化“这个 Requirement 到底意味着什么”：

- `SpecificationContract`
- `BehaviorContract`
- `ConstraintContract`
- `StateContract`
- `InputOutputContract`

每个 RequirementContract 必须且只能有一个 EngineeringRequirement owner。

### SemanticContract

SemanticContract 不属于单一 Requirement，而是引用 OntologyAsset 并约束一个或多个 Requirement：

```text
OntologyAsset
     ↑ usesOntology
SemanticContract
     ↑ constrainedBy
EngineeringRequirement
```

### Verification

验证被拆成三层：

```text
VerificationObjective
        ↑ derivedFromObjective
VerificationMethod
        ├─ verifiesRequirement → EngineeringRequirement
        └─ satisfiedByEvidence → VerificationEvidence → concrete artifact
```

`VerificationObjective` 只表达“要证明什么”，不能直接拥有执行证据。

## 4. 与现有代码图的连接

本实现直接复用现有关系，不创建第二套代码模型：

```text
Method / Class / Component
        ── code:implementsRequirement ──→ EngineeringRequirement

TestCase
        ── code:verifies ──→ EngineeringRequirement
        ── code:covers ──→ Method / Class / Contract
```

因此代码方法变化可以反向追踪到 Requirement，再进入 Contract、Semantic Contract 和 Verification；Requirement 变化也可以反向定位实现代码和验证节点。

## 5. Validation

仓库现有 SHACL 校验会自动加载新增 ontology / shapes / example：

```bash
code-ontology-platform validate
```

JSON Graph 也可直接校验：

```bash
code-ontology-engineering validate \
  examples/engineering-semantic-closed-loop.graph.json
```

核心约束：

1. 顶层 EngineeringRequirement 必须有唯一 Capability owner；子 Requirement 可从父节点继承。
2. Requirement-owned Contract 必须有唯一 EngineeringRequirement owner。
3. SemanticContract 必须引用 OntologyAsset，并至少约束一个 EngineeringRequirement。
4. VerificationMethod 必须来自唯一 VerificationObjective。
5. VerificationMethod 至少验证一个 EngineeringRequirement，并至少有一个 VerificationEvidence。
6. VerificationObjective 不得直接拥有 Evidence。
7. VerificationEvidence 必须指向可审计 Artifact。

## 6. Coverage

Coverage 明确区分三个维度：

```text
Implementation Coverage
= 有 code:implementsRequirement 的 leaf EngineeringRequirement / leaf 总数

Verification Coverage
= 有 VerificationMethod 或 TestCase 验证的 leaf EngineeringRequirement / leaf 总数

Verification Evidence Coverage
= 有具体 Evidence 的 VerificationMethod / VerificationMethod 总数
```

执行：

```bash
code-ontology-engineering coverage \
  examples/engineering-semantic-closed-loop.graph.json
```

覆盖率以 leaf Requirement 为基础，避免父需求挂一个测试就掩盖子需求缺口。

## 7. Engineering Context Collect

Context 收集不是向量搜索，也不是任意图邻域。它只沿白名单工程关系收集：

```bash
code-ontology-engineering collect \
  examples/engineering-semantic-closed-loop.graph.json \
  req:token --depth 2
```

允许关系覆盖 Requirement/Capability、Requirement/Contract、Semantic Contract/Ontology、Verification/Evidence、Implementation、Test、Call、Field 和 API implementation。

目的：给 Agent 一个**由工程关系限定的 context package**，而不是把所有“相关”节点塞进上下文。

## 8. Typed Impact

硬规则：

> Graph reachability 只代表候选路径；只有显式 ImpactRule 才能产生 Confirmed impact。

执行：

```bash
code-ontology-engineering impact \
  examples/engineering-semantic-closed-loop.graph.json \
  code:validator --depth 4
```

示例中，修改 `TokenValidator.validate` 会得到：

```text
TokenValidator.validate
    ├─ inverse callsDirectly → AuthMiddleware.authenticate
    └─ implementsRequirement → Reject invalid access tokens
                                   ├─ definesContract → SpecificationContract
                                   ├─ constrainedBy → SemanticContract
                                   ├─ inverse verifiesRequirement → TestVerification
                                   └─ inverse code:verifies → UnitTest
```

每条 impact 保存 `seed / target / targetType / impactType / ruleId / depth / path / state / confidence`。

主要规则包括：Requirement parent/child、Requirement↔Contract、Requirement↔SemanticContract、Ontology→SemanticContract、Requirement↔Implementation、Requirement→Verification/Test、callee→caller、Field→reader/writer、API→implementation、Capability→Requirement。

Verification/Test 自身变化只把 Requirement 作为 context，不继续扩散到实现和 Contract，避免“一个测试变化导致整个功能重做”的过度传播。

## 9. 与规划链的边界

本模块负责**事实语义和确定性分析**，不替代现有规划链：

```text
DesignIntentIR
→ AlignmentArtifact
→ ChangeSet
→ Planning Impact
→ NodeChangeRequirementArtifact
→ Human Gate
```

规划阶段可以把 `EngineeringSemantics.impact()` 的结果作为 ImpactGraph 的确定性 evidence；实现后重新扫描 Actual Graph，再以同一规则复算，实现设计—代码—测试—Requirement 的对账。

本模块不允许 AI 写入 Current Graph，也不把推断候选升级为事实。

## 10. 最小运行方式

```bash
python3 -m venv .venv
.venv/bin/pip install -e .

.venv/bin/code-ontology-platform validate

.venv/bin/code-ontology-engineering validate \
  examples/engineering-semantic-closed-loop.graph.json

.venv/bin/code-ontology-engineering coverage \
  examples/engineering-semantic-closed-loop.graph.json

.venv/bin/code-ontology-engineering collect \
  examples/engineering-semantic-closed-loop.graph.json req:token --depth 2

.venv/bin/code-ontology-engineering impact \
  examples/engineering-semantic-closed-loop.graph.json code:validator --depth 4
```

## 11. MCP 接入

工程语义 MCP 不是第二套平台，它继承现有 `ReadOnlyMcpGateway`，并通过现有 `PlatformService._analysis_graph` 读取相同的 SQLite graph snapshot。

启动：

```bash
code-ontology-engineering-mcp \
  --database data/code-ontology.db
```

新增 4 个只读工具：

```text
engineering_validate
engineering_coverage
engineering_collect
engineering_impact
```

它们都支持现有 graph scope：`repositoryId / graphSpace / revision`。`engineering_collect` 接收 `entityId + depth`，`engineering_impact` 接收 `entityIds + depth`。

MCP 层只负责参数校验、图快照解析和结果裁剪；所有工程语义算法仍由同一个 `EngineeringSemantics` 确定性实现提供，因此 CLI、CI 与 Agent 得到同一种结果语义。
