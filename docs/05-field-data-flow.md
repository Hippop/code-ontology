# 字段访问与数据流

## 1. 设计目标

类型依赖只能说明“方法涉及 UserDTO”，不能说明它是否读取、修改或传播发生变化的 `UserDTO.email`。字段和数据流模型的目标是把类型级候选缩小为字段级真实影响，并建立从请求、领域对象、数据库、消息到响应的端到端值链。

## 2. 最终关系体系

```text
dataDependsOn
├── fieldAccess
│   ├── readsField
│   ├── writesField
│   ├── initializesField
│   └── mutatesField
├── valueFlow
│   ├── assignedFrom
│   ├── passesValueTo
│   ├── argumentFlowsToParameter
│   ├── returnsValueFrom
│   ├── copiesValueTo
│   └── flowsTo
└── transformation
    ├── mapsTo
    ├── derivedFrom
    ├── convertsTo
    ├── aggregatesFrom
    ├── serializesTo
    └── deserializesTo
```

统一方向原则：值流尽量按 source → target 保存；若使用 `target derivedFrom source`，必须定义明确逆关系并保持全库一致。

## 3. 字段访问语义

### readsField

Callable 读取字段，包括 getter、比较、校验、传参、日志、序列化和条件判断。使用方式应作为边属性：Read、Compare、Validate、Serialize、Log、Hash、Filter。

### writesField

Callable 写入字段，包括赋值、setter、Builder、构造初始化、反序列化和 ORM 注入。`initializesField` 是 writesField 的子属性。

### mutatesField

用于集合增删、原地修改、复合赋值等读写同时发生的操作。不要用单一 writesField 丢失“依赖旧值”的事实。

## 4. FieldAccessSite

高精度模型：

```text
Method hasAccessSite FieldAccessSite
FieldAccessSite accessesField Field
```

保存 read/write/readWrite、源位置、接收者类型、条件、循环、null check、alias resolution 和置信度。仓库级 MVP 可以将其压缩为方法到字段的边，但证据库应保留可回溯位置。

## 5. 跨方法值流

调用点必须保存参数位置：

```text
SourceField flowsTo CallArgument(index=0)
CallArgument argumentFlowsToParameter CalleeParameter(index=0)
Callee returnsValueFrom Source
```

只有调用边不能判断传递的是哪个字段。跨过程分析建议生成 MethodSummary，而不是把每个 SSA Value 长期写入全局图。

MethodSummary 包含：读取字段集合、写入字段集合、参数到返回值/字段/外部 Sink 的流、SideEffect、异常和调用摘要。

## 6. mapsTo、derivedFrom、convertsTo

`mapsTo` 表示不同模型间稳定语义对应，如 DTO.email → Entity.email。它不等于运行时某一次赋值，也不应声明为对称或通用传递。

`derivedFrom` 表示经过计算、格式化、聚合、哈希、掩码等产生。它表达来源而非类型等同。

`convertsTo` 表达显式类型或格式转换，最好关联 Converter/Mapper 节点，以便识别吸收点。

## 7. 传播方向

- 字段定义删除、重命名、类型变化：反向查找 readers/writers；
- 字段值语义变化：沿正向 flowsTo/derived/mapping 查下游；
- 敏感级别变化：追踪到日志、API、消息、数据库和分析系统；
- 写入规则变化：重点分析 Producer/Writer；
- 读取容错变化：重点分析 Consumer/Reader。

## 8. 变化吸收

```text
API EmailAddress
  → Mapper convertsTo String
  → Entity.email String
```

Mapper 本身是 ConfirmedImpact；若目标字段类型、序列化和语义保持不变，Mapper 可标记 ContainmentPoint，传播停止。若只是类型不变但格式语义改变，仍需继续产生 BehaviorImpact。

## 9. 别名、集合和动态对象

`u = dto; u.email` 需要 points-to/alias 分析。Map、JSON Object、反射属性和动态语言字段可使用 `mayReadField`、`mayWriteField` 或 DynamicProperty 节点，不能伪装成确定关系。集合元素流应保留 element role，不要只关联容器字段。

## 10. 敏感数据扩展

通过字段角色可推断 PIIField、CredentialField、FinancialField。若敏感字段 `flowsTo` LogStatement、PublicSchemaField、ExternalEvent 或低安全等级存储，应产生 Security/Compliance Candidate。角色推断应基于显式数据分类、Schema 标记和人工确认，名称推断仅作弱证据。

## 11. 示例

```java
User toEntity(UserDTO dto) {
    User user = new User();
    user.setEmail(normalize(dto.getEmail()));
    return user;
}
```

事实：方法 readsField `UserDTO.email`；`UserDTO.email` flowsTo normalize 参数；normalize 返回值 derivedFrom 源字段；方法 writesField `User.email`；`UserDTO.email mapsTo User.email`；返回值 returnsValueFrom `user`。

当源字段类型变化时，normalize 和 Mapper 是直接影响；若 normalize 输出仍是 String，实体和数据库类型影响可被吸收，但转换逻辑测试仍为必须执行。

## 12. 数据抽取与置信度

编译器/IR/SSA 提供最高精度；框架生成 Mapper、序列化元数据和运行 Trace 作为补充；同名字段推断只能产生低置信 mapsTo 候选。每条流必须记录 evidenceSource、sourceLocation、resolutionStatus 和 confidence。

## 13. 注意事项

- 类型引用不等于字段读取；
- read 与 write 不可合并；
- 不要全局物化全部局部值；
- `mapsTo` 不是 `owl:sameAs`；
- 不要把 `flowsTo` 声明为无条件传递；
- 数据流路径表示可能的数据依赖，不表示该路径在所有运行中都会执行。