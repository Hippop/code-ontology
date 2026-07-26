# 消息与异步契约模型

## 1. 设计目标

异步消息通过 Broker、Topic/Queue、Schema、Consumer Group 和重试机制跨越服务边界。生产者并不直接调用消费者，因此不能用普通方法调用边表达。模型必须支持多消费者、延迟、重复、乱序、历史重放、Schema 版本和未知消费者。

## 2. 最终节点

```text
MessagingEntity
├── MessageBroker
├── Topic
├── Queue
├── Exchange
├── DeadLetterQueue
├── EventType
├── CommandMessage
├── NotificationMessage
├── MessageSchema
├── MessageField
├── ProducerBinding
├── ConsumerBinding
├── ConsumerGroup
├── Subscription
├── Serializer
├── Deserializer
├── RetryPolicy
├── DeliveryGuarantee
├── OrderingPolicy
└── SchemaRegistry
```

业务事件与技术消息分离：`OrderPaid` 业务事实可以由 `OrderPaid-v2` Avro Schema 表示，并发布到 `order-events` Topic。

## 3. 最终关系

```text
Callable publishesEvent EventType
Callable publishesCommand CommandMessage
Callable consumesEvent EventType
Callable handlesCommand CommandMessage
EventType hasMessageSchema MessageSchema
MessageSchema hasMessageField MessageField
EventType publishedTo Topic
ConsumerGroup subscribesTo Topic
ConsumerMethod memberOfConsumerGroup ConsumerGroup
CodeType serializesAsMessage MessageSchema
MessageSchema deserializesMessageAs CodeType
EventType usesMessageKey MessageField
Consumer governedByRetryPolicy RetryPolicy
ConsumerGroup deadLettersTo DeadLetterQueue
EventType governedByOrdering OrderingPolicy
Schema registeredIn SchemaRegistry
```

`subscribesTo Topic` 是物理订阅，`consumesEvent EventType` 是语义消费；两者都必须存在，才能避免共享 Topic 带来的全量误报。

## 4. 事件、命令和通知

事件描述已经发生的事实；命令要求特定目标执行动作；通知通常传递状态提示。删除唯一命令消费者可能让业务动作无人执行，而删除某个事件消费者不一定影响其他消费者，因此传播规则必须识别消息语义。

## 5. Schema 与代码类型分离

Java Record、Avro Schema、Proto Message、JSON Schema 不是同一实体。通过 `serializesAsMessage` 和字段级 `serializesTo` 连接。代码内部改成 Money 值对象，但 Serializer 仍输出旧 number 字段时，契约可以保持不变。

## 6. 生产时机和事务

PublicationPolicy 保存 BeforeCommit、AfterCommit、InsideTransaction、OutboxRelay。发布时机变化即使 Schema 不变，也可能造成数据库回滚后消息已发、消费者读不到最新数据或消息丢失，应产生 Semantic/DataConsistency Impact。

## 7. Key、分区和顺序

Message Key 影响分区、负载和顺序。`key=orderId → userId` 可能破坏订单内事件顺序。OrderingPolicy 应保存作用范围：None、Partition、Aggregate、Global，以及 orderingKey。

## 8. 投递、幂等、重试和 DLQ

DeliveryGuarantee 表达 AtMostOnce、AtLeastOnce、EffectivelyOnce。消费者使用 `eventId` 或业务键实现幂等时，建立 `usesAsIdempotencyKey`。字段删除或算法变化会产生 IdempotencyImpact。

RetryPolicy 保存次数、退避、可重试异常和延迟队列。DLQ 节点连接重放工具、告警和处理责任。新消费者不能解析旧消息时，不只在线消费失败，历史重放和 DLQ 重放也会失败。

## 9. 四向兼容矩阵

必须验证：旧消息→旧消费者、新消息→旧消费者、旧消息→新消费者、新消息→新消费者。消息系统的长期保留和事件溯源使“旧消息→新消费者”尤其重要。

CompatibilityAssessment 要保存 producer/schema version、consumer version、方向、状态、测试证据和 Schema Registry 模式。

## 10. Schema 变化规则

- 可选字段新增且有默认值：通常较兼容，但检查严格反序列化和消息大小；
- 必填字段新增：旧消费者高风险；
- 字段删除/重命名/类型变化：通常破坏；
- Protobuf 字段编号复用：Critical；
- 枚举新增：旧消费者穷举分支风险；
- 业务语义变化：即使 Schema 完全相同，也向依赖该语义的消费者传播。

## 11. 运行与静态证据

来源包括 Listener 注解、Binding 配置、AsyncAPI、Broker Subscription、Schema Registry、ACL、Trace、消费指标。区分 configured、static、observed、mayConsume。未观察到可能是低频或灾备任务，不能据此删除影响。

## 12. 示例

`OrderPaid.amount number → MoneyObject`：生产端 Mapper/Serializer 和 Schema Registry 受影响；SettlementConsumer 与 AnalyticsConsumer 实际读取 amount，业务影响高；NotificationConsumer 不读取 amount，可降低业务逻辑影响，但仍需验证反序列化。下游数据库列、报表和历史重放测试继续纳入路径。

## 13. 注意事项

- Producer 与 Consumer 不建立 callsDirectly；
- EventType 与 Topic 不合并；
- 共享 Topic 需要事件过滤；
- Schema Diff 不能发现业务语义、时机、Key、顺序和投递变化；
- 没有已知消费者不等于没有消费者；
- 不要把 `publishedTo` 或 `consumesEvent` 声明为传递属性。