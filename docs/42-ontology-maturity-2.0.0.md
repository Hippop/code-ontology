# 本体成熟化 2.0.0：优化结果与兼容边界

日期：2026-09-09。本文记录已实施的第一轮优化，不等于 [整体设计](40-ontology-modeling-completeness-and-maturity-design.md) 五个阶段已经全部完成。

## 1. 范围与版本

本轮不增加业务动作、动作执行、业务函数或行为 DSL；现有 dev 49 类不变。保留已有 BehaviorClause、流程与状态定义，只澄清 BehaviorClause 的文本表达边界。

由于新规则会拒绝原先被放行的部分模型，开发元模型升为 **2.0.0**，而不是宣称完全兼容的补丁版本。包仍标记 `RepositoryBaseline`，不是签名发布或已安装到所有项目的证明。

| 指标 | 优化前 | 优化后 |
|---|---:|---:|
| 五套本体的类 | 240 | 241 |
| dev 类 | 49 | 49 |
| 对象属性 | 296 | 296 |
| 数据属性 | 75 | 75 |
| 类/对象属性/数据属性术语总数 | 611 | 612 |
| 有自身 label 和 comment 的类 | 49 | 241 |
| 有自身 label 和 comment 的全部术语 | 145 | 337 |
| NodeShape 定义 | 78 | 80 |
| 候选定义检查的固定关键反例 | 0 | 8 |

注：NodeShape 数不等于规则数；仍有 275 个旧属性术语缺少自身说明，未宣称全部术语文档已经补齐。`dev:semanticLayer` 注解属性不计入 612 项。

定义绑定摘要：`b503f77dfec3f0723765b494f9614ebe7ad647009d466294ecc67648c6fae606`。它覆盖当前清单与定义/约束文件，不覆盖查询、示例或全部验证器代码。

## 2. 已完成的优化

### 2.1 定义引用和语义说明

- 补全已经被 plan 与 SDN 示例引用的 `biz:Requirement`，继承 biz:BusinessEntity，保留 canonicalId 规则。
- 未将其声明为 eng/dev 需求的 sameAs 或等价类。
- 为 code 81 类、biz 原 26 类、eng 22 类、plan 62 类补充中文名称与定义；加上新增业务需求和原有 dev，全部 241 类可直接从机器定义查询说明。
- 区分业务概念与技术表示、代码类与 OWL 类、规划与实际事实、验证意图与证据。
- 对 `rdfs:subClassOf/domain/range/subPropertyOf`、OWL 逆关系及 SHACL 关键类型/路径引用增加命名空间内的定义闭合检查。
- 严格检查 RDF 数据中使用的 code/biz/eng/plan/dev 类型和谓词，不能靠 RDFS 推理把拼写错误变成已声明术语。
- 此检查发现 SDN 规划示例中的未声明 `biz:containsSupportingCode`，已改为现有 `biz:containsSupportingEntity`；没有新增同义关系。

### 2.2 身份规则

JSON 模型先展开旧短 ID，再检查展开后的唯一性，最后构造 RDF 节点。`a` 和 `urn:engineering-node:a` 不再能静默合并。非法 IRI 字符在构造 URIRef 前拒绝。

业务 canonicalId 在同一 ModelRevision 内必须唯一；同一逻辑属性在不同模型修订中复用 canonicalId 仍合法。未绑定模型的旧业务资产尚未新增全局唯一性要求，避免把不同领域资产错误合并为同一作用域。

### 2.3 关系与模型上下文

`DEV_MODEL_LINK` 增补 motivates、refines、hasAttribute、mappingTarget 的同模型检查，保留原有需求、条款和设计关系检查。

条款 `constrains` 的目标限定为有类型的开发业务概念、属性或需求；`mappingSource` 限定为有类型的需求、条款、验收、业务概念、属性或规则，不再只检查“是不是一个 IRI”。

新增计划义务上下文检查：

- 义务语义目标属于计划目标模型。
- 义务来源差异使用同一目标模型与基线。
- 该差异确实声明 createsObligation 指向对应义务。

仍允许 Declared 映射指向已有代码产物，它只是尚待核实的声明；不得自动升级为 Observed 或 Satisfied。

### 2.4 值类型约束

ValueConstraint 的 valueDatatype 必须来自本版本明确支持的词表：

`xsd:string`、`xsd:boolean`、`xsd:integer`、`xsd:decimal`、`xsd:float`、`xsd:double`、`xsd:date`、`xsd:dateTime`、`xsd:anyURI`。

即使尚未提供枚举或默认值，也不能引用一个任意未知 datatype。允许词表不等于生成器支持全部这些类型；现有受限生成器仍执行自己的支持性检查。

### 2.5 定义目录与前端

元模型详情关联列表不再只依赖 domain/range，也从直接与继承 SHACL 属性形状中提取适用关系；简单 inversePath 显示为入向关系。返回 SHACL 来源，未通过添加错误 domain 来“修复”界面。

例如现在 GenerationSpecification 的关联列表能够显示 appliesRule、inputDesign、preserves、usesTechnology、targetPath；ValueConstraint 能显示 constrains、valueDatatype、allowedValue、defaultValue。

目录 API 返回 definitionIssues；定义目录查询 01 扩展到 code-ontology 命名空间下的组合定义，不再仅展示 dev，不再因缺 label 而丢弃旧属性。

草稿前端显示定义问题和各关键反例是否被预期规则拦截；成功文案明确为“草稿检查通过（尚未发布）”。

### 2.6 校验结论与反例

Registry 和 CLI 共同采用新的定义/词汇检查。两者仍保留各自明确的加载范围：Registry 为包清单，CLI 为命令指定目录。

