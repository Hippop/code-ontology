# 当前本体定义逐项审计清单

审计日期：2026-09-09。此文件是现状快照，不是新本体定义。

对应整体设计：[本体建模完整性审查与成熟化整体设计](40-ontology-modeling-completeness-and-maturity-design.md)。

定义绑定摘要：`da239c22fe1e7a661488ea9beb452dfcc4b38646419a199ef8dc0cfc9ea4629d`。

范围：开发包清单中的五套本体、四套 SHACL；611 项术语＝240 类＋296 对象属性＋75 数据属性。另有 dev:semanticLayer 注解属性，不计入 611 项。SDN 领域扩展不在本目录包内。

判读：类的“直接/含继承 Shape 数”只统计 sh:targetClass，不代表具体语义规则覆盖率；属性的“直接路径引用数”只统计 sh:path 恰为该属性的形状，排除复杂路径、SPARQL、运行时代码和逆关系。0 不自动等于错误。“缺”表示机器定义未提供，不表示外部说明文档不存在。

## code 定义

### 类（81）

| 术语 | 标签 | 说明 | 直接/含继承 Shape 数 | 上位类 |
|---|---|---|---|---|
| `code:APIOperation` | 缺 | 缺 | 0/0 | code:ContractEntity |
| `code:AcceptanceCriterion` | 缺 | 缺 | 0/0 | code:BusinessEntity |
| `code:ArchitectureEntity` | 缺 | 缺 | 0/0 | code:ImpactAnalysisEntity |
| `code:ArtifactVersion` | 缺 | 缺 | 0/0 | code:BuildArtifact |
| `code:BoundedContext` | 缺 | 缺 | 0/0 | code:ArchitectureEntity |
| `code:BuildArtifact` | 缺 | 缺 | 0/0 | code:DeliveryEntity |
| `code:BusinessCapability` | 缺 | 缺 | 0/0 | code:BusinessEntity |
| `code:BusinessEntity` | 缺 | 缺 | 0/0 | code:ImpactAnalysisEntity |
| `code:BusinessProcess` | 缺 | 缺 | 0/0 | code:BusinessEntity |
| `code:BusinessProcessStep` | 缺 | 缺 | 0/0 | code:BusinessEntity |
| `code:BusinessRule` | 缺 | 缺 | 0/0 | code:BusinessEntity |
| `code:Callable` | 缺 | 缺 | 0/0 | code:CodeEntity |
| `code:ChangeEntity` | 缺 | 缺 | 0/0 | code:ImpactAnalysisEntity |
| `code:ChangeItem` | 缺 | 缺 | 0/0 | code:ChangeEntity |
| `code:ChangeSet` | 缺 | 缺 | 0/0 | code:ChangeEntity |
| `code:Class` | 缺 | 缺 | 0/0 | code:Type |
| `code:CodeEntity` | 缺 | 缺 | 0/0 | code:ImpactAnalysisEntity |
| `code:Column` | 缺 | 缺 | 0/0 | code:DataEntity |
| `code:CommandMessage` | 缺 | 缺 | 0/0 | code:ContractEntity |
| `code:CompatibilityAssessment` | 缺 | 缺 | 0/0 | code:ImpactAnalysisEntity |
| `code:Component` | 缺 | 缺 | 0/0 | code:ArchitectureEntity |
| `code:ConfigurationChanged` | 缺 | 缺 | 0/0 | code:ChangeItem |
| `code:ConfigurationEntity` | 缺 | 缺 | 0/0 | code:ImpactAnalysisEntity |
| `code:ConfigurationKey` | 缺 | 缺 | 0/0 | code:ConfigurationEntity |
| `code:ConfigurationSource` | 缺 | 缺 | 0/0 | code:ConfigurationEntity |
| `code:ConfigurationValue` | 缺 | 缺 | 0/0 | code:ConfigurationEntity |
| `code:Constructor` | 缺 | 缺 | 0/0 | code:Callable |
| `code:ConsumerGroup` | 缺 | 缺 | 0/0 | code:ImpactAnalysisEntity |
| `code:ContractChanged` | 缺 | 缺 | 0/0 | code:ChangeItem |
| `code:ContractEntity` | 缺 | 缺 | 0/0 | code:ImpactAnalysisEntity |
| `code:ContractTest` | 缺 | 缺 | 0/0 | code:TestCase |
| `code:CriticalBusinessCapability` | 缺 | 缺 | 0/0 | code:BusinessCapability |
| `code:DataEntity` | 缺 | 缺 | 0/0 | code:ImpactAnalysisEntity |
| `code:Database` | 缺 | 缺 | 0/0 | code:DataEntity |
| `code:DeliveryEntity` | 缺 | 缺 | 0/0 | code:ImpactAnalysisEntity |
| `code:DeployableUnit` | 缺 | 缺 | 0/0 | code:DeliveryEntity |
| `code:Deployment` | 缺 | 缺 | 0/0 | code:DeliveryEntity |
| `code:DeploymentAction` | 缺 | 缺 | 0/0 | code:DeliveryEntity |
| `code:EndToEndTest` | 缺 | 缺 | 0/0 | code:TestCase |
| `code:Enum` | 缺 | 缺 | 0/0 | code:Type |
| `code:Environment` | 缺 | 缺 | 0/0 | code:ImpactAnalysisEntity |
| `code:EventType` | 缺 | 缺 | 0/0 | code:ContractEntity |
| `code:FeatureFlag` | 缺 | 缺 | 0/0 | code:ConfigurationKey |
| `code:Field` | 缺 | 缺 | 0/0 | code:CodeEntity |
| `code:FieldTypeChanged` | 缺 | 缺 | 0/0 | code:ChangeItem |
| `code:Function` | 缺 | 缺 | 0/0 | code:Callable |
| `code:ImpactAnalysisEntity` | 缺 | 缺 | 0/0 | — |
| `code:ImpactAssessment` | 缺 | 缺 | 0/0 | code:ImpactAnalysisEntity |
| `code:ImpactEvidence` | 缺 | 缺 | 0/0 | code:ImpactAnalysisEntity |
| `code:ImpactPath` | 缺 | 缺 | 0/0 | code:ImpactAnalysisEntity |
| `code:Index` | 缺 | 缺 | 0/0 | code:DataEntity |
| `code:IntegrationTest` | 缺 | 缺 | 0/0 | code:TestCase |
| `code:Interface` | 缺 | 缺 | 0/0 | code:Type |
| `code:LogicalService` | 缺 | 缺 | 0/0 | code:ArchitectureEntity |
| `code:MessageField` | 缺 | 缺 | 0/0 | code:SchemaField |
| `code:MessageSchema` | 缺 | 缺 | 0/0 | code:Schema |
| `code:Method` | 缺 | 缺 | 0/0 | code:Callable |
| `code:MethodDeleted` | 缺 | 缺 | 0/0 | code:ChangeItem |
| `code:Module` | 缺 | 缺 | 0/0 | code:CodeEntity |
| `code:Parameter` | 缺 | 缺 | 0/0 | code:CodeEntity |
| `code:Query` | 缺 | 缺 | 0/0 | code:DataEntity |
| `code:Release` | 缺 | 缺 | 0/0 | code:DeliveryEntity |
| `code:Repository` | 缺 | 缺 | 0/0 | code:CodeEntity |
| `code:RequestSchema` | 缺 | 缺 | 0/0 | code:Schema |
| `code:Requirement` | 缺 | 缺 | 0/0 | code:BusinessEntity |
| `code:ResponseSchema` | 缺 | 缺 | 0/0 | code:Schema |
| `code:RuntimeInstance` | 缺 | 缺 | 0/0 | code:DeliveryEntity |
| `code:Schema` | 缺 | 缺 | 0/0 | code:ContractEntity |
| `code:SchemaField` | 缺 | 缺 | 0/0 | code:ContractEntity |
| `code:Secret` | 缺 | 缺 | 0/0 | code:ConfigurationEntity |
| `code:SignatureChanged` | 缺 | 缺 | 0/0 | code:ChangeItem |
| `code:SourceFile` | 缺 | 缺 | 0/0 | code:CodeEntity |
| `code:Table` | 缺 | 缺 | 0/0 | code:DataEntity |
| `code:Team` | 缺 | 缺 | 0/0 | code:ImpactAnalysisEntity |
| `code:TestCase` | 缺 | 缺 | 0/0 | code:VerificationEntity |
| `code:TestEnvironment` | 缺 | 缺 | 0/0 | code:VerificationEntity |
| `code:TestFixture` | 缺 | 缺 | 0/0 | code:VerificationEntity |
| `code:Topic` | 缺 | 缺 | 0/0 | code:ContractEntity |
| `code:Type` | 缺 | 缺 | 0/0 | code:CodeEntity |
| `code:UnitTest` | 缺 | 缺 | 0/0 | code:TestCase |
| `code:VerificationEntity` | 缺 | 缺 | 0/0 | code:ImpactAnalysisEntity |

