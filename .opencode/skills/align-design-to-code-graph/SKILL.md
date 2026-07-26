---
name: align-design-to-code-graph
description: 将已评审的目标业务和技术实体与 Current Knowledge Graph 中的代码、API、数据、消息、配置和测试实体进行候选对齐。
compatibility: opencode
metadata:
  version: "1.0.0"
  owner: architecture
  stage: align
  artifact-type: CandidateAlignmentDraft
---

## 前置条件

- Requirement IR 已通过需求评审；
- Desired Entity 具有稳定 ID 和证据；
- Current Graph Revision 已固定；
- 不允许直接修改 Current Graph。

## 工作步骤

1. 调用 `ontology_requirement_context`，stage 使用 `align`；
2. 对每个 Desired Entity 先查稳定 ID、全限定符号、operationId、Schema ID 和数据库全限定名；
3. 使用 `ontology_graph_query` 查询候选实体及受控邻域；
4. 比较节点类型、所属模块、业务能力、调用上下文、数据关系、测试和历史映射；
5. 生成 Top-N CandidateAlignment；
6. 将对齐类型标记为 Exact、Equivalent、Represents、Extends、Reuses、Replaces、NoMatch 或 Ambiguous；
7. 从确认度最高的业务入口构建 ImplementationSliceDraft；
8. 将 primary entry、supporting code、contract、data、message、configuration 和 test 分角色记录；
9. 使用 `ontology_alignment_candidates` 保存 Candidate 草案。

## 证据优先级

```text
显式稳定 ID
> 全限定代码或契约标识
> 已确认历史映射
> 名称 + 类型 + 模块 + 图上下文
> 数据流或调用路径
> 测试名称和注释
> 纯语义相似
```

## 输出契约

```json
{
  "desiredEntityId": "string",
  "candidates": [
    {
      "currentEntityId": "string",
      "alignmentType": "Exact|Equivalent|Represents|Extends|Reuses|Replaces|NoMatch|Ambiguous",
      "confidence": 0.0,
      "evidenceRefs": [],
      "positiveReasons": [],
      "negativeReasons": []
    }
  ],
  "implementationSlice": {
    "processStepId": "string",
    "primaryEntries": [],
    "supportingCode": [],
    "contracts": [],
    "dataObjects": [],
    "messages": [],
    "configurations": [],
    "tests": []
  },
  "reviewRequired": true,
  "unresolvedQuestions": []
}
```

## 禁止事项

- 不得仅凭名称自动确认关键映射；
- 不得把全调用闭包作为 ImplementationSlice；
- 不得把 Desired Entity 写入 Current Graph；
- 不得选择架构方案；
- 不得将 NoMatch 自动解释为必须新增代码。