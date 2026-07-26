---
name: implement-approved-change
description: 在独立 Worktree 中，仅按 Approved Change、Architecture Decision、文件白名单和验证义务修改代码并运行受控测试。
compatibility: opencode
metadata:
  version: "1.0.0"
  owner: engineering
  stage: implement
  artifact-type: ImplementationPatch
---

## 前置条件

必须同时满足：

```text
Requirement 状态允许 Implement
Proposed Change 已 Approved
Architecture Decision 已确认
Base Commit 与 Repository Snapshot 一致
allowedFiles / forbiddenFiles 已提供
requiredTests / forbiddenChanges 已提供
```

任何条件缺失都不得编辑代码。

## 工作步骤

1. 调用 `ontology_requirement_context`，stage 使用 `implement`；
2. 阅读 Approved Change、ImplementationSlice、相关源码和测试；
3. 检查工作区状态和 Base Commit；
4. 制定与 proposalId 对应的最小实施顺序；
5. 只修改白名单文件和允许目录；
6. 保持未指定输入和旧契约的兼容行为；
7. 为新业务规则增加可识别的代码边界和测试断言；
8. 运行格式化、编译、目标测试和批准的回归测试；
9. 检查 `git diff` 是否存在越界变化；
10. 生成 ImplementationPatch 和 TestExecutionReport；
11. 使用 `ontology_record_agent_artifact` 保存结果。

## 每个修改的追踪要求

```json
{
  "file": "path",
  "changeSummary": "string",
  "proposalIds": ["string"],
  "verificationObligationIds": ["string"],
  "evidenceRefs": ["string"]
}
```

## 代码原则

- 优先复用已批准的扩展点；
- 不进行与需求无关的重构；
- 不为了测试通过削弱断言；
- 不吞掉异常或关闭安全检查；
- 不添加未批准的外部依赖；
- 数据库变化必须有正式 Migration；
- 公共契约变化必须同步正式 Schema；
- 动态配置必须说明默认值、作用域和刷新语义。

## 测试顺序

```text
受影响单元测试
→ 新增负向测试
→ 契约/Schema 测试
→ 数据库或消息集成测试
→ 模块回归测试
```

## 停止条件

需要修改 forbiddenFiles、出现未批准架构变化、Base Commit 过期、测试暴露设计冲突、需要凭据或生产访问时立即停止。

## 禁止事项

不得 commit、push、merge、rebase、创建发布、执行 kubectl/helm/terraform 或访问生产系统。