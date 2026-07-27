---
name: review-change-architecture
description: 对平台提供的 Proposed Change 快照执行一次性、只读、无副作用的独立架构评审，并返回结构化 ReviewFinding。
compatibility: opencode
metadata:
  version: "1.0.0"
  owner: architecture
  stage: architecture-review
  artifact-type: ArchitectureReviewAdvice
---

## 目标

只评审 Prompt 中已提供的 Change Plan 快照。平台确定性引擎负责保存计划和执行
审批；本 Skill 只提供独立审查意见，不调用工具，不修改任何状态。

## 有界执行

1. 读取 Prompt 中的 Change Plan；
2. 按下列检查表逐项判断；
3. 对证据不足的事项使用 `Question`，不要继续搜索；
4. 输出一个 JSON 对象；
5. 立即结束。

禁止调用 Skill 以外的任何工具，禁止查询本体平台、读取仓库、运行命令、编辑文件、
派生 Task、保存 Draft 或改变审批状态。

## 检查表

- 需求、差异与 Proposed Change 是否一致；
- 服务、Bounded Context、租户、认证和授权边界；
- API、消息、数据库、配置的向前与向后兼容；
- 状态机、事务、并发、幂等、顺序、超时、重试和补偿；
- 历史数据、迁移、回滚和混合版本；
- 部署顺序、消费者与运行版本；
- 正向、负向、兼容和回归验证义务；
- 未批准范围、无证据目标与过度设计。

## 唯一输出契约

只输出合法 JSON，不使用 Markdown 代码围栏：

```json
{
  "status": "Reviewed",
  "summary": "string",
  "findings": [
    {
      "findingId": "architecture-finding-1",
      "severity": "Blocker|Major|Minor|Question|AcceptedRiskCandidate",
      "proposalIds": [],
      "evidenceRefs": [],
      "reason": "string",
      "requiredAction": "string",
      "humanOwnerRole": "string"
    }
  ],
  "checkedDimensions": [],
  "remainingUnknowns": [],
  "recommendedNextAction": "Accept|NeedsRevision|Reject"
}
```

即使没有 Finding，也必须返回空 `findings`、完整 `checkedDimensions` 和
`remainingUnknowns`。
