# 变更模型

## 1. 设计目标

知识图谱描述系统“是什么”，变更模型描述某次提交“改变了什么语义”。只记录 Added/Deleted/Modified 或覆盖当前节点属性，会丢失 before/after、变化意图、兼容性和可重算能力。最终模型以 ChangeSet 和原子化 ChangeItem 为分析起点。

## 2. 最终节点

```text
ChangeEntity
├── ChangeSet
│   ├── Commit
│   ├── PullRequest
│   ├── ConfigurationRollout
│   └── ReleaseChangeSet
└── ChangeItem
    ├── StructuralChange
    ├── DeclarationChange
    ├── BehaviorChange
    ├── ContractChange
    ├── DataChange
    ├── ConfigurationChange
    └── DeliveryChange
```

一个 PR 包含多个 ChangeItem。每个 ChangeItem 只描述一个主要目标和一个可判定语义变化，复杂重构通过多个 ChangeItem 和 `relatedChange` 连接。

## 3. 最终关系与属性

```text
ChangeSet containsChange ChangeItem
ChangeItem changesEntity EntityRevisionOrLogicalEntity
ChangeItem beforeRevision Revision
ChangeItem afterRevision Revision
ChangeItem relatedChange ChangeItem
ChangeItem detectedBy Detector
ChangeItem motivatedBy Requirement
ChangeItem introduces/updates/removes Entity
```

核心属性：changeType、beforeValue、afterValue、sourceLocation、confidence、intent、breakingLevel、compatibilityStatus、author、timestamp、analysisScope。

## 4. 语义化变化类型

### 结构与声明

Type/Method/Field Added、Deleted、Renamed、Moved、VisibilityChanged；Parameter Added/Removed/Reordered/TypeChanged；ReturnType/Nullable Changed；Inheritance/Interface/Override Changed；Generic/Annotation Changed。

### 行为

Algorithm、Condition、ExceptionBehavior、Transaction、Concurrency、Caching、Retry、Timeout、Ordering、Idempotency、SideEffect、Performance、SecurityBehavior Changed。

### 契约

Operation、Path、Method、Parameter、Request/Response/Error Schema、Field、Enum、StatusCode、Authentication、Authorization、MessageMeaning、PublicationTiming Changed。

### 数据

Table/Column/Constraint/Index/View/Query/Migration/DataFormat Changed。

### 配置与交付

ConfigurationValue/Default/Override/Scope、FeatureRollout、SecretRotation、ArtifactDependency、RuntimeVersion、RoutingPolicy Changed。

## 5. 变化检测分层

文本 Diff 只负责定位候选；AST/语义 Diff 识别声明变化；Schema Diff 识别契约和数据库变化；规则和分析器识别行为变化。比如移除 `@Transactional` 不应只记录 AnnotationRemoved，还应派生 TransactionBehaviorChanged。

LLM 可帮助识别意图和业务语义变化，但输出必须关联代码/文档证据并标记置信度，不能直接作为确定事实。

## 6. 重命名、移动和删除新增匹配

重命名不能简单表示 Delete+Add，否则影响报告无法生成迁移建议，历史实体对齐也会断裂。使用签名相似度、结构 Hash、调用上下文和 Git rename 信息创建 `Renamed/Moved` ChangeItem，并连接同一 LogicalEntity 的前后 Revision。

## 7. 原始变化与派生变化

传播过程中，一个变化经过节点后可能产生新的可观察变化：Repository ReturnTypeChanged → Service InternalAdaptationRequired；若 Service 对外返回也改变，再派生 Service ReturnTypeChanged；若 Service 吸收，则不产生公共签名变化。

派生变化仍是 ChangeItem 或 DerivedChange，必须关联 `derivedFromChange`、规则和路径，避免只用 Affected=true。

## 8. 变化组合

多个单项变化可能共同产生更高层语义。例如字段新增 + required=true + 无 default = BreakingRequestChange。规则引擎可创建 CompositeChange，但必须保留组成 ChangeItem。

相反，同一逻辑重构可能包含删除旧方法、添加新方法、更新调用者，但外部契约不变。ChangeSet 层应支持意图聚合，避免把中间编译状态误判为最终发布影响。

## 9. 版本和范围

ChangeItem 必须绑定 base revision、target revision、Repository、环境或配置作用域。配置中心和 Feature Flag 变化没有源码 Commit，也应作为独立 ChangeSet 进入统一审计。

## 10. 示例

`UserDTO.email String → EmailAddress`：创建 FieldTypeChanged，before/after 类型指向 Type Revision；若 JSON Schema 仍 string，则没有直接 ContractChanged；若 Mapper 新增转换，创建 Mapper ImplementationChanged；若 Entity 同步变更，继续创建 FieldTypeChanged；若数据库列变 JSON，再创建 ColumnTypeChanged 和 MigrationChange。

## 11. 注意事项

- 不要覆盖旧节点后再尝试推断变化；
- 不要只使用文件级 Modified；
- 行为变化不一定有签名变化；
- 重命名应保持逻辑实体连续性；
- ChangeType 是传播规则的主要输入，分类错误会放大后续误报；
- 变更检测器版本和证据必须保存，以便重新计算。