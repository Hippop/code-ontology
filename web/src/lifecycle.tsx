import cytoscape, { Core, EventObjectNode } from "cytoscape";
import React, { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import "./lifecycle.css";
import { useLeaveGuard, useNavigation } from "./navigation-guard";
import { generationStatus, updateEpoch } from "./flow-state";
import { PlatformDevelopmentPanel } from "./platform-development";
import { MetamodelAuthoring } from "./metamodel-authoring";
import { DevelopmentSlicePanel } from "./development-slice";
import { MetaCatalog, MetaRepository, ModelBinding, MetamodelCenter, MetamodelFields, metaRequest } from "./metamodel";

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
  metamodelRef?: ModelBinding;
};

type Repository = {
  repositoryId: string;
  name: string;
  path: string;
  defaultBranch?: string;
  graphStoragePath?: string;
  metadata?: Record<string, unknown>;
};

type ScanResult = {
  runId: string;
  repositoryId: string;
  snapshotId: string;
  revision: string;
  status: string;
  graphStoragePath?: string;
  graphSnapshotFile?: string;
  summary?: { nodeCount: number; edgeCount: number };
  coverage?: {
    totalJavaFiles: number;
    parsedJavaFiles: number;
    failedJavaFiles: number;
    unresolvedCallCount?: number;
    externalCallCount?: number;
  };
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
  suggestedGraphStoragePath?: string | null;
};

export type WorkbenchView = "lifecycle" | "workflow" | "compare" | "graphs" | "trace";

const lifecyclePhases = [
  ["baseline", "01", "仓库与存储接入", "代码库绑定与 .code-ontology 空间"],
  ["scan", "02", "图谱扫描基线", "代码事实抽取与图谱版本"],
  ["ontology", "03", "项目本体建模", "实体、关系与 SHACL 约束校验"],
  ["requirement", "04", "需求意图 IR", "需求提取与可验证意图建模"],
  ["alignment", "05", "语义对齐裁决", "代码事实与目标设计比对决策"],
  ["plan", "06", "批准计划契约", "变更集审核与生成契约锁定"],
  ["generate", "07", "确定性代码生成", "Diff 审查与安全应用到工作树"],
  ["verify", "08", "提交门禁核验", "精确快照、计划对账与影响闭环"],
  ["release", "09", "发布就绪审计", "全生命周期因果溯源与发布决策"],
] as const;

const governancePhases = [
  ["metamodel", "DEF", "定义与关系", "平台类型、关系与约束"],
  ["authoring", "EDIT", "定义修订", "元模型草稿与正反例检查"],
  ["self", "SELF", "平台自开发项目", "平台自身也是一个业务项目"],
  ["examples", "LAB", "示例与生成实验", "引用定义，校验业务实例"],
  ["task", "DEMO", "任务优先级示例", "独立的业务执行切片"],
] as const;

const phases = [...lifecyclePhases, ...governancePhases] as const;