### 对象属性（127）

| 术语 | 标签 | 说明 | 直接路径引用数 | domain → range |
|---|---|---|---|---|
| `code:accountableTo` | 缺 | 缺 | 0 | 未声明 → code:Team |
| `code:affectsEntity` | 缺 | 缺 | 0 | code:ImpactAssessment → code:ImpactAnalysisEntity |
| `code:assertsContract` | 缺 | 缺 | 0 | code:ContractTest → code:ContractEntity |
| `code:belongsToComponent` | 缺 | 缺 | 0 | 未声明 → code:Component |
| `code:belongsToModule` | 缺 | 缺 | 0 | 未声明 → code:Module |
| `code:belongsToService` | 缺 | 缺 | 0 | 未声明 → code:LogicalService |
| `code:builtFrom` | 缺 | 缺 | 0 | code:BuildArtifact → code:CodeEntity |
| `code:callRelation` | 缺 | 缺 | 0 | code:Callable → code:Callable |
| `code:callsDirectly` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `code:callsRemoteOperation` | 缺 | 缺 | 0 | code:Callable → code:APIOperation |
| `code:canCoexistWith` | 缺 | 缺 | 0 | code:ArtifactVersion → code:ArtifactVersion |
| `code:causesImpact` | 缺 | 缺 | 0 | code:ChangeItem → code:ImpactAssessment |
| `code:changesEntity` | 缺 | 缺 | 0 | code:ChangeItem → code:ImpactAnalysisEntity |
| `code:compensatedBy` | 缺 | 缺 | 0 | code:BusinessProcessStep → code:BusinessProcessStep |
| `code:configurationDependsOn` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `code:configurationReadBy` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `code:consumesAPI` | 缺 | 缺 | 0 | 未声明 → code:APIOperation |
| `code:consumesEvent` | 缺 | 缺 | 0 | code:Callable → code:EventType |
| `code:containedIn` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `code:contains` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `code:containsChange` | 缺 | 缺 | 0 | code:ChangeSet → code:ChangeItem |
| `code:containsStep` | 缺 | 缺 | 0 | code:BusinessProcess → code:BusinessProcessStep |
| `code:contractDependsOn` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `code:covers` | 缺 | 缺 | 0 | code:TestCase → code:ImpactAnalysisEntity |
| `code:dataDependsOn` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `code:declarationDependsOn` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `code:declaredIn` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `code:declares` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `code:definesConfiguration` | 缺 | 缺 | 0 | code:ConfigurationSource → code:ConfigurationKey |
| `code:deliveryDependsOn` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `code:dependsOn` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `code:dependsOnArtifact` | 缺 | 缺 | 0 | 未声明 → code:BuildArtifact |
| `code:dependsOnSecret` | 缺 | 缺 | 0 | 未声明 → code:Secret |
| `code:dependsOnTestEnvironment` | 缺 | 缺 | 0 | code:TestCase → code:TestEnvironment |
| `code:deployedAs` | 缺 | 缺 | 0 | code:DeployableUnit → code:ArtifactVersion |
| `code:deployedTo` | 缺 | 缺 | 0 | code:Deployment → code:Environment |
| `code:derivedFrom` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `code:deserializesMessageAs` | 缺 | 缺 | 0 | code:MessageSchema → code:Type |
| `code:deserializesTo` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `code:dispatchesTo` | 缺 | 缺 | 0 | code:Callable → code:Callable |
| `code:effectiveIn` | 缺 | 缺 | 0 | code:ConfigurationValue → code:Environment |
| `code:enforcesRule` | 缺 | 缺 | 0 | code:ImpactAnalysisEntity → code:BusinessRule |
| `code:executesQuery` | 缺 | 缺 | 0 | code:Callable → code:Query |
| `code:executionDependsOn` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `code:exposedBy` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `code:exposes` | 缺 | 缺 | 0 | code:LogicalService → code:APIOperation |
| `code:extendsType` | 缺 | 缺 | 0 | code:Type → code:Type |
| `code:fieldAccess` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `code:guardedByFeatureFlag` | 缺 | 缺 | 0 | 未声明 → code:FeatureFlag |
| `code:hasFieldType` | 缺 | 缺 | 0 | code:Field → code:Type |
| `code:hasImpactPath` | 缺 | 缺 | 0 | code:ImpactAssessment → code:ImpactPath |
| `code:hasMessageSchema` | 缺 | 缺 | 0 | code:EventType → code:MessageSchema |
| `code:hasParameterType` | 缺 | 缺 | 0 | code:Callable → code:Type |
| `code:hasRequestSchema` | 缺 | 缺 | 0 | code:APIOperation → code:RequestSchema |
| `code:hasResponseSchema` | 缺 | 缺 | 0 | code:APIOperation → code:ResponseSchema |
| `code:hasReturnType` | 缺 | 缺 | 0 | code:Callable → code:Type |
| `code:hasSchemaField` | 缺 | 缺 | 0 | code:Schema → code:SchemaField |
| `code:implementsAcceptanceCriterion` | 缺 | 缺 | 0 | 未声明 → code:AcceptanceCriterion |
| `code:implementsOperation` | 缺 | 缺 | 0 | code:Callable → code:APIOperation |
| `code:implementsProcessStep` | 缺 | 缺 | 0 | code:ImpactAnalysisEntity → code:BusinessProcessStep |
| `code:implementsRequirement` | 缺 | 缺 | 0 | code:ImpactAnalysisEntity → code:Requirement |
| `code:implementsType` | 缺 | 缺 | 0 | code:Type → code:Interface |
| `code:instantiatesType` | 缺 | 缺 | 0 | code:Callable → code:Type |
| `code:invokesReflectively` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `code:isAPIConsumedBy` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `code:isColumnReadBy` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `code:isColumnWrittenBy` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `code:isConsumedBy` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `code:isCoveredBy` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `code:isDirectlyCalledBy` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `code:isEnforcedBy` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `code:isExtendedBy` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `code:isImplementedBy` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `code:isMappedFrom` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `code:isOverriddenBy` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `code:isParameterTypeOf` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `code:isPublishedBy` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `code:isReadBy` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `code:isReturnTypeOf` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `code:isSerializedFrom` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `code:isSupportedBy` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `code:isVerifiedBy` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `code:isWrittenBy` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `code:mappedToTable` | 缺 | 缺 | 0 | code:Type → code:Table |
| `code:mapsTo` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `code:mayBeCalledBy` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `code:mayCall` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `code:messagingDependsOn` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `code:mustPrecede` | 缺 | 缺 | 0 | code:DeploymentAction → code:DeploymentAction |
| `code:observedCalls` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `code:operationImplementedBy` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `code:overridesConfiguration` | 缺 | 缺 | 0 | code:ConfigurationValue → code:ConfigurationValue |
| `code:overridesMethod` | 缺 | 缺 | 0 | code:Callable → code:Callable |
| `code:ownedBy` | 缺 | 缺 | 0 | 未声明 → code:Team |
| `code:ownsEntity` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `code:packagedInto` | 缺 | 缺 | 0 | 未声明 → code:BuildArtifact |
| `code:partOfRelease` | 缺 | 缺 | 0 | code:ArtifactVersion → code:Release |
| `code:passesValueTo` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `code:persistedAs` | 缺 | 缺 | 0 | code:Field → code:Column |
| `code:precedes` | 缺 | 缺 | 0 | code:BusinessProcessStep → code:BusinessProcessStep |
| `code:providesValueFor` | 缺 | 缺 | 0 | code:ConfigurationValue → code:ConfigurationKey |
| `code:publishedTo` | 缺 | 缺 | 0 | code:EventType → code:Topic |
| `code:publishesEvent` | 缺 | 缺 | 0 | code:Callable → code:EventType |
| `code:readsColumn` | 缺 | 缺 | 0 | 未声明 → code:Column |
| `code:readsConfiguration` | 缺 | 缺 | 0 | 未声明 → code:ConfigurationKey |
| `code:readsData` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `code:readsField` | 缺 | 缺 | 0 | code:Callable → code:Field |
| `code:readsTable` | 缺 | 缺 | 0 | 未声明 → code:Table |
| `code:recommendedTest` | 缺 | 缺 | 0 | code:ImpactAssessment → code:TestCase |
| `code:referencesType` | 缺 | 缺 | 0 | 未声明 → code:Type |
| `code:relatedTo` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `code:requirementImplementedBy` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `code:reviewedBy` | 缺 | 缺 | 0 | 未声明 → code:Team |
| `code:runsVersion` | 缺 | 缺 | 0 | code:RuntimeInstance → code:ArtifactVersion |
| `code:serializesAsMessage` | 缺 | 缺 | 0 | code:Type → code:MessageSchema |
| `code:serializesTo` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `code:structurallyRelatedTo` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `code:subscribesTo` | 缺 | 缺 | 0 | code:ConsumerGroup → code:Topic |
| `code:supportedByEvidence` | 缺 | 缺 | 0 | code:ImpactAssessment → code:ImpactEvidence |
| `code:supportsCapability` | 缺 | 缺 | 0 | code:ImpactAnalysisEntity → code:BusinessCapability |
| `code:typeDependency` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `code:usesFixture` | 缺 | 缺 | 0 | code:TestCase → code:TestFixture |
| `code:verifies` | 缺 | 缺 | 0 | code:TestCase → code:ImpactAnalysisEntity |
| `code:writesColumn` | 缺 | 缺 | 0 | 未声明 → code:Column |
| `code:writesData` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `code:writesField` | 缺 | 缺 | 0 | code:Callable → code:Field |
| `code:writesTable` | 缺 | 缺 | 0 | 未声明 → code:Table |

