# 测试、覆盖与验证模型

## 1. 设计目标

测试模型把“哪些对象受到影响”转化成“需要执行哪些测试、哪些影响路径缺少验证”。最终模型必须区分执行覆盖与语义验证：代码被测试执行过，不代表测试对变化行为有断言。

## 2. 最终节点

```text
VerificationEntity
├── TestSuite
├── TestCase
│   ├── UnitTest
│   ├── IntegrationTest
│   ├── ContractTest
│   ├── EndToEndTest
│   ├── MigrationTest
│   ├── PerformanceTest
│   ├── SecurityTest
│   └── ReplayTest
├── Assertion
├── TestFixture
├── TestEnvironment
├── TestExecution
├── FailureMode
└── CompatibilityScenario
```

TestCase 必须独立于测试类和文件。Fixture 包括对象 Builder、JSON、SQL、消息样本、Mock 响应、Snapshot 和 Golden File。

## 3. 最终关系

```text
TestCase covers Entity
TestCase verifies EntityOrRule
TestCase assertsContract ContractEntity
TestCase validatesSchema Schema
TestCase verifiesBehavior BusinessRule
TestCase verifiesFailureMode FailureMode
TestCase coversDataFlow ImpactPath
TestCase usesFixture TestFixture
TestCase dependsOnTestEnvironment TestEnvironment
TestCase executesWithConfiguration ConfigurationValue
TestCase belongsToTestSuite TestSuite
TestExecution executesTest TestCase
TestExecution onRevision Revision
TestExecution result TestResult
```

`assertsContract`、`validatesSchema`、`verifiesBehavior` 是 `verifies` 的子属性。

## 4. covers 与 verifies

`covers` 来自覆盖工具和运行 Trace，只说明执行路径。`verifies` 表示测试设计目的和有效断言对象。两者联合可识别：高价值测试、间接覆盖、Mock 掉真实实现的失效测试、名称与行为不一致的陈旧测试。

验证关系来源有不同置信度：显式元数据/需求链接 > 断言数据流分析 > 测试名称推断 > 同文件/同类名推断。

## 5. 契约和字段级验证

API/消息测试不应只关联 Operation 或 EventType，还要关联具体 SchemaField、状态码、错误和兼容场景。接口测试只断言 200 并不验证 `email` 字段类型。

DataFlowCoverage 表达测试数据确实从 SourceField 流入 TargetField。它比普通行覆盖更适合 Mapper、序列化和持久化变化。

## 6. Fixture 影响

字段、Schema、数据库或消息变化经常首先破坏 Fixture。`Fixture represents Schema/Entity`，字段级可建立映射。影响报告应把测试代码和 Fixture 修改分开列出。

## 7. 测试环境与配置

IntegrationTest 依赖数据库、Broker、Schema Registry、容器镜像和证书。测试失败可能来自 TestEnvironment 变化。测试还应记录执行配置；若生产 timeout=500ms，而测试始终使用 3000ms，测试通过不能证明生产安全。

## 8. 测试选择算法

测试候选来源：

1. 直接 `verifies`/`assertsContract`/`validatesSchema`；
2. 直接或高置信 `covers`；
3. 受影响路径上的 Unit/Integration Test；
4. 所属业务流程的 E2E；
5. 与变化类型匹配的专项测试，例如 Migration、Replay、Security、Performance。

排序应综合关联强度、业务关键度、历史失败概率、稳定性、环境匹配和执行成本，而不是只按图距离。

## 9. 测试缺口

对关键对象设置最低验证要求：Public API 需要 ContractTest；MessageSchema 需要兼容和重放测试；Migration 需要迁移/回滚测试；Feature Flag 需要启用和关闭路径；CriticalBusinessRule 需要行为测试。

由于开放世界，输出应是“当前采集范围内未发现验证”，而非绝对“没有测试”。SHACL 或治理查询可用于发现缺口。

## 10. TestExecution 与 Flaky

TestExecution 保存版本、环境、结果、时长、失败类别和时间。历史结果用于识别 FlakyTest、StaleTest、OrphanTest 和高失败概率测试。Flaky 结果降低判定可信度，但不降低测试与变化的语义相关性。

## 11. 示例

`UserResponse.email string → object`：必须执行 Provider ContractTest、Consumer ContractTest 和 MapperTest；Consumer Service 实际读取字段时执行其 Unit/Integration Test；完整用户查询流程可选择 E2E。若移动端没有字段级契约测试，报告为验证缺口。

## 12. RDFS/OWL/SHACL

RDFS 统一测试类型和验证关系；OWL 定义 inverseOf 和测试角色；SHACL 检查关键契约、规则、迁移是否有最低测试。判断“无覆盖”使用闭包数据集上的查询/规则，而非 OWL 否定推理。

## 13. 注意事项

- 覆盖率高不等于验证充分；
- 测试文件名相似只是弱证据；
- 不要对所有影响都选择全部 E2E；
- Fixture、环境和配置必须纳入影响；
- 历史覆盖数据必须绑定 Commit/ArtifactVersion，不能直接套用到当前代码。