import React, { useEffect, useMemo, useState } from "react";
import "./metamodel.css";

export type ModelBinding = { id: string; version: string; contentHash: string };
export type MetaRepository = { repositoryId: string; name: string };
export type MetaTerm = { iri: string; name: string; kind: string; label: string; description: string; parents: string[]; layers: string[]; sources: string[] };
export type MetaCatalog = { binding: ModelBinding; terms: MetaTerm[]; files: { path: string; kind: string; tripleCount: number; contentHash: string }[]; examples: string[]; queries: string[] };
type Definition = Record<string, unknown[]>;
type Constraint = { iri: string; targetClass: string; inherited: boolean; sources: string[]; properties: { id: string; definition: Definition }[]; rules: Definition };
type Detail = MetaTerm & { ancestors: MetaTerm[]; children: MetaTerm[]; constraints: Constraint[]; relations: (MetaTerm & { role: string })[]; definition: Definition; usage: { source: string; entityId: string; relation: string; scope: string }[] };
type Validation = { conforms: boolean; issueCount: number; issues: { entityId: string; path: string; message: string }[] };
type DevelopmentGeneration = { applied: boolean; adapter: string; specification: string; inputHash: string; artifactCount: number; artifacts: { targetPath: string; contentHash: string; status: string; source: string }[] };
const layerNames: Record<string, string> = { CodeStructure: "代码结构", DependencyAndData: "依赖与数据", ContractAndEntry: "契约与入口", Verification: "验证", BusinessSemantics: "业务语义", DeliveryAndRuntime: "交付运行", ChangeAndImpact: "变化与影响" };
const queryNames = ["定义与约束目录", "业务意图到代码产物", "未完成的工程义务", "验证证据与满足性", "元模型与项目引用", "契约变化影响候选"];