### 数据属性（11）

| 术语 | 标签 | 说明 | 直接路径引用数 | domain → range |
|---|---|---|---|---|
| `code:afterValue` | 缺 | 缺 | 0 | code:ChangeItem → xsd:string |
| `code:analysisSource` | 缺 | 缺 | 0 | 未声明 → xsd:string |
| `code:beforeValue` | 缺 | 缺 | 0 | code:ChangeItem → xsd:string |
| `code:confidence` | 缺 | 缺 | 0 | 未声明 → xsd:decimal |
| `code:environmentName` | 缺 | 缺 | 0 | code:Environment → xsd:string |
| `code:impactType` | 缺 | 缺 | 0 | 未声明 → xsd:string |
| `code:propagationState` | 缺 | 缺 | 0 | 未声明 → xsd:string |
| `code:riskLevel` | 缺 | 缺 | 0 | 未声明 → xsd:string |
| `code:sourceRevision` | 缺 | 缺 | 0 | 未声明 → xsd:string |
| `code:stableId` | 缺 | 缺 | 0 | 未声明 → xsd:string |
| `code:version` | 缺 | 缺 | 0 | 未声明 → xsd:string |

## biz 定义

### 类（26）

| 术语 | 标签 | 说明 | 直接/含继承 Shape 数 | 上位类 |
|---|---|---|---|---|
| `biz:AcceptanceCriterion` | 缺 | 缺 | 0/1 | biz:BusinessEntity |
| `biz:Actor` | 缺 | 缺 | 0/1 | biz:BusinessEntity |
| `biz:AuthorizationRule` | 缺 | 缺 | 0/1 | biz:BusinessRule |
| `biz:BrokenMapping` | 缺 | 缺 | 0/1 | biz:BusinessMapping |
| `biz:BusinessAttribute` | 缺 | 缺 | 0/1 | biz:BusinessEntity |
| `biz:BusinessCapability` | 缺 | 缺 | 0/1 | biz:BusinessEntity |
| `biz:BusinessDomain` | 缺 | 缺 | 0/1 | biz:BusinessEntity |
| `biz:BusinessEntity` | 缺 | 缺 | 1/1 | code:ImpactAnalysisEntity |
| `biz:BusinessEvent` | 缺 | 缺 | 0/1 | biz:BusinessEntity |
| `biz:BusinessMapping` | 缺 | 缺 | 1/1 | code:ImpactAnalysisEntity |
| `biz:BusinessObject` | 缺 | 缺 | 0/1 | biz:BusinessEntity |
| `biz:BusinessProcess` | 缺 | 缺 | 1/2 | biz:BusinessEntity |
| `biz:BusinessProcessStep` | 缺 | 缺 | 0/1 | biz:BusinessEntity |
| `biz:BusinessRule` | 缺 | 缺 | 0/1 | biz:BusinessEntity |
| `biz:BusinessState` | 缺 | 缺 | 0/1 | biz:BusinessEntity |
| `biz:CandidateMapping` | 缺 | 缺 | 0/1 | biz:BusinessMapping |
| `biz:CompensationRule` | 缺 | 缺 | 0/1 | biz:BusinessRule |
| `biz:ConfirmedMapping` | 缺 | 缺 | 1/2 | biz:BusinessMapping |
| `biz:ConsistencyRule` | 缺 | 缺 | 0/1 | biz:BusinessRule |
| `biz:ImplementationSlice` | 缺 | 缺 | 1/1 | code:ImpactAnalysisEntity |
| `biz:RoutingRule` | 缺 | 缺 | 0/1 | biz:BusinessRule |
| `biz:ServiceLevelObjective` | 缺 | 缺 | 0/1 | biz:BusinessEntity |
| `biz:StateTransition` | 缺 | 缺 | 1/2 | biz:BusinessEntity |
| `biz:StateTransitionRule` | 缺 | 缺 | 0/1 | biz:BusinessRule |
| `biz:UseCase` | 缺 | 缺 | 1/2 | biz:BusinessEntity |
| `biz:ValidationRule` | 缺 | 缺 | 0/1 | biz:BusinessRule |

### 对象属性（54）

