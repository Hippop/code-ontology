---
name: explain-change-impact
description: 将结构化变更、影响路径、风险、测试和发布结论转换为面向开发、测试、架构、产品和运维的可追溯解释。
compatibility: opencode
metadata:
  version: "1.0.0"
  owner: architecture
  stage: impact
  artifact-type: ImpactExplanation
---

## 适用条件

仅在已经存在结构化 Proposed Change、ImpactAssessment、ReconciliationResult 或测试/发布结论时使用。不得凭自然语言需求直接生成影响结论。

## 工作步骤

1. 获取目标变更和受控 Impact Path；
2. 检查每条结论是否具备 changeId、ruleId、path 和 evidenceRef；
3. 区分 Confirmed、Contained、Rejected 和 Unresolved；
4. 按角色生成摘要；
5. 解释为什么受影响、为什么传播停止或为什么无法判断；
6. 列出需要执行的测试、人工检查和发布动作；
7. 保存 ImpactExplanation Artifact。

## 角色视图

```text
Developer：文件、符号、调用、数据流和修改原因
Test Owner：受影响规则、已有测试、缺失测试和负向场景
Architect：边界、兼容、风险、替代方案和未知消费者
Product/Domain：能力、流程、规则和验收影响
Operations：构建、部署顺序、配置、监控和回滚
```

## 输出契约

```json
{
  "changeId": "string",
  "summary": "string",
  "certainty": "Confirmed|Contained|Rejected|Unresolved",
  "roleViews": {
    "developer": {},
    "test": {},
    "architecture": {},
    "business": {},
    "operations": {}
  },
  "impactPaths": [],
  "evidenceRefs": [],
  "requiredActions": [],
  "unknowns": []
}
```

## 禁止事项

- 不得隐藏 Unresolved；
- 不得把图上可达表述为确定影响；
- 不得把低置信度动态调用写成已发生调用；
- 不得省略破坏性变化、数据迁移或生产风险；
- 不得生成无证据的精确文件和方法结论。