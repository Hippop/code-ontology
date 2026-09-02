import cytoscape, { Core, EventObjectNode } from "cytoscape";
import React, { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import "./lifecycle.css";

type JsonObject = Record<string, unknown>;

type EngineeringNode = JsonObject & {
  id: string;
  type: string;
  label?: string;
  path?: string;
};

type EngineeringEdge = JsonObject & {
  source: string;
  relation: string;
  target: string;
};

type EngineeringModel = JsonObject & {
  graphId: string;
  graphType: string;
  revision: string;
  repositoryId: string;
  nodes: EngineeringNode[];
  edges: EngineeringEdge[];
};

type Repository = {
  repositoryId: string;
  name: string;
  path: string;
  defaultBranch?: string;
};

type Analysis = {
  validation: { conforms: boolean; issueCount: number; issues: JsonObject[] };
  coverage: {
    requirementCount: number;
    leafRequirementCount: number;
    implementation: { covered: number; total: number; ratio: number | null };
    verification: { covered: number; total: number; ratio: number | null };
    verificationEvidence: { covered: number; total: number; ratio: number | null };
  };
  summary: { nodeCount: number; edgeCount: number };
  context?: { nodes: EngineeringNode[]; edges: EngineeringEdge[]; summary: JsonObject };
  impact?: { impactCount: number; impacts: JsonObject[] };
};

type GenerationResult = {
  applied: boolean;
  artifactCount: number;
  inputHash: string;
  artifacts: Array<{
    contractId: string;
    requirementId: string;
    targetPath: string;
    contentHash: string;
    status: string;
    source?: string | null;
  }>;
};

type GateResult = {
  status: "ReadyToCommit" | "BlockCommit";
  repositoryId: string;
  snapshot: {
    baseRevision: string;
    workingTreeSnapshotHash: string;
    clean: boolean;
    changedFiles: Array<{ status: string; path: string }>;
  };
  blockers: Array<{ code: string; message?: string; paths?: string[] }>;
  impactObligations: JsonObject[];
  verificationCoverage: JsonObject;
  modelValidation: JsonObject;
};

type WorkbenchBootstrap = {
  model: EngineeringModel;
  repositories: Repository[];
  suggestedRepositoryPath?: string | null;
};

export type WorkbenchView = "lifecycle" | "workflow" | "compare" | "graphs" | "trace";

const phases = [
  ["baseline", "01", "仓库基线", "扫描事实与版本"],
  ["ontology", "02", "本体构建", "概念、关系与约束"],
  ["requirement", "03", "需求意图", "Requirement IR"],
  ["alignment", "04", "语义对齐", "复用、扩展或新建"],
  ["plan", "05", "批准计划", "变更集与生成契约"],
  ["generate", "06", "代码生成", "预览、审查与应用"],
  ["verify", "07", "提交门禁", "实际变更与影响闭环"],
  ["release", "08", "发布审计", "对账、证据与回放"],
] as const;

type Phase = "overview" | (typeof phases)[number][0];

const nodeTypes = [
  "BusinessCapability",
  "EngineeringRequirement",
  "SpecificationContract",
  "BehaviorContract",
  "ConstraintContract",
  "VerificationObjective",
  "TestVerification",
  "TestExecutionEvidence",
  "Module",
  "Class",
  "IntegrationTest",
];

const relationTypes = [
  "eng:specifiesCapability",
  "eng:definesContract",
  "eng:constrainedBy",
  "code:implementsRequirement",
  "code:verifies",
  "eng:derivedFromObjective",
  "eng:verifiesRequirement",
  "eng:satisfiedByEvidence",
  "eng:evidenceArtifact",
];

async function requestJson<T>(path: string, token: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init?.body) headers.set("Content-Type", "application/json");
  const response = await fetch(path, { ...init, headers });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload?.error?.message ?? `HTTP ${response.status}`);
  }
  return payload as T;
}

function post<T>(path: string, token: string, body: JsonObject): Promise<T> {
  return requestJson<T>(path, token, { method: "POST", body: JSON.stringify(body) });
}

function ratio(value: number | null): string {
  return value === null ? "—" : `${Math.round(value * 100)}%`;
}