Registry 响应新增 completeness：空图为 Empty，其他普通校验结果为 NotEvaluated。一般 SHACL 对空图通过仍合法，但不再暗示项目完整。

候选定义检查先跑正例，再运行八个固定反例，并检查是否命中预期规则：

| 反例 | 预期规则 |
|---|---|
| 默认值超出枚举 | DEV_DEFAULT_OUTSIDE_ENUM |
| 业务目标与需求跨模型 | DEV_MODEL_LINK |
| 业务概念与属性跨模型 | DEV_MODEL_LINK |
| 同模型重复业务 ID | MM_CANONICAL_ID_UNIQUE |
| 不存在的条款目标 | MM_REFERENCE_RESOLVED |
| 不存在的映射源 | MM_REFERENCE_RESOLVED |
| 无值情况下引用未知 datatype | MM_DATATYPE_REGISTERED |
| 演示证据冒充满足性证明 | DEV_ASSESSMENT_EVIDENCE |

删除开发约束文件全部形状后，即使正例通过，候选检查也会因负例失守而失败。固定反例由可信仓库代码产生，不接受客户端上传可执行测试代码。

这不是完备的约束变异测试、OWL 一致性证明、兼容分析或发布审批。新增约束仍需要增加对应反例。

## 3. 旧模型与草稿的处理

1. 本轮没有改写 SQLite、localStorage 或已保存项目模型。
2. 旧 metamodelRef 因版本/内容摘要变化而返回 409；不要直接替换摘要后宣称迁移成功。
3. 先保留旧模型导出，再从当前目录获取绑定并执行校验。
4. 对同模型重复业务 ID、未解析引用、跨模型关系、未支持 datatype 逐项修复。
5. 合法的跨修订概念复用保持逻辑业务 ID，但采用各自的模型节点；当前尚无通用外部模型导入管理。
6. 旧定义草稿保存了旧 baseBinding，会被拒绝继续覆盖；可从新模板创建草稿并人工复核迁移。未实现自动合并。
7. 包内演示的基础包与约束集版本已更新，其他独立资产版本不盲目统一；演示数据仍为示例，不代表生产发布。

审计文档 40/41 保留优化前原始数据，便于比较，不将历史发现误当成当前仍未修复的问题。项目的历史定义不可变存储仍是后续工作，不能声称仓库现已保存完整的 1.0.0 安装副本。

## 4. 与审计问题的对应

| 审计项 | 当前状态 |
|---|---|
| A01 ID 规范化碰撞 | 已修复并测试 |
| A02 未声明业务需求 | 已补全并检查组合定义引用 |
| A03 清空约束仍通过 | 已增加八个关键反例拦截；不是完整发布门禁 |
| A04 旧术语说明 | 所有类已补齐；275 个旧属性说明仍待补齐 |
| A05 同名术语 | 继续保留完整 IRI；未全面重构所有旧引擎 localName 使用 |
| A06 跨模型关系 | 已修复本次发现的核心关系，新增计划义务上下文；未实现通用外部模型导入 |
| A07 业务 ID 重复 | 已实现模型修订内唯一性 |
| A08 悬空语义引用 | 条款目标和映射源已收紧；不是所有关系的通用引用系统 |
| A09 未知值类型 | 已增加固定词表检查 |
| A10 JSON 表达不完整 | 尚未实现 model-json/2、多类型和外部 IRI 引用 |
| A11 详情遗漏关联 | 已补简单 SHACL 及逆路径来源；复杂表达仍需原文查看 |
| A12 OWL 逆关系 | 保持现有 rdfs 推理边界，尚未增加逆关系规范化 |
| A13 空图/未知谓词 | 未知保留命名空间术语被拒绝；空图明确未完成项目建模 |
| A14 基础类型 Shape | 未新增通用 code 结构 shapes；不宣称所有类约束完整 |
| A15 加载/目录差异 | 查询 01 扩展组合定义；CLI/API 共用预检，但未统一 PackageResolver |
| A16 多版本与使用索引 | 尚未实现 |
| A17 命名图隔离 | 尚未实现通用 Dataset 存储 |
| A18 维护与说明 | 本次能力边界已记录；历史 SQLite ResourceWarning 尚未修复 |

## 5. 验证

新增 `tests/test_metamodel_maturity.py`，覆盖 14 项回归测试，包括全部类说明、定义闭合、跨模型、作用域唯一性、悬空/错误类型目标、值类型、词汇拼写、ID 规范化、映射合法对照、计划上下文、关联展示、空图以及候选约束清空反例。

复现命令（仓库根目录）：

```bash
.venv/bin/python -W ignore::ResourceWarning -m unittest discover -s tests -q
.venv/bin/python -m code_ontology_platform validate
env PATH="/home/weichen/.nvm/versions/node/v20.20.2/bin:$PATH" npm --prefix web run build
```

本地默认 Node 为 v10.19.0，不能解析当前 TypeScript；构建使用已有 Node v20.20.2，不修改项目依赖。其他机器请使用满足项目工具链要求的 Node，替换上述环境路径。

本次验证结果：全量 126 项测试通过（200.534 秒），5 个 TTL 示例通过，TypeScript/Vite 构建通过。构建仍提示主包超过 500 kB，这是后续拆包优化事项；未运行真实浏览器交互验收。

## 6. 后续顺序

建议下一轮先完成静态关系/数据属性说明与 model-json/2，使现有本体可以无损地从前端建立；然后补代码结构形状、统一包闭包和模型版本存储。暂不扩展新的行为体系，也不把“模型符合约束”当成“任意代码都能生成”。
