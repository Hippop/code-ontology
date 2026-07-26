# 结构关系

## 1. 设计目标

结构关系负责回答“实体在哪里、属于谁、如何被打包和聚合”，它是变更定位、边界识别、责任继承、构建选择和结果汇总的基础。结构关系本身通常不表示执行或数据依赖。

## 2. 三类结构

### 物理结构

Repository、Directory、SourceFile、ResourceFile 之间的存储结构。它来自版本库和文件系统。

### 声明结构

File 声明 Type，Type 声明 Method/Field，Callable 声明 Parameter。它来自编译器语义模型。

### 逻辑和架构归属

节点属于 Module、Component、Layer、BoundedContext、LogicalService、BusinessCapability。逻辑归属不能仅从目录名推断，显式架构配置和构建模型具有更高优先级。

## 3. 最终关系集合

```text
structurallyRelatedTo
├── contains / containedIn
├── declares / declaredIn
├── declaredInFile / fileDeclares
├── nestedIn / containsNestedType
├── belongsToModule
├── belongsToComponent
├── belongsToLayer
├── belongsToBoundedContext
├── belongsToService
├── packagedInto
└── ownedBy
```

`contains` 是通用物理或逻辑包含关系，`declares` 表达语言声明。不要用一个 `contains` 覆盖所有语义，否则查询难以区分源码声明与部署包含。

## 4. 方向与逆关系

事实按自然方向保存：

```text
Type declares Method
Method declaredIn Type
Method belongsToModule user-domain
```

OWL 可声明稳定逆属性，例如 `declares inverseOf declaredIn`。高频查询可以将逆边物化，但必须避免把物化边再次当成独立来源重复计数。

## 5. 结构关系在波及分析中的作用

### 变更定位

Git Diff 首先定位 SourceFile，再通过源位置映射到 Field、Method、Type，随后向上聚合到 Module、Component 和 Service。

### 结果聚合

多个方法影响可以汇总为模块、服务和团队影响，但结构父节点不自动成为功能影响节点。聚合结果应标记为 `containsAffectedEntity` 或统计视图，而不是伪造依赖传播。

### 构建与部署

受影响 CodeEntity 通过 `packagedInto` 或 `builtFrom` 找到构建产物，再定位部署单元。

### 责任继承

若 Method 没有显式 owner，可沿 `declaredIn`、`belongsToModule`、`ownedBy` 解析责任团队。继承只用于责任解析，不表示团队关系参与技术传播。

## 6. 边属性和证据

结构边应记录：来源解析器、有效版本、置信度、源位置、是否显式配置。编译器解析的声明边通常置信度为 1；根据目录规则推断的 Component/Service 归属应降低置信度。

## 7. 示例

```text
Repository code-ontology-demo
  contains Module user-service
Module user-service
  contains SourceFile UserController.java
SourceFile UserController.java
  declares Type UserController
Type UserController
  declares Method updateUser
Method updateUser
  belongsToComponent UserApplication
  belongsToService user-service
```

当 `updateUser` 受影响时，可以得出“user-service 中存在受影响方法”，但不能仅因为同一 Type 中还有 `getUser` 就判定 `getUser` 受影响。

## 8. RDFS/OWL 使用

RDFS 用 `subPropertyOf` 统一结构查询；OWL 用 inverseOf 和少量类型推理。不要把 `contains` 声明为通用 TransitiveProperty：某些包含关系跨层可传递，但声明、版本、部署和租户范围常有不同语义。需要闭包时使用限定路径查询。

## 9. 常见错误

- 将兄弟节点关系当成影响关系；
- 仅依靠文件路径判定业务和服务归属；
- 使用 domain/range 做数据校验；
- 把逻辑服务、构建模块和部署单元合并；
- 节点移动后创建完全无关的新实体，丢失跨版本 LogicalEntity 对齐。

## 10. 最终约束

每个核心代码成员必须能沿结构路径定位到 SourceFile、Module 和 Repository；对可部署代码应能继续定位到 LogicalService 或 DeployableUnit。缺失结构链应作为数据质量问题，而不是在传播阶段临时猜测。