export async function metaRequest<T>(url: string, token: string, body?: unknown): Promise<T> {
  const response = await fetch(url, { method: body === undefined ? "GET" : "POST", headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(body === undefined ? {} : { "Content-Type": "application/json" }) }, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error?.message ?? `请求失败 ${response.status}`);
  return data as T;
}
const short = (value: string) => value.split(/[\/#]/).at(-1) ?? value;
const valueText = (value: unknown): string => typeof value === "string" ? value : typeof value === "object" && value !== null && "value" in value ? String(value.value) : JSON.stringify(value);

export function MetamodelCenter({ catalog, token, onUse, initialIri, repositories = [], workspace = "governance" }: { workspace?: "governance" | "development"; catalog: MetaCatalog; token: string; onUse: () => void; initialIri?: string; repositories?: MetaRepository[] }) {
  const [tab, setTab] = useState(workspace === "development" ? "examples" : "definitions");
  const [search, setSearch] = useState("");
  const [kind, setKind] = useState("Class");
  const [layer, setLayer] = useState("");
  const [namespace, setNamespace] = useState("dev");
  const [iri, setIri] = useState(initialIri ?? "https://example.org/code-ontology/development#Requirement");
  const [detail, setDetail] = useState<Detail>();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [example, setExample] = useState(catalog.examples[0]);
  const [turtle, setTurtle] = useState("");
  const [validation, setValidation] = useState<Validation>();
  const [query, setQuery] = useState(catalog.queries[1]);
  const [results, setResults] = useState<{ columns: string[]; rows: Record<string, string>[] }>();
  const [developmentGeneration, setDevelopmentGeneration] = useState<DevelopmentGeneration>();
  const [generationRepository, setGenerationRepository] = useState("");
  const [allowIllustrative, setAllowIllustrative] = useState(false);
  const [overwriteGeneration, setOverwriteGeneration] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    setDetail(undefined); setError(""); setLoading(true);
    metaRequest<Detail>(`/api/metamodel/term?iri=${encodeURIComponent(iri)}&revision=${catalog.binding.contentHash}`, token)
      .then(value => { if (active) setDetail(value); }).catch(e => { if (active) setError(String(e.message)); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [iri, catalog.binding.contentHash, token]);
  useEffect(() => {
    let active = true;
    if (workspace !== "development") return;
    setTurtle(""); setValidation(undefined); setResults(undefined); setDevelopmentGeneration(undefined);
    metaRequest<{ turtle: string }>(`/api/metamodel/example?name=${encodeURIComponent(example)}&revision=${catalog.binding.contentHash}`, token)
      .then(value => { if (active) setTurtle(value.turtle); }).catch(e => { if (active) setError(e.message); });
    return () => { active = false; };
  }, [example, token, catalog.binding.contentHash, workspace]);
  const terms = useMemo(() => catalog.terms.filter(t => (!kind || t.kind === kind) && (!namespace || t.name.startsWith(namespace + ":")) && (!layer || t.layers.includes(layer)) && `${t.name} ${t.label} ${t.description}`.toLowerCase().includes(search.toLowerCase())), [catalog, search, kind, namespace, layer]);
  function selectTerm(value: string) { setIri(value); setTab("definitions"); }
  async function run(mode: "validate" | "query" | "generate" | "apply") {
    setBusy(true); setError("");
    try {
      if (mode === "validate") setValidation(await metaRequest<Validation>("/api/metamodel/validate", token, { turtle, revision: catalog.binding.contentHash }));
      else if (mode === "query") setResults(await metaRequest("/api/metamodel/query", token, { query, example, revision: catalog.binding.contentHash }));
      else {
        const applying = mode === "apply";
        if (applying && !generationRepository) throw new Error("应用生成前请选择目标仓库");
        setDevelopmentGeneration(await metaRequest<DevelopmentGeneration>(`/api/development-code-generation/${applying ? "apply" : "preview"}`, token, { turtle, revision: catalog.binding.contentHash, ...(applying ? { repositoryId: generationRepository, allowIllustrative, overwrite: overwriteGeneration } : {}) }));
      }
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }
  return <div className="metamodel-center">
    <section className="meta-hero"><div><span className="eyebrow">METAMODEL / SEMANTIC FOUNDATION</span><h2>{workspace === "governance" ? "元模型 · 平台语义核心" : "示例模型与生成实验"}</h2><p>{workspace === "governance" ? "统一定义类型、关系、约束与版本，为所有业务项目提供建模依据。这里不执行具体业务代码。" : "引用已安装元模型，在业务实例上校验、查询和预览生成。示例不是生产业务模型。"}</p></div><div className="meta-version"><span>仓库安装版本</span><strong>{catalog.binding.version}</strong><code>{catalog.binding.contentHash.slice(0, 16)}</code><button type="button" onClick={onUse}>{workspace === "governance" ? "进入业务项目绑定 →" : "关联到当前项目模型 →"}</button></div></section>
    <div className="meta-counts"><span><b>{catalog.terms.filter(t => t.kind === "Class").length}</b> 类定义</span><span><b>{catalog.terms.filter(t => t.kind === "ObjectProperty").length}</b> 对象关系</span><span><b>{catalog.terms.filter(t => t.kind === "DatatypeProperty").length}</b> 数据属性</span><span><b>{catalog.files.length}</b> 定义与约束文件</span></div>
    <nav className="meta-tabs" aria-label="元模型视图">{(workspace === "governance" ? [["definitions", "定义与关系"], ["sources", "版本与来源"]] : [["examples", "实例与校验"]]).map(([id, title]) => <button type="button" key={id} className={tab === id ? "active" : ""} onClick={() => setTab(id)}>{title}</button>)}</nav>
    {error && <p role="alert" className="error">{error}</p>}
    {tab === "definitions" && <div className="meta-browser">
      <aside className="meta-catalog"><label>搜索定义<input placeholder="需求、契约、Requirement…" value={search} onChange={e => setSearch(e.target.value)} /></label><div className="meta-filters"><label>定义类型<select value={kind} onChange={e => setKind(e.target.value)}><option value="">全部</option><option value="Class">类</option><option value="ObjectProperty">对象关系</option><option value="DatatypeProperty">数据属性</option></select></label><label>定义包<select value={namespace} onChange={e => setNamespace(e.target.value)}><option value="">全部定义包</option>{["dev", "eng", "biz", "code", "plan"].map(n => <option key={n} value={n}>{n}</option>)}</select></label></div><label>语义层<select value={layer} onChange={e => setLayer(e.target.value)}><option value="">全部语义层</option>{Object.entries(layerNames).map(([id, text]) => <option key={id} value={id}>{text}</option>)}</select></label><p className="meta-muted">{terms.length} 项匹配 · 完整标识区分同名概念</p><div className="meta-term-list" role="list" aria-label="元模型定义列表">{terms.map(t => <button type="button" role="listitem" key={t.iri} className={iri === t.iri ? "active" : ""} onClick={() => selectTerm(t.iri)}><strong>{t.label}</strong><code>{t.name}</code></button>)}{!terms.length && <p>没有匹配的定义，请调整筛选条件。</p>}</div></aside>
      <section className="meta-detail" aria-label="定义详情">{loading && <p role="status">正在读取定义与继承约束…</p>}{detail && <>
        <div className="meta-detail-heading"><span>{detail.kind}</span><h3>{detail.label}</h3><code>{detail.iri}</code><p>{detail.description || "该定义尚未提供说明。"}</p></div>
        <div className="meta-section"><h4>定义来源</h4>{detail.sources.map(s => <p key={s}><code>{s}</code></p>)}</div>
        <div className="meta-section"><h4>继承与扩展</h4><p className="meta-muted">上位类型 → 当前定义 → 直接子类</p><div className="meta-lineage">{detail.ancestors.map(t => <button type="button" key={t.iri} onClick={() => selectTerm(t.iri)}>{t.name}</button>)}<strong>{detail.name}</strong>{detail.children.map(t => <button type="button" key={t.iri} onClick={() => selectTerm(t.iri)}>{t.name}</button>)}</div></div>
        <div className="meta-section"><h4>生效约束 <span>{detail.constraints.length}</span></h4>{!detail.constraints.length && <p className="meta-muted">没有针对该定义的类约束，属性定义见下方。</p>}{detail.constraints.map(c => <details key={`${c.iri}-${c.targetClass}`} className="meta-constraint"><summary>{short(c.iri)} <small>{c.inherited ? `继承自 ${short(c.targetClass)}` : "直接约束"}</small></summary><p className="meta-muted">{c.sources.join(" · ")}</p>{c.properties.map(p => <div key={p.id} className="meta-property"><strong>{(p.definition["sh:path"] ?? []).map(valueText).join(" ")}</strong>{Object.entries(p.definition).filter(([key]) => key !== "sh:path").map(([key, vals]) => <p key={key}><span>{key}</span> {vals.map(valueText).join(" · ")}</p>)}</div>)}<details><summary>完整约束表达</summary><pre>{JSON.stringify(c.rules, null, 2)}</pre></details></details>)}</div>
        <div className="meta-section"><h4>关联属性与关系 <span>{detail.relations.length}</span></h4><div className="meta-relation-list">{detail.relations.map(r => <button type="button" key={`${r.iri}-${r.role}`} onClick={() => selectTerm(r.iri)}><span>{r.role === "domain" ? "作为起点" : "作为终点"}</span><strong>{r.label}</strong><code>{r.name}</code></button>)}</div><details><summary>OWL / RDFS 定义明细</summary><pre>{JSON.stringify(detail.definition, null, 2)}</pre></details></div>
        <div className="meta-section"><h4>实例引用 <span>{detail.usage.length}</span></h4><p className="meta-muted">范围：包内示例与目标模型，非生产实例全量索引。</p>{detail.usage.map((u, i) => <article className="meta-usage" key={i}><code>{u.entityId}</code><span>{u.relation}</span><small>{u.source}</small></article>)}</div>
      </>}</section>
    </div>}
    {tab === "examples" && <div className="meta-examples"><section><label>示例模型<select value={example} onChange={e => setExample(e.target.value)} disabled={busy}>{catalog.examples.map(e => <option key={e}>{e}</option>)}</select></label><p className="meta-muted">演示实例与待开发目标模型不代表功能已经实现。修改下方副本可检验约束。</p><textarea aria-label="Turtle 模型副本" spellCheck={false} value={turtle} onChange={e => { setTurtle(e.target.value); setValidation(undefined); setDevelopmentGeneration(undefined); }} /><div className="button-row"><button type="button" disabled={busy || !turtle} onClick={() => run("validate")}>{busy ? "处理中…" : "校验模型约束"}</button><button type="button" className="secondary" disabled={busy || !turtle} onClick={() => run("generate")}>预览生成规范</button></div><div className="meta-generation-controls"><label>应用目标仓库<select aria-label="应用目标仓库" value={generationRepository} onChange={e => setGenerationRepository(e.target.value)} disabled={busy}><option value="">仅预览，不写入</option>{repositories.map(r => <option key={r.repositoryId} value={r.repositoryId}>{r.name} · {r.repositoryId}</option>)}</select></label><label className="meta-check"><input type="checkbox" checked={allowIllustrative} onChange={e => setAllowIllustrative(e.target.checked)} />明确允许示例 Illustrative 写入</label><label className="meta-check"><input type="checkbox" checked={overwriteGeneration} onChange={e => setOverwriteGeneration(e.target.checked)} />允许覆盖目标文件</label><button type="button" className="danger-action" disabled={busy || !turtle || !generationRepository || !allowIllustrative} onClick={() => run("apply")}>应用生成规范</button></div>{validation && <div role="status" className={`meta-verdict ${validation.conforms ? "valid" : "invalid"}`}><strong>{validation.conforms ? "模型符合约束" : `${validation.issueCount} 个约束问题`}</strong><p>符合约束仅表示模型结构有效，不表示需求已完成。</p>{validation.issues.map((i, index) => <article key={index}><code>{i.entityId}</code><p>{i.message}</p></article>)}</div>}{developmentGeneration && <div role="status" className="meta-verdict valid"><strong>{developmentGeneration.applied ? "已应用 TransformationRule" : "已按 TransformationRule 生成预览"}</strong><p>{developmentGeneration.adapter} · {short(developmentGeneration.specification)} · {developmentGeneration.inputHash.slice(0, 16)}</p>{developmentGeneration.artifacts.map(a => <details key={a.targetPath} open><summary>{a.status} · {a.targetPath}</summary><pre>{a.source}</pre></details>)}<p className="meta-muted">应用结果会写入选择的登记仓库；Illustrative 示例只有在明确勾选后才允许写入。</p></div>}</section><section><label>能力查询<select value={query} onChange={e => setQuery(e.target.value)}>{catalog.queries.map((q, i) => <option key={q} value={q}>{queryNames[i] ?? q}</option>)}</select></label><p className="meta-muted">查询包内原始示例；上方编辑副本仅用于校验，不影响查询数据。</p><button type="button" disabled={busy} onClick={() => run("query")}>运行能力查询</button>{results && <div className="meta-query-results"><p role="status">返回 {results.rows.length} 行（最多 500 行）</p><div className="meta-table-scroll"><table><thead><tr>{results.columns.map(c => <th key={c}>{c}</th>)}</tr></thead><tbody>{results.rows.map((r, i) => <tr key={i}>{results.columns.map(c => <td key={c} title={r[c]}>{r[c] ? short(r[c]) : "—"}</td>)}</tr>)}</tbody></table></div></div>}</section></div>}
    {tab === "sources" && <section className="meta-sources"><h3>安装定义与版本依据</h3><p>当前安装 1 个仓库版本。每个项目模型绑定包标识、版本和所有定义文件的内容摘要；文件变化后必须重新复核绑定。</p><code>{catalog.binding.id}</code><p><code>{catalog.binding.contentHash}</code></p>{catalog.files.map(f => <article key={f.path}><strong>{f.path}</strong><span>{f.tripleCount} triples</span><code>{f.contentHash.slice(0, 20)}</code></article>)}<p className="meta-muted">在“定义修订”中建立草稿并运行正反例检查；通过后仍需仓库审查安装，草稿不会自动发布到业务项目。</p></section>}
  </div>;
}

// Basic literal fields derive from SHACL. Object references remain explicit graph edges.
export function MetamodelFields({ type, catalog, token, values, onChange, onDatatypes }: { type: string; catalog: MetaCatalog; token: string; values: Record<string, string>; onChange: (values: Record<string, string>) => void; onDatatypes: (values: Record<string, string>) => void }) {
  const [detail, setDetail] = useState<Detail>();
  const [error, setError] = useState("");
  useEffect(() => { let active = true; setDetail(undefined); setError("");
    metaRequest<Detail>(`/api/metamodel/term?iri=${encodeURIComponent(type)}&revision=${catalog.binding.contentHash}`, token).then(d => { if (active) setDetail(d); }).catch(e => { if (active) setError(e.message); });
    return () => { active = false; };
  }, [type, catalog.binding.contentHash, token]);
  useEffect(() => {
    const datatypes: Record<string, string> = {};
    for (const c of detail?.constraints ?? []) for (const p of c.properties) {
      const path = p.definition["sh:path"]?.[0], datatype = p.definition["sh:datatype"]?.[0];
      if (typeof path === "string" && typeof datatype === "string") datatypes[path] = datatype;
    }
    onDatatypes(datatypes);
  }, [detail, onDatatypes]);
  const fields = new Map<string, { label: string; required: boolean }>();
  for (const c of detail?.constraints ?? []) for (const p of c.properties) {
    const path = p.definition["sh:path"]?.[0];
    const term = catalog.terms.find(t => t.iri === path && t.kind === "DatatypeProperty");
    if (term) fields.set(term.iri, { label: term.label, required: fields.get(term.iri)?.required || Number(valueText(p.definition["sh:minCount"]?.[0] ?? "0")) > 0 });
  }
  return <div className="meta-dynamic-fields">{error && <p role="alert">{error}</p>}{fields.size > 0 && <p className="meta-muted">属性与数据类型来自 SHACL；多值用换行分隔，日期等按 XSD 格式填写。复杂约束可在模型 JSON 中编辑，最终以后端校验为准。</p>}{[...fields].map(([iri, f]) => <label key={iri}>{f.label}{f.required ? " *" : ""}<textarea aria-label={`属性 ${f.label}`} required={f.required} value={values[iri] ?? ""} onChange={e => onChange({ ...values, [iri]: e.target.value })} /></label>)}</div>;
}
