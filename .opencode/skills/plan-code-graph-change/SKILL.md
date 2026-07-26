---
name: plan-code-graph-change
description: 基于已评审 Requirement IR、Current/Desired Graph Diff 和已确认实体对齐生成可评审的代码图变更、兼容评估、验证义务和任务 DAG。
compatibility: opencode
metadata:
  version: "1.0.0"
  owner: architecture
  stage: plan
  artifact-type: ProposedChangeDraft
---

## 前置条件

```text
Requirement IR 已通过需求评审
关键实体对齐已确认
Current/Desired Graph Revision 已固定
Semantic Graph Diff 可用
规划规则版本已固定
```

## 工作步骤

1. 获取 stage=`plan` 的需求上下文；
2. 按 Graph Difference 分类：Node、Relation、Behavior、Contract、Data、Configuration、State、Test、Deployment；
3. 应用确定性规划规则，先生成 Required Proposal；
4. 查询相关 ImplementationSlice、契约消费者、数据依赖和部署单元；
5. 补充 Recommended、Alternative 和 Unresolved 项；
6. 对公共契约、数据库、消息、配置和跨服务变化执行兼容评估；
7. 生成 VerificationObligation；
8. 生成 ImplementationTask DAG 和文件候选；
9. 标记人工 Gate、责任角色和批准条件；
10. 使用 `ontology_change_plan_draft` 保存 Draft。

## 必查工程层

```text
业务流程与规则
API/Schema/Error Contract
代码声明与行为
字段和数据流
数据库与迁移
消息生产消费
配置与 Feature Flag
事务、并发、幂等、超时和重试
测试与负向验收
构建、部署、回滚和运行监控
```

## 输出契约

```json
{
  "changeSet": {
    "requirementId": "string",
    "currentRevision": "string",
    "desiredRevision": "string",
    "ruleSetVersion": "string"
  },
  "proposals": [
    {
      "proposalId": "string",
      "category": "Required|Recommended|Alternative|Unresolved",
      "changeType": "string",
      "targetCurrentEntityId": "string|null",
      "desiredEntityId": "string|null",
      "reason": "string",
      "evidenceRefs": [],
      "compatibility": {},
      "risk": {},
      "dependsOn": [],
      "humanGate": "string|null"
    }
  ],
  "verificationObligations": [],
  "implementationTasks": [],
  "unresolvedQuestions": []
}
```

## 强制人工 Gate

- 删除或破坏公共 API、消息或数据库对象；
- 不可逆迁移；
- 跨服务责任迁移；
- 租户隔离、认证、授权或 Secret 变化；
- 无法确认的外部消费者；
- 生产发布顺序或回滚不明确；
- 多个架构方案成本和风险接近。

## 禁止事项

不得批准提案、修改代码、把推荐项升级为需求事实，或使用无证据的文件名作为确定目标。