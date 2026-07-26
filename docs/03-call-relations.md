# 调用关系

## 1. 设计目标

调用关系描述执行依赖，但必须区分编译期确定调用、动态分派候选、运行时观察和远程调用。最终模型既要支持精确反向查找调用者，也要避免把“可达”误判为“必然受影响”。

## 2. Callable 节点

`Callable` 统一 Method、Function、Constructor、Lambda、StoredProcedure、ScriptEntry。对 Lambda 和匿名函数，只有在能够稳定定位并显著提升分析精度时才建立长期节点。

## 3. 最终关系体系

```text
executionDependsOn
└── callRelation
    ├── callsDirectly
    ├── mayCall
    ├── observedCalls
    ├── dispatchesTo
    ├── invokesReflectively
    ├── invokesCallback
    ├── schedulesAsync
    └── callsStoredProcedure
```

远程调用单独使用 `callsRemoteOperation`，目标是 APIOperation，而不是 Provider 内部方法。

### callsDirectly

静态语义解析可唯一确定目标。适用于静态函数、final/private 方法、解析后的直接构造调用等。删除或签名变化对直接调用者通常形成高确定性影响。

### mayCall

由于虚方法、依赖注入、函数指针、动态语言或不完整类路径而存在多个可能目标。它是候选关系，不应与确定调用混合。

### dispatchesTo

连接抽象方法、接口方法与可能的具体实现。调用方通常调用接口方法，再通过 `dispatchesTo` 找到实现。接口使用者与实现者的传播规则不同。

### observedCalls

运行时追踪确认在某环境和时间窗口发生过的调用。应记录环境、版本、次数、延迟和最后观察时间。未观察到不能证明不会调用。

### invokesReflectively

由类名、方法名、注解扫描或配置推断出的反射调用，必须保留证据和置信度。

### schedulesAsync / invokesCallback

表达任务提交、回调注册和异步执行。它们不是同步调用，传播时要考虑执行上下文、异常边界和延迟。

## 4. 调用点模型

高精度场景使用 CallSite：

```text
Caller hasCallSite CallSite
CallSite targets Callee
```

CallSite 保存文件、行列、参数绑定、分派类型、是否位于条件/循环/try/异步块、返回值是否被使用。普通仓库级分析可将这些信息作为边属性，自动修复和语句级解释再物化节点。

## 5. 方向与影响传播

事实保存 `Caller → Callee`。当 Callee 发生删除、签名、返回值或异常变化时，通常反向遍历调用者。实现逻辑或性能变化是否继续向上游传播取决于调用方是否吸收、调用频率和业务可观察性。

不要把 `callsDirectly` 声明为传递属性。A 直接调用 B、B 直接调用 C，并不表示 A 直接调用 C。跨层可达使用 SPARQL property path 或图算法，名称应为 `mayReach`、`transitivelyDependsOn` 或分析时路径，而不是污染直接事实。

## 6. 变化类型与传播

- `MethodDeleted`：直接调用者为 Confirmed CompileImpact；mayCall 为 Possible。
- `ParameterTypeChanged`：检查参数位置、实参类型和转换器。
- `ReturnTypeChanged`：检查返回值是否使用、赋值目标和调用方适配。
- `ExceptionBehaviorChanged`：检查 catch、声明异常、事务和全局异常映射。
- `ImplementationChanged`：直接调用者通常是 RegressionCandidate，不自动形成编译影响。
- `PerformanceBehaviorChanged`：结合调用频率和上游 SLO 传播。

## 7. 多态与接口

完整链路：

```text
Caller callsDirectly InterfaceMethod
InterfaceMethod dispatchesTo ImplementationA
InterfaceMethod dispatchesTo ImplementationB
```

接口方法变化需要分别分析：调用者对契约的依赖、实现者对实现义务的依赖、Mock 和测试桩。运行时类型证据可调整实现优先级，但不能删除静态合法实现。

## 8. 递归与环

对递归和相互调用先计算强连通分量 SCC，将环作为传播单元，避免重复遍历。环内节点仍需分别记录影响，但路径搜索应设置 visited、最大深度和路径预算。

## 9. 证据融合

推荐置信度顺序：编译器解析 > 字节码/IR > 框架元数据 > 运行时 Trace > 配置推断 > 文本/命名推断。静态和运行证据可以共同支持同一逻辑边，但必须保留多来源，不应覆盖。

## 10. 示例

```text
UserController.getUser
  callsDirectly UserService.getUser
UserService.getUser
  callsDirectly UserRepository.findById
UserRepository.findById
  hasReturnType User
```

Repository 返回值改为 Optional<User>：Service 为确定适配点。若 Service 将 Optional 转回原有 UserResponse 并维持异常和返回契约，Controller 的编译影响停止，但仍保留回归测试建议。

## 11. 注意事项

- 远程 HTTP/gRPC 不连接到 Provider 方法；
- observedCalls 不等于唯一真实调用图；
- 同名方法不代表同一调用目标；
- 动态分派候选必须关联接收者类型和解析范围；
- 调用关系只描述执行依赖，不描述具体字段如何流动，字段级传播交给数据流模型。