| 术语 | 标签 | 说明 | 直接路径引用数 | domain → range |
|---|---|---|---|---|
| `biz:attributeOfBusinessObject` | 缺 | 缺 | 0 | biz:BusinessAttribute → biz:BusinessObject |
| `biz:belongsToCapability` | 缺 | 缺 | 1 | 未声明 → biz:BusinessCapability |
| `biz:belongsToDomain` | 缺 | 缺 | 0 | biz:BusinessCapability → biz:BusinessDomain |
| `biz:belongsToProcess` | 缺 | 缺 | 0 | biz:BusinessProcessStep → biz:BusinessProcess |
| `biz:belongsToUseCase` | 缺 | 缺 | 0 | biz:BusinessProcess → biz:UseCase |
| `biz:branchesTo` | 缺 | 缺 | 0 | biz:BusinessProcessStep → biz:BusinessProcessStep |
| `biz:compensatedBy` | 缺 | 缺 | 0 | biz:BusinessProcessStep → biz:BusinessProcessStep |
| `biz:configuresRule` | 缺 | 缺 | 0 | code:ConfigurationKey → biz:BusinessRule |
| `biz:constrainsBusinessAttribute` | 缺 | 缺 | 0 | biz:BusinessRule → biz:BusinessAttribute |
| `biz:constrainsBusinessObject` | 缺 | 缺 | 0 | biz:BusinessRule → biz:BusinessObject |
| `biz:containsCapability` | 缺 | 缺 | 0 | biz:BusinessDomain → biz:BusinessCapability |
| `biz:containsStep` | 缺 | 缺 | 1 | biz:BusinessProcess → biz:BusinessProcessStep |
| `biz:containsSupportingEntity` | 缺 | 缺 | 0 | biz:ImplementationSlice → code:ImpactAnalysisEntity |
| `biz:containsUseCase` | 缺 | 缺 | 0 | biz:BusinessCapability → biz:UseCase |
| `biz:enforcesRule` | 缺 | 缺 | 0 | code:ImpactAnalysisEntity → biz:BusinessRule |
| `biz:follows` | 缺 | 缺 | 0 | biz:BusinessProcessStep → biz:BusinessProcessStep |
| `biz:fromState` | 缺 | 缺 | 1 | biz:StateTransition → biz:BusinessState |
| `biz:governedBy` | 缺 | 缺 | 0 | biz:BusinessProcessStep → biz:BusinessRule |
| `biz:governsStep` | 缺 | 缺 | 0 | biz:BusinessRule → biz:BusinessProcessStep |
| `biz:guardedBy` | 缺 | 缺 | 0 | biz:StateTransition → biz:BusinessRule |
| `biz:hasAcceptanceCriterion` | 缺 | 缺 | 0 | code:Requirement → biz:AcceptanceCriterion |
| `biz:hasBusinessAttribute` | 缺 | 缺 | 0 | biz:BusinessObject → biz:BusinessAttribute |
| `biz:hasBusinessInput` | 缺 | 缺 | 0 | biz:BusinessProcessStep → biz:BusinessObject |
| `biz:hasBusinessOutput` | 缺 | 缺 | 0 | biz:BusinessProcessStep → biz:BusinessObject |
| `biz:hasEntryStep` | 缺 | 缺 | 1 | biz:BusinessProcess → biz:BusinessProcessStep |
| `biz:hasExitStep` | 缺 | 缺 | 1 | biz:BusinessProcess → biz:BusinessProcessStep |
| `biz:hasPrimaryEntry` | 缺 | 缺 | 1 | biz:ImplementationSlice → code:ImpactAnalysisEntity |
| `biz:implementsProcessStep` | 缺 | 缺 | 1 | biz:ImplementationSlice → biz:BusinessProcessStep |
| `biz:includesProcess` | 缺 | 缺 | 1 | biz:UseCase → biz:BusinessProcess |
| `biz:isEnforcedBy` | 缺 | 缺 | 0 | biz:BusinessRule → code:ImpactAnalysisEntity |
| `biz:isImplementedBySlice` | 缺 | 缺 | 0 | biz:BusinessProcessStep → biz:ImplementationSlice |
| `biz:isRealizedBy` | 缺 | 缺 | 0 | biz:UseCase → code:ImpactAnalysisEntity |
| `biz:mappingBusinessEntity` | 缺 | 缺 | 1 | biz:BusinessMapping → biz:BusinessEntity |
| `biz:mappingRelation` | 缺 | 缺 | 0 | biz:BusinessMapping → rdf:Property |
| `biz:mappingTechnicalEntity` | 缺 | 缺 | 1 | biz:BusinessMapping → code:ImpactAnalysisEntity |
| `biz:performedByStep` | 缺 | 缺 | 0 | biz:StateTransition → biz:BusinessProcessStep |
| `biz:performsUseCase` | 缺 | 缺 | 0 | biz:Actor → biz:UseCase |
| `biz:precedes` | 缺 | 缺 | 0 | biz:BusinessProcessStep → biz:BusinessProcessStep |
| `biz:primaryImplementsStep` | 缺 | 缺 | 0 | code:CodeEntity → biz:BusinessProcessStep |
| `biz:producesBusinessEvent` | 缺 | 缺 | 0 | biz:BusinessProcessStep → biz:BusinessEvent |
| `biz:realizesUseCase` | 缺 | 缺 | 0 | code:ImpactAnalysisEntity → biz:UseCase |
| `biz:representsBusinessAttribute` | 缺 | 缺 | 0 | code:ImpactAnalysisEntity → biz:BusinessAttribute |
| `biz:representsBusinessEvent` | 缺 | 缺 | 0 | code:ContractEntity → biz:BusinessEvent |
| `biz:representsBusinessObject` | 缺 | 缺 | 0 | code:ImpactAnalysisEntity → biz:BusinessObject |
| `biz:runsInDeployableUnit` | 缺 | 缺 | 0 | biz:ImplementationSlice → code:DeployableUnit |
| `biz:satisfiesAcceptanceCriterion` | 缺 | 缺 | 0 | 未声明 → biz:AcceptanceCriterion |
| `biz:storesBusinessAttribute` | 缺 | 缺 | 0 | code:DataEntity → biz:BusinessAttribute |
| `biz:storesBusinessObject` | 缺 | 缺 | 0 | code:DataEntity → biz:BusinessObject |
| `biz:supportedByEvidence` | 缺 | 缺 | 1 | biz:BusinessMapping → code:ImpactEvidence |
| `biz:supportsStep` | 缺 | 缺 | 0 | code:ImpactAnalysisEntity → biz:BusinessProcessStep |
| `biz:toState` | 缺 | 缺 | 1 | biz:StateTransition → biz:BusinessState |
| `biz:transitionsState` | 缺 | 缺 | 0 | biz:BusinessProcessStep → biz:StateTransition |
| `biz:triggeredByBusinessEvent` | 缺 | 缺 | 0 | 未声明 → biz:BusinessEvent |
| `biz:verifiesBusinessEntity` | 缺 | 缺 | 0 | code:TestCase → biz:BusinessEntity |

### 数据属性（6）

| 术语 | 标签 | 说明 | 直接路径引用数 | domain → range |
|---|---|---|---|---|
| `biz:canonicalId` | 缺 | 缺 | 1 | 未声明 → xsd:string |
| `biz:confidence` | 缺 | 缺 | 1 | 未声明 → xsd:decimal |
| `biz:lastVerifiedCommit` | 缺 | 缺 | 1 | 未声明 → xsd:string |
| `biz:reviewStatus` | 缺 | 缺 | 0 | 未声明 → xsd:string |
| `biz:validFrom` | 缺 | 缺 | 0 | 未声明 → xsd:dateTime |
| `biz:validTo` | 缺 | 缺 | 0 | 未声明 → xsd:dateTime |

## eng 定义

### 类（22）

| 术语 | 标签 | 说明 | 直接/含继承 Shape 数 | 上位类 |
|---|---|---|---|---|
| `eng:AnalysisEvidence` | 缺 | 缺 | 0/1 | eng:VerificationEvidence |
| `eng:AnalysisVerification` | 缺 | 缺 | 0/1 | eng:VerificationMethod |
| `eng:BehaviorContract` | 缺 | 缺 | 0/1 | eng:RequirementContract |
| `eng:ConstraintContract` | 缺 | 缺 | 0/1 | eng:RequirementContract |
| `eng:DemonstrationVerification` | 缺 | 缺 | 0/1 | eng:VerificationMethod |
| `eng:EngineeringRequirement` | 缺 | 缺 | 1/1 | code:Requirement |
| `eng:EngineeringSubmodel` | 缺 | 缺 | 0/0 | code:ImpactAnalysisEntity |
| `eng:ExecutedVerificationMethod` | 缺 | 缺 | 1/2 | eng:VerificationMethod |
| `eng:FormalProofVerification` | 缺 | 缺 | 0/1 | eng:VerificationMethod |
| `eng:InputOutputContract` | 缺 | 缺 | 0/1 | eng:RequirementContract |
| `eng:InspectionVerification` | 缺 | 缺 | 0/1 | eng:VerificationMethod |
| `eng:OntologyAsset` | 缺 | 缺 | 0/0 | code:ImpactAnalysisEntity |
| `eng:ProofEvidence` | 缺 | 缺 | 0/1 | eng:VerificationEvidence |
| `eng:RequirementContract` | 缺 | 缺 | 1/1 | code:ContractEntity |
| `eng:SemanticContract` | 缺 | 缺 | 1/1 | code:ContractEntity |
| `eng:SpecificationContract` | 缺 | 缺 | 0/1 | eng:RequirementContract |
| `eng:StateContract` | 缺 | 缺 | 0/1 | eng:RequirementContract |
| `eng:TestExecutionEvidence` | 缺 | 缺 | 0/1 | eng:VerificationEvidence |
| `eng:TestVerification` | 缺 | 缺 | 0/1 | eng:VerificationMethod |
| `eng:VerificationEvidence` | 缺 | 缺 | 1/1 | code:ImpactEvidence |
| `eng:VerificationMethod` | 缺 | 缺 | 1/1 | code:VerificationEntity |
| `eng:VerificationObjective` | 缺 | 缺 | 1/1 | code:VerificationEntity |

### 对象属性（17）

| 术语 | 标签 | 说明 | 直接路径引用数 | domain → range |
|---|---|---|---|---|
| `eng:capabilitySpecifiedBy` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `eng:constrainedBy` | 缺 | 缺 | 1 | eng:EngineeringRequirement → eng:SemanticContract |
| `eng:constrainsRequirement` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `eng:contractDefinedBy` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `eng:definesContract` | 缺 | 缺 | 0 | eng:EngineeringRequirement → eng:RequirementContract |
| `eng:derivedFromObjective` | 缺 | 缺 | 1 | eng:VerificationMethod → eng:VerificationObjective |
| `eng:derivedFromRequirement` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `eng:derivesRequirement` | 缺 | 缺 | 0 | eng:EngineeringRequirement → eng:EngineeringRequirement |
| `eng:evidenceArtifact` | 缺 | 缺 | 1 | eng:VerificationEvidence → code:ImpactAnalysisEntity |
| `eng:evidenceSatisfiesVerification` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `eng:hasVerificationMethod` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `eng:rootCapability` | 缺 | 缺 | 0 | eng:EngineeringSubmodel → code:BusinessCapability |
| `eng:satisfiedByEvidence` | 缺 | 缺 | 2 | eng:VerificationMethod → eng:VerificationEvidence |
| `eng:specifiesCapability` | 缺 | 缺 | 2 | eng:EngineeringRequirement → code:BusinessCapability |
| `eng:usesOntology` | 缺 | 缺 | 1 | eng:SemanticContract → eng:OntologyAsset |
| `eng:verifiedByMethod` | 缺 | 缺 | 0 | 未声明 → 未声明 |
| `eng:verifiesRequirement` | 缺 | 缺 | 1 | eng:VerificationMethod → eng:EngineeringRequirement |

### 数据属性（1）

