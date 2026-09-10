import React, { useEffect, useState } from "react";
import { useLeaveGuard } from "./navigation-guard";
import { metaRequest } from "./metamodel";
import "./platform-development.css";

type Requirement = { id: string; iri: string; label: string; statement: string; source: string; test: string; scope: string };
type Summary = { modelId: string; title: string; createdAt: string; modelHash: string; parentModelId?: string };
type Model = Summary & { binding: { version: string; contentHash: string }; baseline: { hash: string }; requirements: Requirement[]; turtle: string; validation: { conforms: boolean } };
type Preview = { approvalHash: string; files: Record<string,string> };
type Approval = { approvalId: string; approvalHash: string; reason: string; createdAt: string };
type RunSummary = { runId: string; createdAt: string; status: string };
type Run = RunSummary & { currentStatus: string; directory: string; baselineCurrent: boolean; bindingCurrent: boolean; changedFiles: string[]; turtle: string;
  validation: { conforms: boolean; issues: unknown[] }; report: { passed: boolean; error?: string; cases: { id: string; passed: boolean; tests: number; skipped: number; log?: string; error?: string }[] } };
const API = "/api/platform-development/";

export function PlatformDevelopmentPanel({ token }: { token: string }) {
  const [models,setModels]=useState<Summary[]>([]);
  const [model,setModel]=useState<Model>();
  const [preview,setPreview]=useState<Preview>();
  const [approvals,setApprovals]=useState<Approval[]>([]);
  const [runs,setRuns]=useState<RunSummary[]>([]);
  const [run,setRun]=useState<Run>();
  const [title,setTitle]=useState("code-ontology 平台开发管理");
  const [reason,setReason]=useState("");
  const [selected,setSelected]=useState("metamodel");
  const [busy,setBusy]=useState(false);
  useLeaveGuard({ label: "平台开发操作", dirty: false, busy });
  const [error,setError]=useState("");
  useEffect(()=>{let active=true;
    setModel(undefined);setPreview(undefined);setRun(undefined);setApprovals([]);setRuns([]);setModels([]);
    metaRequest<{models:Summary[]}>(API+"models",token).then(r=>{if(active)setModels(r.models);}).catch(e=>{if(active)setError(e.message);});
    return ()=>{active=false;};
  },[token]);
  async function history(id:string){
    const h=await metaRequest<{approvals:Approval[];runs:RunSummary[]}>(API+"history?modelId="+encodeURIComponent(id),token);
    setApprovals(h.approvals);setRuns(h.runs);
  }
  async function act(action:"create"|"load"|"preview"|"approve"|"execute"|"run",id?:string){
    setBusy(true);setError("");
    try {
      if(action==="create" || action==="load"){
        const m=action==="create" ? await metaRequest<Model>(API+"models",token,{title,parentModelId:model?.modelId}) : await metaRequest<Model>(API+"model?modelId="+encodeURIComponent(id??""),token);
        setModel(m);setTitle(m.title);setPreview(undefined);setRun(undefined);setApprovals([]);setRuns([]);setReason("");
        setModels((await metaRequest<{models:Summary[]}>(API+"models",token)).models);await history(m.modelId);
      } else if(action==="preview" && model) {
        setPreview(undefined);
        setPreview(await metaRequest<Preview>(API+"preview?modelId="+encodeURIComponent(model.modelId),token));
      } else if(action==="approve" && model && preview){
        await metaRequest<Approval>(API+"approve",token,{modelId:model.modelId,approvalHash:preview.approvalHash,reason});await history(model.modelId);
      } else if(action==="execute" && model && id){
        setRun(undefined);
        setRun(await metaRequest<Run>(API+"execute",token,{approvalId:id}));await history(model.modelId);
      } else if(action==="run" && id){
        setRun(undefined);setRun(await metaRequest<Run>(API+"run?runId="+encodeURIComponent(id),token));
      }
    } catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setBusy(false);}
  }
  const requirement=model?.requirements.find(r=>r.id===selected);
  const approved=preview && approvals.find(a=>a.approvalHash===preview.approvalHash);
  const edited=model && title!==model.title;
  return <div className="self-development">
    <section className="panel"><h2>平台自开发 · 基于元模型 2.0.0 的业务闭环</h2>
      <p>八个业务环节复用现有服务与固定回归测试，新增 Python / TypeScript 需求追踪契约生成。模型、批准和执行记录保存到服务端；不会覆盖当前仓库源码，也不会自动部署。</p>
      {error && <p role="alert" className="error">{error}</p>}
      <fieldset disabled={busy}>
        <label>模型历史<select value={model?.modelId??""} onChange={e=>act("load",e.target.value)}><option value="" disabled>选择已保存版本</option>{models.map(m=><option key={m.modelId} value={m.modelId}>{m.title} · {m.createdAt}</option>)}</select></label>
        <label>本次开发基线名称<input value={title} maxLength={200} onChange={e=>setTitle(e.target.value)}/></label>
        <button type="button" onClick={()=>act("create")}>{model?"从当前记录保存新模型与源码基线":"建立平台业务模型与源码基线"}</button>
      </fieldset>
      <p>当前使用固定验收配置，不接受任意需求文本、命令或目标路径。Ready 只表示已列出的回归范围就绪，不能替代完整业务验收或生产发布审批。</p>
    </section>
    {model && <>
      <section className="panel"><h3>1 · 需求、契约与设计映射</h3><p>元模型 {model.binding.version} · 校验{model.validation.conforms?"通过":"未通过"} · 模型 {model.modelHash.slice(0,16)}</p><p>源码基线 <code>{model.baseline.hash}</code></p>
        <label>查看业务环节<select value={selected} onChange={e=>setSelected(e.target.value)}>{model.requirements.map(r=><option key={r.id} value={r.id}>{r.label}</option>)}</select></label>
        {requirement && <><h4>{requirement.label}</h4><p>{requirement.statement}</p><div className="self-chain" aria-label="需求通过契约条款关联技术设计，并以验收判断关闭义务">
          <span>业务目标<small>motivates ↓</small>需求</span><span>语义契约<small>hasClause ↓</small>不变式条款</span><span>技术设计<small>addresses ↑</small>条款 / 需求</span><span>固定验收<small>verifies ↑</small>验收条件</span><span>满足性判断<small>supportedBy ↓</small>真实证据</span>
        </div><dl><dt>需求 IRI</dt><dd><code>{requirement.iri}</code></dd><dt>声明实现位置（不是满足性证明）</dt><dd><code>{requirement.source}</code></dd><dt>独立验收</dt><dd><code>{requirement.test}</code></dd></dl></>}
        <details><summary>完整项目本体 Turtle</summary><pre>{model.turtle}</pre></details>
      </section>
      <section className="panel"><h3>2 · 审查生成内容并批准</h3><p>预览绑定模型、源码基线及生成产物摘要；变化后必须新建版本并重新批准。</p>
        {edited && <p role="status">名称已修改，请保存新模型版本后继续。</p>}
        <fieldset disabled={busy||Boolean(edited)}><button type="button" onClick={()=>act("preview")}>检查基线并预览生成</button>
        {preview && <><p>批准摘要 <code>{preview.approvalHash}</code></p>{Object.entries(preview.files).map(([path,source])=><details key={path}><summary>{path}</summary><pre>{source}</pre></details>)}
          <label>批准理由<textarea value={reason} maxLength={2000} onChange={e=>setReason(e.target.value)}/></label><button type="button" disabled={!reason.trim()} onClick={()=>act("approve")}>批准当前预览（不立即执行）</button>
          {approved && <><p>已有匹配批准：{approved.createdAt} · {approved.reason}</p><button type="button" onClick={()=>act("execute",approved.approvalId)}>生成契约并执行平台固定验收</button></>}
        </>}</fieldset>
      </section>
      <section className="panel"><h3>3 · 执行记录、证据与对账</h3><p>运行期间会执行固定 Python 回归测试，可能需要数分钟。报告保留每组测试数量、失败日志和证据图。</p>
        {busy && <p role="status">正在处理，请等待结果；生成操作只写入新的受管理目录。</p>}
        <label>历史执行<select disabled={busy} value={run?.runId??""} onChange={e=>act("run",e.target.value)}><option value="" disabled>选择记录并复核当前摘要</option>{runs.map(r=><option key={r.runId} value={r.runId}>{r.createdAt} · 历史 {r.status}</option>)}</select></label>
        {run && <><h4>当前：{run.currentStatus} · 历史：{run.status}</h4><p>基线{run.baselineCurrent?"一致":"已变化"} · 定义绑定{run.bindingCurrent?"一致":"已变化"} · 证据图校验{run.validation.conforms?"通过":"失败"}</p><p>产物目录 <code>{run.directory}</code></p>
          <button type="button" disabled={busy} onClick={()=>act("run",run.runId)}>重新核对源码、产物与证据</button>
          {run.changedFiles.length>0 && <p>变化文件：{run.changedFiles.join("、")}</p>}{run.report.error && <p role="alert">{run.report.error}</p>}
          {run.report.cases.map(c=><details key={c.id}><summary>{model.requirements.find(r=>r.id===c.id)?.label??c.id} · {c.passed?"通过":"失败"} · {c.tests} 项 / 跳过 {c.skipped}</summary><pre>{c.log??c.error??"固定验收通过"}</pre></details>)}
          <details><summary>执行、证据与义务本体</summary><pre>{run.turtle}</pre></details><details><summary>约束问题</summary><pre>{JSON.stringify(run.validation.issues,null,2)}</pre></details>
        </>}
      </section>
    </>}
  </div>;
}
