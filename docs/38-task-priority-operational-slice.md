# 任务优先级：项目模型到真实验收

## 实际操作

启动工作台，进入「00 元模型中心」，展开「项目实战：任务优先级开发闭环」。

1. 输入切片名称，选择默认优先级，点击「保存项目模型版本」。
2. 展开项目 Turtle，检查目标、需求、条款、设计、生成规范、任务及验收条件。
3. 点击「批准并执行：生成代码 → 运行验收 → 回写证据」。此操作批准当前保存的
   模型版本，在新的受管理目录生成代码并执行固定验收程序。
4. 查看八项验收结果、产物目录、代码摘要、报告摘要和证据图。
5. 重新打开页面后，从已保存模型和执行历史加载记录。
6. 点击「重新检查文件与证据摘要」。源码、验收脚本、模型、报告或证据图有变化，
   或安装元模型已变化时，当前状态变为 Stale，历史执行结果保留。

调整默认值后必须保存新模型版本，旧版本和执行记录不可覆盖。
模型和记录保存在平台 SQLite；文件位于数据库旁的 `development-runs/<runId>/`。
每次运行使用新目录。此处不把文件写入用户现有业务仓库。

## 元模型驱动的实际链路

输入表单 → 独立身份的 ModelRevision → SHACL 校验 → 保存模型及元模型绑定
→ 执行操作批准保存内容摘要 → GenerationSpecification 生成 `src/task.py`
→ 文件级 ObservationRun → 独立验收程序 → VerificationRun / Evidence
→ SatisfactionAssessment → 义务关闭 / 保持 Open → ReleaseAssessment。

复用任务示例的意图与设计，移除所有 Illustrative 执行、报告和判断，再建立项目模型。
执行时间、报告、退出码、文件摘要来自本次执行；没有把演示记录改名为真实证据。
每次运行具有独立执行节点身份，业务需求仍引用原保存模型身份。

固定验收程序 `task_acceptance.py` 不导入生成器，以独立 Python 进程检查默认值、
三个合法值、未知字符串、空字符串、None 和数字输入。只有八项测试全部通过、
前后文件摘要一致且证据图校验通过时，才得到 Ready。测试失败会保存报告、
Failed 验证执行及 NotSatisfied 判断，义务保持 Open。

## API

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| POST | `/api/development-slices/models` | `name`、`defaultPriority` 创建不可覆盖的模型版本 |
| GET | `/api/development-slices/models` | 模型列表 |
| GET | `/api/development-slices/model?modelId=...` | 保存的模型与 Turtle |
| POST | `/api/development-slices/execute` | `modelId` 执行该版本 |
| GET | `/api/development-slices/runs?modelId=...` | 执行历史概要（执行时结果） |
| GET | `/api/development-slices/run?runId=...` | 记录详情与当前文件摘要复核 |

接口沿用平台的 Bearer Token 配置。`status` 表示执行时结论，`currentStatus`
表示当前查询复核后的结论；使用者应以 `currentStatus` 判断证据是否仍可用。

## 适用边界

本次覆盖单一任务输入切片，允许 low/medium/high，默认值可配置。自然语言规则、
自定义 Turtle、任意命令和任意目标路径没有接入此执行入口。就绪范围不含任务调度、
API 服务、数据库持久化、跨文件业务集成或生产发布。文件采集为文件级摘要，
不是完整 AST 反向建模。元模型包发布迁移和多业务项目编辑仍为独立功能。

执行批准记录表示本地工作台动作，非具有身份认证签名的多人审查。
结果读取会检查已记录文件，不自动持续监控，也不把范围外文件计入该快照。
固定验收脚本有版本和内容摘要，独立进程有超时；它不是运行任意用户程序的沙箱。
