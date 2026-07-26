---
name: verify-and-reconcile
description: 将 Approved Change 与代码 Diff、Actual Graph、测试和运行证据逐项对账，识别缺失、意外、偏离和未验证实现。
compatibility: opencode
metadata:
  version: "1.0.0"
  owner: quality-architecture
  stage: verify
  artifact-type: ReconciliationReport
---

## 前置条件

- Approved Change Graph 可用；
- 实现代码 Diff 已固定；
- 静态分析器已生成 Actual Graph；
- 测试结果和 VerificationObligation 可读取；
- 对账 Agent 不修改代码。

## 工作步骤

1. 使用 `ontology_reconciliation_context` 获取受控上下文；
2. 按 proposalId 建立 Approved/Actual 对照；
3. 验证结构事实：节点、字段、方法、Schema、表、配置是否真实存在；
4. 验证关系事实：调用、读写、规则执行、映射、生产消费是否真实建立；
5. 验证行为：条件、失败路径、事务、幂等、超时、回滚和副作用；
6. 验证契约、数据、配置和部署；
7. 将测试覆盖与业务断言分开；
8. 对动态行为使用运行证据，证据不足时标记 Unverified；
9. 检查未批准的新增依赖、公共契约、配置或数据变化；
10. 生成并保存 ReconciliationReport。

## 状态定义

```text
ImplementedAsDesigned：批准目标和实际事实一致，且验证义务满足
MissingImplementation：批准项没有对应实际事实
UnexpectedImplementation：实际出现未批准变化
ChangedDesign：实现采用不同设计，需要补充设计决策
PartiallyImplemented：只完成部分批准目标
Unverified：存在候选事实但证据不足
```

## 输出契约

```json
{
  "reconciliationRunId": "string",
  "results": [
    {
      "proposalId": "string",
      "status": "ImplementedAsDesigned|MissingImplementation|UnexpectedImplementation|ChangedDesign|PartiallyImplemented|Unverified",
      "actualEntityIds": [],
      "evidenceRefs": [],
      "reason": "string",
      "requiredAction": "string|null",
      "ownerRole": "string|null"
    }
  ],
  "verificationObligations": [],
  "releaseRecommendation": "Pass|Block|NeedsHumanReview",
  "unresolvedQuestions": []
}
```

## 判定原则

- 文件修改不是行为完成证据；
- 调用覆盖不是业务规则验证；
- 仅存在测试名称不是断言证据；
- Desired Graph 不是 Actual Graph；
- AI 推断不能替代静态或运行事实；
- 任何关键负向验收未验证时不得给出 Pass。

## 禁止事项

不得修复代码、篡改测试结果、降低验证标准或自动接受设计偏差。