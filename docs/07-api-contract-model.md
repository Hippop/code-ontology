# API 与同步契约模型

## 1. 设计目标

API 模型识别内部变化是否突破服务边界，影响前端、移动端、SDK、其他服务或外部合作方。Controller Method 与 APIOperation、代码 DTO 与 Contract Schema 必须分离，才能正确表示内部重构、序列化吸收、版本并存和消费者兼容。

## 2. 最终节点

```text
ContractEntity
├── APIContract
├── APIOperation
│   ├── RESTOperation
│   ├── GraphQLOperation
│   └── RPCMethod
├── APIParameter
├── APIResponse
├── RequestSchema
├── ResponseSchema
├── ErrorSchema
├── SchemaField
├── SecurityRequirement
├── APIConsumer
└── APIVersionFamily
```

REST Operation 稳定 ID 至少包含服务、HTTP Method、规范化 Path 和版本。APIResponse 独立保存 status、mediaType、headers 和 bodySchema。

## 3. 最终关系

```text
Service exposes APIOperation
Callable implementsOperation APIOperation
APIOperation hasParameter APIParameter
APIOperation hasRequestSchema RequestSchema
APIOperation hasResponse APIResponse
APIResponse hasBodySchema Schema
Schema hasSchemaField SchemaField
CodeField serializesTo SchemaField
SchemaField deserializesTo ConsumerField
Consumer consumesAPI APIOperation
ConsumerMethod callsRemoteOperation APIOperation
Operation versionOf Family
NewVersion supersedes OldVersion
Operation governedBySecurity Requirement
```

远程调用目标是 APIOperation，不是 Provider Controller 方法。

## 4. 参数与请求模型

APIParameter 与 Java Parameter 分离，通过 `bindsToAPIParameter` 连接。参数保存 location、required、nullable、default、format、range、pattern、enum 和 deprecated。

RequestSchema 字段新增的兼容性取决于 required/default/反序列化策略；必填字段新增通常破坏旧客户端，可选字段新增仍可能改变默认行为、缓存键和权限逻辑。

## 5. 响应和错误契约

响应必须按状态码和媒体类型建模。只记录 `hasResponseSchema` 会丢失成功/失败和错误条件。异常通过 `mappedToErrorResponse` 连接 ErrorSchema/StatusCode；异常映射从 409 变为 500 属于契约行为变化，即使方法签名不变。

## 6. 序列化边界

```text
UserResponse.email serializesTo ApiUserResponse.email
```

Java 字段重命名但 `@JsonProperty` 保持不变时，内部影响被序列化层吸收。外部字段名、类型、格式、可空性和语义不变，ContractImpact 可拒绝；Serializer/Mapper 仍是回归影响点。

## 7. 消费者模型

消费者来源包括 Feign/HTTP Client、生成 SDK、前端请求、GraphQL 文档、gRPC Stub、Gateway Trace 和服务目录。区分：`staticallyConsumesAPI`、`observedConsumesAPI`、`mayConsumeAPI`。

未发现消费者不代表没有消费者。公开 API、外部 API 或缺少完整客户端仓库的 API 必须保留 UnknownExternalConsumerRisk。

## 8. 兼容规则

### 请求方向

- 新增可选参数/字段：通常向后兼容，但需检查行为默认值；
- 新增必填字段：旧客户端通常不兼容；
- non-null → nullable：服务端更宽松；
- nullable → non-null：旧请求可能失败。

### 响应方向

- 删除/重命名字段：高风险；
- 类型变化：通常破坏；
- 新增字段：多数宽松客户端兼容，严格 Schema 客户端可能失败；
- non-null → nullable：消费者风险高；
- 枚举新增：旧客户端穷举逻辑可能失败。

兼容性必须有方向和消费者能力，不能只保存一个无方向的 `compatible=true`。

## 9. GraphQL 与 gRPC

GraphQL 以 Query/Mutation/Subscription Field 和返回字段为契约单位，不能只建 `/graphql` 路径。消费者选择集可提供字段级运行证据。

gRPC 模型必须保存 Service、RPC Method、Message、FieldNumber、oneof、reserved。Protobuf 字段编号变化和复用通常比字段名变化更危险。

## 10. 安全契约

Authentication、Authorization、Scope、Role、Header 和 Token Requirement 是正式契约。无认证→需要认证、普通用户→管理员、Scope 收紧等变化需传播到所有消费者、Gateway、SDK 和测试，并产生 SecurityImpact。

## 11. 版本与迁移

每个 API 版本是独立 Operation/Schema 节点，并通过 versionOf/supersedes 连接。渐进迁移通常采用新字段或 v2，并保留旧契约直到消费者完成升级。不要仅把 version 作为字符串属性共用同一节点。

## 12. 示例

内部 `EmailAddress` 值对象变化：若 ResponseMapper 仍输出 JSON string，API Contract 不变；若变为对象 `{localPart, domain}`，SchemaFieldTypeChanged 传播到所有消费者字段、生成 SDK、ContractTest 和发布顺序。

## 13. 证据来源

OpenAPI、GraphQL SDL、Proto、框架路由元数据、API Gateway、客户端代码、生成器配置、运行 Trace、契约测试。运行调用频率用于风险排序，不用于证明未调用的 API 无消费者。

## 14. 注意事项

- Controller 方法不等于 API Operation；
- 代码字段不等于外部 Schema 字段；
- HTTP 调用不是本地 callsDirectly；
- 只比较名称和类型不够，还要比较 required、nullable、format、enum、错误和安全；
- API 文档与运行 Gateway 不一致时应产生 Contract Drift。