import { tool } from "@opencode-ai/plugin"

const DEFAULT_BASE_URL = "http://127.0.0.1:8080"

function baseUrl(): string {
  return (process.env.CODE_ONTOLOGY_API_URL ?? DEFAULT_BASE_URL).replace(/\/$/, "")
}

function authHeaders(): Record<string, string> {
  const token = process.env.CODE_ONTOLOGY_API_TOKEN
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function request(path: string, init: RequestInit = {}): Promise<string> {
  const response = await fetch(`${baseUrl()}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...authHeaders(),
      ...(init.headers ?? {}),
    },
  })

  const text = await response.text()
  if (!response.ok) {
    throw new Error(`Code Ontology API ${response.status}: ${text.slice(0, 1000)}`)
  }

  return text || "{}"
}

function parsePayload(payload: string): unknown {
  try {
    return JSON.parse(payload)
  } catch (error) {
    throw new Error(`payload 必须是合法 JSON: ${String(error)}`)
  }
}

export const requirement_context = tool({
  description:
    "读取某个需求和设计版本的受控 Agent 上下文，包括文档证据、Requirement IR、审批状态和允许的工作阶段。",
  args: {
    requirementId: tool.schema.string().min(1).describe("稳定 Requirement ID"),
    designRevisionId: tool.schema
      .string()
      .min(1)
      .describe("稳定 DesignRevision ID"),
    stage: tool.schema
      .enum(["extract", "align", "plan", "implement", "verify", "impact"])
      .describe("当前 Agent 阶段"),
  },
  async execute(args) {
    const query = new URLSearchParams({
      designRevisionId: args.designRevisionId,
      stage: args.stage,
    })
    return request(
      `/api/agent-context/requirements/${encodeURIComponent(args.requirementId)}?${query}`,
    )
  },
})

export const graph_query = tool({
  description:
    "使用白名单 QueryType 查询 Current、Desired、Proposed、Actual 或 Impact 子图。禁止提交任意 SPARQL、Cypher 或写查询。",
  args: {
    graphSpace: tool.schema
      .enum(["current", "desired", "proposed", "approved", "actual", "impact"])
      .describe("目标图空间"),
    queryType: tool.schema
      .enum([
        "ENTITY_NEIGHBORHOOD",
        "IMPLEMENTATION_SLICE",
        "BUSINESS_TRACE",
        "CALL_PATH",
        "CONTRACT_CONSUMERS",
        "DATA_DEPENDENCIES",
        "CHANGE_CONTEXT",
        "IMPACT_PATHS",
      ])
      .describe("平台支持的白名单图查询类型"),
    entityId: tool.schema.string().min(1).describe("查询起点稳定 ID"),
    targetEntityId: tool.schema
      .string()
      .optional()
      .describe("路径查询的可选目标稳定 ID"),
    revision: tool.schema.string().optional().describe("仓库或图 Revision"),
    depth: tool.schema
      .number()
      .int()
      .min(0)
      .max(6)
      .default(2)
      .describe("最大遍历深度，平台上限为 6"),
    limit: tool.schema
      .number()
      .int()
      .min(1)
      .max(500)
      .default(100)
      .describe("最大返回节点或路径数量"),
  },
  async execute(args) {
    return request("/api/agent-context/graph-query", {
      method: "POST",
      body: JSON.stringify(args),
    })
  },
})

export const alignment_candidates = tool({
  description:
    "保存或更新实体对齐候选草案。该工具不能确认关键映射，只能创建 Candidate 状态 Artifact。",
  args: {
    runId: tool.schema.string().min(1).describe("Agent/Analysis Run ID"),
    requirementId: tool.schema.string().min(1).describe("Requirement ID"),
    payload: tool.schema
      .string()
      .min(2)
      .describe("符合 CandidateAlignmentDraft Schema 的 JSON 字符串"),
    idempotencyKey: tool.schema
      .string()
      .min(8)
      .describe("避免重复提交的幂等键"),
  },
  async execute(args) {
    return request("/api/alignments/agent-candidates", {
      method: "POST",
      headers: { "Idempotency-Key": args.idempotencyKey },
      body: JSON.stringify({
        runId: args.runId,
        requirementId: args.requirementId,
        status: "Candidate",
        payload: parsePayload(args.payload),
      }),
    })
  },
})

export const change_plan_draft = tool({
  description:
    "提交 Proposed Change 草案。只能创建 Draft/Proposed 状态，不能批准、实施、合并或发布。",
  args: {
    runId: tool.schema.string().min(1).describe("Agent/Planning Run ID"),
    requirementId: tool.schema.string().min(1).describe("Requirement ID"),
    payload: tool.schema
      .string()
      .min(2)
      .describe("符合 ProposedChangeDraft Schema 的 JSON 字符串"),
    idempotencyKey: tool.schema
      .string()
      .min(8)
      .describe("避免重复提交的幂等键"),
  },
  async execute(args) {
    return request("/api/change-plans/agent-drafts", {
      method: "POST",
      headers: { "Idempotency-Key": args.idempotencyKey },
      body: JSON.stringify({
        runId: args.runId,
        requirementId: args.requirementId,
        status: "Draft",
        payload: parsePayload(args.payload),
      }),
    })
  },
})

export const reconciliation_context = tool({
  description:
    "读取某次实现对账的 Approved Change、代码 Diff、Actual Graph、测试结果和待验证义务。",
  args: {
    reconciliationRunId: tool.schema
      .string()
      .min(1)
      .describe("Reconciliation Run ID"),
  },
  async execute(args) {
    return request(
      `/api/reconciliation-runs/${encodeURIComponent(args.reconciliationRunId)}/agent-context`,
    )
  },
})

export const record_agent_artifact = tool({
  description:
    "保存结构化 AgentArtifact，包括 Agent、Skill、上下文 Hash、证据、假设和未解决问题。",
  args: {
    runId: tool.schema.string().min(1).describe("Agent Run ID"),
    artifactType: tool.schema
      .enum([
        "RequirementIRDraft",
        "DesiredGraphDraft",
        "CandidateAlignmentDraft",
        "ImplementationSliceDraft",
        "ProposedChangeDraft",
        "ArchitectureReview",
        "ImplementationPatch",
        "TestExecutionReport",
        "ReconciliationReport",
        "ImpactExplanation",
      ])
      .describe("Artifact 类型"),
    payload: tool.schema.string().min(2).describe("结构化 JSON 字符串"),
    idempotencyKey: tool.schema.string().min(8).describe("幂等键"),
  },
  async execute(args, context) {
    return request("/api/agent-artifacts", {
      method: "POST",
      headers: { "Idempotency-Key": args.idempotencyKey },
      body: JSON.stringify({
        runId: args.runId,
        artifactType: args.artifactType,
        agentName: context.agent,
        sessionId: context.sessionID,
        payload: parsePayload(args.payload),
      }),
    })
  },
})
