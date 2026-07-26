# 类型与声明依赖

## 1. 为什么类型依赖必须独立于调用关系

调用关系描述运行时执行链，类型依赖描述声明、编译和契约约束。一个方法即使从未被执行，也可能因为参数类型、返回类型、继承或注解变化而无法编译。反过来，运行时调用成立也不代表存在公共类型契约。

## 2. 最终关系体系

```text
declarationDependsOn
└── typeDependency
    ├── hasParameterType
    ├── hasReturnType
    ├── hasFieldType
    ├── hasPropertyType
    ├── hasGenericArgument
    ├── extendsType
    ├── implementsType
    ├── overridesMethod
    ├── referencesType
    ├── instantiatesType
    ├── declaresThrownType
    ├── catchesExceptionType
    ├── annotatedWith
    ├── aliasesType
    └── hasUnderlyingType
```

对高频反向分析定义 `isParameterTypeOf`、`isReturnTypeOf`、`isExtendedBy`、`isImplementedBy`、`isOverriddenBy` 等逆属性。

## 3. 参数和返回类型

参数节点应保留位置、名称、可空性、默认值、变长参数和注解。重载方法的稳定 ID 必须包含规范化参数签名。

```text
Method hasParameter Parameter
Parameter hasType Type
```

也可物化快捷边 `Method hasParameterType Type`。参数节点是权威事实，快捷边用于查询。

返回值同样应区分：声明类型、实际推断类型、可空性、异步包装、错误通道和流式返回。`Future<User>` 不应只保留 raw type Future，必须保存泛型参数 User。

## 4. 字段、泛型和容器

字段类型关系应精确到 Field。对于 `List<User>`、`Map<String, User>`、数组和 Optional，应保存 raw type、generic position 和 element/value type。

```text
Field users hasFieldType List
Field users hasGenericArgument User position=0
```

容器元素变化可能传播到序列化、数据库映射和消费者，不应被 raw type 掩盖。

## 5. 继承、实现和覆盖

`extendsType` 连接子类型到父类型；`implementsType` 连接实现类型到接口；`overridesMethod` 建立方法级覆盖。只有类级 implements 无法判断接口某个方法变化具体影响哪些实现。

接口新增抽象方法通常影响所有非抽象实现；接口新增默认方法则规则不同。父类私有方法变化不传播到子类，protected/public 可覆盖方法变化需要检查实际 override。

## 6. referencesType 与精确关系

`referencesType` 是广义兜底，用于 cast、instanceof、class literal、catch、局部变量和无法归入更精确关系的引用。若已知 `hasParameterType`、`instantiatesType` 等关系，不应只保留 referencesType，否则影响规则失去语义。

## 7. 实例化与构造调用

`instantiatesType` 表示方法创建某类型实例，`callsDirectly Constructor` 表示具体构造调用。工厂、反射和依赖注入可能只有 `mayInstantiate`。类型删除和构造签名变化需要分别使用类型关系和调用关系分析。

## 8. 类型别名和值对象

类型别名或底层表示使用 `aliasesType`、`hasUnderlyingType`，不要使用 `owl:sameAs`。领域值对象 `EmailAddress` 与 `String` 即使可互转，也具有不同业务语义、验证和序列化行为。

## 9. 枚举与异常

Enum、EnumValue 必须分离。除 `referencesType` 外，建议保存 `referencesEnumValue`、`switchesOnEnum`、`serializesEnum`、`persistsEnum`。响应枚举新增值可能破坏旧消费者的穷举分支。

异常关系包括 `declaresThrownType`、`catchesExceptionType` 和异常到 API ErrorResponse 的映射。新增异常可能穿透事务和服务边界，即使方法返回类型不变。

## 10. 注解依赖

注解可能改变路由、事务、缓存、权限、序列化和依赖注入。简单场景用 `annotatedWith AnnotationType`，需要参数级分析时使用 AnnotationInstance 节点保存属性值和源位置。

## 11. 变化传播示例

`UserDTO.email: String → EmailAddress`：

- 所有 `hasParameterType UserDTO` 只是类型级候选；
- 直接 `readsField UserDTO.email` 的方法优先级更高；
- 使用 String API、传给 String 参数或赋给 String 字段时形成确定编译影响；
- 仅做 null 判断可能仍可编译；
- Mapper 若转换回 String，可成为吸收点。

## 12. 数据抽取

优先使用编译器语义模型、字节码或语言服务器。文本搜索只用于补漏。必须记录 resolutionStatus：Resolved、Ambiguous、Unresolved、External。外部库类型还要记录依赖版本和源码/二进制可见性。

## 13. 注意事项

- domain/range 只用于推断，不用于拒绝错误数据；
- 不要丢失泛型位置和可空性；
- 不要将文本引用当成已解析类型引用；
- 不要把别名和值对象视为完全相同；
- 公共签名、内部局部类型和测试类型应具有不同风险权重。