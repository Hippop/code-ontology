# 数据库模型

## 1. 设计目标

数据库模型连接代码对象、SQL、ORM、表列、约束、视图和迁移，使分析既能从代码变化追踪到数据存储，也能从 Schema 变化反向定位源码、服务、报表和运行版本。数据库对象必须作为独立节点，不能仅作为 Repository 方法的字符串属性。

## 2. 最终节点

```text
DataEntity
├── Database
├── DatabaseSchema
├── Table
├── Column
├── View
├── Index
├── Constraint
├── Sequence
├── StoredProcedure
├── Query
├── Migration
└── DataFormat
```

Query 节点用于承载 SQL 文本、规范化 AST、方言、动态条件和执行证据；Migration 表达 Schema 演进动作，而不是普通 SQL 文件。

## 3. 最终关系

```text
readsTable / writesTable
readsColumn / writesColumn
insertsIntoTable / updatesTable / deletesFromTable
executesQuery
queryReadsTable / queryWritesTable
queryReadsColumn / queryWritesColumn
mappedToTable
persistedAs
usesIndex
constrainedBy
derivesFrom
callsStoredProcedure
reliesOnDefaultValue
changedByMigration
```

Field `persistedAs` Column，Type `mappedToTable` Table。实体和表、字段和列绝不使用 sameAs。

## 4. 表级与列级并存

表级关系用于快速粗筛、共享表和服务边界分析；列级关系用于删除、类型、可空性和默认值等精确影响。若存在 `readsColumn`，可规则推导 `readsTable`，但表级边不能反推出所有列级访问。

## 5. Query 节点

复杂 SQL、MyBatis XML、NamedQuery、报表、存储过程调用应建立 Query：

```text
Method executesQuery Query
Query readsColumn user_table.email
Query writesColumn audit_table.value
```

Query 属性包括 normalizedSql、dialect、queryType、dynamic、parseStatus、sourceLocation、bindParameters、observedFrequency 和 latency。动态 SQL 中仅条件性出现的列使用 mayRead/mayWrite 或条件属性。

## 6. ORM 建模

```text
UserEntity mappedToTable user_table
UserEntity.email persistedAs user_table.email
EmailConverter converts UserEntity.email to user_table.email
```

Repository 派生查询可由 Repository 泛型、方法命名和 ORM 元数据联合推断。框架约定产生的关系应标记 evidenceType，而不是伪装成 SQL Parser 确定事实。

## 7. 约束、索引和默认值

Constraint 和 Index 不只是结构附属物。唯一约束可能实现幂等或唯一业务规则；索引影响查询性能；默认值影响省略该列的 INSERT。

```text
InsertQuery reliesOnDefaultValue status
UniqueConstraint enforcesRule CallbackIdempotency
Query filtersBy email
Query usesIndex idx_user_email
```

删除索引通常形成 PerformanceImpact，而非 CompileImpact。

## 8. 视图、计算列和存储过程

View/Column `derivedFrom` 基础表列。底层列变化应先影响视图定义，再影响读取视图的代码。StoredProcedure 可同时是 Callable 和 DatabaseObject，连接应用调用、内部 SQL 和数据副作用。

## 9. Schema 变化传播

- ColumnDeleted/Renamed：直接 readers/writers、ORM Field、Query、View、Fixture 为高风险；
- ColumnTypeChanged：检查绑定类型、函数、比较、索引、Converter 和历史数据；
- nullable true→false：重点反查 writers 和历史 null；
- nullable false→true：重点检查 readers 的 null 假设；
- DefaultChanged：影响省略列的插入路径；
- ConstraintChanged：关联业务规则和并发语义；
- IndexChanged：结合 Query 过滤、排序和运行指标。

## 10. 数据迁移

Migration 应保存 beforeSchema、afterSchema、expand/migrate/contract 阶段、可逆性、数据回填、锁风险、目标环境和 Rollback。应用部署顺序不能只由 SQL 顺序决定，必须结合旧/新应用对旧/新 Schema 的兼容矩阵。

## 11. 共享数据库耦合

多个服务访问同一表或列时，即使没有 API/消息关系，也存在隐式耦合。图中应聚合访问服务、读写角色和运行版本。共享表变化通常提高跨团队风险，但不自动证明所有服务都受具体列影响。

## 12. 示例

`user_table.email VARCHAR → JSON`：定位 ORM 字段、直接 SQL、使用 LOWER/LIKE 的 Query、写入批任务、报表、索引和迁移。若 EmailAddressConverter 仍输出 VARCHAR，则 Java 类型变化可能被吸收；若列同步改 JSON，所有字符串函数和直接写入者需重新评估。

## 13. 证据来源

DDL、迁移脚本、数据库 Catalog、ORM 注解、SQL AST、执行计划、运行 Query 日志。Catalog 是当前运行事实，迁移脚本是期望演进事实，二者不一致时应产生 Drift 问题。

## 14. 注意事项

- 不只解析 ORM，也要覆盖原生 SQL、报表和批处理；
- 文本出现表名不能直接生成 readsTable；
- 当前主分支无依赖不代表生产旧版本无依赖；
- 数据格式语义变化可能比 SQL 类型变化更危险；
- 数据库关系描述访问，不表示代码变化一定要求 Schema 变化。