| 术语 | 标签 | 说明 | 直接路径引用数 | domain → range |
|---|---|---|---|---|
| `eng:executionStatus` | 缺 | 缺 | 0 | eng:VerificationMethod → 未声明 |

## plan 定义

### 类（62）

| 术语 | 标签 | 说明 | 直接/含继承 Shape 数 | 上位类 |
|---|---|---|---|---|
| `plan:AddEntityDifference` | 缺 | 缺 | 0/0 | plan:GraphDifference |
| `plan:AddRelationDifference` | 缺 | 缺 | 0/0 | plan:GraphDifference |
| `plan:AlternativeImplementation` | 缺 | 缺 | 0/1 | plan:ReconciliationResult |
| `plan:CandidateAlignment` | 缺 | 缺 | 1/1 | code:ImpactAnalysisEntity |
| `plan:CannotVerify` | 缺 | 缺 | 0/1 | plan:ReconciliationResult |
| `plan:ConstraintDifference` | 缺 | 缺 | 0/0 | plan:GraphDifference |
| `plan:DeliveryAction` | 缺 | 缺 | 0/0 | code:DeliveryEntity |
| `plan:DeliveryDifference` | 缺 | 缺 | 0/0 | plan:GraphDifference |
| `plan:DesignArtifact` | 缺 | 缺 | 0/0 | code:ImpactAnalysisEntity |
| `plan:DesignChangeSet` | 缺 | 缺 | 1/1 | code:ChangeSet |
| `plan:DesignDecision` | 缺 | 缺 | 1/1 | code:ImpactAnalysisEntity |
| `plan:DesignDocument` | 缺 | 缺 | 1/1 | plan:DesignArtifact |
| `plan:DesignRevision` | 缺 | 缺 | 1/1 | plan:DesignArtifact |
| `plan:DesignSection` | 缺 | 缺 | 0/0 | plan:DesignArtifact |
| `plan:DesiredAPIOperation` | 缺 | 缺 | 0/1 | plan:DesiredTechnicalEntity |
| `plan:DesiredBusinessEntity` | 缺 | 缺 | 0/1 | plan:DesiredGraphEntity |
| `plan:DesiredCodeRole` | 缺 | 缺 | 0/1 | plan:DesiredTechnicalEntity |
| `plan:DesiredConfigurationKey` | 缺 | 缺 | 0/1 | plan:DesiredTechnicalEntity |
| `plan:DesiredDatabaseObject` | 缺 | 缺 | 0/1 | plan:DesiredTechnicalEntity |
| `plan:DesiredDeploymentAction` | 缺 | 缺 | 0/1 | plan:DesiredTechnicalEntity |
| `plan:DesiredEventType` | 缺 | 缺 | 0/1 | plan:DesiredTechnicalEntity |
| `plan:DesiredGraphEntity` | 缺 | 缺 | 1/1 | code:ImpactAnalysisEntity |
| `plan:DesiredSchema` | 缺 | 缺 | 0/1 | plan:DesiredTechnicalEntity |
| `plan:DesiredSchemaField` | 缺 | 缺 | 0/1 | plan:DesiredTechnicalEntity |
| `plan:DesiredTechnicalEntity` | 缺 | 缺 | 0/1 | plan:DesiredGraphEntity |
| `plan:DesiredTestObligation` | 缺 | 缺 | 0/1 | plan:DesiredTechnicalEntity |
| `plan:DocumentEvidence` | 缺 | 缺 | 1/1 | code:ImpactEvidence |
| `plan:ExplicitDesignFact` | 缺 | 缺 | 0/0 | plan:DesignArtifact |
| `plan:GraphDifference` | 缺 | 缺 | 0/0 | plan:SemanticGraphDiff |
| `plan:ImplementationSuggestion` | 缺 | 缺 | 0/0 | plan:DesignArtifact |
| `plan:ImplementationTask` | 缺 | 缺 | 1/1 | code:ImpactAnalysisEntity |
| `plan:ImplementedAsDesigned` | 缺 | 缺 | 0/1 | plan:ReconciliationResult |
| `plan:InferredDesignFact` | 缺 | 缺 | 0/0 | plan:DesignArtifact |
| `plan:MigrationAction` | 缺 | 缺 | 0/0 | code:DeliveryEntity |
| `plan:MissingImplementation` | 缺 | 缺 | 0/1 | plan:ReconciliationResult |
| `plan:ModifyEntityDifference` | 缺 | 缺 | 0/0 | plan:GraphDifference |
| `plan:PartiallyImplemented` | 缺 | 缺 | 0/1 | plan:ReconciliationResult |
| `plan:PlanningRule` | 缺 | 缺 | 0/0 | code:ImpactAnalysisEntity |
| `plan:ProposedBehaviorChange` | 缺 | 缺 | 0/1 | plan:ProposedChange |
| `plan:ProposedChange` | 缺 | 缺 | 1/1 | code:ChangeItem |
| `plan:ProposedConfigurationChange` | 缺 | 缺 | 0/1 | plan:ProposedChange |
| `plan:ProposedConstraintChange` | 缺 | 缺 | 0/1 | plan:ProposedChange |
| `plan:ProposedContractChange` | 缺 | 缺 | 0/1 | plan:ProposedChange |
| `plan:ProposedDataMigration` | 缺 | 缺 | 0/1 | plan:ProposedChange |
| `plan:ProposedDeploymentChange` | 缺 | 缺 | 0/1 | plan:ProposedChange |
| `plan:ProposedNodeAddition` | 缺 | 缺 | 0/1 | plan:ProposedChange |
| `plan:ProposedNodeModification` | 缺 | 缺 | 1/2 | plan:ProposedChange |
| `plan:ProposedNodeRemoval` | 缺 | 缺 | 1/2 | plan:ProposedChange |
| `plan:ProposedRelationAddition` | 缺 | 缺 | 0/1 | plan:ProposedChange |
| `plan:ProposedRelationRemoval` | 缺 | 缺 | 0/1 | plan:ProposedChange |
| `plan:ProposedTestChange` | 缺 | 缺 | 0/1 | plan:ProposedChange |
| `plan:ReconciliationResult` | 缺 | 缺 | 1/1 | code:ImpactAnalysisEntity |
| `plan:ReconciliationRun` | 缺 | 缺 | 1/1 | code:ImpactAnalysisEntity |
| `plan:RemoveEntityDifference` | 缺 | 缺 | 0/0 | plan:GraphDifference |
| `plan:RemoveRelationDifference` | 缺 | 缺 | 0/0 | plan:GraphDifference |
| `plan:RequirementIR` | 缺 | 缺 | 1/1 | plan:DesignArtifact |
| `plan:SemanticGraphDiff` | 缺 | 缺 | 0/0 | code:ImpactAnalysisEntity |
| `plan:StateTransitionDifference` | 缺 | 缺 | 0/0 | plan:GraphDifference |
| `plan:UnexpectedImplementation` | 缺 | 缺 | 0/1 | plan:ReconciliationResult |
| `plan:UnresolvedDesignQuestion` | 缺 | 缺 | 0/0 | plan:DesignArtifact |
| `plan:VerificationDifference` | 缺 | 缺 | 0/0 | plan:GraphDifference |
| `plan:VerificationObligation` | 缺 | 缺 | 0/0 | code:VerificationEntity |

### 对象属性（41）

