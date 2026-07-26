# 实现架构与演进说明

本路径保留用于兼容旧链接。最终实现架构已经整理到：

- [实现架构与数据管道](16-implementation-architecture.md)
- [总体架构](00-overall-architecture.md)
- [变更模型](13-change-model.md)
- [影响传播规则](14-impact-propagation-rules.md)
- [RDFS、OWL、SHACL 与规则引擎边界](15-rdfs-owl-shacl.md)

## 实现原则

实现不以“第一版只做若干关系”为最终设计约束。完整目标包括：多语言和多平台采集、LogicalEntity/Revision 版本化、知识图/变更图/影响图分离、增量更新、规则版本化、运行版本关联、测试和发布闭环。

具体交付可以按工程优先级分阶段完成，但每个阶段都应遵守正式模型的稳定 ID、关系方向、证据、版本和传播语义，避免用临时简化破坏后续演进。