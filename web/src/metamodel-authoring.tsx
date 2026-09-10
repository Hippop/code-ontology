import React, { useEffect, useRef, useState } from "react";
import { useLeaveGuard } from "./navigation-guard";
import { metaRequest, ModelBinding } from "./metamodel";

type Draft = { draftId: string; revision: number; name: string; baseBinding: ModelBinding; ontology: string; shapes: string; savedAt?: string };
type Check = { conforms: boolean; stage: string; report: string; examples: { source: string; conforms: boolean; report: string }[]; negativeExamples?: { name: string; expectedRule: string; passed: boolean }[]; issues?: { entityId: string; message: string }[] };

export function MetamodelAuthoring({ token }: { token: string }) {
  const [draft, setDraft] = useState<Draft>();
  const [list, setList] = useState<Draft[]>([]);
  const [history, setHistory] = useState<Draft[]>([]);
  const [check, setCheck] = useState<Check>();
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [section, setSection] = useState<"ontology" | "shapes">("ontology");

  const savedDraft = useRef<Draft | undefined>(undefined);
  async function saveDraft() {
    if (!draft) throw new Error("草稿尚未加载");
    setBusy(true);
    try {
      const saved = await metaRequest<Draft>("/api/metamodel/drafts", token, draft);
      savedDraft.current = saved; setDraft(saved); setDirty(false);
    } finally { setBusy(false); }
  }
  useLeaveGuard({ label: "元模型定义草稿", dirty, busy, save: saveDraft,
    discard: () => { setDraft(savedDraft.current); setDirty(false); setCheck(undefined); } });

  async function refresh() {
    const result = await metaRequest<{ drafts: Draft[] }>("/api/metamodel/drafts", token);
    setList(result.drafts);
  }
  useEffect(() => { let active = true;
    Promise.all([metaRequest<Draft>("/api/metamodel/drafts/template", token), metaRequest<{ drafts: Draft[] }>("/api/metamodel/drafts", token)])
      .then(([template, saved]) => { if (active) { savedDraft.current = template; setDraft(template); setList(saved.drafts); } })
      .catch(e => { if (active) setError(e.message); });
    return () => { active = false; };
  }, [token]);
  useEffect(() => {
    const prevent = (e: BeforeUnloadEvent) => { if (dirty) { e.preventDefault(); e.returnValue = ""; } };
    window.addEventListener("beforeunload", prevent);
    return () => window.removeEventListener("beforeunload", prevent);
  }, [dirty]);
  async function run(action: "save" | "check" | "new" | "load", id?: string) {
    if (!draft) return;
    setBusy(true); setError(""); setNotice("");
    try {
      if (action === "save") {
        const saved = await metaRequest<Draft>("/api/metamodel/drafts", token, draft);
        savedDraft.current = saved; setDraft(saved); setDirty(false); await refresh();
        const result = await metaRequest<{ revisions: Draft[] }>(`/api/metamodel/drafts/history?draftId=${encodeURIComponent(saved.draftId)}`, token);
        setHistory(result.revisions); setNotice(`已保存修订 ${saved.revision}，保留历史版本。`);
      } else if (action === "check") setCheck(await metaRequest<Check>("/api/metamodel/drafts/check", token, draft));
      else {
        if (dirty && !window.confirm("当前有未保存修改，是否放弃这些修改并加载？")) return;
        if (action === "new") { const template = await metaRequest<Draft>("/api/metamodel/drafts/template", token); savedDraft.current = template; setDraft(template); setHistory([]); }
        else {
          const result = await metaRequest<{ revisions: Draft[] }>(`/api/metamodel/drafts/history?draftId=${encodeURIComponent(id ?? "")}`, token);
          setHistory(result.revisions); savedDraft.current = result.revisions[0]; setDraft(result.revisions[0]);
        }
        setCheck(undefined); setDirty(false);
      }
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }
  function update(patch: Partial<Draft>) { if (draft) { setDraft({ ...draft, ...patch }); setDirty(true); setCheck(undefined); setNotice(""); } }
  function download() {
    if (!draft) return;
    const url = URL.createObjectURL(new Blob([draft[section]], { type: "text/turtle;charset=utf-8" }));
    const link = document.createElement("a"); link.href = url; link.download = `${section}-draft-r${draft.revision}.ttl`; link.click(); URL.revokeObjectURL(url);
  }
  return <section className="meta-authoring">
    <h3>建立和修订元模型</h3>
    <p>编辑开发元模型的类、关系及约束。草稿保存在服务端，可重新加载历史修订。检查包括定义引用、SHACL、两个正例及关键反例，不等于发布审批。</p>
    <p className="meta-muted">草稿基于当前安装版本；保存后仍需审查并将导出的文件纳入仓库，才会影响项目绑定。</p>
    {error && <p role="alert" className="error">{error}</p>}{notice && <p role="status">{notice}</p>}
    <fieldset disabled={busy}>
      <label>已保存的草稿<select aria-label="已保存的草稿" value={draft?.draftId ?? ""} onChange={e => run("load", e.target.value)}><option value="" disabled>选择草稿</option>{list.map(d => <option key={d.draftId} value={d.draftId}>{d.name} · 修订 {d.revision}</option>)}</select></label>
      <button type="button" onClick={() => run("new")}>从安装版本新建</button>
      {draft && <><label>草稿名称<input value={draft.name} onChange={e => update({ name: e.target.value })} /></label>
        <p>基础版本 {draft.baseBinding.version} · 草稿修订 {draft.revision} · {dirty ? "有未保存修改" : "已加载"}</p>
        <div className="button-row"><button type="button" onClick={() => setSection("ontology")}>类与关系定义</button><button type="button" onClick={() => setSection("shapes")}>SHACL 约束定义</button></div>
        <textarea aria-label={section === "ontology" ? "元模型定义草稿" : "元模型约束草稿"} spellCheck={false} value={draft[section]} onChange={e => update({ [section]: e.target.value })} />
        <div className="button-row"><button type="button" onClick={() => run("save")}>保存草稿修订</button><button type="button" onClick={() => run("check")}>校验定义与示例</button><button type="button" onClick={download}>导出当前 Turtle</button></div>
      </>}
    </fieldset>
    {busy && <p role="status">正在处理草稿…</p>}
    {check && <section role="status" className={`meta-verdict ${check.conforms ? "valid" : "invalid"}`}><strong>{check.conforms ? "草稿检查通过（尚未发布）" : "候选元模型存在问题"}</strong><p>{check.report}</p>{check.issues?.map((i, n) => <p key={n}>{i.entityId} · {i.message}</p>)}{check.examples.map(e => <details key={e.source}><summary>{e.conforms ? "通过" : "失败"} · {e.source}</summary><pre>{e.report}</pre></details>)}{check.negativeExamples?.map(e => <p key={e.name}>{e.passed ? "正确拦截" : "反例未被预期规则拦截"} · {e.name} · {e.expectedRule}</p>)}</section>}
    {history.length > 0 && <details><summary>修订历史（{history.length}）</summary>{history.map(d => <details key={d.revision}><summary>修订 {d.revision} · {d.savedAt}</summary><pre>{d.ontology}</pre><pre>{d.shapes}</pre></details>)}</details>}
  </section>;
}
