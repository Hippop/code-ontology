# 配置、环境变量、Feature Flag 与 Secret

## 1. 设计目标

配置模型处理“代码不变但运行行为改变”的场景。超时、重试、并发、缓存、安全开关、环境覆盖和 Secret 轮换可能造成生产事故，却不会产生编译错误。最终模型必须区分配置定义、配置值、来源、优先级、环境、有效值和消费时机。

## 2. 最终节点

```text
ConfigurationEntity
├── ConfigurationKey
├── ConfigurationValue
├── ConfigurationSource
│   ├── ConfigFile
│   ├── EnvironmentVariable
│   ├── CommandLineSource
│   ├── ConfigCenter
│   └── SecretStore
├── ConfigurationProfile
├── Environment
├── FeatureFlag
├── FeatureVariant
├── TargetSegment
└── Secret
```

ConfigurationKey 是稳定定义；不同环境和来源的具体值建为 ConfigurationValue。不要把生产值直接覆盖在 Key 上。

## 3. 最终关系

```text
CodeEntity readsConfiguration ConfigurationKey
ConfigurationSource definesConfiguration ConfigurationKey
ConfigurationValue providesValueFor ConfigurationKey
ConfigurationValue sourcedFrom ConfigurationSource
ConfigurationValue effectiveIn Environment
ConfigurationValue overridesConfiguration ConfigurationValue
ConfigurationField bindsConfiguration ConfigurationKey
CodeEntity guardedByFeatureFlag FeatureFlag
FeatureFlag hasVariant FeatureVariant
FeatureFlag targetsSegment TargetSegment
Service dependsOnSecret Secret
Deployment mountsSecret Secret
Service subscribesToConfiguration ConfigurationKey
```

## 4. 有效值计算

配置优先级、Profile、环境条件和运行上下文不能由简单 OWL 推理处理。规则引擎应根据框架特定优先级计算 `EffectiveConfigurationValue`，并保留原始候选值和来源。

配置 Diff 应比较规范化值：`3s`、`3000ms`、`3000` 在明确单位后可能等价。数值相同但单位、类型或解释方式变化仍是语义变化。

## 5. 读取方式和生命周期

CodeEntity 可在 BuildTime、StartupTime、Runtime 读取配置。ActivationMode 包括 BuildRequired、RestartRequired、DynamicReload、PerRequest。该属性决定变更是重新构建、重启还是即时生效。

配置绑定对象：

```text
PaymentProperties.timeout bindsConfiguration payment.timeout
PaymentClient.send readsField PaymentProperties.timeout
```

可规则推导 PaymentClient `readsConfiguration payment.timeout`。

## 6. Feature Flag

Feature Flag 不是普通 Boolean Key。它可能是布尔、百分比灰度、用户分群或多变体路由。受控关系必须记录启用条件：flag=true、flag=false、variant=v2。

```text
NewCheckout enabledWhen new-checkout=v2
LegacyCheckout enabledWhen new-checkout=legacy
```

Flag 从 5% 调到 100% 不要求代码部署，但会放大真实流量、数据库写入、远程调用和消息吞吐，应产生 RuntimeRolloutImpact。

Flag 生命周期保存 owner、创建时间、过期时间、默认变体和回滚策略。AlwaysOn、AlwaysOff、Expired、Orphaned Flag 应进入治理规则。

## 7. Secret

Secret 节点只保存标识、存储位置、版本、轮换和加载模式，禁止保存明文。`reloadMode` 包括 StartupOnly、PeriodicRefresh、EventDriven、PerRequest。

Secret 轮换传播到依赖服务、部署挂载和运行实例。旧 Key 是否并行有效决定滚动发布安全性。

## 8. 变化传播

- KeyRemoved：检查 required/default/nullability；无默认值可能导致启动失败；
- DefaultChanged：只影响未显式覆盖的环境和部署；
- OverrideChanged：先计算目标环境最终有效值；
- Timeout/RetryChanged：结合运行延迟、调用频率和下游限流；
- ConcurrencyChanged：传播到数据库、消息顺序和容量；
- SecurityFlagChanged：提高 SecurityImpact；
- FeatureRolloutChanged：沿启用路径传播并调整流量系数；
- SecretRotated：根据 reloadMode 生成刷新、重启和兼容要求。

## 9. 配置组合规则

配置项经常共同决定行为。例如 timeout、retry、circuit breaker 不能单独分析。建议建立 ConfigurationGroup 或 Rule 引用，识别组合风险：短超时 + 高重试可能放大下游流量。

## 10. 示例

生产 `payment.timeout 3000ms → 500ms`、retry `3 → 10`，而外部 API P95 为 800ms：PaymentClient 和 RetryExecutor 是直接运行影响；正常请求会被误判超时，重试放大下游流量，熔断和线程池受影响。若生产存在更高优先级环境变量保持 3000ms，则本次文件变更对生产无效，但可能影响测试和本地环境。

## 11. 证据来源

配置文件、环境清单、Helm/Kubernetes、配置中心、Secret Store 元数据、框架绑定、运行时 effective config 和 Flag 平台。敏感值应在采集器侧脱敏或只传递 Hash/版本。

## 12. 注意事项

- 配置文件变化不等于所有 Key 变化；
- 原始定义变化不等于目标环境有效值变化；
- Feature Flag 需要条件和流量信息；
- Secret 不保存明文；
- 未配置可能表示回退默认值、启动失败或条件分支，规则必须区分；
- 动态配置变更也应进入 ChangeSet 和审计链。