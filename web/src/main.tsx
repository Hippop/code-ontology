import cytoscape, { Core, EventObjectNode } from "cytoscape";
import React, {
  FormEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { createRoot } from "react-dom/client";
import { LifecycleWorkbench, WorkbenchView } from "./lifecycle";
import "./styles.css";

type JsonObject = Record<string, unknown>;
type GraphSpace =
  | "current"
  | "business"
  | "desired"
  | "proposed"
  | "approved"
  | "actual"
  | "impact";

type GraphNode = JsonObject & {
  id: string;
  type?: string;
  label?: string;
  name?: string;
};

type GraphEdge = JsonObject & {
  source: string;
  relation: string;
  target: string;
};

type GraphRevision = {
  graphSpace: GraphSpace;
  revision: string;
  createdAt: string;
  nodeCount: number;
  edgeCount: number;
  metadata: JsonObject;
};

type GraphCatalog = {
  graphSpaces: GraphSpace[];
  revisions: GraphRevision[];
  count: number;
};

type GraphResult = {
  graphSpace: GraphSpace;
  queryType: string;
  revision: string;
  startEntityId?: string;
  targetEntityId?: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  paths: string[][];
  truncated: boolean;
  summary?: {
    totalNodes: number;
    totalEdges: number;
    selectedNodes: number;
    selectedEdges: number;
    entityTypes: Array<{ name: string; count: number }>;
    relations: Array<{ name: string; count: number }>;
  };
};

type ComparedGraph = {
  graphSpace: GraphSpace;
  revision: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
};

type GraphCompareResult = {
  base: ComparedGraph;
  target: ComparedGraph;
  nodes: GraphNode[];
  edges: GraphEdge[];
  fieldChanges: Array<{
    entityId: string;
    field: string;
    before: unknown;
    after: unknown;
  }>;
  truncated: boolean;
  summary: {
    baseNodes: number;
    baseEdges: number;
    targetNodes: number;
    targetEdges: number;
    nodeChanges: Record<string, number>;
    edgeChanges: Record<string, number>;
    selectedNodes: number;
    selectedEdges: number;
    fieldChanges: number;
    entityTypes: Array<{ name: string; count: number }>;
  };
};

type Replay = {
  requirementId: string;
  designRevisionId: string;
  replayHash: string;
  auditChain: {
    status: string;
    eventCount: number;
    headHash: string;
  };
  events: Array<{
    eventId: string;
    eventType: string;
    actor?: string;
    timestamp: string;
    payload: JsonObject;
  }>;
  resources: {
    requirementIR?: JsonObject;
    workflowRuns?: JsonObject[];
    alignmentRuns: JsonObject[];
    changePlans: JsonObject[];
    agentRuns: JsonObject[];
    reconciliationRuns: JsonObject[];
    impactRuns: JsonObject[];
    reviews: JsonObject[];
    artifacts: JsonObject[];
  };
};

type RequirementWorkflow = JsonObject & {
  workflowId: string;
  repositoryId: string;
  requirementId?: string;
  currentRevision: string;
  status: string;
  stage: string;
  pendingGate?: string;
  nextActions: string[];
  pendingItems: JsonObject[];
  resourceIds: JsonObject;
  steps: Array<{
    sequence: number;
    stage: string;
    status: string;
    timestamp: string;
    resource: JsonObject;
    detail: JsonObject;
  }>;
  agentRuns: JsonObject[];
};

const graphSpaceLabels: Record<GraphSpace, string> = {
  current: "代码本体 · Current",
  business: "业务本体 · Business",
  desired: "目标设计 · Desired",
  proposed: "变更草案 · Proposed",
  approved: "批准变更 · Approved",
  actual: "实际实现 · Actual",
  impact: "波及分析 · Impact",
};

const graphSpaceColors: Record<GraphSpace, string> = {
  current: "#49a8ff",
  business: "#27d3a2",
  desired: "#a88bff",
  proposed: "#f6b94a",
  approved: "#5ae68a",
  actual: "#44d4e8",
  impact: "#ff7a82",
};

const queryTypes = [
  ["GRAPH_OVERVIEW", "图谱总览"],
  ["ENTITY_NEIGHBORHOOD", "实体邻域"],
  ["IMPLEMENTATION_SLICE", "实现切片"],
  ["BUSINESS_TRACE", "业务追踪"],
  ["CALL_PATH", "调用路径"],
  ["CONTRACT_CONSUMERS", "契约消费者"],
  ["DATA_DEPENDENCIES", "数据依赖"],
  ["CHANGE_CONTEXT", "变更上下文"],
  ["IMPACT_PATHS", "波及路径"],
] as const;

const stages = [
  ["Requirement", "requirementIR"],
  ["Alignment", "alignmentRuns"],
  ["Plan", "changePlans"],
  ["Agent", "agentRuns"],
  ["Reconcile", "reconciliationRuns"],
  ["Impact", "impactRuns"],
] as const;

async function requestJson<T>(
  path: string,
  token: string,
  init?: RequestInit,
): Promise<T> {
  const headers = new Headers(init?.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init?.body) headers.set("Content-Type", "application/json");
  const response = await fetch(path, { ...init, headers });
  const payload = await response.json();
  if (!response.ok) {
    const message =
      payload?.error?.message ?? `Request failed with HTTP ${response.status}`;
    throw new Error(message);
  }
  return payload as T;
}

function statusOf(value: unknown): string {
  if (!value || typeof value !== "object") return "Missing";
  const record = value as JsonObject;
  return String(record.status ?? record.approvalState ?? "Available");
}

function latest(values: JsonObject[]): JsonObject | undefined {
  return values.at(-1);
}

function shortLabel(value: string, maximum = 34): string {
  const tail = value.includes(":") ? value.split(":").at(-1) ?? value : value;
  return tail.length > maximum ? `${tail.slice(0, maximum - 1)}…` : tail;
}

function nodeShape(type: string): string {
  if (/Process|ChangeSet|Module|Repository/.test(type)) return "round-rectangle";
  if (/Rule|Constraint|Decision/.test(type)) return "diamond";
  if (/Table|Schema|Entity/.test(type)) return "barrel";
  if (/Test|Verification/.test(type)) return "hexagon";
  if (/Event|Message/.test(type)) return "octagon";
  return "ellipse";
}

function nodeColor(node: GraphNode, graphSpace: GraphSpace): string {
  const changeStatus = String(node.changeStatus ?? "");
  if (changeStatus === "Added") return "#27d3a2";
  if (changeStatus === "Removed") return "#ff6874";
  if (changeStatus === "Modified") return "#f6b94a";
  if (changeStatus === "Unchanged") return "#4f7392";
  if (graphSpace === "impact") {
    const state = String(node.state ?? "");
    if (state === "Direct") return "#ff5c68";
    if (state === "Propagated") return "#f6b94a";
    if (state === "Contained") return "#4f7392";
    if (state === "Unresolved") return "#c278ff";
  }
  if (node.externalReference === true) return "#486174";
  return graphSpaceColors[graphSpace];
}

function JsonInspector({
  value,
  height,
}: {
  value: unknown;
  height: number;
}) {
  return (
    <pre className="json-inspector" style={{ maxHeight: height }}>
      {JSON.stringify(value ?? {}, null, 2)}
    </pre>
  );
}

function GraphCanvas({
  result,
  onSelect,
}: {
  result: GraphResult;
  onSelect: (value: GraphNode | GraphEdge) => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const graph = useRef<Core | null>(null);

  useEffect(() => {
    if (!host.current) return;
    graph.current?.destroy();
    graph.current = cytoscape({
      container: host.current,
      elements: [
        ...result.nodes.map((node) => ({
          data: {
            id: node.id,
            label: shortLabel(
              String(node.label ?? node.name ?? node.qualifiedName ?? node.id),
            ),
            type: String(node.type ?? "Unknown"),
            color: nodeColor(node, result.graphSpace),
            payload: node,
          },
          classes: nodeShape(String(node.type ?? "")),
        })),
        ...result.edges.map((edge, index) => ({
          data: {
            id: `edge-${index}-${edge.source}-${edge.target}`,
            source: edge.source,
            target: edge.target,
            label: shortLabel(edge.relation, 26),
            color:
              edge.changeStatus === "Added"
                ? "#27d3a2"
                : edge.changeStatus === "Removed"
                  ? "#ff6874"
                  : edge.changeStatus === "Modified"
                    ? "#f6b94a"
                    : "#314c62",
            payload: edge,
          },
          classes: edge.changeStatus === "Removed" ? "removed" : "",
        })),
      ],
      style: [
        {
          selector: "node",
          style: {
            "background-color": "data(color)",
            "border-color": "#07101c",
            "border-width": 3,
            color: "#dceaf7",
            label: "data(label)",
            shape: "ellipse",
            width: 42,
            height: 42,
            "font-family": "IBM Plex Mono, monospace",
            "font-size": 9,
            "text-max-width": "110px",
            "text-wrap": "ellipsis",
            "text-valign": "bottom",
            "text-margin-y": 8,
          },
        },
        {
          selector: "node.round-rectangle",
          style: { shape: "round-rectangle" },
        },
        {
          selector: "node.diamond",
          style: { shape: "diamond" },
        },
        {
          selector: "node.barrel",
          style: { shape: "barrel" },
        },
        {
          selector: "node.hexagon",
          style: { shape: "hexagon" },
        },
        {
          selector: "node.octagon",
          style: { shape: "octagon" },
        },
        {
          selector: "node:selected",
          style: {
            "border-color": "#ffffff",
            "border-width": 4,
            "overlay-color": "#ffffff",
            "overlay-opacity": 0.08,
          },
        },
        {
          selector: "edge",
          style: {
            color: "#718ca3",
            label: "data(label)",
            width: 1.5,
            "line-color": "data(color)",
            "line-style": "solid",
            "target-arrow-color": "data(color)",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
            "font-family": "IBM Plex Mono, monospace",
            "font-size": 7,
            "text-background-color": "#07101c",
            "text-background-opacity": 0.86,
            "text-background-padding": "2px",
            "text-rotation": "autorotate",
          },
        },
        {
          selector: "edge.removed",
          style: { "line-style": "dashed" },
        },
        {
          selector: "edge:selected",
          style: {
            color: "#f6b94a",
            "line-color": "#f6b94a",
            "target-arrow-color": "#f6b94a",
            width: 3,
          },
        },
      ],
      layout: {
        name: "cose",
        animate: false,
        fit: true,
        padding: 36,
        idealEdgeLength: 92,
        nodeRepulsion: 8500,
      },
    });
    graph.current.on("tap", "node", (event: EventObjectNode) => {
      onSelect(event.target.data("payload") as GraphNode);
    });
    graph.current.on("tap", "edge", (event: EventObjectNode) => {
      onSelect(event.target.data("payload") as GraphEdge);
    });
    return () => graph.current?.destroy();
  }, [onSelect, result]);

  return <div className="ontology-canvas" ref={host} aria-label="Ontology graph" />;
}

function GraphExplorer({ token }: { token: string }) {
  const [catalog, setCatalog] = useState<GraphCatalog>();
  const [graphSpace, setGraphSpace] = useState<GraphSpace>("current");
  const [revision, setRevision] = useState("");
  const [queryType, setQueryType] = useState("GRAPH_OVERVIEW");
  const [entityId, setEntityId] = useState("");
  const [targetEntityId, setTargetEntityId] = useState("");
  const [entityType, setEntityType] = useState("");
  const [relation, setRelation] = useState("");
  const [search, setSearch] = useState("");
  const [depth, setDepth] = useState(2);
  const [limit, setLimit] = useState(160);
  const [result, setResult] = useState<GraphResult>();
  const [selected, setSelected] = useState<GraphNode | GraphEdge>();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const revisions = useMemo(
    () =>
      catalog?.revisions.filter((item) => item.graphSpace === graphSpace) ?? [],
    [catalog, graphSpace],
  );
  const selectedRevision = revisions.find((item) => item.revision === revision);

  async function loadCatalog() {
    setError("");
    try {
      const next = await requestJson<GraphCatalog>("/api/graphs", token);
      setCatalog(next);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    }
  }

  useEffect(() => {
    void loadCatalog();
  }, [token]);

  useEffect(() => {
    const firstRevision = revisions[0]?.revision ?? "";
    if (!revisions.some((item) => item.revision === revision)) {
      setRevision(firstRevision);
      setResult(undefined);
      setSelected(undefined);
    }
  }, [revision, revisions]);

  async function loadGraph(event?: FormEvent) {
    event?.preventDefault();
    if (!revision) {
      setError(`${graphSpaceLabels[graphSpace]} 尚无可用图版本。`);
      return;
    }
    if (queryType !== "GRAPH_OVERVIEW" && !entityId.trim()) {
      setError("邻域或路径查询必须提供起始 Entity ID。");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const body: JsonObject = {
        graphSpace,
        queryType,
        revision,
        depth,
        limit,
      };
      if (queryType === "GRAPH_OVERVIEW") {
        body.entityTypes = entityType ? [entityType] : [];
        body.relations = relation ? [relation] : [];
        if (search.trim()) body.search = search.trim();
      } else {
        body.entityId = entityId.trim();
        if (targetEntityId.trim()) body.targetEntityId = targetEntityId.trim();
      }
      const next = await requestJson<GraphResult>(
        "/api/agent-context/graph-query",
        token,
        { method: "POST", body: JSON.stringify(body) },
      );
      setResult(next);
      setSelected(next.nodes[0]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setLoading(false);
    }
  }

  const typeOptions = result?.summary?.entityTypes ?? [];
  const relationOptions = result?.summary?.relations ?? [];

  return (
    <section className="explorer-shell">
      <form className="explorer-toolbar" onSubmit={loadGraph}>
        <label>
          GRAPH SPACE
          <select
            value={graphSpace}
            onChange={(event) => setGraphSpace(event.target.value as GraphSpace)}
          >
            {(catalog?.graphSpaces ?? Object.keys(graphSpaceLabels)).map((space) => (
              <option key={space} value={space}>
                {graphSpaceLabels[space as GraphSpace]}
              </option>
            ))}
          </select>
        </label>
        <label className="wide-control">
          REVISION
          <select
            value={revision}
            onChange={(event) => setRevision(event.target.value)}
          >
            {!revisions.length && <option value="">No graph revision</option>}
            {revisions.map((item) => (
              <option key={item.revision} value={item.revision}>
                {item.revision} · {item.nodeCount}N/{item.edgeCount}E
              </option>
            ))}
          </select>
        </label>
        <label>
          QUERY
          <select
            value={queryType}
            onChange={(event) => setQueryType(event.target.value)}
          >
            {queryTypes.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <button disabled={loading}>
          {loading ? "LOADING…" : "LOAD GRAPH"}
        </button>
      </form>

      {queryType === "GRAPH_OVERVIEW" ? (
        <div className="graph-filters">
          <label>
            SEARCH
            <input
              value={search}
              placeholder="ID / label / path"
              onChange={(event) => setSearch(event.target.value)}
            />
          </label>
          <label>
            ENTITY TYPE
            <select
              value={entityType}
              onChange={(event) => setEntityType(event.target.value)}
            >
              <option value="">All entity types</option>
              {typeOptions.map((item) => (
                <option key={item.name} value={item.name}>
                  {item.name} ({item.count})
                </option>
              ))}
            </select>
          </label>
          <label>
            RELATION
            <select
              value={relation}
              onChange={(event) => setRelation(event.target.value)}
            >
              <option value="">All relations</option>
              {relationOptions.map((item) => (
                <option key={item.name} value={item.name}>
                  {item.name} ({item.count})
                </option>
              ))}
            </select>
          </label>
          <label>
            NODE LIMIT
            <input
              type="number"
              min={1}
              max={500}
              value={limit}
              onChange={(event) => setLimit(Number(event.target.value))}
            />
          </label>
        </div>
      ) : (
        <div className="graph-filters">
          <label className="wide-control">
            START ENTITY ID
            <input
              value={entityId}
              placeholder="code:repo:java:com.example.Service"
              onChange={(event) => setEntityId(event.target.value)}
            />
          </label>
          <label className="wide-control">
            TARGET ENTITY ID
            <input
              value={targetEntityId}
              placeholder="optional"
              onChange={(event) => setTargetEntityId(event.target.value)}
            />
          </label>
          <label>
            DEPTH
            <input
              type="number"
              min={0}
              max={6}
              value={depth}
              onChange={(event) => setDepth(Number(event.target.value))}
            />
          </label>
          <label>
            NODE LIMIT
            <input
              type="number"
              min={1}
              max={500}
              value={limit}
              onChange={(event) => setLimit(Number(event.target.value))}
            />
          </label>
        </div>
      )}

      {error && <div className="error">{error}</div>}

      <div className="graph-stat-strip">
        <div>
          <span>SPACE</span>
          <strong>{graphSpace.toUpperCase()}</strong>
        </div>
        <div>
          <span>FULL GRAPH</span>
          <strong>
            {result?.summary?.totalNodes ?? selectedRevision?.nodeCount ?? 0}N /{" "}
            {result?.summary?.totalEdges ?? selectedRevision?.edgeCount ?? 0}E
          </strong>
        </div>
        <div>
          <span>VISIBLE</span>
          <strong>
            {result?.nodes.length ?? 0}N / {result?.edges.length ?? 0}E
          </strong>
        </div>
        <div>
          <span>STATUS</span>
          <strong className={result?.truncated ? "warn" : "ok"}>
            {result?.truncated ? "TRUNCATED" : result ? "COMPLETE" : "READY"}
          </strong>
        </div>
      </div>

      <div className="graph-workspace">
        <div className="panel graph-main">
          <div className="panel-heading">
            <div>
              <span>ONTOLOGY / GRAPH</span>
              <h2>{graphSpaceLabels[graphSpace]}</h2>
            </div>
            <p>{result?.revision ?? (revision || "No revision selected")}</p>
          </div>
          {result?.nodes.length ? (
            <GraphCanvas result={result} onSelect={setSelected} />
          ) : (
            <div className="graph-empty">
              <strong>尚未装载图谱</strong>
              <p>选择图空间和 Revision 后点击 LOAD GRAPH。</p>
            </div>
          )}
        </div>

        <aside className="panel graph-inspector">
          <div className="panel-heading">
            <div>
              <span>EVIDENCE / INSPECTOR</span>
              <h2>实体与关系证据</h2>
            </div>
          </div>
          {selected ? (
            <>
              <div className="selected-summary">
                <span>{String(selected.type ?? selected.relation ?? "Entity")}</span>
                <strong>
                  {String(selected.label ?? selected.id ?? selected.relation)}
                </strong>
              </div>
              <JsonInspector value={selected} height={520} />
            </>
          ) : (
            <div className="inspector-empty">点击节点或关系查看完整属性与证据。</div>
          )}
        </aside>
      </div>

      {!!result?.paths.length && (
        <div className="panel path-panel">
          <div className="panel-heading">
            <div>
              <span>PATHS / RESULT</span>
              <h2>查询路径</h2>
            </div>
            <p>{result.paths.length} paths</p>
          </div>
          <div className="path-list">
            {result.paths.map((path, index) => (
              <button
                type="button"
                key={`${index}-${path.join(">")}`}
                onClick={() =>
                  setSelected(
                    result.nodes.find((node) => node.id === path.at(-1)),
                  )
                }
              >
                <span>{String(index + 1).padStart(2, "0")}</span>
                <code>{path.join(" → ")}</code>
              </button>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

function GraphCompare({ token }: { token: string }) {
  const [catalog, setCatalog] = useState<GraphCatalog>();
  const [baseSpace, setBaseSpace] = useState<GraphSpace>("current");
  const [targetSpace, setTargetSpace] = useState<GraphSpace>("actual");
  const [baseRevision, setBaseRevision] = useState("");
  const [targetRevision, setTargetRevision] = useState("");
  const [changeStatus, setChangeStatus] = useState("");
  const [entityType, setEntityType] = useState("");
  const [search, setSearch] = useState("");
  const [limit, setLimit] = useState(300);
  const [mode, setMode] = useState<"overlay" | "split">("overlay");
  const [result, setResult] = useState<GraphCompareResult>();
  const [selected, setSelected] = useState<GraphNode | GraphEdge>();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    void requestJson<GraphCatalog>("/api/graphs", token)
      .then(setCatalog)
      .catch((caught) =>
        setError(caught instanceof Error ? caught.message : String(caught)),
      );
  }, [token]);

  const baseRevisions = useMemo(
    () =>
      catalog?.revisions.filter((item) => item.graphSpace === baseSpace) ?? [],
    [baseSpace, catalog],
  );
  const targetRevisions = useMemo(
    () =>
      catalog?.revisions.filter((item) => item.graphSpace === targetSpace) ?? [],
    [catalog, targetSpace],
  );

  useEffect(() => {
    if (!baseRevisions.some((item) => item.revision === baseRevision)) {
      setBaseRevision(baseRevisions[0]?.revision ?? "");
      setResult(undefined);
    }
  }, [baseRevision, baseRevisions]);

  useEffect(() => {
    if (!targetRevisions.some((item) => item.revision === targetRevision)) {
      setTargetRevision(targetRevisions[0]?.revision ?? "");
      setResult(undefined);
    }
  }, [targetRevision, targetRevisions]);

  async function compare(event?: FormEvent) {
    event?.preventDefault();
    if (!baseRevision || !targetRevision) {
      setError("Base 和 Target 都必须选择可用的图版本。");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const next = await requestJson<GraphCompareResult>(
        "/api/graphs/compare",
        token,
        {
          method: "POST",
          body: JSON.stringify({
            base: { graphSpace: baseSpace, revision: baseRevision },
            target: { graphSpace: targetSpace, revision: targetRevision },
            changeStatuses: changeStatus ? [changeStatus] : [],
            entityTypes: entityType ? [entityType] : [],
            search: search.trim() || undefined,
            limit,
          }),
        },
      );
      setResult(next);
      setSelected(next.nodes[0]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setLoading(false);
    }
  }

  const overlayResult = useMemo<GraphResult | undefined>(
    () =>
      result
        ? {
            graphSpace: result.target.graphSpace,
            revision: `${result.base.revision} → ${result.target.revision}`,
            queryType: "GRAPH_COMPARE",
            nodes: result.nodes,
            edges: result.edges,
            paths: [],
            truncated: result.truncated,
          }
        : undefined,
    [result],
  );
  const baseGraphResult = useMemo<GraphResult | undefined>(
    () =>
      result
        ? {
            ...result.base,
            queryType: "GRAPH_COMPARE",
            paths: [],
            truncated: result.truncated,
          }
        : undefined,
    [result],
  );
  const targetGraphResult = useMemo<GraphResult | undefined>(
    () =>
      result
        ? {
            ...result.target,
            queryType: "GRAPH_COMPARE",
            paths: [],
            truncated: result.truncated,
          }
        : undefined,
    [result],
  );

  return (
    <section className="explorer-shell">
      <form className="compare-toolbar" onSubmit={compare}>
        <label>
          BASE SPACE
          <select
            value={baseSpace}
            onChange={(event) => setBaseSpace(event.target.value as GraphSpace)}
          >
            {(catalog?.graphSpaces ?? Object.keys(graphSpaceLabels)).map((space) => (
              <option key={space} value={space}>
                {graphSpaceLabels[space as GraphSpace]}
              </option>
            ))}
          </select>
        </label>
        <label>
          BASE REVISION
          <select
            value={baseRevision}
            onChange={(event) => setBaseRevision(event.target.value)}
          >
            {baseRevisions.map((item) => (
              <option key={item.revision} value={item.revision}>
                {item.revision} · {item.nodeCount}N/{item.edgeCount}E
              </option>
            ))}
          </select>
        </label>
        <label>
          TARGET SPACE
          <select
            value={targetSpace}
            onChange={(event) => setTargetSpace(event.target.value as GraphSpace)}
          >
            {(catalog?.graphSpaces ?? Object.keys(graphSpaceLabels)).map((space) => (
              <option key={space} value={space}>
                {graphSpaceLabels[space as GraphSpace]}
              </option>
            ))}
          </select>
        </label>
        <label>
          TARGET REVISION
          <select
            value={targetRevision}
            onChange={(event) => setTargetRevision(event.target.value)}
          >
            {targetRevisions.map((item) => (
              <option key={item.revision} value={item.revision}>
                {item.revision} · {item.nodeCount}N/{item.edgeCount}E
              </option>
            ))}
          </select>
        </label>
        <button disabled={loading}>
          {loading ? "COMPARING…" : "COMPARE"}
        </button>
      </form>

      <div className="compare-filters">
        <label>
          VIEW
          <select
            value={mode}
            onChange={(event) => setMode(event.target.value as "overlay" | "split")}
          >
            <option value="overlay">差异叠加</option>
            <option value="split">左右对照</option>
          </select>
        </label>
        <label>
          CHANGE STATUS
          <select
            value={changeStatus}
            onChange={(event) => setChangeStatus(event.target.value)}
          >
            <option value="">All changes</option>
            <option value="Added">Added</option>
            <option value="Removed">Removed</option>
            <option value="Modified">Modified</option>
            <option value="Unchanged">Unchanged</option>
          </select>
        </label>
        <label>
          ENTITY TYPE
          <select
            value={entityType}
            onChange={(event) => setEntityType(event.target.value)}
          >
            <option value="">All entity types</option>
            {(result?.summary.entityTypes ?? []).map((item) => (
              <option key={item.name} value={item.name}>
                {item.name} ({item.count})
              </option>
            ))}
          </select>
        </label>
        <label>
          SEARCH
          <input
            value={search}
            placeholder="ID / label / path"
            onChange={(event) => setSearch(event.target.value)}
          />
        </label>
        <label>
          NODE LIMIT
          <input
            type="number"
            min={1}
            max={500}
            value={limit}
            onChange={(event) => setLimit(Number(event.target.value))}
          />
        </label>
      </div>

      {error && <div className="error">{error}</div>}
      <div className="change-legend">
        {["Added", "Removed", "Modified", "Unchanged"].map((status) => (
          <span key={status} className={`change-${status.toLowerCase()}`}>
            {status} {result?.summary.nodeChanges[status] ?? 0}
          </span>
        ))}
        <span>Field changes {result?.summary.fieldChanges ?? 0}</span>
        <span className={result?.truncated ? "warn" : "ok"}>
          {result?.truncated ? "TRUNCATED" : result ? "COMPLETE" : "READY"}
        </span>
      </div>

      <div className="compare-workspace">
        <div className="panel compare-main">
          <div className="panel-heading">
            <div>
              <span>GRAPH / COMPARE</span>
              <h2>{mode === "overlay" ? "差异叠加" : "左右版本对照"}</h2>
            </div>
            <p>
              {baseSpace}/{baseRevision} → {targetSpace}/{targetRevision}
            </p>
          </div>
          {!result ? (
            <div className="graph-empty">
              <strong>尚未执行图谱对照</strong>
              <p>选择 Base 和 Target Revision 后点击 COMPARE。</p>
            </div>
          ) : mode === "overlay" && overlayResult ? (
            <div className="compare-canvas">
              <GraphCanvas result={overlayResult} onSelect={setSelected} />
            </div>
          ) : baseGraphResult && targetGraphResult ? (
            <div className="side-by-side">
              <section>
                <b>BASE · {graphSpaceLabels[result.base.graphSpace]}</b>
                <GraphCanvas
                  result={baseGraphResult}
                  onSelect={setSelected}
                />
              </section>
              <section>
                <b>TARGET · {graphSpaceLabels[result.target.graphSpace]}</b>
                <GraphCanvas
                  result={targetGraphResult}
                  onSelect={setSelected}
                />
              </section>
            </div>
          ) : null}
        </div>
        <aside className="panel graph-inspector">
          <div className="panel-heading">
            <div>
              <span>DIFF / EVIDENCE</span>
              <h2>字段与实体差异</h2>
            </div>
          </div>
          {selected ? (
            <JsonInspector value={selected} height={690} />
          ) : (
            <div className="inspector-empty">点击差异节点或关系查看前后值。</div>
          )}
        </aside>
      </div>

      {!!result?.fieldChanges.length && (
        <section className="panel">
          <div className="panel-heading">
            <div>
              <span>FIELD / CHANGES</span>
              <h2>属性级差异</h2>
            </div>
            <p>{result.fieldChanges.length} visible changes</p>
          </div>
          <div className="field-change-list">
            {result.fieldChanges.map((change, index) => (
              <button
                type="button"
                key={`${change.entityId}-${change.field}-${index}`}
                onClick={() =>
                  setSelected(
                    result.nodes.find((node) => node.id === change.entityId),
                  )
                }
              >
                <code>{change.entityId}</code>
                <strong>{change.field}</strong>
                <span>{JSON.stringify(change.before)}</span>
                <span>{JSON.stringify(change.after)}</span>
              </button>
            ))}
          </div>
        </section>
      )}
    </section>
  );
}

function WorkflowControl({ token }: { token: string }) {
  const [workflow, setWorkflow] = useState<RequirementWorkflow>();
  const [workflowId, setWorkflowId] = useState("");
  const [repositoryId, setRepositoryId] = useState("");
  const [currentRevision, setCurrentRevision] = useState("");
  const [requirementId, setRequirementId] = useState("");
  const [documentId, setDocumentId] = useState("");
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [actor, setActor] = useState("platform-owner");
  const [agentMode, setAgentMode] = useState("required");
  const [decision, setDecision] = useState("");
  const [rationale, setRationale] = useState("");
  const [allowedFiles, setAllowedFiles] = useState("src/**");
  const [forbiddenFiles, setForbiddenFiles] = useState(
    ".git/**\n.env\n**/secrets/**",
  );
  const [requiredTests, setRequiredTests] = useState("./mvnw test");
  const [securityDataApproved, setSecurityDataApproved] = useState(false);
  const [candidateSelections, setCandidateSelections] = useState<
    Record<string, string>
  >({});
  const [selected, setSelected] = useState<unknown>();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!workflow || workflow.pendingGate !== "AlignmentReview") return;
    const defaults: Record<string, string> = {};
    for (const pending of workflow.pendingItems) {
      const desiredId = String(pending.desiredEntityId ?? "");
      const candidates = Array.isArray(pending.candidates)
        ? (pending.candidates as JsonObject[])
        : [];
      const firstCandidate = candidates[0];
      if (desiredId && firstCandidate?.candidateId) {
        defaults[desiredId] = String(firstCandidate.candidateId);
      }
    }
    setCandidateSelections(defaults);
  }, [workflow]);

  useEffect(() => {
    const gate = workflow?.pendingGate;
    if (gate === "RequirementReview") setDecision("Confirm");
    else if (gate === "ArchitectureReview") setDecision("Accept");
    else if (gate === "ChangeApproval") setDecision("Approve");
    else setDecision("");
  }, [workflow?.pendingGate]);

  async function createWorkflow(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const next = await requestJson<RequirementWorkflow>(
        "/api/requirement-workflows",
        token,
        {
          method: "POST",
          body: JSON.stringify({
            repositoryId,
            currentRevision: currentRevision || undefined,
            requirementId: requirementId || undefined,
            actor,
            agentMode,
            document: {
              documentId: documentId || undefined,
              title,
              owner: actor,
            },
            revision: {
              revisionNumber: "1.0",
              content,
              actor,
            },
          }),
        },
      );
      setWorkflow(next);
      setWorkflowId(next.workflowId);
      setSelected(next);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setLoading(false);
    }
  }

  async function loadWorkflow(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const next = await requestJson<RequirementWorkflow>(
        `/api/requirement-workflows/${encodeURIComponent(workflowId)}`,
        token,
      );
      setWorkflow(next);
      setSelected(next);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setLoading(false);
    }
  }

  function lines(value: string): string[] {
    return value
      .split(/\r?\n/)
      .map((item) => item.trim())
      .filter(Boolean);
  }

  async function resumeWorkflow(event: FormEvent) {
    event.preventDefault();
    if (!workflow?.pendingGate) return;
    setLoading(true);
    setError("");
    try {
      const body: JsonObject = {
        gate: workflow.pendingGate,
        actor,
        rationale,
      };
      if (workflow.pendingGate === "AlignmentReview") {
        body.selections = Object.values(candidateSelections).map((candidateId) => ({
          candidateId,
          decision: "Confirm",
          rationale,
        }));
      } else {
        body.decision = decision;
      }
      if (workflow.pendingGate === "RequirementReview") {
        body.acceptUnresolved = true;
      }
      if (workflow.pendingGate === "ChangeApproval") {
        body.allowedFiles = lines(allowedFiles);
        body.forbiddenFiles = lines(forbiddenFiles);
        body.requiredTests = lines(requiredTests);
        body.securityDataApproved = securityDataApproved;
      }
      const next = await requestJson<RequirementWorkflow>(
        `/api/requirement-workflows/${encodeURIComponent(workflow.workflowId)}/resume`,
        token,
        { method: "POST", body: JSON.stringify(body) },
      );
      setWorkflow(next);
      setSelected(next);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setLoading(false);
    }
  }

  async function retryWorkflow(event: FormEvent) {
    event.preventDefault();
    if (!workflow || workflow.status !== "Failed") return;
    setLoading(true);
    setError("");
    try {
      const next = await requestJson<RequirementWorkflow>(
        `/api/requirement-workflows/${encodeURIComponent(workflow.workflowId)}/retry`,
        token,
        {
          method: "POST",
          body: JSON.stringify({ actor, rationale }),
        },
      );
      setWorkflow(next);
      setSelected(next);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="workflow-shell">
      <form className="workflow-load" onSubmit={loadWorkflow}>
        <label>
          WORKFLOW ID
          <input
            value={workflowId}
            placeholder="requirement-workflow-..."
            onChange={(event) => setWorkflowId(event.target.value)}
          />
        </label>
        <button disabled={loading || !workflowId}>LOAD WORKFLOW</button>
      </form>

      <details className="workflow-create" open={!workflow}>
        <summary>CREATE COMPLETE REQUIREMENT WORKFLOW</summary>
        <form onSubmit={createWorkflow}>
          <label>
            REPOSITORY ID
            <input
              required
              value={repositoryId}
              onChange={(event) => setRepositoryId(event.target.value)}
            />
          </label>
          <label>
            CURRENT REVISION
            <input
              value={currentRevision}
              placeholder="optional · latest scanned revision"
              onChange={(event) => setCurrentRevision(event.target.value)}
            />
          </label>
          <label>
            REQUIREMENT ID
            <input
              value={requirementId}
              placeholder="optional when document declares it"
              onChange={(event) => setRequirementId(event.target.value)}
            />
          </label>
          <label>
            AGENT MODE
            <select
              value={agentMode}
              onChange={(event) => setAgentMode(event.target.value)}
            >
              <option value="required">Required</option>
              <option value="advisory">Advisory</option>
              <option value="disabled">Disabled</option>
            </select>
          </label>
          <label>
            DOCUMENT ID
            <input
              value={documentId}
              placeholder="optional"
              onChange={(event) => setDocumentId(event.target.value)}
            />
          </label>
          <label>
            TITLE
            <input
              required
              value={title}
              onChange={(event) => setTitle(event.target.value)}
            />
          </label>
          <label>
            ACTOR
            <input
              required
              value={actor}
              onChange={(event) => setActor(event.target.value)}
            />
          </label>
          <label className="workflow-content">
            DESIGN CONTENT
            <textarea
              required
              value={content}
              placeholder="完整需求与详细设计 Markdown"
              onChange={(event) => setContent(event.target.value)}
            />
          </label>
          <button disabled={loading}>
            {loading ? "STARTING…" : "START WORKFLOW"}
          </button>
        </form>
      </details>

      {error && <div className="error">{error}</div>}
      {!workflow && !error && (
        <section className="empty">
          <span>ORCHESTRATION</span>
          <h2>创建或装载完整需求工作流。</h2>
          <p>Agent 自动执行分析阶段；人工 Gate 明确暂停并可恢复。</p>
        </section>
      )}

      {workflow && (
        <>
          <div className="workflow-status">
            <div>
              <span>STATUS</span>
              <strong>{workflow.status}</strong>
            </div>
            <div>
              <span>STAGE</span>
              <strong>{workflow.stage}</strong>
            </div>
            <div>
              <span>PENDING GATE</span>
              <strong>{workflow.pendingGate || "NONE"}</strong>
            </div>
            <div>
              <span>AGENT RUNS</span>
              <strong>{workflow.agentRuns.length}</strong>
            </div>
          </div>

          {workflow.pendingGate && (
            <form className="gate-form" onSubmit={resumeWorkflow}>
              <div className="gate-title">
                <span>HUMAN GATE</span>
                <strong>{workflow.pendingGate}</strong>
              </div>
              {workflow.pendingGate === "AlignmentReview" ? (
                <div className="candidate-decisions">
                  {workflow.pendingItems.map((pending) => {
                    const desiredId = String(pending.desiredEntityId ?? "");
                    const candidates = Array.isArray(pending.candidates)
                      ? (pending.candidates as JsonObject[])
                      : [];
                    return (
                      <label key={desiredId}>
                        {desiredId}
                        <select
                          value={candidateSelections[desiredId] ?? ""}
                          onChange={(event) =>
                            setCandidateSelections((current) => ({
                              ...current,
                              [desiredId]: event.target.value,
                            }))
                          }
                        >
                          {candidates.map((candidate) => (
                            <option
                              key={String(candidate.candidateId)}
                              value={String(candidate.candidateId)}
                            >
                              {String(
                                candidate.currentEntityId ??
                                  candidate.alignmentType ??
                                  candidate.candidateId,
                              )}{" "}
                              · {String(candidate.confidence ?? "")}
                            </option>
                          ))}
                        </select>
                      </label>
                    );
                  })}
                </div>
              ) : (
                <label>
                  DECISION
                  <select
                    value={decision}
                    onChange={(event) => setDecision(event.target.value)}
                  >
                    {workflow.pendingGate === "RequirementReview" && (
                      <>
                        <option value="Confirm">Confirm</option>
                        <option value="NeedsRevision">Needs Revision</option>
                        <option value="Reject">Reject</option>
                      </>
                    )}
                    {workflow.pendingGate === "ArchitectureReview" && (
                      <>
                        <option value="Accept">Accept</option>
                        <option value="NeedsRevision">Needs Revision</option>
                        <option value="Reject">Reject</option>
                      </>
                    )}
                    {workflow.pendingGate === "ChangeApproval" && (
                      <option value="Approve">Approve</option>
                    )}
                  </select>
                </label>
              )}
              <label>
                RATIONALE
                <input
                  required
                  value={rationale}
                  onChange={(event) => setRationale(event.target.value)}
                />
              </label>
              {workflow.pendingGate === "ChangeApproval" && (
                <div className="execution-policy-form">
                  <label>
                    ALLOWED FILES
                    <textarea
                      value={allowedFiles}
                      onChange={(event) => setAllowedFiles(event.target.value)}
                    />
                  </label>
                  <label>
                    FORBIDDEN FILES
                    <textarea
                      value={forbiddenFiles}
                      onChange={(event) => setForbiddenFiles(event.target.value)}
                    />
                  </label>
                  <label>
                    REQUIRED TESTS
                    <textarea
                      value={requiredTests}
                      onChange={(event) => setRequiredTests(event.target.value)}
                    />
                  </label>
                  <label className="checkbox-control">
                    <input
                      type="checkbox"
                      checked={securityDataApproved}
                      onChange={(event) =>
                        setSecurityDataApproved(event.target.checked)
                      }
                    />
                    SECURITY / DATA APPROVED
                  </label>
                </div>
              )}
              <button disabled={loading}>
                {loading ? "RESUMING…" : "SUBMIT GATE & RESUME"}
              </button>
            </form>
          )}

          {workflow.status === "Failed" && (
            <form className="gate-form retry-form" onSubmit={retryWorkflow}>
              <div className="gate-title">
                <span>RECOVERY</span>
                <strong>RETRY {workflow.stage}</strong>
              </div>
              <label>
                RETRY RATIONALE
                <input
                  required
                  value={rationale}
                  onChange={(event) => setRationale(event.target.value)}
                />
              </label>
              <button disabled={loading || !rationale.trim()}>
                {loading ? "RETRYING…" : "RETRY FAILED STAGE"}
              </button>
            </form>
          )}

          <div className="workflow-workspace">
            <section className="panel">
              <div className="panel-heading">
                <div>
                  <span>WORKFLOW / TIMELINE</span>
                  <h2>Agent、Skill 与人工 Gate</h2>
                </div>
                <p>{workflow.workflowId}</p>
              </div>
              <div className="workflow-timeline">
                {workflow.steps
                  .slice()
                  .reverse()
                  .map((step) => (
                    <button
                      type="button"
                      key={`${step.sequence}-${step.stage}`}
                      onClick={() => setSelected(step)}
                    >
                      <span>{String(step.sequence).padStart(2, "0")}</span>
                      <strong>{step.stage}</strong>
                      <b>{step.status}</b>
                      <time>{new Date(step.timestamp).toLocaleString()}</time>
                    </button>
                  ))}
              </div>
            </section>
            <aside className="panel">
              <div className="panel-heading">
                <div>
                  <span>WORKFLOW / EVIDENCE</span>
                  <h2>状态与执行证据</h2>
                </div>
              </div>
              <JsonInspector value={selected ?? workflow} height={650} />
            </aside>
          </div>
        </>
      )}
    </section>
  );
}

function TraceGraph({ replay }: { replay: Replay }) {
  const host = useRef<HTMLDivElement>(null);
  const graph = useRef<Core | null>(null);
  useEffect(() => {
    if (!host.current) return;
    graph.current?.destroy();
    const resources = replay.resources;
    const entries = [
      resources.requirementIR,
      latest(resources.alignmentRuns),
      latest(resources.changePlans),
      latest(resources.agentRuns),
      latest(resources.reconciliationRuns),
      latest(resources.impactRuns),
    ];
    graph.current = cytoscape({
      container: host.current,
      elements: [
        ...stages.map(([label], index) => ({
          data: {
            id: `stage-${index}`,
            label,
            state: statusOf(entries[index]),
          },
        })),
        ...stages.slice(1).map((_, index) => ({
          data: {
            id: `edge-${index}`,
            source: `stage-${index}`,
            target: `stage-${index + 1}`,
          },
        })),
      ],
      style: [
        {
          selector: "node",
          style: {
            "background-color": "#27d3a2",
            color: "#e8f1ff",
            label: "data(label)",
            "font-family": "IBM Plex Mono, monospace",
            "font-size": 12,
            "text-valign": "bottom",
            "text-margin-y": 10,
            width: 46,
            height: 46,
            "border-width": 4,
            "border-color": "#102c3c",
          },
        },
        {
          selector: "edge",
          style: {
            width: 2,
            "line-color": "#29445b",
            "target-arrow-color": "#4f7392",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
          },
        },
      ],
      layout: { name: "grid", rows: 1, padding: 36 },
    });
    return () => graph.current?.destroy();
  }, [replay]);
  return <div className="trace-graph" ref={host} aria-label="Requirement trace graph" />;
}

function TraceWorkbench({
  token,
  requirementId,
  setRequirementId,
}: {
  token: string;
  requirementId: string;
  setRequirementId: (value: string) => void;
}) {
  const [replay, setReplay] = useState<Replay>();
  const [selected, setSelected] = useState<JsonObject>();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function load(event?: FormEvent) {
    event?.preventDefault();
    setLoading(true);
    setError("");
    try {
      const next = await requestJson<Replay>(
        `/api/audit/replay/requirements/${encodeURIComponent(requirementId)}`,
        token,
      );
      setReplay(next);
      setSelected(next.resources.requirementIR);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setLoading(false);
    }
  }

  const completion = useMemo(() => {
    if (!replay) return 0;
    const values = replay.resources;
    return [
      values.requirementIR,
      latest(values.alignmentRuns),
      latest(values.changePlans),
      latest(values.agentRuns),
      latest(values.reconciliationRuns),
      latest(values.impactRuns),
    ].filter(Boolean).length;
  }, [replay]);

  return (
    <>
      <form onSubmit={load} className="query-bar">
        <label>
          REQUIREMENT
          <input
            value={requirementId}
            onChange={(event) => setRequirementId(event.target.value)}
          />
        </label>
        <div className="query-hint">
          读取 Requirement IR、人工 Gate、Agent、对账和影响审计链。
        </div>
        <button disabled={loading}>{loading ? "LOADING…" : "LOAD TRACE"}</button>
      </form>

      {error && <div className="error">{error}</div>}
      {!replay && !error && (
        <section className="empty">
          <span>TRACE</span>
          <h2>输入 Requirement ID，装载完整决策链。</h2>
          <p>该视图展示流程证据；实体和关系请进入 Graph Explorer。</p>
        </section>
      )}

      {replay && (
        <>
          <section className="metrics">
            <article>
              <span>PIPELINE</span>
              <strong>{completion}/6</strong>
              <small>materialized stages</small>
            </article>
            <article>
              <span>AUDIT CHAIN</span>
              <strong
                className={replay.auditChain.status === "Verified" ? "ok" : "bad"}
              >
                {replay.auditChain.status}
              </strong>
              <small>{replay.auditChain.eventCount} linked events</small>
            </article>
            <article>
              <span>ARTIFACTS</span>
              <strong>{replay.resources.artifacts.length}</strong>
              <small>content-addressed records</small>
            </article>
            <article>
              <span>REPLAY HASH</span>
              <strong className="hash">{replay.replayHash.slice(7, 19)}</strong>
              <small>{replay.designRevisionId}</small>
            </article>
          </section>

          <section className="panel graph-panel">
            <div className="panel-heading">
              <div>
                <span>TRACE / DECISION LINEAGE</span>
                <h2>Requirement lifecycle</h2>
              </div>
              <p>{replay.requirementId}</p>
            </div>
            <TraceGraph replay={replay} />
          </section>

          <section className="split">
            <div className="panel">
              <div className="panel-heading">
                <div>
                  <span>ARTIFACTS / STAGES</span>
                  <h2>Stage ledger</h2>
                </div>
              </div>
              <div className="ledger">
                {stages.map(([label, key]) => {
                  const value = replay.resources[key];
                  const item = Array.isArray(value) ? latest(value) : value;
                  return (
                    <button
                      type="button"
                      key={key}
                      className={selected === item ? "active" : ""}
                      onClick={() => setSelected(item)}
                    >
                      <span>{label}</span>
                      <b>{statusOf(item)}</b>
                    </button>
                  );
                })}
              </div>
            </div>
            <div className="panel evidence">
              <div className="panel-heading">
                <div>
                  <span>EVIDENCE / IMMUTABLE</span>
                  <h2>Artifact payload</h2>
                </div>
              </div>
              <JsonInspector value={selected} height={390} />
            </div>
          </section>

          <section className="panel">
            <div className="panel-heading">
              <div>
                <span>AUDIT / HUMAN + MACHINE</span>
                <h2>Decision events</h2>
              </div>
              <p>{replay.events.length} events</p>
            </div>
            <div className="events">
              {replay.events
                .slice()
                .reverse()
                .slice(0, 20)
                .map((event) => (
                  <button
                    type="button"
                    key={event.eventId}
                    onClick={() => setSelected(event.payload)}
                  >
                    <time>{new Date(event.timestamp).toLocaleString()}</time>
                    <strong>{event.eventType}</strong>
                    <span>{event.actor || "system"}</span>
                  </button>
                ))}
            </div>
          </section>
        </>
      )}
    </>
  );
}

function App() {
  const [view, setView] = useState<WorkbenchView>("lifecycle");
  const [requirementId, setRequirementId] = useState("REQ-SDN-2026-001");
  const [token, setToken] = useState("");

  return (
    <main>
      <header>
        <div>
          <p className="eyebrow">CODE ONTOLOGY / INTELLIGENCE PLATFORM</p>
          <h1>Ontology Workbench</h1>
          <p className="subtitle">
            代码事实、业务语义、变更设计、实际实现与波及路径统一浏览。
          </p>
        </div>
        <div className="header-controls">
          <label className="token-control">
            API TOKEN
            <input
              value={token}
              type="password"
              placeholder="optional"
              onChange={(event) => setToken(event.target.value)}
            />
          </label>
          <div className="system-state">
            <span className="pulse" /> PLATFORM ONLINE
          </div>
        </div>
      </header>

      <nav className="view-tabs" aria-label="Workbench views">
        <button
          type="button"
          className={view === "lifecycle" ? "active" : ""}
          onClick={() => setView("lifecycle")}
        >
          ONTOLOGY FLOW
          <small>本体 · 生成 · Git 门禁 · 发布</small>
        </button>
        <button
          type="button"
          className={view === "workflow" ? "active" : ""}
          onClick={() => setView("workflow")}
        >
          WORKFLOW CONTROL
          <small>多 Agent · 人工 Gate · 自动恢复</small>
        </button>
        <button
          type="button"
          className={view === "compare" ? "active" : ""}
          onClick={() => setView("compare")}
        >
          GRAPH COMPARE
          <small>左右对照 · 差异叠加 · 属性变更</small>
        </button>
        <button
          type="button"
          className={view === "graphs" ? "active" : ""}
          onClick={() => setView("graphs")}
        >
          GRAPH EXPLORER
          <small>代码 · 业务 · 变更 · 波及</small>
        </button>
        <button
          type="button"
          className={view === "trace" ? "active" : ""}
          onClick={() => setView("trace")}
        >
          REQUIREMENT TRACE
          <small>决策 · Gate · Agent · 审计</small>
        </button>
      </nav>

      {view === "lifecycle" && <LifecycleWorkbench token={token} onNavigate={setView} />}
      {view === "graphs" && <GraphExplorer token={token} />}
      {view === "compare" && <GraphCompare token={token} />}
      {view === "workflow" && <WorkflowControl token={token} />}
      {view === "trace" && (
        <TraceWorkbench
          token={token}
          requirementId={requirementId}
          setRequirementId={setRequirementId}
        />
      )}
    </main>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