| 术语 | 标签 | 说明 | 直接路径引用数 | domain → range |
|---|---|---|---|---|
| `plan:affectsProposedChange` | 缺 | 缺 | 1 | plan:DesignDecision → plan:ProposedChange |
| `plan:alignedCurrentEntity` | 缺 | 缺 | 1 | plan:CandidateAlignment → code:ImpactAnalysisEntity |
| `plan:alignedDesiredEntity` | 缺 | 缺 | 1 | plan:CandidateAlignment → plan:DesiredGraphEntity |
| `plan:basedOnAlignment` | 缺 | 缺 | 0 | plan:ProposedChange → plan:CandidateAlignment |
| `plan:basedOnGraphDiff` | 缺 | 缺 | 0 | plan:DesignChangeSet → plan:SemanticGraphDiff |
| `plan:comparesCurrentRevision` | 缺 | 缺 | 0 | plan:SemanticGraphDiff → 未声明 |
| `plan:comparesDesiredRevision` | 缺 | 缺 | 0 | plan:SemanticGraphDiff → plan:DesignRevision |
| `plan:containsDifference` | 缺 | 缺 | 0 | plan:SemanticGraphDiff → plan:GraphDifference |
| `plan:containsProposedChange` | 缺 | 缺 | 1 | plan:DesignChangeSet → plan:ProposedChange |
| `plan:containsReconciliationResult` | 缺 | 缺 | 1 | plan:ReconciliationRun → plan:ReconciliationResult |
| `plan:containsSection` | 缺 | 缺 | 0 | plan:DesignRevision → plan:DesignSection |
| `plan:createsTask` | 缺 | 缺 | 0 | plan:ProposedChange → plan:ImplementationTask |
| `plan:definesDesiredEntity` | 缺 | 缺 | 1 | plan:RequirementIR → plan:DesiredGraphEntity |
| `plan:dependsOnProposedChange` | 缺 | 缺 | 0 | plan:ProposedChange → plan:ProposedChange |
| `plan:derivedByRule` | 缺 | 缺 | 0 | plan:ProposedChange → plan:PlanningRule |
| `plan:derivedFromDesignRevision` | 缺 | 缺 | 1 | plan:DesignChangeSet → plan:DesignRevision |
| `plan:derivedFromRequirement` | 缺 | 缺 | 1 | plan:DesignChangeSet → biz:Requirement |
| `plan:derivedFromRevision` | 缺 | 缺 | 1 | 未声明 → plan:DesignRevision |
| `plan:describesRequirement` | 缺 | 缺 | 1 | plan:RequirementIR → biz:Requirement |
| `plan:desiredCounterpartOf` | 缺 | 缺 | 0 | plan:DesiredGraphEntity → code:ImpactAnalysisEntity |
| `plan:desiredRoleType` | 缺 | 缺 | 0 | plan:DesiredCodeRole → 未声明 |
| `plan:differenceCurrentEntity` | 缺 | 缺 | 0 | plan:GraphDifference → code:ImpactAnalysisEntity |
| `plan:differenceDesiredEntity` | 缺 | 缺 | 0 | plan:GraphDifference → plan:DesiredGraphEntity |
| `plan:hasAlternativeAlignment` | 缺 | 缺 | 0 | plan:CandidateAlignment → plan:CandidateAlignment |
| `plan:hasRevision` | 缺 | 缺 | 1 | plan:DesignDocument → plan:DesignRevision |
| `plan:implementsProposedChange` | 缺 | 缺 | 1 | plan:ImplementationTask → plan:ProposedChange |
| `plan:matchedActualEntity` | 缺 | 缺 | 0 | plan:ReconciliationResult → code:ImpactAnalysisEntity |
| `plan:normalizedAs` | 缺 | 缺 | 1 | plan:DesignRevision → plan:RequirementIR |
| `plan:proposesEntity` | 缺 | 缺 | 1 | plan:ProposedChange → plan:DesiredGraphEntity |
| `plan:reconcilesChangeSet` | 缺 | 缺 | 1 | plan:ReconciliationRun → plan:DesignChangeSet |
| `plan:reconcilesProposedChange` | 缺 | 缺 | 1 | plan:ReconciliationResult → plan:ProposedChange |
| `plan:requiresDecision` | 缺 | 缺 | 1 | plan:ProposedChange → plan:DesignDecision |
| `plan:requiresDeliveryAction` | 缺 | 缺 | 0 | plan:ProposedChange → plan:DeliveryAction |
| `plan:requiresMigrationAction` | 缺 | 缺 | 0 | plan:ProposedChange → plan:MigrationAction |
| `plan:requiresVerification` | 缺 | 缺 | 0 | plan:ProposedChange → plan:VerificationObligation |
| `plan:revisionOf` | 缺 | 缺 | 0 | plan:DesignRevision → plan:DesignDocument |
| `plan:selectedAlternative` | 缺 | 缺 | 0 | plan:DesignDecision → 未声明 |
| `plan:supportedByDesignEvidence` | 缺 | 缺 | 3 | 未声明 → plan:DocumentEvidence |
| `plan:targetsCurrentEntity` | 缺 | 缺 | 2 | plan:ProposedChange → code:ImpactAnalysisEntity |
| `plan:usesActualRevision` | 缺 | 缺 | 0 | plan:ReconciliationRun → 未声明 |
| `plan:verifiedByTest` | 缺 | 缺 | 0 | plan:ReconciliationResult → code:TestCase |

### 数据属性（18）

| 术语 | 标签 | 说明 | 直接路径引用数 | domain → range |
|---|---|---|---|---|
| `plan:alignmentStatus` | 缺 | 缺 | 0 | 未声明 → xsd:string |
| `plan:alignmentType` | 缺 | 缺 | 1 | 未声明 → xsd:string |
| `plan:confidence` | 缺 | 缺 | 2 | 未声明 → xsd:decimal |
| `plan:contentHash` | 缺 | 缺 | 1 | 未声明 → xsd:string |
| `plan:decisionQuestion` | 缺 | 缺 | 1 | 未声明 → xsd:string |
| `plan:decisionRationale` | 缺 | 缺 | 1 | 未声明 → xsd:string |
| `plan:documentId` | 缺 | 缺 | 1 | 未声明 → xsd:string |
| `plan:missingStatus` | 缺 | 缺 | 0 | 未声明 → xsd:string |
| `plan:proposalStatus` | 缺 | 缺 | 1 | 未声明 → xsd:string |
| `plan:reasonCode` | 缺 | 缺 | 0 | 未声明 → xsd:string |
| `plan:reconciliationStatus` | 缺 | 缺 | 1 | 未声明 → xsd:string |
| `plan:revisionNumber` | 缺 | 缺 | 1 | 未声明 → xsd:string |
| `plan:riskLevel` | 缺 | 缺 | 1 | 未声明 → xsd:string |
| `plan:ruleVersion` | 缺 | 缺 | 0 | 未声明 → xsd:string |
| `plan:sectionId` | 缺 | 缺 | 1 | 未声明 → xsd:string |
| `plan:sourceText` | 缺 | 缺 | 1 | 未声明 → xsd:string |
| `plan:taskStatus` | 缺 | 缺 | 1 | 未声明 → xsd:string |
| `plan:toolVersion` | 缺 | 缺 | 0 | 未声明 → xsd:string |

## dev 定义

### 类（49）

| 术语 | 标签 | 说明 | 直接/含继承 Shape 数 | 上位类 |
|---|---|---|---|---|
| `dev:AcceptanceCriterion` | 可验证验收条件 | 有 | 1/2 | code:AcceptanceCriterion, dev:Entity |
| `dev:Approval` | 范围绑定批准 | 有 | 1/2 | dev:Entity |
| `dev:BehaviorClause` | 行为条款 | 有 | 1/3 | dev:ContractClause |
| `dev:BusinessAttribute` | 业务属性 | 有 | 1/3 | biz:BusinessAttribute, dev:Entity |
| `dev:BusinessConcept` | 业务概念 | 有 | 1/3 | biz:BusinessObject, dev:Entity |
| `dev:BusinessGoal` | 业务目标 | 有 | 1/2 | dev:Entity |
| `dev:BusinessRule` | 业务规则 | 有 | 1/3 | biz:BusinessRule, dev:Entity |
| `dev:ChangeObligation` | 实现义务 | 有 | 0/2 | dev:Obligation |
| `dev:ChangePlan` | 开发变更计划 | 有 | 1/2 | dev:Entity |
| `dev:CodeArtifact` | 代码产物修订 | 有 | 1/2 | code:SourceFile, dev:Entity |
| `dev:CodeSnapshot` | 代码快照 | 有 | 1/2 | dev:Entity |
| `dev:ConstraintSet` | 约束集 | 有 | 0/2 | dev:VersionedAsset |
| `dev:ContractClause` | 契约条款 | 有 | 1/2 | dev:Entity |
| `dev:DesignDecision` | 架构决策 | 有 | 1/2 | dev:Entity |
| `dev:DesignElement` | 目标设计元素 | 有 | 1/2 | dev:Entity |
| `dev:DomainExtension` | 领域扩展包 | 有 | 1/4 | dev:MetamodelPackage |
| `dev:Entity` | 受治理开发实体 | 有 | 1/1 | code:ImpactAnalysisEntity |
| `dev:Evidence` | 可审计证据 | 有 | 1/3 | dev:Entity, eng:VerificationEvidence |
| `dev:ExecutionRun` | 执行记录 | 有 | 1/2 | dev:Entity |
| `dev:GenerationRun` | 生成执行 | 有 | 2/4 | dev:ExecutionRun |
| `dev:GenerationSpecification` | 生成规范 | 有 | 2/3 | dev:Entity |
| `dev:GraphRevision` | 图修订 | 有 | 2/4 | dev:VersionedAsset |
| `dev:ImpactAssessment` | 开发影响判断 | 有 | 1/2 | code:ImpactAssessment, dev:Entity |
| `dev:ImpactRule` | 影响传播规则 | 有 | 1/3 | dev:VersionedAsset |
| `dev:ImplementationSlice` | 实现切片 | 有 | 0/2 | biz:ImplementationSlice, dev:Entity |
| `dev:ImplementationTask` | 开发任务 | 有 | 1/2 | dev:Entity |
| `dev:Invariant` | 不变式条款 | 有 | 0/2 | dev:ContractClause |
| `dev:MetamodelPackage` | 元模型包修订 | 有 | 1/3 | dev:VersionedAsset, eng:OntologyAsset |
| `dev:MigrationPlan` | 元模型迁移计划 | 有 | 1/2 | dev:Entity |
| `dev:ModelRevision` | 项目模型修订 | 有 | 1/3 | dev:VersionedAsset |
| `dev:Obligation` | 工程义务 | 有 | 1/2 | dev:Entity |
| `dev:ObservationRun` | 事实采集执行 | 有 | 1/3 | dev:ExecutionRun |
| `dev:Project` | 工程项目 | 有 | 0/1 | dev:Entity |
| `dev:ProjectProfile` | 项目模型配置 | 有 | 1/3 | dev:VersionedAsset |
| `dev:RealizationMapping` | 实现映射记录 | 有 | 1/2 | dev:Entity |
| `dev:ReleaseAssessment` | 交付就绪判断 | 有 | 2/3 | dev:Entity |
| `dev:Requirement` | 开发需求 | 有 | 1/3 | dev:Entity, eng:EngineeringRequirement |
| `dev:RuleSet` | 规则集 | 有 | 1/3 | dev:VersionedAsset |
| `dev:SatisfactionAssessment` | 满足性判断 | 有 | 2/3 | dev:Entity |
| `dev:SemanticContract` | 领域语义契约 | 有 | 1/3 | dev:Entity, eng:SemanticContract |
| `dev:SemanticDelta` | 语义差异 | 有 | 1/2 | dev:Entity |
| `dev:TechnicalRepresentation` | 技术表示设计 | 有 | 1/3 | dev:DesignElement |
| `dev:TechnologyProfile` | 技术栈配置 | 有 | 1/3 | dev:VersionedAsset |
| `dev:TransformationRule` | 模型转换规则 | 有 | 1/3 | dev:VersionedAsset |
| `dev:ValueConstraint` | 值约束条款 | 有 | 2/4 | dev:ContractClause |
| `dev:VerificationObligation` | 验证义务 | 有 | 0/2 | dev:Obligation |
| `dev:VerificationRun` | 验证执行 | 有 | 1/3 | dev:ExecutionRun |
| `dev:VerificationSpecification` | 验证规范 | 有 | 1/3 | dev:VersionedAsset |
| `dev:VersionedAsset` | 版本化资产 | 有 | 1/2 | dev:Entity |

