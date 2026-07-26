# 业务、需求、规则与责任模型

## 1. 设计目标

技术影响必须翻译成业务影响和协作对象。仅输出“18 个方法、3 张表、2 个消费者”无法支撑产品、测试、发布和治理决策。业务层用于回答影响哪些能力、流程、需求、验收条件和业务规则，以及哪些团队需要维护、评审或审批。

## 2. 最终节点

```text
BusinessEntity
├── BusinessDomain
├── BoundedContext
├── BusinessCapability
├── BusinessProcess
├── BusinessProcessStep
├── UseCase
├── BusinessRule
├── BusinessEvent
├── Requirement
├── AcceptanceCriterion
├── ServiceLevelObjective
└── ComplianceRequirement

OrganizationEntity
├── Team
├── Role
├── Person
├── OnCallGroup
└── ReviewPolicy
```

BusinessCapability 是长期稳定聚合中心；Requirement 是阶段性交付对象；BusinessRule 是长期必须满足的约束；BusinessProcess 表达顺序、分支和补偿。

## 3. 最终关系

```text
Entity supportsCapability Capability
Entity realizesUseCase UseCase
Entity participatesInProcess Process
Entity implementsProcessStep Step
Entity implementsRequirement Requirement
Entity implementsAcceptanceCriterion Criterion
Entity enforcesRule BusinessRule
TechnicalEvent representsBusinessEvent BusinessEvent
Requirement contributesTo Capability
Capability dependsOnCapability Capability
Step precedes/follows/branchesTo/compensatedBy Step
Entity ownedBy Team
Entity maintainedBy Team
Capability accountableTo Team
Runtime operatedBy Team
Entity reviewedBy Team
Impact requiresReviewBy Team
```

责任关系语义必须分开：ownedBy 负责维护，accountableTo 对业务结果负责，operatedBy 负责生产运行，reviewedBy 表示评审要求。

## 4. 能力、服务和上下文

一个服务可以支持多个能力，一个能力也可由多个服务共同实现。不要将微服务与业务能力一一对应。BoundedContext 表达模型和语言边界，BusinessDomain 用于更高层聚合。

映射粒度采用分层策略：Service/Component 显式维护能力；关键 API、Event、Method 和 Rule 可精确映射；其余成员通过结构和语义规则继承为候选。

## 5. 需求和验收条件

Requirement 不应只关联首次实现它的 Commit，还要关联当前实现节点。验收条件独立建模，使代码、规则和测试可以精确追踪。

```text
REQ 用户修改邮箱
├── 邮箱格式合法
├── 邮箱唯一
├── 发送确认通知
└── 需要身份验证
```

Validator、Repository、Event、API Security 和测试分别实现/验证对应 Criterion。

## 6. 业务规则

BusinessRule 可能由方法、数据库约束、配置、消息幂等和流程共同实现。例如“支付回调只能处理一次”可能由 Handler、去重表、唯一索引和 EventId 共同保证。规则不能只绑定一个方法。

删除唯一约束时，数据库技术影响应升级为 BusinessRuleImpact，并解释可能造成重复入账或重复事件。

## 7. 业务流程

BusinessProcess 包含有序 Step，并支持 branch、compensation 和 trigger。技术节点通过 `implementsProcessStep` 连接。同步 API、异步消息和数据库操作可共同实现同一业务流程。

补偿步骤必须显式建模；修改库存预占时，应同时评估释放库存、超时补偿和人工重放，而不是只看正向主链路。

## 8. 技术变化到业务影响

不是所有技术变化都产生业务行为影响。日志、注释和内部等价重构通常是 `TechnicalChangeWithinCapability`。校验、规则、唯一约束、API 可用性、事件语义和关键配置变化才可能产生：

- CapabilityBehaviorImpact；
- CapabilityAvailabilityImpact；
- BusinessRuleImpact；
- ProcessFlowImpact；
- RequirementRegressionRisk；
- ComplianceImpact；
- CustomerExperienceImpact。

判断需要考虑节点是否为 PrimaryImplementation、是否有替代实现、可观察行为是否变化、是否影响主流程或补偿流程。

## 9. 责任和评审

负责人优先绑定 Team/Role，而不是个人。方法可以沿 Module/Component 继承 owner。跨团队影响通过受影响实体的归属聚合，但团队关系不参与技术传播。

ReviewPolicy 示例：破坏性 Public API 需要 API Architecture Team；不可逆 Migration 需要 DBA；安全配置需要 Security Team；Critical Capability 的 High Risk 需要业务负责人审批。

## 10. SLO 与关键度

Capability 保存 criticality，并关联 Availability、Latency、ErrorRate、Throughput 和 BusinessSuccess SLO。性能或配置变化可从技术指标传播到能力 SLO 风险。风险评分应考虑能力关键度、流程中心度、用户暴露、资金/数据正确性、合规和回滚难度。

## 11. 映射来源

架构目录和显式配置可信度最高；需求链接、API Tag、DDD 模块、代码注解、测试名称和 LLM 语义识别可生成候选。每条业务映射保存 source、confidence、approvedBy、validFrom/To。LLM 结果必须可人工确认。

## 12. 示例

`OrderPaid.amount` 类型变化：SettlementConsumer 读取 amount 并支持“财务结算”，为高业务风险；AnalyticsConsumer 写入数仓并支持“经营分析”，为数据和报表风险；NotificationConsumer 不读取 amount，仅保留反序列化候选，用户通知业务逻辑风险较低。

## 13. 注意事项

- 包名和服务名不是业务能力；
- 技术 owner 与业务 accountable 不同；
- 没有业务映射表示知识缺失；
- 所有技术变化都标红业务能力会造成严重噪声；
- 业务关系主要用于解释、聚合和治理，不替代调用、数据和契约关系。