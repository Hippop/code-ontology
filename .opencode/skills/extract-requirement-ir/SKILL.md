---
name: extract-requirement-ir
description: 将特性文档和详细设计证据规范化为 Requirement IR、目标业务/技术实体、验收条件和未解决设计问题。
compatibility: opencode
metadata:
  version: "1.0.0"
  owner: product-architecture
  stage: extract
  artifact-type: RequirementIRDraft
---

## 前置条件

必须提供 Requirement ID、DesignRevision ID 和平台生成的文档证据。不得使用旧版本文档替代当前 DesignRevision。

## 输入

```text
Requirement metadata
DesignRevision metadata
DesignSection list
DocumentEvidence list
Existing business vocabulary
Requirement IR schema
```

## 工作步骤

1. 调用 `ontology_requirement_context`，stage 使用 `extract`；
2. 按背景、目标、范围、流程、规则、数据、API、消息、配置、异常、测试和发布分组证据；
3. 抽取 Capability、UseCase、Process、Step、BusinessRule、BusinessObject、BusinessAttribute、BusinessEvent、StateTransition 和 AcceptanceCriterion；
4. 抽取期望 API、Schema、数据库、配置、消息和代码角色；
5. 将每条结果分类为 Explicit、Inferred、Suggested 或 Unresolved；
6. 为每条结果关联 source section、source text 和 evidenceRef；
7. 检查单位、默认值、范围、空值、兼容、失败、回滚和发布语义；
8. 生成 RequirementIRDraft；
9. 使用 `ontology_record_agent_artifact` 保存。

## 规则

- 文档明确陈述才是 Explicit；
- 多条证据共同推出但未直接陈述的是 Inferred；
- 具体类名、文件名和实现模式通常属于 Suggested；
- 缺少关键信息时创建 UnresolvedDesignQuestion；
- 不根据当前代码反向篡改需求语义；
- 不把 UI 页面、Controller 或表名直接当作 BusinessCapability。

## 输出最小结构

```json
{
  "requirement": {},
  "scope": {"included": [], "excluded": []},
  "businessCapabilities": [],
  "useCases": [],
  "processChanges": [],
  "businessRules": [],
  "businessObjects": [],
  "contractChanges": [],
  "dataChanges": [],
  "configurationChanges": [],
  "acceptanceCriteria": [],
  "desiredEntities": [],
  "evidenceRefs": [],
  "assumptions": [],
  "unresolvedQuestions": []
}
```

## 停止条件

文档版本冲突、关键规则定义冲突、无法确定业务单位或失败语义时，输出草案并进入人工需求评审，不继续代码对齐。