type Phase = "overview" | (typeof phases)[number][0];

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
  return value.split(/[#/:]/).at(-1) ?? value;
}

function nodeColor(type: string): string {
  type = localName(type);
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
  const [phase, changePhase] = useState<Phase>("metamodel");
  const navigate = useNavigation();
  const setPhase = (next: Phase) => { if (next !== phase) navigate(() => changePhase(next)); };
  const [model, setModel] = useState<EngineeringModel>();
  const [catalog, setCatalog] = useState<MetaCatalog>();
  const [catalogError, setCatalogError] = useState("");
  const [definitionIri, setDefinitionIri] = useState<string>();
  const [nodeProperties, setNodeProperties] = useState<Record<string, string>>({});
  const [nodeDatatypes, setNodeDatatypes] = useState<Record<string, string>>({});
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [repositoryId, setRepositoryId] = useState("");
  const [repositoryPath, setRepositoryPath] = useState("");
  const [graphStoragePath, setGraphStoragePath] = useState("");
  const [scanResult, setScanResult] = useState<ScanResult>();
  const [scanning, setScanning] = useState(false);
  const [analysis, setAnalysis] = useState<Analysis>();
  const [generation, setGeneration] = useState<GenerationResult>();
  const [gate, setGate] = useState<GateResult>();
  const [selectedNode, setSelectedNode] = useState<EngineeringNode>();
  const [impactSeeds, setImpactSeeds] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(false);
  const [modelText, setModelText] = useState("");
  const [nodeDraft, setNodeDraft] = useState({ id: "", type: "https://example.org/code-ontology/engineering#EngineeringRequirement", label: "", path: "" });
  const [edgeDraft, setEdgeDraft] = useState({ source: "", relation: "https://example.org/code-ontology/engineering#definesContract", target: "" });
  const [overwrite, setOverwrite] = useState(false);
  const [confirmApply, setConfirmApply] = useState(false);
  const [plannedText, setPlannedText] = useState("[]");
  const [verificationText, setVerificationText] = useState("[]");
  const [reviewedHash, setReviewedHash] = useState("");

  useEffect(() => {
    let active = true;
    setLoading(true);
    setCatalog(undefined); setCatalogError("");
    metaRequest<MetaCatalog>("/api/metamodel/catalog", token)
      .then(value => { if (active) setCatalog(value); })
      .catch(caught => { if (active) setCatalogError(caught.message); });
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
        setGraphStoragePath(value.suggestedGraphStoragePath ?? (value.suggestedRepositoryPath ? `${value.suggestedRepositoryPath}/.code-ontology` : ""));
        const preferred = value.repositories.find((item) => item.repositoryId === initial.repositoryId) ?? value.repositories[0];
        if (preferred) {
          setRepositoryId(preferred.repositoryId);
          if (preferred.graphStoragePath) setGraphStoragePath(preferred.graphStoragePath);
        }
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

  const contextKey = JSON.stringify([repositoryId, token, model, catalog?.binding]);
  const contextEpoch = useRef({ key: "", epoch: 0 });
  const generationEpoch = useRef({ key: "", epoch: 0 });
  const gateEpoch = useRef({ key: "", epoch: 0 });
  updateEpoch(contextEpoch.current, contextKey);
  updateEpoch(generationEpoch.current, JSON.stringify([contextKey, overwrite]));
  updateEpoch(gateEpoch.current, JSON.stringify([contextKey, plannedText, verificationText]));
  useEffect(() => {
    setScanResult(undefined); setAnalysis(undefined); setGeneration(undefined); setGate(undefined);
    setReviewedHash(""); setConfirmApply(false); setSelectedNode(undefined);
    setLoading(false); setScanning(false); setError(""); setNotice("");
  }, [contextKey]);
  useEffect(() => { setConfirmApply(false); setGeneration(undefined); }, [overwrite]);
  useEffect(() => { setGate(undefined); setReviewedHash(""); }, [plannedText, verificationText]);

  const jsonDirty = Boolean(model && modelText !== JSON.stringify(model, null, 2));
  useLeaveGuard({ label: "项目模型 JSON 草稿", dirty: jsonDirty, busy: false,
    save: async () => {
      const parsed = JSON.parse(modelText) as EngineeringModel;
      if (!Array.isArray(parsed.nodes) || !Array.isArray(parsed.edges)) throw new Error("模型必须包含 nodes 和 edges 数组");
      // Store before navigating: a quota failure must keep the draft open.
      localStorage.setItem("code-ontology.engineering-draft", JSON.stringify(parsed));
      mutate(parsed);
    },
    discard: () => setModelText(model ? JSON.stringify(model, null, 2) : "")
  });

  const counts = useMemo(() => {
    const values = model?.nodes ?? [];
    return {
      requirements: values.filter((node) => ["EngineeringRequirement", "Requirement"].includes(localName(node.type))).length,
      capabilities: values.filter((node) => localName(node.type) === "BusinessCapability").length,
      contracts: values.filter((node) => node.type.includes("Contract")).length,
      tests: values.filter((node) => node.type.includes("Test") || node.type.includes("Verification")).length,
      generators: values.filter((node) => typeof node.generation === "object").length,
    };
  }, [model]);

  const selectedRepository = repositories.find((item) => item.repositoryId === repositoryId);
  const nodeTypes = catalog?.terms.filter(term => term.kind === "Class") ?? [];
  const relationTypes = catalog?.terms.filter(term => term.kind === "ObjectProperty") ?? [];
  const bindingCurrent = Boolean(catalog && model?.metamodelRef?.contentHash === catalog.binding.contentHash && model.metamodelRef.id === catalog.binding.id && model.metamodelRef.version === catalog.binding.version);

  function selectRepository(repo: Repository) {
    setRepositoryId(repo.repositoryId);
    setRepositoryPath(repo.path);
    setGraphStoragePath(repo.graphStoragePath || `${repo.path}/.code-ontology`);
  }

  function handleRepositoryPathChange(val: string) {
    setRepositoryPath(val);
    if (!graphStoragePath || graphStoragePath.endsWith("/.code-ontology") || graphStoragePath.endsWith("\\.code-ontology")) {
      setGraphStoragePath(val ? `${val}/.code-ontology` : "");
    }
  }

  async function scanSelectedRepository() {
    if (!selectedRepository || loading || scanning) return;
    setScanning(true);
    setError("");
    const requestEpoch = contextEpoch.current.epoch;
    try {
      const result = await post<ScanResult>(
        `/api/repositories/${encodeURIComponent(selectedRepository.repositoryId)}/scans`,
        token,
        { includeGraph: false }
      );
      if (requestEpoch !== contextEpoch.current.epoch) return;
      setScanResult(result);
      setAnalysis(undefined); setGeneration(undefined); setGate(undefined); setReviewedHash(""); setConfirmApply(false);
      generationEpoch.current.epoch++; gateEpoch.current.epoch++;
      setNotice(`代码图谱扫描完成！已提取 ${result.summary?.nodeCount ?? result.coverage?.parsedJavaFiles ?? 0} 个节点与 ${result.summary?.edgeCount ?? 0} 条关系，快照已保存至 ${result.graphSnapshotFile ?? selectedRepository.graphStoragePath ?? ".code-ontology/graphs"}`);
      setPhase("scan");
    } catch (caught) {
      if (requestEpoch !== contextEpoch.current.epoch) return;
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      if (requestEpoch === contextEpoch.current.epoch) setScanning(false);
    }
  }

  function mutate(next: EngineeringModel) {
    setModel(next);
    setModelText(JSON.stringify(next, null, 2));
    setAnalysis(undefined);
    setGeneration(undefined);
    setGate(undefined);
    setReviewedHash("");
    setConfirmApply(false);
    setSelectedNode(current => next.nodes.find(node => node.id === current?.id));
  }

  async function bindMetamodel() {
    if (!model || !catalog) return;
    setLoading(true); setError("");
    const requestEpoch = contextEpoch.current.epoch;
    try {
      const result = await metaRequest<{ model: EngineeringModel }>("/api/metamodel/bind", token, { model, revision: catalog.binding.contentHash });
      if (requestEpoch !== contextEpoch.current.epoch) return;
      mutate(result.model);
      setPhase("ontology");
      setNotice("当前浏览器草稿已关联元模型；旧类型已转换为完整 IRI。请运行校验，绑定本身不代表符合约束。");
    } catch (caught) {
      if (requestEpoch !== contextEpoch.current.epoch) return; setError(caught instanceof Error ? caught.message : String(caught)); }
    finally { if (requestEpoch === contextEpoch.current.epoch) setLoading(false); }
  }

  async function registerRepository(event: FormEvent) {
    event.preventDefault();
    if (!model) return;
    setLoading(true);
    setError("");
    const requestEpoch = contextEpoch.current.epoch;
    try {
      const repository = await post<Repository>("/api/repositories", token, {
        path: repositoryPath,
        repositoryId: model.repositoryId || undefined,
        graphStoragePath: graphStoragePath || undefined,
      });
      if (requestEpoch !== contextEpoch.current.epoch) return;
      setRepositories((current) => [repository, ...current.filter((item) => item.repositoryId !== repository.repositoryId)]);
      setRepositoryId(repository.repositoryId);
      mutate({ ...model, repositoryId: repository.repositoryId });
      setNotice(`代码库 ${repository.name} 已成功绑定，图谱空间初始化于 ${repository.graphStoragePath ?? ".code-ontology"}`);
    } catch (caught) {
      if (requestEpoch !== contextEpoch.current.epoch) return;
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      if (requestEpoch === contextEpoch.current.epoch) setLoading(false);
    }
  }

  async function analyze() {
    if (!model) return;
    setLoading(true);
    setError("");
    setNotice("");
    const requestEpoch = contextEpoch.current.epoch;
    try {
      const seeds = impactSeeds.split(",").map((item) => item.trim()).filter(Boolean);
      const result = await post<Analysis>("/api/engineering-semantics/analyze", token, {
        model,
        ...(selectedNode ? { entityId: selectedNode.id, contextDepth: 2 } : {}),
        ...(seeds.length ? { changedEntityIds: seeds, impactDepth: 5 } : {}),
      });
      if (requestEpoch !== contextEpoch.current.epoch) return;
      setAnalysis(result);
      setNotice(result.validation.conforms ? "本体模型满足工程语义约束。" : `发现 ${result.validation.issueCount} 个语义问题。`);
    } catch (caught) {
      if (requestEpoch !== contextEpoch.current.epoch) return;
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      if (requestEpoch === contextEpoch.current.epoch) setLoading(false);
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
    next.properties = Object.fromEntries(Object.entries(nodeProperties).filter(([, value]) => value.trim()).map(([iri, value]) => [iri, value.split("\n").map(v => v.trim()).filter(Boolean).map(v => nodeDatatypes[iri] ? { value: v, datatype: nodeDatatypes[iri] } : v)]));
    if (nodeDraft.path.trim()) next.path = nodeDraft.path.trim();
    mutate({ ...model, nodes: [...model.nodes, next] });
    setSelectedNode(next);
    setNodeDraft({ ...nodeDraft, id: "", label: "", path: "" });
    setNodeProperties({});
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
    if (!model || !repositoryId || loading || scanning) return;
    if (apply && (!generation || generation.applied || !confirmApply)) return;
    setConfirmApply(false);
    if (!apply) setGeneration(undefined);
    setLoading(true);
    setError("");
    const requestEpoch = generationEpoch.current.epoch;
    try {
      const result = await post<GenerationResult>(`/api/ontology-code-generation/${apply ? "apply" : "preview"}`, token, {
        repositoryId,
        model,
        overwrite,
      });
      if (requestEpoch !== generationEpoch.current.epoch) return;
      setGeneration(result);
      setNotice(apply ? `已将 ${result.artifactCount} 个生成产物应用到工作树。` : `已生成 ${result.artifactCount} 个产物预览，尚未写入工作树。`);
      if (apply) {
        setConfirmApply(false);
        setGate(undefined);
        setReviewedHash("");
      }
    } catch (caught) {
      if (requestEpoch !== generationEpoch.current.epoch) return;
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      if (requestEpoch === generationEpoch.current.epoch) setLoading(false);
    }
  }

  async function verifyGate(useReviewedHash = false) {
    if (!model || !repositoryId || loading || scanning) return;
    setLoading(true);
    setError("");
    const requestEpoch = gateEpoch.current.epoch;
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
      if (requestEpoch !== gateEpoch.current.epoch) return;
      setGate(result);
      if (!useReviewedHash) setReviewedHash(result.snapshot.workingTreeSnapshotHash);
      setNotice(result.status === "ReadyToCommit" ? "当前工作树满足提交门禁。" : `提交被 ${result.blockers.length} 个阻断项拦截。`);
    } catch (caught) {
      if (requestEpoch !== gateEpoch.current.epoch) return;
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      if (requestEpoch === gateEpoch.current.epoch) setLoading(false);
    }
  }

  const governance = phase === "metamodel" || phase === "authoring";
  const workspaceNav = <nav className="workspace-switch" aria-label="工作空间">
    <button type="button" aria-pressed={governance} onClick={() => setPhase("metamodel")}><span>PLATFORM CORE</span><strong>元模型治理</strong><small>定义开发的类型、关系、约束与版本</small></button>
    <button type="button" aria-pressed={!governance} onClick={() => setPhase("overview")}><span>BUSINESS DEVELOPMENT</span><strong>业务开发</strong><small>引用元模型，完成项目需求到代码的闭环</small></button>
  </nav>;

  // Platform definitions are independent of project bootstrap and repository selection.
  if (governance) return <>{workspaceNav}<section className="lifecycle-shell governance-shell">
    <nav className="lifecycle-rail" aria-label="元模型治理导航"><div className="workspace-rail-heading"><strong>平台语义核心</strong><p>定义供所有业务项目引用，不隶属于某个项目。</p></div>
      {phases.filter(([id]) => id === "metamodel" || id === "authoring").map(([id,number,title,description]) => <button key={id} type="button" aria-current={phase === id ? "page" : undefined} className={phase === id ? "active" : ""} onClick={() => setPhase(id)}><span>{number}</span><div><strong>{title}</strong><small>{description}</small></div></button>)}
    </nav><div className="lifecycle-content"><div className="lifecycle-context"><div><span>PLATFORM / METAMODEL</span><strong>{phase === "authoring" ? "定义修订与约束检查" : "类型、关系与约束目录"}</strong><small>{catalog ? `安装版本 ${catalog.binding.version} · ${catalog.binding.contentHash.slice(0,16)}` : "读取安装定义"}</small></div></div>
      {catalogError && <p role="alert" className="error">{catalogError}</p>}
      {phase === "authoring" ? <section className="panel"><p>编辑平台元模型草稿；检查通过不等于发布。离开页面前请保存修订。</p><MetamodelAuthoring token={token}/></section> : catalog ? <MetamodelCenter key="governance" catalog={catalog} token={token} onUse={() => setPhase("ontology")} initialIri={definitionIri}/> : !catalogError && <p role="status">正在读取元模型定义…</p>}
    </div></section></>;

  if (loading && !model) return <>{workspaceNav}<section className="empty"><h2>正在装载业务项目…</h2></section></>;
  if (!model) return <>{workspaceNav}<div className="error">{error || "无法装载工程模型；仍可独立使用元模型治理。"}</div></>;

  const renderOverview = () => (
    <div className="lifecycle-overview">
      <section className="lifecycle-hero panel">
        <div>
          <span>END-TO-END / GOVERNED ENGINEERING</span>
          <h2>引用元模型，开展具体业务开发</h2>
          <p>元模型提供统一的开发语义；项目在其下建立业务实例、需求契约、设计映射和验证证据。平台自身的开发管理也是一个业务项目。</p>
        </div>
        <button type="button" onClick={() => setPhase("ontology")}>绑定元模型并建立项目 →</button>
      </section>
      <section className="metrics lifecycle-metrics">
        <Metric label="MODEL" value={model.revision} note={model.graphId} />
        <Metric label="REQUIREMENTS" value={counts.requirements} note={`${counts.capabilities} capability owners`} />
        <Metric label="TRACEABILITY" value={analysis ? ratio(analysis.coverage.implementation.ratio) : "未检查"} note="requirement → code" tone={analysis?.coverage.implementation.ratio === 1 ? "ok" : ""} />
        <Metric label="COMMIT GATE" value={gate?.status ?? "未运行"} note={gate ? `${gate.snapshot.changedFiles.length} changed files` : "bind to exact snapshot"} tone={gate?.status === "ReadyToCommit" ? "ok" : ""} />
      </section>
      <section className="flow-map">
        {lifecyclePhases.map(([id, number, title, description]) => (
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
        <div className="panel-heading">
          <div>
            <span>PHASE 01 / REPOSITORY & STORAGE BINDING</span>
            <h2>接入代码库与图谱存储</h2>
          </div>
          <p>{repositories.length} 个已登记仓库</p>
        </div>
        <form className="stage-form" onSubmit={registerRepository}>
          <label>
            代码库路径 (REPOSITORY PATH) *
            <input
              required
              value={repositoryPath}
              onChange={(event) => handleRepositoryPathChange(event.target.value)}
              placeholder="/absolute/path/to/repository"
            />
          </label>
          <label>
            代码库图谱保存路径 (GRAPH STORAGE PATH)
            <input
              value={graphStoragePath}
              onChange={(event) => setGraphStoragePath(event.target.value)}
              placeholder={repositoryPath ? `${repositoryPath}/.code-ontology` : "默认生成 .code-ontology 文件夹"}
            />
            <small style={{ color: "#7aa2c0", fontSize: "11px", marginTop: "4px" }}>
              未输入时系统默认在代码库根目录下自动创建并绑定 <code>.code-ontology</code> 文件夹
            </small>
          </label>
          <label>
            仓库标识符 (MODEL REPOSITORY ID)
            <input
              value={model.repositoryId}
              onChange={(event) => mutate({ ...model, repositoryId: event.target.value })}
              placeholder="留空自动由路径名派生"
            />
          </label>
          <button disabled={loading || !repositoryPath}>{loading ? "正在注册与初始化…" : "注册代码库并绑定图谱空间"}</button>
        </form>
      </section>

      <section className="panel">
        <div className="panel-heading">
          <div>
            <span>CURRENT / ACTIVE REPOSITORY</span>
            <h2>当前工作仓库与图谱空间</h2>
          </div>
          {selectedRepository && <span style={{ color: "#27d3a2", fontSize: "12px", border: "1px solid #27d3a2", padding: "2px 8px", borderRadius: "4px" }}>已绑定</span>}
        </div>
        {selectedRepository ? (
          <div style={{ padding: "16px 20px", display: "grid", gap: "14px", borderBottom: "1px solid #1c3042" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <strong style={{ fontSize: "16px", color: "#e8f1ff" }}>{selectedRepository.name}</strong>
              <code style={{ fontSize: "11px", color: "#27d3a2", background: "#0a202d", padding: "2px 6px" }}>{selectedRepository.repositoryId}</code>
            </div>
            <div style={{ display: "grid", gap: "8px", fontSize: "12px", color: "#9bb2c5" }}>
              <div><span>代码库路径：</span><code style={{ color: "#c8dded" }}>{selectedRepository.path}</code></div>
              <div><span>默认分支：</span><b style={{ color: "#8ee8c8" }}>{selectedRepository.defaultBranch ?? "HEAD"}</b></div>
              <div>
                <span>图谱存储路径：</span>
                <code style={{ color: "#27d3a2" }}>{selectedRepository.graphStoragePath ?? `${selectedRepository.path}/.code-ontology`}</code>
              </div>
            </div>
            <div style={{ display: "flex", gap: "10px", flexWrap: "wrap", marginTop: "4px" }}>
              <button
                type="button"
                disabled={scanning}
                onClick={scanSelectedRepository}
              >
                {scanning ? "正在提取代码事实…" : "一键扫描并构建代码本体图谱 →"}
              </button>
              {scanResult && (
                <button
                  type="button"
                  className="secondary"
                  onClick={() => setPhase("scan")}
                >
                  查看图谱基线看板 ({scanResult.summary?.nodeCount ?? 0} 节点) →
                </button>
              )}
            </div>
          </div>
        ) : (
          <p className="stage-empty">请在左侧输入代码库路径以绑定仓库与初始化图谱空间。</p>
        )}

        <div style={{ padding: "12px 18px 6px", borderBottom: "1px solid #1c3042" }}>
          <span style={{ fontSize: "10px", letterSpacing: "0.08em", color: "#66859d" }}>SWITCH REPOSITORY</span>
          <h3 style={{ fontSize: "13px", margin: "4px 0 0", color: "#d7f4ec" }}>切换已注册仓库</h3>
        </div>
        <div className="repository-list">
          {repositories.map((repository) => (
            <button
              type="button"
              key={repository.repositoryId}
              className={repositoryId === repository.repositoryId ? "active" : ""}
              onClick={() => selectRepository(repository)}
            >
              <strong>{repository.name}</strong>
              <span>{repository.repositoryId}</span>
              <small title={repository.path}>{repository.path}</small>
              <span style={{ color: "#8ee8c8", fontSize: "10px" }}>{repository.graphStoragePath ? "· .code-ontology" : "· 默认路径"}</span>
              <b>{repository.defaultBranch ?? "—"}</b>
            </button>
          ))}
          {!repositories.length && <p className="stage-empty">暂无注册仓库。</p>}
        </div>
      </section>

      <section className="panel stage-guide">
        <div className="panel-heading">
          <div><span>ARCHITECTURE / SPECIFICATION</span><h2>图谱治理规范</h2></div>
        </div>
        <ol>
          <li><strong>图谱持久化隔离</strong>：图谱快照存储在 <code>.code-ontology/graphs/</code>，与源码严格解耦。</li>
          <li><strong>工程模型版本受控</strong>：项目语义模型存放于 <code>.code-ontology/models/</code>。</li>
          <li><strong>自动化保护</strong>：系统自动创建 <code>.gitignore</code> 忽略临时扫描快照与本地缓存。</li>
          <li><strong>基线驱动开发</strong>：扫描生成 Current Graph 后，方可进入本体对齐与变更计划。</li>
        </ol>
        <button type="button" onClick={() => onNavigate("graphs")}>打开代码图谱探索器</button>
      </section>
    </div>
  );

  const renderScan = () => (
    <div className="stage-grid">
      <section className="panel wide">
        <div className="panel-heading">
          <div>
            <span>PHASE 02 / CODE GRAPH BASELINE</span>
            <h2>代码事实抽取与图谱基线</h2>
          </div>
          <p>{selectedRepository?.name ?? "未选择仓库"}</p>
        </div>
        <div className="metrics" style={{ gridTemplateColumns: "repeat(4, minmax(0, 1fr))", margin: "16px 20px" }}>
          <Metric label="SCAN STATUS" value={scanResult ? scanResult.status : "待扫描"} note={selectedRepository ? selectedRepository.name : "请先绑定仓库"} tone={scanResult?.status === "Completed" ? "ok" : scanResult ? "warn" : ""} />
          <Metric label="PARSED FILES" value={scanResult?.coverage?.parsedJavaFiles ?? "—"} note={`${scanResult?.coverage?.failedJavaFiles ?? 0} failed`} />
          <Metric label="GRAPH NODES" value={scanResult?.summary?.nodeCount ?? "—"} note="classes, methods, fields" />
          <Metric label="RELATION EDGES" value={scanResult?.summary?.edgeCount ?? "—"} note="calls, inherits, contracts" />
        </div>
        <div style={{ padding: "16px 20px", background: "#0b1a28", borderTop: "1px solid #1c3042", borderBottom: "1px solid #1c3042", display: "grid", gap: "12px" }}>
          <div>
            <span style={{ fontSize: "11px", color: "#66859d", display: "block" }}>代码图谱快照落盘文件</span>
            <code style={{ fontSize: "12px", color: "#27d3a2", wordBreak: "break-all" }}>
              {scanResult?.graphSnapshotFile ?? (selectedRepository?.graphStoragePath ? `${selectedRepository.graphStoragePath}/graphs/current/` : ".code-ontology/graphs/current/")}
            </code>
            <p style={{ margin: "6px 0 0", fontSize: "11px", color: "#8fa7ba" }}>
              代码事实由 AST 静态解析引擎确定性提取并生成不可变快照，为后续语义对齐与波及分析提供绝对客观的代码底座。
            </p>
          </div>
          <div style={{ display: "flex", gap: "12px", alignItems: "center", flexWrap: "wrap" }}>
            <button type="button" disabled={scanning || !selectedRepository} onClick={scanSelectedRepository}>
              {scanning ? "正在提取代码图谱…" : "重新扫描代码库 (RE-SCAN)"}
            </button>
            <button type="button" className="secondary" onClick={() => setPhase("ontology")}>
              进入 03 项目本体建模 →
            </button>
            <button type="button" className="secondary" onClick={() => onNavigate("graphs")}>
              在图谱探索器中探索
            </button>
          </div>
        </div>
        {scanResult?.coverage && (
          <div style={{ padding: "16px 20px", display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: "16px", fontSize: "12px" }}>
            <div style={{ padding: "12px", background: "#08131f", border: "1px solid #1a2f42" }}>
              <span style={{ color: "#7e9bb1", display: "block", marginBottom: "4px" }}>调用分析：已解析文件</span>
              <strong style={{ fontSize: "16px", color: "#27d3a2" }}>{scanResult.coverage.parsedJavaFiles} 个文件</strong>
            </div>
            <div style={{ padding: "12px", background: "#08131f", border: "1px solid #1a2f42" }}>
              <span style={{ color: "#7e9bb1", display: "block", marginBottom: "4px" }}>外部依赖调用</span>
              <strong style={{ fontSize: "16px", color: "#8ee8c8" }}>{scanResult.coverage.externalCallCount ?? 0} 个外部调用点</strong>
            </div>
            <div style={{ padding: "12px", background: "#08131f", border: "1px solid #1a2f42" }}>
              <span style={{ color: "#7e9bb1", display: "block", marginBottom: "4px" }}>未解析调用数</span>
              <strong style={{ fontSize: "16px", color: scanResult.coverage.unresolvedCallCount ? "#f6b94a" : "#27d3a2" }}>{scanResult.coverage.unresolvedCallCount ?? 0} 个待推导项</strong>
            </div>
          </div>
        )}
      </section>

      <section className="panel stage-guide">
        <div className="panel-heading">
          <div><span>NEXT / PHASE TRANSITION</span><h2>基线就绪条件</h2></div>
        </div>
        <ol>
          <li>已成功扫描提取源码事实，形成 Current Graph。</li>
          <li>图谱文本快照已写入 <code>.code-ontology/graphs/</code>。</li>
          <li>下一步可进入 03 项目本体，将业务实体、需求与代码进行结构化映射。</li>
        </ol>
        <button type="button" onClick={() => setPhase("ontology")}>前往 03 项目本体建模</button>
        <button type="button" className="secondary" onClick={() => onNavigate("graphs")}>在图谱探索器中深入检索</button>
      </section>
    </div>
  );

  const renderOntology = () => (
    <div className="ontology-studio">
      <section className="panel stage-guide"><h3>{bindingCurrent ? `已关联元模型 ${model.metamodelRef?.version}` : "尚未关联当前元模型"}</h3><p>{bindingCurrent ? model.metamodelRef?.contentHash : "先关联元模型，再从真实定义创建项目实体。旧模型可显式转换；绑定后将执行 SHACL 约束校验。"}</p><div className="button-row"><button type="button" disabled={loading || !catalog} onClick={bindMetamodel}>{bindingCurrent ? "重新绑定并复核" : "关联元模型"}</button><button type="button" onClick={() => setPhase("metamodel")}>查看元模型定义</button></div></section>
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
      {analysis && !analysis.validation.conforms && <section className="panel stage-guide"><h3>需要修正的模型约束</h3>{analysis.validation.issues.map((issue, index) => <p key={index}><code>{String(issue.entityId ?? issue.nodeId ?? "模型")}</code> · {String(issue.message ?? issue.code ?? JSON.stringify(issue))}{issue.path ? <small> · {String(issue.path)}</small> : null}</p>)}</section>}
      <div className="ontology-layout">
        <section className="panel model-panel">
          <div className="panel-heading"><div><span>ONTOLOGY / VISUAL MODEL</span><h2>{model.graphId}</h2></div><p>{analysis?.context ? "context slice" : "complete model"}</p></div>
          <OntologyModelCanvas model={model} focus={analysis?.context} onSelect={setSelectedNode} />
        </section>
        <aside className="panel ontology-inspector">
          <div className="panel-heading"><div><span>ENTITY / INSPECTOR</span><h2>{selectedNode ? localName(selectedNode.id) : "未选择实体"}</h2></div></div>
          <pre>{JSON.stringify(selectedNode ?? analysis?.validation ?? {}, null, 2)}</pre>
          {selectedNode && <button type="button" onClick={() => { setDefinitionIri(selectedNode.type); setPhase("metamodel"); }}>查看该实体的类型定义</button>}
          {analysis?.impact && <div className="impact-summary"><span>CONFIRMED IMPACT</span><strong>{analysis.impact.impactCount}</strong><small>由显式传播规则确认</small></div>}
        </aside>
      </div>
      <div className="ontology-builders">
        <form className="panel builder-form" onSubmit={addNode}>
          <div className="panel-heading"><div><span>AUTHOR / ENTITY</span><h2>新增本体实体</h2></div></div>
          <label>ID<input required value={nodeDraft.id} onChange={(event) => setNodeDraft({ ...nodeDraft, id: event.target.value })} placeholder="req:payment-refund" /></label>
          <label>TYPE<select value={nodeDraft.type} onChange={(event) => { setNodeDraft({ ...nodeDraft, type: event.target.value }); setNodeProperties({}); }}>{nodeTypes.map(term => <option key={term.iri} value={term.iri}>{term.label} · {term.name}</option>)}</select></label>
          <label>LABEL<input required value={nodeDraft.label} onChange={(event) => setNodeDraft({ ...nodeDraft, label: event.target.value })} /></label>
          <label>CODE PATH<input value={nodeDraft.path} onChange={(event) => setNodeDraft({ ...nodeDraft, path: event.target.value })} placeholder="src/domain/refund.py" /></label>
          {catalog && <MetamodelFields type={nodeDraft.type} catalog={catalog} token={token} values={nodeProperties} onChange={setNodeProperties} onDatatypes={setNodeDatatypes} />}
          <button disabled={!bindingCurrent || loading}>ADD ENTITY</button>
        </form>
        <form className="panel builder-form" onSubmit={addEdge}>
          <div className="panel-heading"><div><span>AUTHOR / RELATION</span><h2>建立可追踪关系</h2></div></div>
          <label>SOURCE<select required value={edgeDraft.source} onChange={(event) => setEdgeDraft({ ...edgeDraft, source: event.target.value })}><option value="">选择实体</option>{model.nodes.map((node) => <option key={node.id} value={node.id}>{node.id}</option>)}</select></label>
          <label>RELATION<select value={edgeDraft.relation} onChange={(event) => setEdgeDraft({ ...edgeDraft, relation: event.target.value })}>{relationTypes.map(term => <option key={term.iri} value={term.iri}>{term.label} · {term.name}</option>)}</select></label>
          <label>TARGET<select required value={edgeDraft.target} onChange={(event) => setEdgeDraft({ ...edgeDraft, target: event.target.value })}><option value="">选择实体</option>{model.nodes.map((node) => <option key={node.id} value={node.id}>{node.id}</option>)}</select></label>
          <button disabled={!bindingCurrent || loading}>ADD RELATION</button>
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
      <section className="panel wide"><div className="panel-heading"><div><span>MODEL / REQUIREMENTS</span><h2>当前需求资产</h2></div></div><div className="entity-table">{model.nodes.filter((node) => ["EngineeringRequirement", "Requirement"].includes(localName(node.type))).map((node) => <button type="button" key={node.id} onClick={() => { setSelectedNode(node); setPhase("ontology"); }}><code>{node.id}</code><strong>{node.label}</strong><span>{model.edges.filter((edge) => edge.source === node.id || edge.target === node.id).length} links</span></button>)}</div></section>
    </div>
  );

  const renderAlignment = () => (
    <div className="stage-grid"><section className="panel stage-guide wide"><div className="panel-heading"><div><span>ALIGNMENT / CURRENT ↔ DESIRED</span><h2>先复用语义，再批准结构变化</h2></div></div><div className="stage-copy"><p>候选对齐明确 ExactReuse、ExtendExisting、ModifyExisting、ReplaceExisting、NoMatch 与 Ambiguous。人工确认消除歧义后，生成 Proposed Graph。</p><div className="button-row"><button type="button" onClick={() => onNavigate("compare")}>打开图谱对比</button><button type="button" className="secondary" onClick={() => onNavigate("graphs")}>检查实现切片</button></div></div></section><section className="panel stage-guide"><div className="panel-heading"><div><span>GATE / SEMANTICS</span><h2>进入计划前</h2></div></div><ol><li>需求语义已确认</li><li>Current 与 Desired 图谱分离</li><li>所有 Ambiguous 候选有人工决策</li></ol></section></div>
  );

  const renderPlan = () => (
    <div className="stage-grid"><section className="panel wide"><div className="panel-heading"><div><span>PLAN / GENERATION CONTRACTS</span><h2>可执行变更契约</h2></div><p>{counts.generators} generators</p></div><div className="contract-list">{model.nodes.filter((node) => typeof node.generation === "object").map((node) => <article key={node.id}><span>{node.type}</span><strong>{node.label}</strong><code>{JSON.stringify(node.generation)}</code></article>)}{!counts.generators && <p className="stage-empty">在 RequirementContract 节点添加 generation 配置后，可进入确定性代码生成。</p>}</div></section><section className="panel stage-guide"><div className="panel-heading"><div><span>APPROVAL / CHANGE SET</span><h2>批准边界</h2></div></div><ol><li>目标实体与目标路径明确</li><li>生成契约有唯一需求所有者</li><li>测试与影响义务进入计划</li></ol><button type="button" onClick={() => setPhase("generate")}>进入代码生成</button></section></div>
  );

  const renderGenerate = () => (
    <div className="generation-layout"><section className="panel"><div className="panel-heading"><div><span>CODEGEN / CONTROL</span><h2>预览、审查、应用</h2><p role="status">{generationStatus(generation, loading && phase === "generate")}</p></div><p>{selectedRepository?.name ?? "未绑定仓库"}</p></div><div className="generation-controls"><label>REPOSITORY<select value={repositoryId} onChange={(event) => setRepositoryId(event.target.value)}><option value="">选择已注册仓库</option>{repositories.map((repository) => <option key={repository.repositoryId} value={repository.repositoryId}>{repository.name} · {repository.repositoryId}</option>)}</select></label><label className="checkbox-control"><input type="checkbox" disabled={loading || scanning} checked={overwrite} onChange={(event) => setOverwrite(event.target.checked)} />允许更新已存在的生成文件</label><button type="button" disabled={loading || scanning || !repositoryId} onClick={() => runGeneration(false)}>PREVIEW GENERATION</button><label className="checkbox-control danger-check"><input type="checkbox" disabled={loading || scanning || !generation || generation.applied} checked={confirmApply} onChange={(event) => setConfirmApply(event.target.checked)} />我已审查预览，允许写入工作树</label><button type="button" className="danger-action" disabled={loading || scanning || !repositoryId || !confirmApply || !generation || generation.applied} onClick={() => runGeneration(true)}>APPLY TO WORKTREE</button></div></section>{generation && <section className="panel generated-artifacts"><div className="panel-heading"><div><span>ARTIFACTS / {generation.applied ? "APPLIED" : "PREVIEW"}</span><h2>{generation.artifactCount} 个确定性产物</h2></div><p>{generation.inputHash.slice(0, 16)}</p></div>{generation.artifacts.map((artifact) => <article key={artifact.targetPath}><header><div><span>{artifact.status}</span><strong>{artifact.targetPath}</strong></div><code>{artifact.contentHash.slice(0, 16)}</code></header>{artifact.source && <pre>{artifact.source}</pre>}</article>)}</section>}</div>
  );

  const renderVerify = () => (
    <div className="verify-layout"><section className="panel"><div className="panel-heading"><div><span>PRE-COMMIT / EXACT SNAPSHOT</span><h2>计划—实际—影响闭环</h2></div><p>{selectedRepository?.name ?? "选择仓库"}</p></div><div className="gate-controls"><label>PLANNED CHANGES JSON<textarea disabled={loading || scanning} value={plannedText} onChange={(event) => setPlannedText(event.target.value)} spellCheck={false} /></label><label>VERIFICATION RESULTS JSON<textarea disabled={loading || scanning} value={verificationText} onChange={(event) => setVerificationText(event.target.value)} spellCheck={false} /></label><button type="button" disabled={loading || scanning || !repositoryId} onClick={() => verifyGate(false)}>RUN PRE-COMMIT REVIEW</button>{reviewedHash && <button type="button" className="secondary" disabled={loading} onClick={() => verifyGate(true)}>RECHECK REVIEWED SNAPSHOT</button>}</div></section>{gate && <section className={`panel gate-result ${gate.status === "ReadyToCommit" ? "ready" : "blocked"}`}><div className="gate-verdict"><span>COMMIT DECISION</span><strong>{gate.status}</strong><small>{gate.snapshot.workingTreeSnapshotHash}</small></div><div className="gate-metrics"><div><span>CHANGED FILES</span><strong>{gate.snapshot.changedFiles.length}</strong></div><div><span>OBLIGATIONS</span><strong>{gate.impactObligations.length}</strong></div><div><span>BLOCKERS</span><strong>{gate.blockers.length}</strong></div></div>{gate.blockers.length > 0 && <div className="blocker-list">{gate.blockers.map((blocker, index) => <article key={`${blocker.code}-${index}`}><strong>{blocker.code}</strong><span>{blocker.message ?? blocker.paths?.join(", ") ?? "需要处理"}</span></article>)}</div>}<div className="changed-files">{gate.snapshot.changedFiles.map((file) => <div key={file.path}><b>{file.status}</b><code>{file.path}</code></div>)}</div></section>}</div>
  );

  const renderRelease = () => (
    <div className="stage-grid"><section className="panel release-card wide"><div className="release-state"><span>RELEASE READINESS</span><strong className={gate?.status === "ReadyToCommit" ? "ok" : ""}>{gate?.status === "ReadyToCommit" ? "EVIDENCE READY" : "NOT READY"}</strong><p>发布不是按钮，而是 Approved Graph、Actual Graph、测试证据、影响义务和精确快照共同形成的决策。</p></div><div className="release-actions"><button type="button" onClick={() => onNavigate("compare")}>Approved ↔ Actual 对账</button><button type="button" onClick={() => onNavigate("trace")}>打开需求审计回放</button><button type="button" className="secondary" onClick={() => setPhase("verify")}>返回提交门禁</button></div></section><section className="panel stage-guide"><div className="panel-heading"><div><span>AUDIT / REQUIRED</span><h2>发布证据</h2></div></div><ol><li>本体模型符合约束</li><li>需求—实现—验证覆盖完整</li><li>批准计划与实际变更一致</li><li>影响义务全部关闭</li><li>工作树快照未发生漂移</li></ol></section></div>
  );

  const independentProject = phase === "self" || phase === "task" || phase === "examples";
  const metaRepositories: MetaRepository[] = repositories.map(({ repositoryId, name }) => ({ repositoryId, name }));
  const contents: Record<Phase, () => React.ReactNode> = {
    overview: renderOverview,
    baseline: renderBaseline,
    scan: renderScan,
    ontology: renderOntology,
    requirement: renderRequirement,
    alignment: renderAlignment,
    plan: renderPlan,
    generate: renderGenerate,
    verify: renderVerify,
    release: renderRelease,
    metamodel: () => catalog ? <MetamodelCenter catalog={catalog} token={token} onUse={bindMetamodel} initialIri={definitionIri} repositories={metaRepositories} /> : <p>元模型目录尚未装载，请检查服务或刷新页面。</p>,
    authoring: () => null,
    self: () => <PlatformDevelopmentPanel token={token} />,
    examples: () => catalog ? <MetamodelCenter key="development" workspace="development" catalog={catalog} token={token} onUse={bindMetamodel} repositories={metaRepositories}/> : <p role="alert">{catalogError || "正在读取业务项目所需的元模型…"}</p>,
    task: () => <DevelopmentSlicePanel token={token}/>,
  };

  return (
    <>{workspaceNav}<section className="lifecycle-shell">
      <div className="lifecycle-rail" aria-label="Ontology engineering lifecycle">
        <button type="button" className={phase === "overview" ? "active home" : "home"} onClick={() => setPhase("overview")}>
          <span>FLOW</span><strong>业务项目总览</strong><small>{selectedRepository?.name ?? "未绑定仓库"}</small>
        </button>
        <div style={{ padding: "10px 14px 4px", fontSize: "10px", color: "#4f728c", letterSpacing: "0.08em", borderBottom: "1px solid #142535" }}>
          CORE LIFECYCLE
        </div>
        {lifecyclePhases.map(([id, number, title, description]) => (
          <button
            type="button"
            data-phase={id}
            key={id}
            className={phase === id ? "active" : ""}
            onClick={() => setPhase(id)}
          >
            <span>{number}</span>
            <div><strong>{title}</strong><small>{description}</small></div>
            <b>
              {id === "baseline" && selectedRepository ? "✓" :
               id === "scan" && scanResult ? "✓" :
               id === "ontology" && analysis ? (analysis.validation.conforms ? "✓" : "!") :
               id === "generate" && generation ? (generation.applied ? "待验" : "预览") :
               id === "verify" && gate ? (gate.status === "ReadyToCommit" ? "✓" : "!") : ""}
            </b>
          </button>
        ))}
        <div style={{ padding: "10px 14px 4px", fontSize: "10px", color: "#4f728c", letterSpacing: "0.08em", borderBottom: "1px solid #142535", marginTop: "6px" }}>
          业务项目与示例
        </div>
        {governancePhases.filter(([id]) => id !== "metamodel" && id !== "authoring").map(([id, number, title, description]) => (
          <button
            type="button"
            data-phase={id}
            key={id}
            className={phase === id ? "active" : ""}
            onClick={() => setPhase(id)}
          >
            <span>{number}</span>
            <div><strong>{title}</strong><small>{description}</small></div>
          </button>
        ))}
      </div>
      <div className="lifecycle-content">
        <div className="lifecycle-context"><div><span>BUSINESS / PROJECT</span><strong>{phase === "overview" ? "业务项目总览" : phases.find(([id]) => id === phase)?.[2]}</strong><small>{independentProject ? "独立项目上下文 · 绑定与版本见项目内记录" : `${model.graphId} · rev ${model.revision}`}</small></div>{!independentProject && <button type="button" onClick={() => setPhase("overview")}>MODEL {model.nodes.length}N / {model.edges.length}E</button>}</div>
        {(error || notice) && <div className={error ? "error lifecycle-message" : "notice lifecycle-message"}>{error || notice}<button type="button" onClick={() => { setError(""); setNotice(""); }}>×</button></div>}
        <div className="project-metamodel-reference"><span>{independentProject ? "此项目使用独立的模型与元模型绑定，请在下方查看。" : <>引用元模型：{model.metamodelRef ? `${model.metamodelRef.version} · ${bindingCurrent ? "绑定当前定义" : "绑定待复核"}` : "尚未绑定"}</>}</span><button type="button" onClick={() => setPhase("metamodel")}>查看平台定义</button><button type="button" onClick={() => setPhase("ontology")}>管理项目绑定</button></div>
        {contents[phase]()}
      </div>
    </section></>
  );
}
