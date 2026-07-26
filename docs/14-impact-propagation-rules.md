# 影响传播规则

## 1. 设计目标

影响传播不是通用图遍历，而是“ChangeType 在特定关系和上下文中产生何种派生变化”的规则计算。系统必须区分候选、确定、吸收、拒绝和未知，保存每一步的规则、证据和传播决策。

## 2. 核心分析节点

```text
ImpactAssessment
├── sourceChange
├── affectedEntity
├── impactType
├── propagationState
├── certainty
├── riskLevel
├── propagationDecision
├── containmentStatus
├── ruleId
├── reasonCode
├── evidence
└── impactPath
```

同一实体可针对同一 ChangeItem 同时存在 CompileImpact、BehaviorImpact、ContractImpact 等多个 Assessment，不应压缩成一个 `affected=true`。

## 3. 状态机

```text
Unvisited → Candidate → Analyzing
                         ├── Confirmed
                         ├── Contained
                         ├── Rejected
                         └── Unresolved
```

- **Candidate**：由图关系发现，尚未判断；
- **Confirmed**：证据足以证明影响；
- **Contained**：当前节点需要适配，但对外可观察变化被吸收；
- **Rejected**：路径存在，但规则证明与本次变化无关；
- **Unresolved**：动态行为、外部消费者或证据不足，需要人工/运行验证。

Contained 不是“不受影响”，而是“自身受影响但传播停止”。

## 4. 影响类型

```text
CompileImpact
BehaviorImpact
ContractImpact
DataImpact
RuntimeImpact
SecurityImpact
PerformanceImpact
DeploymentImpact
BusinessImpact
VerificationImpact
```

确定性和严重度是独立维度：反射候选可能 certainty 低但 severity Critical；内部日志变化 certainty 高但 risk 低。

## 5. 传播决策

每条规则输出：

- `Continue`：形成派生变化继续；
- `ContinueWithDecay`：继续但降低置信度；
- `StopContained`：当前节点吸收变化；
- `StopRejected`：关系与变化无关；
- `Branch`：向调用者、实现者、契约、数据等多个方向；
- `Escalate`：跨公共契约、安全、共享数据或关键能力，提高风险；
- `RequireManualReview`：自动判断不足。

## 6. 规则结构

```text
WHEN
  ChangeType
  SourceNodeType
  RelationType
  TargetNodeType
  EdgeAttributes
  NodeContext
  Environment/Version/RuntimeContext
THEN
  ImpactType
  State/Certainty/Risk
  DerivedChangeType
  Decision
  EvidenceRequirement
```

规则保存 id、version、priority、specificity、confidence、enabled 和 explanationTemplate。结果关联 appliedRule 和 analysisVersion。

## 7. 传播不是原 ChangeType 原样复制

Repository ReturnTypeChanged 到 Service 后，派生的是 InternalAdaptationRequired；只有 Service 对外签名改变，才继续派生 Service ReturnTypeChanged。ColumnTypeChanged 经过 ORM 可能派生 FieldMappingCompatibilityChanged，再经过 Mapper 可能派生 DataRepresentationChanged 或被吸收。

这是“变化变换”，不是简单标红。

## 8. 常见规则

### MethodDeleted + callsDirectly

直接调用者 Confirmed CompileImpact，派生 CallTargetMissing；`mayCall` 为 Possible/Unresolved。

### ReturnTypeChanged

若调用方使用返回值且类型不兼容，Confirmed CompileImpact；忽略返回值时可能只有 BehaviorCandidate；存在适配转换且外部签名不变时调用方为 Contained。

### FieldTypeChanged + readsField/writesField

使用旧类型 API、赋值到旧类型、传给旧参数时确定编译影响；仅 null 判断可能低风险；Converter 可以吸收类型但不一定吸收语义。

### API Response Field Removed

所有已知消费者字段和严格 Schema 客户端为 ContractImpact；公开 API产生 UnknownConsumerRisk；Provider 内部 Mapper 为直接实现影响。

### MessageMeaningChanged

即使 Schema 不变，也向所有依赖业务语义的消费者传播 SemanticImpact；只做审计存储的消费者和驱动业务动作的消费者风险不同。

### Column nullable true→false

重点反查 writers、默认值依赖和历史数据；纯 reader 通常不是直接目标。false→true 则重点检查 reader 的非空假设。

### Feature rollout 5%→100%

代码无 CompileImpact，受控路径产生 Confirmed RuntimeImpact；按流量系数放大下游容量、数据库和消息风险。

## 9. 吸收点判定

节点成为 ContainmentPoint 至少满足：自身已适配；对外输入/输出/异常/副作用/数据格式/事件/性能可观察契约未变化；不存在未处理的旁路传播。

常见吸收点：Mapper、Adapter、Facade、Serializer、Compatibility Layer、Database Converter。仅签名不变不足以证明吸收；若事件发布、事务或值语义改变，仍需继续传播。

## 10. 路径和证据

ImpactPath 保存有序 Step：source、relation、target、方向、edgeConfidence、ruleDecision、derivedChange。Evidence 可来自 StaticAnalysis、RuntimeTrace、SchemaDiff、Config、Coverage、HumanReview。

报告应输出最短高置信证据路径和必要的替代路径，避免只给一个不可解释的风险分数。

## 11. 置信度与风险

```text
pathConfidence = changeConfidence × edgeConfidence × ruleConfidence × decay
risk = severity × exposure × businessCriticality × recoveryDifficulty × confidenceFactor
```

该公式用于排序，不应伪装成精确概率。跨服务、公开 API、共享数据库、安全和不可逆迁移提高 exposure/severity，而不是提高 certainty。

## 12. 搜索控制

- 对递归调用先做 SCC；
- 设置最大深度、最大路径数、关系白名单和边界预算；
- 按 ChangeType 选择关系，不做全图扩散；
- 已被 Contained/Rejected 的派生变化不继续；
- 相同 `(change, entity, derivedType, context)` 去重；
- 对高风险低置信路径保留 ManualReview，不简单丢弃。

## 13. 规则冲突

优先级建议：确定语义事实 > 明确兼容/吸收规则 > 特定变化规则 > 通用关系规则 > 启发式/文本规则。Specific Rule 覆盖 General Rule，但多种 ImpactType 可以并存。冲突决议也要保存 reason 和被抑制规则。

## 14. 测试、业务和发布衍生

影响实体确定后，规则继续生成：推荐测试、验证缺口、业务能力/规则风险、责任团队、Rebuild/Redeploy、兼容矩阵和部署顺序。这些是影响图的扩展，不应反写成永久代码依赖事实。

## 15. 注意事项

- 不把 `dependsOn+` 直接当影响；
- 不用一个风险分数替代影响类型和证据；
- 不因运行未观察到而 Rejected；
- 不把 Contained 当作无需修改；
- 规则和分析版本必须可重放；
- 人工结论应作为 HumanEvidence，后续可反馈规则学习。