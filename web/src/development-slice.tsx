import React, { useEffect, useState } from "react";
import { useLeaveGuard } from "./navigation-guard";
import { metaRequest } from "./metamodel";

type Model = { modelId: string; name: string; defaultPriority: string; modelHash: string; turtle?: string; createdAt: string };
type RunSummary = { runId: string; status: string; startedAt: string };
type Run = RunSummary & { currentStatus: string; directory: string; modelHash: string; snapshotHash: string; reportHash: string;
  source: string; turtle: string; changedFiles: string[]; bindingCurrent: boolean;
  report: { cases: { name: string; passed: boolean; error?: string }[]; passed: boolean; error?: string };
  assessments: { target: string; status: string }[]; validation: { conforms: boolean; issues: unknown[] } };

export function DevelopmentSlicePanel({ token }: { token: string }) {
  const [models, setModels] = useState<Model[]>([]);
  const [model, setModel] = useState<Model>();
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [run, setRun] = useState<Run>();
  const [name, setName] = useState("任务优先级输入");
  const [priority, setPriority] = useState("medium");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useLeaveGuard({ label: "业务示例操作", dirty: false, busy });
  useEffect(() => { let active = true;
    metaRequest<{ models: Model[] }>("/api/development-slices/models", token).then(r => { if (active) setModels(r.models); }).catch(e => { if (active) setError(e.message); });
    return () => { active = false; };
  }, [token]);
  async function act(action: "save" | "load" | "execute" | "run", id?: string) {
    setError(""); setBusy(true);
    try {
      if (action === "save") {
        const saved = await metaRequest<Model>("/api/development-slices/models",token,{ name, defaultPriority: priority });
        setModel(saved); setRun(undefined); setRuns([]);
        setModels((await metaRequest<{models: Model[]}>("/api/development-slices/models",token)).models);
      } else if (action === "load") {
        const saved = await metaRequest<Model>(`/api/development-slices/model?modelId=${encodeURIComponent(id ?? "")}`,token);
        setModel(saved); setRun(undefined); setName(saved.name); setPriority(saved.defaultPriority);
        setRuns((await metaRequest<{runs: RunSummary[]}>(`/api/development-slices/runs?modelId=${saved.modelId}`,token)).runs);
      } else if (action === "execute" && model) {
        setRun(await metaRequest<Run>("/api/development-slices/execute",token,{modelId:model.modelId}));
        setRuns((await metaRequest<{runs: RunSummary[]}>(`/api/development-slices/runs?modelId=${model.modelId}`,token)).runs);
      } else if (action === "run") setRun(await metaRequest<Run>(`/api/development-slices/run?runId=${encodeURIComponent(id ?? "")}`,token));
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }
  const edited = model && (name !== model.name || priority !== model.defaultPriority);
  return <section className="meta-authoring">
    <h3>任务优先级：从模型到真实验收</h3>
    <p>范围：创建任务时使用默认优先级，保留 low / medium / high，拒绝非法输入。每次执行在新的独立目录生成代码并运行 8 项验收；此处的就绪判断只覆盖任务输入，不包含调度或部署。</p>
    {error && <p role="alert" className="error">{error}</p>}
    <fieldset disabled={busy}>
      <label>已保存项目模型<select aria-label="已保存项目模型" value={model?.modelId ?? ""} onChange={e=>act("load",e.target.value)}><option value="" disabled>选择模型版本</option>{models.map(m=><option key={m.modelId} value={m.modelId}>{m.name} · {m.createdAt}</option>)}</select></label>
      <label>切片名称<input value={name} onChange={e=>setName(e.target.value)} /></label>
      <label>默认优先级<select value={priority} onChange={e=>setPriority(e.target.value)}>{["low","medium","high"].map(v=><option key={v}>{v}</option>)}</select></label>
      <button type="button" onClick={()=>act("save")}>保存项目模型版本</button>
      {model && <><p>已保存模型：{model.name} · 默认值 {model.defaultPriority} · {model.modelHash.slice(0,16)}</p>
        {edited && <p>表单有修改，请先保存新版本后执行。</p>}
        <details><summary>项目本体 Turtle</summary><pre>{model.turtle}</pre></details>
        <button type="button" disabled={Boolean(edited)} onClick={()=>act("execute")}>批准并执行：生成代码 → 运行验收 → 回写证据</button>
      </>}
      {runs.length>0 && <label>执行历史<select aria-label="执行历史" value={run?.runId ?? ""} onChange={e=>act("run",e.target.value)}><option value="" disabled>选择记录并复核快照</option>{runs.map(r=><option key={r.runId} value={r.runId}>{r.startedAt} · 执行时 {r.status}</option>)}</select></label>}
    </fieldset>
    {busy && <p role="status">正在处理，执行完成后将保存报告与证据…</p>}
    {run && <section className={`meta-verdict ${run.currentStatus === "Ready" ? "valid" : "invalid"}`}>
      <h4>当前验收：{run.currentStatus === "Ready" ? "切片就绪" : run.currentStatus === "Stale" ? "快照或元模型已变化，旧结论失效" : "未通过"}</h4>
      <p>产物目录：{run.directory}</p><p>代码快照：{run.snapshotHash}</p><p>报告摘要：{run.reportHash}</p>
      <button type="button" disabled={busy} onClick={()=>act("run",run.runId)}>重新检查文件与证据摘要</button>
      {run.changedFiles.length>0 && <p>变化文件：{run.changedFiles.join("、")}</p>}
      <p>以下为执行时记录；当前状态以摘要复核结果为准。</p>
      {run.report.cases.map(c=><p key={c.name}>{c.passed ? "通过" : "失败"} · {c.name} {c.error}</p>)}
      {run.report.error && <p>{run.report.error}</p>}
      <details><summary>验收判断与义务依据</summary>{run.assessments.map(a=><p key={a.target}>{a.target.split(":").at(-1)} · {a.status}</p>)}<p>证据图约束校验：{run.validation.conforms ? "通过" : "失败"}</p><pre>{JSON.stringify(run.validation.issues,null,2)}</pre></details>
      <details><summary>生成的 Task 源码</summary><pre>{run.source}</pre></details>
      <details><summary>真实执行、证据与判断本体</summary><pre>{run.turtle}</pre></details>
    </section>}
  </section>;
}
