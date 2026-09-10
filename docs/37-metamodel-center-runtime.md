# 元模型中心：运行时接入与操作指南

当前定义基线为 2.0.0，见 [优化与兼容说明](42-ontology-maturity-2.0.0.md)。审计文档 40/41 保留 1.0.0 的历史发现，不作为当前缺陷状态清单。

## 本次完成的闭环

仓库 OWL/SHACL 定义 → 元模型目录 → 项目草稿绑定 → 实体与关系构建 →
RDF/SHACL 校验 → dev 转换规则/既有 eng 契约生成 → 提交前约束检查。

这是一条可执行的接入链。dev 目前只有一个明确适配器，不代表任意自然语言规则
或所有 TransformationRule 都已自动执行。

## 前端操作

元模型中心现提供「建立 / 修订元模型定义」编辑器。它从安装的开发元模型
OWL 与 SHACL 文件建立副本，支持服务端保存、重新加载、修订历史查看、Turtle 导出，
以及候选约束对两个包内正例和八个关键反例的回归校验。保存采用乐观并发检查：旧修订写入返回 409，
所有已保存修订保留在平台 SQLite 数据库中。未完成的语法也可保存为草稿。
切换工作台阶段前请保存草稿；校验结果属于当次编辑内容，修改后会清除。

草稿校验包含 Turtle 语法、定义引用闭合、SHACL 元校验、示例符合性及预期规则的反例拦截，不能证明完整 OWL 一致性、
业务正确性或生产实例迁移安全。草稿不会直接安装：导出后仍需通过仓库审查更新
`ontology/ontology-driven-development.ttl` 和对应 shapes 文件。安装版本变化会使
旧基础绑定失效；自动合并、发布及迁移尚未接入。

草稿 API：`GET /api/metamodel/drafts/template` 获取起始副本；
`GET /api/metamodel/drafts` 列出最新草稿；
`GET /api/metamodel/drafts/history?draftId=...` 读取历史；
`POST /api/metamodel/drafts` 保存修订；
`POST /api/metamodel/drafts/check` 校验编辑内容。
保存/校验输入包含 `draftId`、`revision`、`name`、`baseBinding`、`ontology`、`shapes`；
新建时 `draftId` 留空、`revision` 为 0。

启动服务并打开 `http://127.0.0.1:8080/`，进入「ONTOLOGY FLOW」。

1. 选择「00 元模型中心」。按定义包、类型、语义层和关键词查询类、对象关系及数据属性。
2. 点击定义，查看完整 IRI、来源文件、上位类型、直接子类、继承及直接 SHACL 约束，
   并沿关联属性继续查询。完整 OWL 表达和 SPARQL 约束可展开读取。
3. 打开「实例与校验」，选择任务优先级示例或平台自身目标模型。可以修改 Turtle
   副本并校验；不会写回文件。六项能力查询使用包内原始示例，不使用编辑副本。
   示例的 Illustrative/Planned 状态不能被视为真实实施或成功验证证据。
   对任务优先级示例点击「预览生成规范」，可看到由 `GenerationSpecification`、
   `ValueConstraint` 和 `BehaviorClause` 共同生成的 Python 数据类源码；生成器会列出
   输入摘要、规则、保留条款和不支持情况。
4. 点击「关联到当前项目模型」。服务返回转换后的草稿；旧工程短名称通过显式
   v0 适配器转换为完整 IRI。绑定本身不证明符合约束，也不是包发布或迁移批准。
5. 在「02 项目本体」选择元模型中的类型创建实例，用对象关系连接已有实例。
基础属性输入来自简单 SHACL 数据属性路径，支持继承属性、必填提示、按换行录入多值，
   并将声明的 XSD 类型写入 literal。复杂路径、语言标签和条件逻辑仍通过 JSON 编辑。
6. 运行「VALIDATE · COVERAGE · IMPACT」。约束问题按实体、路径和消息显示。
   SHACL 符合性是元模型校验；覆盖率和影响传播仍是旧工程语义算法，不是 dev 满足性证明。
7. 对既有 eng 模板契约选择仓库并预览。校验通过后才能应用；包含 dev 类、属性或关系
   的 JSON 模型仍不会误走旧模板生成器。

8. dev 生成规范 API 只执行显式支持的 Python 枚举/默认值数据类适配器。它要求
   `GenerationSpecification` 被一个已批准 `ChangePlan` 下的 `Template` 任务采用，
   并且 `preserves` 同时覆盖值约束和行为条款。预览无需仓库；应用必须提供已登记的
   `repositoryId`、显式 `overwrite`，且含 `Illustrative` 执行记录的示例默认禁止写入。

前端草稿保存在当前浏览器 localStorage，未新增服务端项目模型持久化、共享或审计记录。
包内实例引用列表只扫描两个示例文件，不是项目实例全量索引。

## 版本与身份