### 对象属性（57）

| 术语 | 标签 | 说明 | 直接路径引用数 | domain → range |
|---|---|---|---|---|
| `dev:addresses` | 针对语义责任 | 有 | 2 | 未声明 → 未声明 |
| `dev:affectedEntity` | 受影响对象 | 有 | 1 | 未声明 → 未声明 |
| `dev:affectsProfile` | 影响项目配置 | 有 | 1 | 未声明 → dev:ProjectProfile |
| `dev:appliesRule` | 应用转换规则 | 有 | 1 | 未声明 → dev:TransformationRule |
| `dev:approvalSubject` | 批准对象 | 有 | 1 | 未声明 → 未声明 |
| `dev:approvedBy` | 批准记录 | 有 | 0 | 未声明 → dev:Approval |
| `dev:assesses` | 判断对象 | 有 | 1 | 未声明 → 未声明 |
| `dev:baseline` | 基线快照 | 有 | 2 | 未声明 → dev:CodeSnapshot |
| `dev:causedBy` | 源于语义差异 | 有 | 2 | 未声明 → dev:SemanticDelta |
| `dev:closedBy` | 由判断关闭 | 有 | 0 | 未声明 → dev:SatisfactionAssessment |
| `dev:constrains` | 约束业务对象 | 有 | 1 | 未声明 → 未声明 |
| `dev:containsEntity` | 包含实体 | 有 | 1 | 未声明 → 未声明 |
| `dev:createsObligation` | 产生工程义务 | 有 | 1 | 未声明 → dev:Obligation |
| `dev:decidedBy` | 依据设计决策 | 有 | 1 | 未声明 → dev:DesignDecision |
| `dev:definesTerm` | 收录语义定义 | 有 | 1 | dev:MetamodelPackage → 未声明 |
| `dev:dependsOnPackage` | 依赖定义包 | 有 | 2 | dev:MetamodelPackage → dev:MetamodelPackage |
| `dev:dependsOnTask` | 任务依赖 | 有 | 1 | dev:ImplementationTask → dev:ImplementationTask |
| `dev:evaluatesModel` | 检查模型修订 | 有 | 1 | 未声明 → dev:ModelRevision |
| `dev:evaluatesSnapshot` | 检查代码快照 | 有 | 1 | 未声明 → dev:CodeSnapshot |
| `dev:executesTask` | 执行开发任务 | 有 | 1 | dev:GenerationRun → dev:ImplementationTask |
| `dev:forProject` | 所属项目 | 有 | 2 | 未声明 → dev:Project |
| `dev:fromPackage` | 迁移源版本 | 有 | 1 | 未声明 → dev:MetamodelPackage |
| `dev:fulfills` | 承担义务 | 有 | 1 | dev:ImplementationTask → dev:Obligation |
| `dev:generatedBy` | 证据执行来源 | 有 | 1 | 未声明 → dev:VerificationRun |
| `dev:hasAcceptanceCriterion` | 具有验收条件 | 有 | 1 | dev:Requirement → dev:AcceptanceCriterion |
| `dev:hasAttribute` | 具有业务属性 | 有 | 0 | dev:BusinessConcept → dev:BusinessAttribute |
| `dev:hasClause` | 包含条款 | 有 | 1 | dev:SemanticContract → dev:ContractClause |
| `dev:hasMember` | 切片成员 | 有 | 0 | dev:ImplementationSlice → 未声明 |
| `dev:hasObligation` | 计划包含义务 | 有 | 1 | dev:ChangePlan → dev:Obligation |
| `dev:hasTask` | 计划包含任务 | 有 | 1 | dev:ChangePlan → dev:ImplementationTask |
| `dev:inModel` | 所属模型修订 | 有 | 1 | 未声明 → dev:ModelRevision |
| `dev:inSnapshot` | 所属代码快照 | 有 | 2 | 未声明 → dev:CodeSnapshot |
| `dev:includesAssessment` | 聚合满足性判断 | 有 | 1 | 未声明 → dev:SatisfactionAssessment |
| `dev:includesRule` | 包含规则 | 有 | 1 | dev:RuleSet → 未声明 |
| `dev:inputDesign` | 输入目标设计 | 有 | 1 | 未声明 → dev:DesignElement |
| `dev:mappingSource` | 映射语义源 | 有 | 1 | dev:RealizationMapping → 未声明 |
| `dev:mappingTarget` | 映射技术目标 | 有 | 1 | dev:RealizationMapping → 未声明 |
| `dev:motivates` | 驱动需求 | 有 | 0 | dev:BusinessGoal → dev:Requirement |
| `dev:observedBy` | 由采集确认 | 有 | 1 | 未声明 → dev:ObservationRun |
| `dev:preserves` | 承诺保留条款 | 有 | 1 | 未声明 → dev:ContractClause |
| `dev:produces` | 产生实际产物 | 有 | 0 | dev:ExecutionRun → 未声明 |
| `dev:refines` | 细化需求 | 有 | 1 | dev:Requirement → dev:Requirement |
| `dev:repository` | 关联仓库 | 有 | 1 | 未声明 → code:Repository |
| `dev:represents` | 表示业务含义 | 有 | 1 | dev:TechnicalRepresentation → 未声明 |
| `dev:supportedBy` | 由证据支持 | 有 | 2 | 未声明 → dev:Evidence |
| `dev:targetModel` | 目标模型 | 有 | 1 | 未声明 → dev:ModelRevision |
| `dev:toPackage` | 迁移目标版本 | 有 | 1 | 未声明 → dev:MetamodelPackage |
| `dev:triggeredRule` | 命中影响规则 | 有 | 1 | 未声明 → dev:ImpactRule |
| `dev:underPlan` | 依据变更计划 | 有 | 2 | 未声明 → dev:ChangePlan |
| `dev:usesConstraints` | 采用约束集 | 有 | 1 | 未声明 → dev:ConstraintSet |
| `dev:usesPackage` | 采用定义包 | 有 | 1 | 未声明 → dev:MetamodelPackage |
| `dev:usesProfile` | 采用项目配置 | 有 | 1 | 未声明 → dev:ProjectProfile |
| `dev:usesRules` | 采用规则集 | 有 | 1 | 未声明 → dev:RuleSet |
| `dev:usesSpecification` | 采用执行规范 | 有 | 2 | 未声明 → 未声明 |
| `dev:usesTechnology` | 采用技术栈 | 有 | 2 | 未声明 → dev:TechnologyProfile |
| `dev:valueDatatype` | 值数据类型 | 有 | 1 | 未声明 → 未声明 |
| `dev:verifies` | 验证语义目标 | 有 | 1 | dev:VerificationSpecification → 未声明 |

