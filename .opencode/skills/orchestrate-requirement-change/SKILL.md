---
name: orchestrate-requirement-change
description: 按受控阶段编排需求文档抽取、代码图对齐、变更规划、人工 Gate、批准后实现和设计实现对账。
compatibility: opencode
metadata:
  version: "1.0.0"
  owner: architecture
  stage: orchestration
  artifact-type: workflow-summary
---

## 适用条件

当输入包含 Requirement ID、DesignRevision ID，并要求从需求分析推进到代码变更、实现或验证时使用。

## 阶段状态机

```text
Extract
→ RequirementReview
→ Align
→ AlignmentReview
→ Plan
→ ArchitectureReview
→ Approval
→ Implement
→ Verify
→ Impact
```

不得跳过人工 Gate。平台上下文没有明确批准状态时，停止在当前 Gate。

## 工作流

1. 调用 `ontology_requirement_context` 获取当前阶段、图 Revision、审批和 Artifact；
2. 检查输入 ID 和上下文 Hash；
3. Extract 阶段调用 `requirement-analyst`；
4. Align 阶段调用 `code-graph-analyst`；
5. Plan 阶段调用 `change-planner`，随后调用 `architecture-reviewer`；
6. Implement 阶段仅在 Approved 状态调用 `implementation-agent`；
7. Actual Graph 已生成后调用 `verification-agent`；
8. 汇总 Artifact、证据、Gate、阻塞项和下一允许动作；
9. 使用 `ontology_record_agent_artifact` 保存阶段结果。

## 输出契约

```json
{
  "requirementId": "string",
  "designRevisionId": "string",
  "stage": "Extract|Align|Plan|Implement|Verify|Impact",
  "status": "Completed|Blocked|NeedsHumanReview|Failed",
  "artifacts": [
    {"artifactId": "string", "artifactType": "string"}
  ],
  "evidenceRefs": ["string"],
  "humanGates": [
    {"gate": "string", "status": "Pending|Approved|Rejected"}
  ],
  "unresolvedQuestions": ["string"],
  "nextAllowedAction": "string"
}
```

## 停止条件

- Requirement 或 DesignRevision 不存在；
- 图 Revision 已变化导致上下文过期；
- 前一 Gate 未批准；
- 子 Agent 输出缺少证据或不符合 Artifact Schema；
- 存在破坏性变化但没有责任人；
- 发现批准范围与实际代码冲突。

## 禁止事项

不得直接编辑代码、批准提案、修改 Current Graph、执行 Git 写操作或部署。