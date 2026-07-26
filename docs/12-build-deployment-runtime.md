# 构建、部署、运行时与发布模型

## 1. 设计目标

源码变化必须继续映射到构建产物、部署单元、运行实例和发布顺序。Module、LogicalService、BuildArtifact、DeployableUnit 和 RuntimeInstance 是不同概念，合并后无法正确处理共享库、SDK、容器镜像、滚动发布和旧版本依赖。

## 2. 最终节点

```text
DeliveryEntity
├── BuildTarget
├── BuildArtifact
│   ├── LibraryArtifact
│   ├── ExecutableArtifact
│   ├── ContainerImage
│   ├── ClientSDK
│   ├── MigrationPackage
│   └── InfrastructurePackage
├── ArtifactVersion
├── DeployableUnit
├── Release
├── Deployment
├── RuntimeInstance
├── DeploymentEnvironment
├── DeploymentStrategy
├── DeploymentAction
├── RoutingPolicy
├── ReleaseGate
└── MonitoringSignal
```

Logical Service 表达架构职责；DeployableUnit 表达独立发布单元；ArtifactVersion 是具体不可变版本；RuntimeInstance 是实际运行副本。

## 3. 最终关系

```text
BuildArtifact builtFrom CodeEntity
CodeEntity packagedInto BuildArtifact
Artifact assembledFrom Artifact
DeployableUnit dependsOnArtifact Artifact
DeployableUnit deployedAs ArtifactVersion
ArtifactVersion versionOf Artifact
ArtifactVersion partOfRelease Release
Deployment deploysArtifact ArtifactVersion
Deployment deployedTo Environment
RuntimeInstance instanceOf DeployableUnit
RuntimeInstance runsVersion ArtifactVersion
Deployment usesStrategy DeploymentStrategy
RoutingPolicy routesTo RuntimeTarget
DeploymentAction mustPrecede/mustFollow Action
Action blockedBy ReleaseGate
Deployment monitoredBy MonitoringSignal
Version canCoexistWith Version
```

兼容关系必须带方向和场景，最好用 CompatibilityAssessment，而不是无方向的 `compatibleWith`。

## 4. 源码、构建和部署影响分离

源码变化可能要求重建，但产物内容未变；共享库发布新版本不代表所有消费者立即部署；配置可能只需动态刷新。ImpactType 至少区分 RebuildRequired、RepackageRequired、RepublishRequired、RedeployRequired、RestartRequired、ConfigurationRefreshRequired 和 MigrationRequired。

## 5. 共享产物

`UserDTO packagedInto user-contract.jar`，多个服务 `dependsOnArtifact`。变化后先判断库本身重建/发布，再判断消费者是否升级依赖、是否实际使用变化符号、二进制兼容和打包方式。不要因为依赖同一库就自动重部署全部服务。

## 6. 运行版本和历史代码

生产可能同时运行 1.7.9 和 1.8.0。RuntimeInstance `runsVersion` ArtifactVersion，ArtifactVersion `containsRevision` CodeEntityRevision。数据库列删除、消息兼容和缓存格式必须分析所有正在运行的历史版本，不能只分析主分支当前代码。

## 7. 部署策略与混部

RollingDeployment 需要新旧版本可共存；BlueGreen 降低应用混部但可能共享数据库；Canary 需要流量比例、目标用户、观察窗口和回滚条件；Recreate 不混部但有可用性风险。

混部需检查：数据库读写格式、缓存/Session、消息 Schema、锁 Key、幂等 Key、API 双向兼容和配置。`canCoexistWith` 必须有测试或规则证据，未知时状态为 Unresolved。

## 8. 数据库发布顺序

采用 Expand–Migrate–Contract：先增加兼容结构，再部署能双读/双写的新应用，回填数据，确认旧版本下线后删除旧结构。

删除旧列前的 Gate：当前所有 RuntimeInstance、离线任务、报表和存储过程均不再依赖。主分支无引用不足以放行。

## 9. API 和消息发布顺序

破坏性 Provider 变化通常需要 Consumer 先升级为同时兼容新旧版本，再切换 Provider，最后移除兼容层。消息还需等待旧消息保留期或确认 Replay 兼容。

发布顺序不能从调用方向直接推导，必须由兼容矩阵决定：旧 Provider/新 Consumer、新 Provider/旧 Consumer、旧 Schema/新 Reader 等。

## 10. 配置、Flag 和 Secret

ConfigurationKey 保存 consumedAt 和 activationMode：BuildTime 需重建，StartupTime 需重启，Runtime 可刷新。Feature Flag 调整属于 RuntimeRollout Action，不一定部署。Secret 轮换根据 reloadMode 和旧 Secret 并行有效期确定重启与顺序。

## 11. Release 与 Gate

Release 聚合 ArtifactVersion、Migration、ConfigurationChange、FeatureFlagChange、Gateway Route 和 MessageSchema。ReleaseGate 可包括：ContractCompatibilityPassed、MigrationTestPassed、ConsumerReady、NoOldRuntimeDependency、SecurityApproved、CanaryHealthy。

DeploymentAction 形成发布 DAG，支持 mustPrecede、canRunInParallelWith、blocks。发布计划是影响分析产物，不是简单流水线配置复制。

## 12. 回滚

区分 BinaryRollbackPossible、DataRollbackPossible 和 OperationalRollbackSafe。新版本写入旧版本无法读取的数据、发布不可兼容消息、删除旧 Secret 或修改幂等 Key 后，即使镜像能回滚，系统也可能不能安全回滚。

## 13. 示例

删除 `user_table.legacy_email`：当前主分支无读取，但生产仍有 1.7.9 实例，其历史 Repository Revision readsColumn 该列。Contract Migration 被 Gate 阻塞，直到旧实例、离线任务和报表全部下线并完成备份/回滚验证。

## 14. 证据来源

构建系统、依赖锁、Artifact Registry、容器清单、SBOM、Kubernetes、服务注册、部署平台、Gateway、Service Mesh、APM 和运行配置。静态“应部署版本”与运行“实际版本”必须分别保存。

## 15. 注意事项

- Service 不等于 Image；
- 当前代码不等于所有运行版本；
- 调用方向不等于发布顺序；
- 兼容性具有方向和场景；
- 配置和 Flag 变化也属于发布/运行影响；
- 数据库 Contract 操作必须有明确 Gate 和回滚证据。