### 数据属性（39）

| 术语 | 标签 | 说明 | 直接路径引用数 | domain → range |
|---|---|---|---|---|
| `dev:actor` | 责任主体 | 有 | 1 | 未声明 → xsd:string |
| `dev:allowedValue` | 允许值 | 有 | 1 | 未声明 → 未声明 |
| `dev:alternative` | 候选方案 | 有 | 1 | 未声明 → xsd:string |
| `dev:changeKind` | 变化种类 | 有 | 1 | 未声明 → xsd:string |
| `dev:chosenOption` | 选定方案 | 有 | 1 | 未声明 → xsd:string |
| `dev:commit` | 提交标识 | 有 | 1 | 未声明 → xsd:string |
| `dev:contentHash` | 内容摘要 | 有 | 1 | 未声明 → xsd:string |
| `dev:defaultValue` | 缺省值 | 有 | 1 | 未声明 → 未声明 |
| `dev:endedAt` | 结束时间 | 有 | 1 | 未声明 → xsd:dateTime |
| `dev:executorVersion` | 执行器版本 | 有 | 1 | 未声明 → xsd:string |
| `dev:expectedResult` | 预期结果 | 有 | 1 | 未声明 → xsd:string |
| `dev:failureBehavior` | 失败行为 | 有 | 1 | 未声明 → xsd:string |
| `dev:framework` | 框架约定 | 有 | 1 | 未声明 → xsd:string |
| `dev:graphRole` | 图角色 | 有 | 1 | 未声明 → xsd:string |
| `dev:graphSpace` | 图生命周期 | 有 | 1 | 未声明 → xsd:string |
| `dev:impactPath` | 影响路径说明 | 有 | 1 | 未声明 → xsd:string |
| `dev:inputHash` | 输入摘要 | 有 | 1 | 未声明 → xsd:string |
| `dev:inputPattern` | 输入模式 | 有 | 2 | 未声明 → xsd:string |
| `dev:language` | 实现语言 | 有 | 1 | 未声明 → xsd:string |
| `dev:mappingRole` | 映射角色 | 有 | 1 | 未声明 → xsd:string |
| `dev:mode` | 实现方式 | 有 | 1 | 未声明 → xsd:string |
| `dev:outputPattern` | 输出模式 | 有 | 1 | 未声明 → xsd:string |
| `dev:postcondition` | 后置条件 | 有 | 1 | 未声明 → xsd:string |
| `dev:precondition` | 前置条件 | 有 | 3 | 未声明 → xsd:string |
| `dev:procedure` | 验证方法 | 有 | 1 | 未声明 → xsd:string |
| `dev:question` | 决策问题 | 有 | 1 | 未声明 → xsd:string |
| `dev:rationale` | 依据说明 | 有 | 1 | 未声明 → xsd:string |
| `dev:reportUri` | 报告位置 | 有 | 1 | 未声明 → xsd:anyURI |
| `dev:scenario` | 证据场景 | 有 | 1 | 未声明 → xsd:string |
| `dev:scope` | 适用范围 | 有 | 1 | 未声明 → xsd:string |
| `dev:source` | 来源 | 有 | 1 | 未声明 → xsd:string |
| `dev:startedAt` | 开始时间 | 有 | 1 | 未声明 → xsd:dateTime |
| `dev:statement` | 语义陈述 | 有 | 1 | 未声明 → xsd:string |
| `dev:status` | 生命周期状态 | 有 | 10 | 未声明 → xsd:string |
| `dev:stopCondition` | 传播停止条件 | 有 | 1 | 未声明 → xsd:string |
| `dev:targetPath` | 产物相对路径 | 有 | 1 | 未声明 → xsd:string |
| `dev:unit` | 业务单位 | 有 | 0 | 未声明 → xsd:string |
| `dev:unsupportedCase` | 不支持情况 | 有 | 1 | 未声明 → xsd:string |
| `dev:version` | 版本 | 有 | 1 | 未声明 → xsd:string |

## 同名术语检查

同名不等价；必须使用完整 IRI。以下仅列出命名碰撞，不表示建议合并。

| localName | 声明位置 |
|---|---|
| AcceptanceCriterion | biz:AcceptanceCriterion, code:AcceptanceCriterion, dev:AcceptanceCriterion |
| BusinessAttribute | biz:BusinessAttribute, dev:BusinessAttribute |
| BusinessCapability | biz:BusinessCapability, code:BusinessCapability |
| BusinessEntity | biz:BusinessEntity, code:BusinessEntity |
| BusinessProcess | biz:BusinessProcess, code:BusinessProcess |
| BusinessProcessStep | biz:BusinessProcessStep, code:BusinessProcessStep |
| BusinessRule | biz:BusinessRule, code:BusinessRule, dev:BusinessRule |
| DesignDecision | dev:DesignDecision, plan:DesignDecision |
| ImpactAssessment | code:ImpactAssessment, dev:ImpactAssessment |
| ImplementationSlice | biz:ImplementationSlice, dev:ImplementationSlice |
| ImplementationTask | dev:ImplementationTask, plan:ImplementationTask |
| Requirement | code:Requirement, dev:Requirement |
| SemanticContract | dev:SemanticContract, eng:SemanticContract |
| VerificationObligation | dev:VerificationObligation, plan:VerificationObligation |
| compensatedBy | biz:compensatedBy, code:compensatedBy |
| confidence | biz:confidence, code:confidence, plan:confidence |
| containsStep | biz:containsStep, code:containsStep |
| contentHash | dev:contentHash, plan:contentHash |
| derivedFromRequirement | eng:derivedFromRequirement, plan:derivedFromRequirement |
| enforcesRule | biz:enforcesRule, code:enforcesRule |
| hasAcceptanceCriterion | biz:hasAcceptanceCriterion, dev:hasAcceptanceCriterion |
| implementsProcessStep | biz:implementsProcessStep, code:implementsProcessStep |
| isEnforcedBy | biz:isEnforcedBy, code:isEnforcedBy |
| precedes | biz:precedes, code:precedes |
| riskLevel | code:riskLevel, plan:riskLevel |
| supportedByEvidence | biz:supportedByEvidence, code:supportedByEvidence |
| verifies | code:verifies, dev:verifies |
| version | code:version, dev:version |

## 定义引用未闭合

`biz:Requirement` 在五套本体内未声明为 owl:Class，但被 plan:describesRequirement、plan:derivedFromRequirement 的 range 引用，并被规划 SHACL 和 SDN 规划示例使用。修订策略见整体设计，不在本次审计中修改。

## 文件摘要

| 文件 | 三元组数 | SHA-256 |
|---|---:|---|
| ontology/code-ontology.ttl | 551 | `810ab952b8c94c704c90ac77f3d8c01b40cff8fdbe95bbc3f08ec1e824b5d61c` |
| ontology/business-code-linkage.ttl | 240 | `76e0318f14a06ea7c7bb875d13073a65ccaf300b1878168a4afa84e567e2fca5` |
| ontology/engineering-semantics.ttl | 94 | `829899a66cf7d0b1c9bf2ea3717a7b4a72a004e3a802cb3ab3cf00841abb54b4` |
| ontology/requirement-change-planning.ttl | 284 | `12d204a169297e1bb4fbd7fd61015931a700cc83cc8eba8392eb5926aab8b9a5` |
| ontology/ontology-driven-development.ttl | 618 | `838785461e968e5feb05142c5c40db2b971385b36db51245016ca804483eceb0` |
| shapes/business-code-linkage-shapes.ttl | 100 | `a11c7a0b775c087b8188676c1a0d1bbee7d1e022886a92399c84e03d1018c1fa` |
| shapes/engineering-semantics-shapes.ttl | 76 | `0e3be7e04ed0bb1c7da227e35423b108ae98152b0f94e1b2d8eba2e657f3acf4` |
| shapes/requirement-change-planning-shapes.ttl | 320 | `6c270bdd1cc01143bcf589fba69217eee489f0cdb79ebc998443a54654f2afae` |
| shapes/ontology-driven-development-shapes.ttl | 933 | `463ec0c3f6fe29778752107cefa0eb6e76ea09c25057e4d87b9c19800e8ebfa8` |