`models/development-metamodel.package.json` 固定本地定义文件、约束文件、示例和查询目录。
加载器不在线拉取 `owl:imports`，也不接受客户端提交的任意文件路径或 SPARQL 文本。

模型新增可选字段：

```json
{
  "metamodelRef": {
    "id": "https://example.org/code-ontology/development",
    "version": "2.0.0",
    "contentHash": "<清单及所有 ontologyFiles/shapeFiles 内容的 SHA-256>"
  }
}
```

摘要覆盖清单和定义/约束文件，不覆盖示例、查询内容或生成模板；它是定义绑定，
不是执行证据摘要。每次请求重新读取安装文件，文件变化后旧绑定返回 HTTP 409。
目前只支持一个仓库安装版本，不提供历史版本仓库、签名发布或不可变发布记录。
生产执行仍应另行固定仓库 commit、输入快照、规则集和生成器版本。

目录严格以完整 IRI 为身份。同名 `biz:BusinessCapability` 与 `code:BusinessCapability`
不会合并；无前缀短名称有歧义时返回 400，旧 JSON 仅在显式绑定适配器中按既有语义转换。

## API 契约

所有 `/api/metamodel/*` 接口沿用服务已有 Bearer Token 配置。

| 方法与路径 | 输入 | 输出 |
| --- | --- | --- |
| GET `/api/metamodel/catalog` | 可选 `revision` | 绑定、定义、文件、示例和查询目录 |
| GET `/api/metamodel/term` | `iri`、可选 `revision` | 定义、继承、约束、关系及有限实例引用 |
| GET `/api/metamodel/example` | `name`、可选 `revision` | 包内允许的示例 Turtle |
| POST `/api/metamodel/bind` | `model`、可选 `revision` | 显式转换的模型副本及绑定 |
| POST `/api/metamodel/validate` | `model` 或 `turtle`、可选 `revision` | 符合性、问题列表和绑定 |
| POST `/api/metamodel/query` | 目录中 `query`、`example`、可选 `revision` | 最多 500 行查询结果 |
| POST `/api/development-code-generation/preview` | `turtle`、可选 `specification`/`revision` | 受限 dev 规则生成预览 |
| POST `/api/development-code-generation/apply` | 上述字段及 `repositoryId`、`overwrite` | 通过授权与边界检查后写入 |

`revision` 是目录返回的内容摘要。绑定 JSON 校验始终检查全部 `metamodelRef` 字段。
JSON 投影将 `nodes[].type` 转为 `rdf:type`、`label` 转为 `rdfs:label`、
`edges` 转为对象属性断言。`nodes[].properties` 接受数据属性 IRI 到 literal 的映射，
支持标量、多值，以及 `{value, datatype}` 或 `{value, language}`；ID 必须唯一，边必须闭合。
旧 `executionStatus` 同时投影为 eng 属性。其他顶层工程字段仍由旧引擎解释，不冒充 RDF 事实。

示例：

```json
{
  "id": "urn:example:goal",
  "type": "https://example.org/code-ontology/development#BusinessGoal",
  "properties": {
    "https://example.org/code-ontology/development#statement": "支持任务优先级"
  }
}
```

该片段仅说明属性表达，完整实例还需满足本体中归属、版本等全部约束。

## 生成及门禁边界

- 绑定错误返回 409；SHACL 不符合时生成返回 400，并附问题详情，写文件前拒绝。
- 旧模板生成结果附带 `metamodelRef`；模板仍通过 `generation.kind` 选择。
- dev 适配器返回 `adapter=python-enum-dataclass-v1`，将 `dev:TechnicalRepresentation`
  表示的业务属性、其 `ValueConstraint` 允许/默认值和 `BehaviorClause` 失败行为写入源码，
  同时输出 `MODEL_INPUT_HASH`、规范 IRI、规则 IRI 和保留条款 IRI。
- 已绑定模型的提交门禁合并 SHACL 结果，不符合时追加 `METAMODEL_CONSTRAINT_VIOLATION` 并阻断。
- 为保持兼容，未绑定的旧 eng 模型仍走旧流程；它们不具有新元模型校验保证。
- 去掉绑定也不能让含 dev 术语的模型绕过生成执行器限制。这不是全面的防篡改或发布权限体系。

## 验证与后续

任务优先级现已接入服务端项目模型保存、真实验收执行、证据回写和快照失效检查，
见 [任务输入业务切片操作指南](38-task-priority-operational-slice.md)。这一专用切片
不改变其他开发规则及通用项目管理的实现边界。

新增 `tests/test_metamodel_registry.py` 覆盖目录身份、继承约束、摘要稳定性及失效、
显式绑定、JSON/SHACL 校验、示例查询、接口认证、实际文件生成与失败前拒绝写入。

后续独立工作：元模型发布/迁移管理、项目模型持久化与实例反向索引、
复杂约束表单、更多 TransformationRule 适配器，以及真实采集—验证—满足性闭环。
