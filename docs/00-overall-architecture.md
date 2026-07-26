# 总体架构

## 1. 目标

代码本体不是“把 AST 放进图数据库”，波及分析也不是“从变更节点做无限可达遍历”。最终系统要把源码事实、契约事实、运行事实和业务事实组织成统一语义模型，并在每次变更发生后生成可解释的影响结论。

系统应回答：改了什么语义；哪些代码、数据、接口、消息、配置、测试、业务和部署对象受到影响；影响是否确定；变化在哪里被转换或吸收；需要哪些测试、团队和发布动作。

## 2. 分层思想

最终模型分为七层：

1. **代码结构层**：Repository、Module、File、Type、Callable、Field、Parameter。
2. **依赖与数据层**：调用、类型、字段访问、值流、数据库访问。
3. **契约与运行入口层**：API、消息、配置、Feature Flag、Secret。
4. **验证层**：测试、覆盖、契约验证、Fixture、执行结果。
5. **业务语义层**：能力、流程、规则、需求、验收条件、责任团队。
6. **交付运行层**：构建产物、版本、部署单元、实例、环境和发布动作。
7. **变化与影响层**：ChangeItem、ImpactAssessment、Evidence、Path、CompatibilityAssessment。

层之间通过明确关系连接，但不合并概念。例如 Controller 方法与 API Operation、Java 字段与 JSON Schema 字段、实体字段与数据库列、逻辑服务与容器镜像均应保持为不同节点。

## 3. 核心原则

### 3.1 事实抽取与语义推理分离

编译器、语言服务器、SQL 解析器、OpenAPI/AsyncAPI 解析器、CI/CD 和运行平台负责产生事实。RDFS/OWL 负责统一类和关系层级、逆关系和少量稳定推理。复杂兼容判断、路径状态、配置优先级、数值风险和传播停止由规则引擎完成。

### 3.2 依赖方向与传播方向分离

事实通常按自然方向存储：Caller `callsDirectly` Callee、Method `readsField` Field、Field `persistedAs` Column。影响分析根据 ChangeType 决定正向或反向遍历。不能把边方向直接理解为固定传播方向。

### 3.3 图可达不等于真实影响

节点在图上可达，只能说明存在候选路径。真实影响还取决于变化类型、使用方式、兼容层、控制条件、环境、运行版本和证据强度。

### 3.4 开放世界与工程闭包并存

本体遵守开放世界思想：未发现消费者不等于没有消费者。工程分析在明确采集范围后，可以使用 `NOT EXISTS`、SHACL 或规则输出“当前数据范围内未发现”，但必须保留范围和时间戳。

### 3.5 每个结论必须可解释

ImpactAssessment 必须关联 SourceChange、AffectedEntity、ImpactType、State、Risk、Rule、Evidence 和 ImpactPath。报告应能说明为什么命中、为什么继续、为什么停止以及置信度来自哪里。

## 4. 三张图

### 知识图谱

存储版本化的事实：结构、依赖、映射、契约、配置、测试、业务和部署。它是长期资产。

### 变更图

以 ChangeSet/ChangeItem 描述一次提交中的语义差异，包括 before/after、目标节点、变化类型和检测证据。

### 影响图

保存本次分析产生的 Candidate、Confirmed、Contained、Rejected、Unresolved 结论、传播路径、派生变化、测试建议和发布约束。

三张图不能混为一张：知识事实可复用，变更事实可重放，影响结论可随规则版本重新计算。

## 5. 总体处理流程

```text
代码与平台数据
  → 解析和规范化
  → 实体对齐与稳定 ID
  → 知识图谱
Git Diff/Schema Diff/配置 Diff
  → 语义 ChangeItem
ChangeItem + 图上下文
  → 规则驱动传播
  → ImpactAssessment/ImpactPath
  → 测试、业务、团队和发布建议
```

## 6. 最终技术职责

- **RDFS**：类与属性层级、统一查询入口。
- **OWL**：逆属性、等价/互斥、语义角色和有限属性链。
- **SHACL**：图数据完整性和治理约束。
- **图查询/算法**：可达性、路径、SCC、边界和聚合。
- **规则引擎**：变化语义、兼容判断、状态转移、吸收和风险。
- **运行时证据**：调整优先级和暴露度，不用于证明静态关系不存在。
- **LLM**：解释、候选语义映射和报告生成，不作为唯一事实来源。

## 7. 全局注意事项

不要把 `callsDirectly`、`mapsTo`、`derivedFrom` 或普通 `dependsOn` 声明成通用传递属性；不要把 RDFS domain/range 当验证规则；不要用 `owl:sameAs` 连接代码类与表、Java 字段与 JSON 字段、事件与 Topic；不要在长期图中无条件物化所有表达式和运行时 Value。