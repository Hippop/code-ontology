---
requirementId: REQ-SDN-2026-001
revision: "1.0"
title: 支持最小带宽约束的网络策略部署
---

# 支持最小带宽约束的网络策略部署

## Business Goal

- [CAP-SDN-POLICY] 网络策略部署应支持链路最小可用带宽约束。

## Scope

- 策略部署请求、路径资格计算、带宽指标新鲜度和失败响应。
- 不修改 OpenFlow 南向协议。

## Business Process

- [BP-SDN-POLICY-DEPLOY] 网络策略带宽约束部署流程。
- [STEP-SDN-VALIDATE] 步骤 1：校验请求和最小带宽字段。
- [STEP-SDN-EVALUATE] 步骤 2：检查指标新鲜度并筛选满足带宽的路径。
- [STEP-SDN-DEPLOY] 步骤 3：仅在规则通过后调用南向流表下发。

## Business Rules

- [BR-SDN-BW-001] 所选路径的每条链路可用带宽必须大于或等于请求的最小带宽。
- [BR-SDN-BW-002] 带宽采样时间超过配置上限时不得用于路径计算。

## API Contract

- POST `/network-policies/{id}/deploy` 保持原操作。
- 请求 Schema 新增可选字段 `minimumBandwidthMbps`，类型为非负整数；未提供时保持旧行为。
- 数据过期或没有可用路径时返回稳定错误码，不得返回成功。

## Configuration

- [CFG-SDN-BW-MAX-AGE] 新增配置 `topology.bandwidth.max-age`，默认值为 `PT30S`，允许环境覆盖。

## Data

- 路径计算读取链路属性 `availableBandwidthMbps` 和 `bandwidthSampleTime`，不新增数据库表。

## Events

- [EVENT-SDN-POLICY-REJECTED] 带宽规则拒绝路径时发布 `NetworkPolicyRejected` 领域事件，并保持消息 Schema 向后兼容。

## Acceptance Criteria

- [AC-SDN-BW-001] 所有候选链路满足最小带宽时才能选择路径。
- [AC-SDN-BW-002] 带宽数据过期时请求失败且不得调用南向流表下发。
- [AC-SDN-BW-003] 未提供 `minimumBandwidthMbps` 时行为与当前版本兼容。

## Deployment and Rollback

- 先发布兼容的新应用版本，再启用环境配置；回滚时关闭新字段使用并恢复旧应用。

## Implementation Suggestions

- 优先扩展现有 `ConstraintEvaluator`，复用当前路径资格规则组合边界。