function localName(value: string): string {
  return value.includes(":") ? value.split(":").at(-1) ?? value : value;
}

function nodeColor(type: string): string {
  if (type === "BusinessCapability") return "#27d3a2";
  if (type === "EngineeringRequirement") return "#49a8ff";
  if (type.includes("Contract")) return "#a88bff";
  if (type.includes("Verification") || type.includes("Test")) return "#f6b94a";
  if (type.includes("Evidence")) return "#44d4e8";
  return "#5f7f99";
}

function OntologyModelCanvas({
  model,
  focus,
  onSelect,
}: {
  model: EngineeringModel;
  focus?: Analysis["context"];
  onSelect: (node: EngineeringNode) => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const graph = useRef<Core | null>(null);
  const visibleNodes = focus?.nodes ?? model.nodes;
  const visibleEdges = focus?.edges ?? model.edges;

  useEffect(() => {
    if (!host.current) return;
    graph.current?.destroy();
    graph.current = cytoscape({
      container: host.current,
      elements: [
        ...visibleNodes.map((node) => ({
          data: {
            id: node.id,
            label: node.label ?? localName(node.id),
            type: node.type,
            color: nodeColor(node.type),
            payload: node,
          },
        })),
        ...visibleEdges.map((edge, index) => ({
          data: {
            id: `semantic-edge-${index}`,
            source: edge.source,
            target: edge.target,
            label: localName(edge.relation),
          },
        })),
      ],
      style: [
        {
          selector: "node",
          style: {
            label: "data(label)",
            "background-color": "data(color)",
            color: "#dcecff",
            "font-family": "IBM Plex Mono, monospace",
            "font-size": 9,
            "text-valign": "bottom",
            "text-margin-y": 7,
            "text-wrap": "ellipsis",
            "text-max-width": "115px",
            width: 28,
            height: 28,
            "border-width": 3,
            "border-color": "#0b1b29",
          },
        },
        {
          selector: "edge",
          style: {
            label: "data(label)",
            width: 1.4,
            "line-color": "#28475d",
            "target-arrow-color": "#52748d",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
            color: "#66859d",
            "font-size": 7,
            "text-background-color": "#07121e",
            "text-background-opacity": 0.85,
            "text-background-padding": "2px",
          },
        },
      ],
      layout: { name: "cose", animate: false, padding: 36, nodeRepulsion: () => 7800 },
    });
    graph.current.on("tap", "node", (event: EventObjectNode) => {
      onSelect(event.target.data("payload") as EngineeringNode);
    });
    return () => graph.current?.destroy();
  }, [model, focus, onSelect, visibleEdges, visibleNodes]);

  return <div className="model-canvas" ref={host} data-testid="ontology-model-canvas" />;
}

function Metric({ label, value, note, tone }: { label: string; value: string | number; note: string; tone?: string }) {
  return (
    <article>
      <span>{label}</span>
      <strong className={tone}>{value}</strong>
      <small>{note}</small>
    </article>
  );
}

export function LifecycleWorkbench({
  token,
  onNavigate,
}: {
  token: string;
  onNavigate: (view: WorkbenchView) => void;
}) {
  const [phase, setPhase] = useState<Phase>("overview");
  const [model, setModel] = useState<EngineeringModel>();
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [repositoryId, setRepositoryId] = useState("");
  const [repositoryPath, setRepositoryPath] = useState("");
  const [analysis, setAnalysis] = useState<Analysis>();
  const [generation, setGeneration] = useState<GenerationResult>();
  const [gate, setGate] = useState<GateResult>();
  const [selectedNode, setSelectedNode] = useState<EngineeringNode>();
  const [impactSeeds, setImpactSeeds] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(false);
  const [modelText, setModelText] = useState("");
  const [nodeDraft, setNodeDraft] = useState({ id: "", type: "EngineeringRequirement", label: "", path: "" });
  const [edgeDraft, setEdgeDraft] = useState({ source: "", relation: "eng:definesContract", target: "" });
  const [overwrite, setOverwrite] = useState(false);
  const [confirmApply, setConfirmApply] = useState(false);
  const [plannedText, setPlannedText] = useState("[]");
  const [verificationText, setVerificationText] = useState("[]");
  const [reviewedHash, setReviewedHash] = useState("");

  useEffect(() => {
    let active = true;
    setLoading(true);
    requestJson<WorkbenchBootstrap>("/api/engineering-workbench", token)
      .then((value) => {
        if (!active) return;
        const cached = localStorage.getItem("code-ontology.engineering-draft");
        let initial = value.model;
        if (cached) {
          try {
            initial = JSON.parse(cached) as EngineeringModel;
          } catch {
            localStorage.removeItem("code-ontology.engineering-draft");
          }
        }
        setModel(initial);
        setModelText(JSON.stringify(initial, null, 2));
        setRepositories(value.repositories);
        setRepositoryPath(value.suggestedRepositoryPath ?? "");
        const preferred = value.repositories.find((item) => item.repositoryId === initial.repositoryId) ?? value.repositories[0];
        if (preferred) setRepositoryId(preferred.repositoryId);
      })
      .catch((caught) => setError(caught instanceof Error ? caught.message : String(caught)))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [token]);

  useEffect(() => {
    if (!model) return;
    localStorage.setItem("code-ontology.engineering-draft", JSON.stringify(model));
  }, [model]);

  const counts = useMemo(() => {
    const values = model?.nodes ?? [];
    return {
      requirements: values.filter((node) => node.type === "EngineeringRequirement").length,
      capabilities: values.filter((node) => node.type === "BusinessCapability").length,
      contracts: values.filter((node) => node.type.includes("Contract")).length,
      tests: values.filter((node) => node.type.includes("Test") || node.type.includes("Verification")).length,
      generators: values.filter((node) => typeof node.generation === "object").length,
    };
  }, [model]);

  const selectedRepository = repositories.find((item) => item.repositoryId === repositoryId);

  function mutate(next: EngineeringModel) {
    setModel(next);
    setModelText(JSON.stringify(next, null, 2));
    setAnalysis(undefined);
    setGeneration(undefined);
    setGate(undefined);
    setReviewedHash("");
  }

  async function registerRepository(event: FormEvent) {
    event.preventDefault();
    if (!model) return;
    setLoading(true);
    setError("");
    try {
      const repository = await post<Repository>("/api/repositories", token, {
        path: repositoryPath,
        repositoryId: model.repositoryId || undefined,
      });
      setRepositories((current) => [repository, ...current.filter((item) => item.repositoryId !== repository.repositoryId)]);
      setRepositoryId(repository.repositoryId);
      mutate({ ...model, repositoryId: repository.repositoryId });
      setNotice(`仓库 ${repository.name} 已绑定到工程本体模型。`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setLoading(false);
    }
  }

  async function analyze() {
    if (!model) return;
    setLoading(true);
    setError("");
    setNotice("");
    try {
      const seeds = impactSeeds.split(",").map((item) => item.trim()).filter(Boolean);
      const result = await post<Analysis>("/api/engineering-semantics/analyze", token, {
        model,
        ...(selectedNode ? { entityId: selectedNode.id, contextDepth: 2 } : {}),
        ...(seeds.length ? { changedEntityIds: seeds, impactDepth: 5 } : {}),
      });
      setAnalysis(result);
      setNotice(result.validation.conforms ? "本体模型满足工程语义约束。" : `发现 ${result.validation.issueCount} 个语义问题。`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setLoading(false);
    }
  }

  function addNode(event: FormEvent) {
    event.preventDefault();
    if (!model) return;
    if (model.nodes.some((node) => node.id === nodeDraft.id.trim())) {
      setError(`实体 ID 已存在：${nodeDraft.id}`);
      return;
    }
    const next: EngineeringNode = { id: nodeDraft.id.trim(), type: nodeDraft.type, label: nodeDraft.label.trim() || nodeDraft.id.trim() };
    if (nodeDraft.path.trim()) next.path = nodeDraft.path.trim();
    mutate({ ...model, nodes: [...model.nodes, next] });
    setSelectedNode(next);
    setNodeDraft({ ...nodeDraft, id: "", label: "", path: "" });
    setError("");
  }

  function addEdge(event: FormEvent) {
    event.preventDefault();
    if (!model) return;
    const next = { source: edgeDraft.source, relation: edgeDraft.relation, target: edgeDraft.target };
    if (!model.nodes.some((node) => node.id === next.source) || !model.nodes.some((node) => node.id === next.target)) {
      setError("关系的起点和终点必须是已存在的实体。");
      return;
    }
    mutate({ ...model, edges: [...model.edges, next] });
    setError("");
  }

  function applyModelJson() {
    try {
      const next = JSON.parse(modelText) as EngineeringModel;
      if (!Array.isArray(next.nodes) || !Array.isArray(next.edges)) throw new Error("nodes 与 edges 必须是数组");
      mutate(next);
      setNotice("JSON 模型已载入草稿。运行语义检查后再进入生成阶段。");
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    }
  }

  async function runGeneration(apply: boolean) {
    if (!model || !repositoryId) return;
    setLoading(true);
    setError("");
    try {
      const result = await post<GenerationResult>(`/api/ontology-code-generation/${apply ? "apply" : "preview"}`, token, {
        repositoryId,
        model,
        overwrite,
      });
      setGeneration(result);
      setNotice(apply ? `已将 ${result.artifactCount} 个生成产物应用到工作树。` : `已生成 ${result.artifactCount} 个产物预览，尚未写入工作树。`);
      if (apply) {
        setConfirmApply(false);
        setGate(undefined);
        setReviewedHash("");
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setLoading(false);
    }
  }

  async function verifyGate(useReviewedHash = false) {
    if (!model || !repositoryId) return;
    setLoading(true);
    setError("");
    try {
      const plannedChanges = JSON.parse(plannedText) as JsonObject[];
      const verificationResults = JSON.parse(verificationText) as JsonObject[];
      if (!Array.isArray(plannedChanges) || !Array.isArray(verificationResults)) throw new Error("计划与验证结果必须是 JSON 数组");
      const result = await post<GateResult>("/api/precommit-verification", token, {
        repositoryId,
        model,
        plannedChanges,
        verificationResults,
        ...(useReviewedHash && reviewedHash ? { reviewedSnapshotHash: reviewedHash } : {}),
      });
      setGate(result);
      if (!useReviewedHash) setReviewedHash(result.snapshot.workingTreeSnapshotHash);
      setNotice(result.status === "ReadyToCommit" ? "当前工作树满足提交门禁。" : `提交被 ${result.blockers.length} 个阻断项拦截。`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setLoading(false);
    }
  }

  if (loading && !model) return <section className="empty"><span>BOOTSTRAP</span><h2>正在装载工程语义工作台…</h2></section>;
  if (!model) return <div className="error">{error || "无法装载工程模型"}</div>;

  const renderOverview = () => (
    <div className="lifecycle-overview">
      <section className="lifecycle-hero panel">
        <div>
          <span>END-TO-END / GOVERNED ENGINEERING</span>
          <h2>用一份可验证的本体模型驱动需求、代码与提交决策</h2>
          <p>模型不只是文档：它同时约束语义对齐、生成契约、实际变更映射、测试义务和发布证据。</p>
        </div>
        <button type="button" onClick={() => setPhase("ontology")}>开始构建本体 →</button>
      </section>
      <section className="metrics lifecycle-metrics">
        <Metric label="MODEL" value={model.revision} note={model.graphId} />
        <Metric label="REQUIREMENTS" value={counts.requirements} note={`${counts.capabilities} capability owners`} />
        <Metric label="TRACEABILITY" value={analysis ? ratio(analysis.coverage.implementation.ratio) : "未检查"} note="requirement → code" tone={analysis?.coverage.implementation.ratio === 1 ? "ok" : ""} />
        <Metric label="COMMIT GATE" value={gate?.status ?? "未运行"} note={gate ? `${gate.snapshot.changedFiles.length} changed files` : "bind to exact snapshot"} tone={gate?.status === "ReadyToCommit" ? "ok" : ""} />
      </section>
      <section className="flow-map">
        {phases.map(([id, number, title, description]) => (
          <button key={id} type="button" onClick={() => setPhase(id)}>
            <span>{number}</span><strong>{title}</strong><small>{description}</small><b>→</b>
          </button>
        ))}
      </section>
    </div>
  );

  const renderBaseline = () => (
    <div className="stage-grid">
      <section className="panel">
        <div className="panel-heading"><div><span>REPOSITORY / GOVERNED SCOPE</span><h2>绑定代码仓库</h2></div><p>{repositories.length} registered</p></div>
        <form className="stage-form" onSubmit={registerRepository}>
          <label>REPOSITORY PATH<input required value={repositoryPath} onChange={(event) => setRepositoryPath(event.target.value)} placeholder="/absolute/path/to/repository" /></label>
          <label>MODEL REPOSITORY ID<input value={model.repositoryId} onChange={(event) => mutate({ ...model, repositoryId: event.target.value })} /></label>
          <button disabled={loading}>REGISTER & BIND</button>
        </form>
      </section>
      <section className="panel">
        <div className="panel-heading"><div><span>BASELINE / SELECTION</span><h2>当前工作仓库</h2></div></div>
        <div className="repository-list">
          {repositories.map((repository) => <button type="button" key={repository.repositoryId} className={repositoryId === repository.repositoryId ? "active" : ""} onClick={() => setRepositoryId(repository.repositoryId)}><strong>{repository.name}</strong><span>{repository.repositoryId}</span><small>{repository.path}</small><b>{repository.defaultBranch ?? "—"}</b></button>)}
          {!repositories.length && <p className="stage-empty">先注册一个允许范围内的 Git 仓库。</p>}
        </div>
      </section>
      <section className="panel stage-guide">
        <div className="panel-heading"><div><span>NEXT / FACTS</span><h2>基线完成条件</h2></div></div>
        <ol><li>仓库身份与 HEAD 修订可读取</li><li>Current Graph 只由扫描器产生</li><li>工程模型绑定稳定 repositoryId</li></ol>
        <button type="button" onClick={() => onNavigate("graphs")}>打开代码图谱探索器</button>
      </section>
    </div>
  );

  const renderOntology = () => (
    <div className="ontology-studio">
      <section className="metrics">
        <Metric label="ENTITIES" value={model.nodes.length} note={`${counts.requirements} requirements`} />
        <Metric label="RELATIONS" value={model.edges.length} note={`${counts.contracts} contracts`} />
        <Metric label="CONFORMANCE" value={analysis ? (analysis.validation.conforms ? "CONFORMS" : `${analysis.validation.issueCount} ISSUES`) : "NOT RUN"} note="engineering invariants" tone={analysis?.validation.conforms ? "ok" : analysis ? "bad" : ""} />
        <Metric label="VERIFICATION" value={analysis ? ratio(analysis.coverage.verification.ratio) : "—"} note={`${counts.tests} methods / tests`} tone={analysis?.coverage.verification.ratio === 1 ? "ok" : ""} />
      </section>
      <section className="ontology-toolbar">
        <label>IMPACT SEEDS<input value={impactSeeds} onChange={(event) => setImpactSeeds(event.target.value)} placeholder="code:http-api, req:platform-access" /></label>
        <div><span>{selectedNode ? `CONTEXT: ${selectedNode.id}` : "选择节点可收集上下文"}</span></div>
        <button type="button" disabled={loading} onClick={analyze}>{loading ? "ANALYZING…" : "VALIDATE · COVERAGE · IMPACT"}</button>
      </section>
      <div className="ontology-layout">
        <section className="panel model-panel">
          <div className="panel-heading"><div><span>ONTOLOGY / VISUAL MODEL</span><h2>{model.graphId}</h2></div><p>{analysis?.context ? "context slice" : "complete model"}</p></div>
          <OntologyModelCanvas model={model} focus={analysis?.context} onSelect={setSelectedNode} />
        </section>
        <aside className="panel ontology-inspector">
          <div className="panel-heading"><div><span>ENTITY / INSPECTOR</span><h2>{selectedNode ? localName(selectedNode.id) : "未选择实体"}</h2></div></div>
          <pre>{JSON.stringify(selectedNode ?? analysis?.validation ?? {}, null, 2)}</pre>
          {analysis?.impact && <div className="impact-summary"><span>CONFIRMED IMPACT</span><strong>{analysis.impact.impactCount}</strong><small>由显式传播规则确认</small></div>}
        </aside>
      </div>
      <div className="ontology-builders">
        <form className="panel builder-form" onSubmit={addNode}>
          <div className="panel-heading"><div><span>AUTHOR / ENTITY</span><h2>新增本体实体</h2></div></div>
          <label>ID<input required value={nodeDraft.id} onChange={(event) => setNodeDraft({ ...nodeDraft, id: event.target.value })} placeholder="req:payment-refund" /></label>
          <label>TYPE<select value={nodeDraft.type} onChange={(event) => setNodeDraft({ ...nodeDraft, type: event.target.value })}>{nodeTypes.map((value) => <option key={value}>{value}</option>)}</select></label>
          <label>LABEL<input required value={nodeDraft.label} onChange={(event) => setNodeDraft({ ...nodeDraft, label: event.target.value })} /></label>
          <label>CODE PATH<input value={nodeDraft.path} onChange={(event) => setNodeDraft({ ...nodeDraft, path: event.target.value })} placeholder="src/domain/refund.py" /></label>
          <button>ADD ENTITY</button>
        </form>
        <form className="panel builder-form" onSubmit={addEdge}>
          <div className="panel-heading"><div><span>AUTHOR / RELATION</span><h2>建立可追踪关系</h2></div></div>
          <label>SOURCE<select required value={edgeDraft.source} onChange={(event) => setEdgeDraft({ ...edgeDraft, source: event.target.value })}><option value="">选择实体</option>{model.nodes.map((node) => <option key={node.id} value={node.id}>{node.id}</option>)}</select></label>
          <label>RELATION<select value={edgeDraft.relation} onChange={(event) => setEdgeDraft({ ...edgeDraft, relation: event.target.value })}>{relationTypes.map((value) => <option key={value}>{value}</option>)}</select></label>
          <label>TARGET<select required value={edgeDraft.target} onChange={(event) => setEdgeDraft({ ...edgeDraft, target: event.target.value })}><option value="">选择实体</option>{model.nodes.map((node) => <option key={node.id} value={node.id}>{node.id}</option>)}</select></label>
          <button>ADD RELATION</button>
        </form>
        <details className="panel model-source">
          <summary>MODEL SOURCE · JSON 导入/高级编辑</summary>
          <textarea value={modelText} onChange={(event) => setModelText(event.target.value)} spellCheck={false} />
          <button type="button" onClick={applyModelJson}>APPLY JSON TO DRAFT</button>
        </details>
      </div>
    </div>
  );

  const renderRequirement = () => (
    <div className="stage-grid">
      <section className="panel stage-guide wide"><div className="panel-heading"><div><span>INTENT / REQUIREMENT IR</span><h2>从自然语言需求到受治理工程意图</h2></div><p>{counts.requirements} modeled</p></div><div className="stage-copy"><p>需求工作流负责提取 Desired Entity、业务规则、验收标准和非功能约束；确认后才允许进入对齐与计划阶段。</p><button type="button" onClick={() => onNavigate("workflow")}>进入 Requirement Workflow</button></div></section>
      <section className="panel wide"><div className="panel-heading"><div><span>MODEL / REQUIREMENTS</span><h2>当前需求资产</h2></div></div><div className="entity-table">{model.nodes.filter((node) => node.type === "EngineeringRequirement").map((node) => <button type="button" key={node.id} onClick={() => { setSelectedNode(node); setPhase("ontology"); }}><code>{node.id}</code><strong>{node.label}</strong><span>{model.edges.filter((edge) => edge.source === node.id || edge.target === node.id).length} links</span></button>)}</div></section>
    </div>
  );

  const renderAlignment = () => (
    <div className="stage-grid"><section className="panel stage-guide wide"><div className="panel-heading"><div><span>ALIGNMENT / CURRENT ↔ DESIRED</span><h2>先复用语义，再批准结构变化</h2></div></div><div className="stage-copy"><p>候选对齐明确 ExactReuse、ExtendExisting、ModifyExisting、ReplaceExisting、NoMatch 与 Ambiguous。人工确认消除歧义后，生成 Proposed Graph。</p><div className="button-row"><button type="button" onClick={() => onNavigate("compare")}>打开图谱对比</button><button type="button" className="secondary" onClick={() => onNavigate("graphs")}>检查实现切片</button></div></div></section><section className="panel stage-guide"><div className="panel-heading"><div><span>GATE / SEMANTICS</span><h2>进入计划前</h2></div></div><ol><li>需求语义已确认</li><li>Current 与 Desired 图谱分离</li><li>所有 Ambiguous 候选有人工决策</li></ol></section></div>
  );

  const renderPlan = () => (
    <div className="stage-grid"><section className="panel wide"><div className="panel-heading"><div><span>PLAN / GENERATION CONTRACTS</span><h2>可执行变更契约</h2></div><p>{counts.generators} generators</p></div><div className="contract-list">{model.nodes.filter((node) => typeof node.generation === "object").map((node) => <article key={node.id}><span>{node.type}</span><strong>{node.label}</strong><code>{JSON.stringify(node.generation)}</code></article>)}{!counts.generators && <p className="stage-empty">在 RequirementContract 节点添加 generation 配置后，可进入确定性代码生成。</p>}</div></section><section className="panel stage-guide"><div className="panel-heading"><div><span>APPROVAL / CHANGE SET</span><h2>批准边界</h2></div></div><ol><li>目标实体与目标路径明确</li><li>生成契约有唯一需求所有者</li><li>测试与影响义务进入计划</li></ol><button type="button" onClick={() => setPhase("generate")}>进入代码生成</button></section></div>
  );

  const renderGenerate = () => (
    <div className="generation-layout"><section className="panel"><div className="panel-heading"><div><span>CODEGEN / CONTROL</span><h2>预览、审查、应用</h2></div><p>{selectedRepository?.name ?? "未绑定仓库"}</p></div><div className="generation-controls"><label>REPOSITORY<select value={repositoryId} onChange={(event) => setRepositoryId(event.target.value)}><option value="">选择已注册仓库</option>{repositories.map((repository) => <option key={repository.repositoryId} value={repository.repositoryId}>{repository.name} · {repository.repositoryId}</option>)}</select></label><label className="checkbox-control"><input type="checkbox" checked={overwrite} onChange={(event) => setOverwrite(event.target.checked)} />允许更新已存在的生成文件</label><button type="button" disabled={loading || !repositoryId} onClick={() => runGeneration(false)}>PREVIEW GENERATION</button><label className="checkbox-control danger-check"><input type="checkbox" checked={confirmApply} onChange={(event) => setConfirmApply(event.target.checked)} />我已审查预览，允许写入工作树</label><button type="button" className="danger-action" disabled={loading || !repositoryId || !confirmApply} onClick={() => runGeneration(true)}>APPLY TO WORKTREE</button></div></section>{generation && <section className="panel generated-artifacts"><div className="panel-heading"><div><span>ARTIFACTS / {generation.applied ? "APPLIED" : "PREVIEW"}</span><h2>{generation.artifactCount} 个确定性产物</h2></div><p>{generation.inputHash.slice(0, 16)}</p></div>{generation.artifacts.map((artifact) => <article key={artifact.targetPath}><header><div><span>{artifact.status}</span><strong>{artifact.targetPath}</strong></div><code>{artifact.contentHash.slice(0, 16)}</code></header>{artifact.source && <pre>{artifact.source}</pre>}</article>)}</section>}</div>
  );

  const renderVerify = () => (
    <div className="verify-layout"><section className="panel"><div className="panel-heading"><div><span>PRE-COMMIT / EXACT SNAPSHOT</span><h2>计划—实际—影响闭环</h2></div><p>{selectedRepository?.name ?? "选择仓库"}</p></div><div className="gate-controls"><label>PLANNED CHANGES JSON<textarea value={plannedText} onChange={(event) => setPlannedText(event.target.value)} spellCheck={false} /></label><label>VERIFICATION RESULTS JSON<textarea value={verificationText} onChange={(event) => setVerificationText(event.target.value)} spellCheck={false} /></label><button type="button" disabled={loading || !repositoryId} onClick={() => verifyGate(false)}>RUN PRE-COMMIT REVIEW</button>{reviewedHash && <button type="button" className="secondary" disabled={loading} onClick={() => verifyGate(true)}>RECHECK REVIEWED SNAPSHOT</button>}</div></section>{gate && <section className={`panel gate-result ${gate.status === "ReadyToCommit" ? "ready" : "blocked"}`}><div className="gate-verdict"><span>COMMIT DECISION</span><strong>{gate.status}</strong><small>{gate.snapshot.workingTreeSnapshotHash}</small></div><div className="gate-metrics"><div><span>CHANGED FILES</span><strong>{gate.snapshot.changedFiles.length}</strong></div><div><span>OBLIGATIONS</span><strong>{gate.impactObligations.length}</strong></div><div><span>BLOCKERS</span><strong>{gate.blockers.length}</strong></div></div>{gate.blockers.length > 0 && <div className="blocker-list">{gate.blockers.map((blocker, index) => <article key={`${blocker.code}-${index}`}><strong>{blocker.code}</strong><span>{blocker.message ?? blocker.paths?.join(", ") ?? "需要处理"}</span></article>)}</div>}<div className="changed-files">{gate.snapshot.changedFiles.map((file) => <div key={file.path}><b>{file.status}</b><code>{file.path}</code></div>)}</div></section>}</div>
  );

  const renderRelease = () => (
    <div className="stage-grid"><section className="panel release-card wide"><div className="release-state"><span>RELEASE READINESS</span><strong className={gate?.status === "ReadyToCommit" ? "ok" : ""}>{gate?.status === "ReadyToCommit" ? "EVIDENCE READY" : "NOT READY"}</strong><p>发布不是按钮，而是 Approved Graph、Actual Graph、测试证据、影响义务和精确快照共同形成的决策。</p></div><div className="release-actions"><button type="button" onClick={() => onNavigate("compare")}>Approved ↔ Actual 对账</button><button type="button" onClick={() => onNavigate("trace")}>打开需求审计回放</button><button type="button" className="secondary" onClick={() => setPhase("verify")}>返回提交门禁</button></div></section><section className="panel stage-guide"><div className="panel-heading"><div><span>AUDIT / REQUIRED</span><h2>发布证据</h2></div></div><ol><li>本体模型符合约束</li><li>需求—实现—验证覆盖完整</li><li>批准计划与实际变更一致</li><li>影响义务全部关闭</li><li>工作树快照未发生漂移</li></ol></section></div>
  );

  const contents: Record<Phase, () => React.ReactNode> = { overview: renderOverview, baseline: renderBaseline, ontology: renderOntology, requirement: renderRequirement, alignment: renderAlignment, plan: renderPlan, generate: renderGenerate, verify: renderVerify, release: renderRelease };

  return (
    <section className="lifecycle-shell">
      <div className="lifecycle-rail" aria-label="Ontology engineering lifecycle">
        <button type="button" className={phase === "overview" ? "active home" : "home"} onClick={() => setPhase("overview")}><span>FLOW</span><strong>全流程控制台</strong><small>{selectedRepository?.name ?? "未绑定仓库"}</small></button>
        {phases.map(([id, number, title, description]) => <button type="button" data-phase={id} key={id} className={phase === id ? "active" : ""} onClick={() => setPhase(id)}><span>{number}</span><div><strong>{title}</strong><small>{description}</small></div><b>{id === "ontology" && analysis ? (analysis.validation.conforms ? "✓" : "!") : id === "generate" && generation ? "✓" : id === "verify" && gate ? (gate.status === "ReadyToCommit" ? "✓" : "!") : ""}</b></button>)}
      </div>
      <div className="lifecycle-content">
        <div className="lifecycle-context"><div><span>CURRENT STAGE</span><strong>{phase === "overview" ? "全流程总览" : phases.find(([id]) => id === phase)?.[2]}</strong><small>{model.graphId} · rev {model.revision}</small></div><button type="button" onClick={() => setPhase("overview")}>MODEL {model.nodes.length}N / {model.edges.length}E</button></div>
        {(error || notice) && <div className={error ? "error lifecycle-message" : "notice lifecycle-message"}>{error || notice}<button type="button" onClick={() => { setError(""); setNotice(""); }}>×</button></div>}
        {contents[phase]()}
      </div>
    </section>
  );
}
