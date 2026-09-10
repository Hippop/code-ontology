"""Ontology-bound self-development: immutable plans, generated contracts and evidence.

Only the fixed repository regression profile is executable. No client commands,
paths, arbitrary Turtle, automatic source overwrite or production publication.
"""
from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path

from rdflib import Graph, Literal, Namespace, RDF, RDFS, URIRef, XSD

from .development_slice import CODE, DEV, ENG, digest
from .errors import conflict, invalid, not_found
from .store import canonical_json, utc_now

BIZ = Namespace("https://example.org/code-ontology/business#")
# Acceptance is deliberately limited to these existing regression suites, not
# an assertion that every feature of the platform has been implemented.
AREAS = (
    ("metamodel", "元模型治理", "metamodel_registry.py", "test_metamodel_registry.py"),
    ("baseline", "仓库事实基线", "repository_scan.py", "test_code_intelligence.py"),
    ("requirement", "需求与业务契约", "engineering_semantics.py", "test_engineering_semantics.py"),
    ("alignment", "语义对齐与对账", "verification_workflow.py", "test_requirement_reconciliation.py"),
    ("plan", "计划审批与执行", "workflow_orchestration.py", "test_execution_workflow.py"),
    ("generation", "本体驱动代码生成", "development_codegen.py", "test_development_codegen.py"),
    ("verification", "提交前验证门禁", "verification_workflow.py", "test_precommit_verification.py"),
    ("audit", "平台记录与审计", "store.py", "test_platform.py"),
)
PROFILE = "platform-regression-v1"
BUSINESS_REQUIREMENTS = {
    "metamodel": "工程师按完整 IRI 查询定义、继承与约束，并绑定安装的元模型版本及摘要",
    "baseline": "建立可查询的仓库代码事实与版本基线，为影响分析提供上下文",
    "requirement": "将需求整理为受治理的工程意图，关联业务能力、契约与验收",
    "alignment": "对批准设计与实际实现进行语义对账，保留未解决差异和影响",
    "plan": "开发工作流经过人工确认和计划批准，执行限制在允许的仓库与命令范围",
    "generation": "根据明确生成规范产生代码，拒绝未支持或未批准的转换",
    "verification": "提交前核对实现覆盖、测试证据、影响义务及工作区快照",
    "audit": "保存平台业务记录和需求阶段上下文，并提供可追溯的审计查询",
    "contract": "从平台业务需求图生成可查询的 Python 追踪契约与 TypeScript 需求类型",
}


class PlatformDevelopment:
    def __init__(self, service):
        self.service, self.store = service, service.store
        self.root = service.project_root

    def _get(self, kind, record_id):
        if not isinstance(record_id, str) or not record_id:
            raise invalid("需要有效的记录 ID")
        rows = self.store.development_records("platform-" + kind, record_id)
        if not rows:
            raise not_found("未找到平台自开发记录")
        return rows[0]

    def catalog(self):
        return {"binding": self.service.metamodel_registry().ref, "profile": PROFILE,
                "areas": [{"id": a, "label": b, "source": c, "test": d} for a,b,c,d in AREAS],
                "scope": "平台固定回归基线与需求追踪契约；不含生产发布、完整浏览器验收和任意需求自动实现"}

    def _snapshot(self):
        files = {}
        for directory in ("src/code_ontology_platform", "tests", "ontology", "shapes", "rules", "models", "examples", "web/src"):
            for path in sorted((self.root / directory).rglob("*")):
                if path.is_file() and not path.is_symlink() and "__pycache__" not in path.parts and path.suffix in {".py", ".ttl", ".json", ".yaml", ".tsx", ".ts", ".css"}:
                    files[path.relative_to(self.root).as_posix()] = digest(path.read_bytes())
        for name in ("pyproject.toml", "web/package.json", "web/package-lock.json"):
            path = self.root / name
            if path.is_file():
                files[name] = digest(path.read_bytes())
        return {"files": files, "hash": digest(canonical_json(files).encode())}

    def create(self, body):
        title = body.get("title", "code-ontology 平台开发管理")
        if not isinstance(title, str) or not title.strip() or len(title) > 200:
            raise invalid("名称必须为 1 至 200 字符")
        parent = body.get("parentModelId")
        if parent is not None:
            self._get("model", parent)
        registry = self.service.metamodel_registry()
        model_id = str(uuid.uuid4())
        n = Namespace(f"urn:platform-development:{model_id}:")
        # Reuse the governed profile definitions, not its planned requirements
        # or its fictitious execution/assessment records.
        original = Graph().parse(self.root / "examples/development-code-ontology.ttl", format="turtle")
        old = Namespace("urn:example:code-ontology-development:")
        keep = {old[k] for k in ("package", "constraints", "rules", "technology", "project", "repository", "profile", "model", "baseline", "rule")}
        g = Graph()
        for s,p,o in original:
            if s in keep and o != old.extension:
                term = lambda v: URIRef(str(v).replace(str(old), str(n))) if isinstance(v, URIRef) else v
                g.add((term(s), p, term(o)))
        def put(s,p,o):
            g.set((s,p,o if isinstance(o, URIRef) else Literal(o)))
        def node(key, kind, label, in_model=False):
            s = n[key]; g.add((s, RDF.type, kind)); put(s,RDFS.label,label)
            if in_model: put(s,DEV.inModel,n.model)
            return s
        def version(s):
            put(s,DEV.version,PROFILE); put(s,DEV.source,"repository:platform-development")
        baseline = self._snapshot()
        put(n.project,RDFS.label,title.strip()); put(n.model,RDFS.label,title.strip())
        put(n.model,DEV.scope,"固定平台回归与生成追踪契约；不包含生产发布")
        put(n.model,DEV.version,model_id)
        put(n.baseline,DEV.contentHash,baseline["hash"]); put(n.baseline,DEV.commit,"workspace:"+baseline["hash"])
        put(n.baseline,DEV.scope,"固定源码、测试、定义、示例与工作台输入文件集合")
        put(n.baseline,RDFS.label,"保存模型时的真实工作区文件基线")
        put(n.rule,RDFS.label,"平台需求图到 Python/TypeScript 追踪契约")
        put(n.rule,DEV.source,"repository:platform_development.py")
        put(n.rule,DEV.inputPattern,"固定平台 Requirement、AcceptanceCriterion 和声明映射")
        put(n.rule,DEV.outputPattern,"Python 追踪索引与 TypeScript 需求 ID 类型")
        put(n.rule,DEV.precondition,"定义绑定、工作区基线与批准摘要均一致")
        put(n.rule,DEV.unsupportedCase,"不生成任意业务逻辑，不替换现有服务实现")
        goal = node("goal",DEV.BusinessGoal,"用本体管理平台自身的开发交付",True)
        put(goal,DEV.statement,"需求、设计、源码、验收与判断在同一版本下可追溯")
        plan = node("plan",DEV.ChangePlan,"平台自开发回归计划")
        for p,o in ((DEV.baseline,n.baseline),(DEV.targetModel,n.model),(DEV.status,"Draft"),(DEV.contentHash,baseline["hash"])): put(plan,p,o)
        decision = node("decision",DEV.DesignDecision,"复用已有服务，生成追踪契约",True)
        for p,o in ((DEV.question,"如何在保留现有实现的前提下引入元模型治理"),(DEV.alternative,"复用服务并生成追踪契约"),(DEV.chosenOption,"复用服务并生成追踪契约"),(DEV.rationale,"不把模板生成当成所有业务已实现")): put(decision,p,o)
        rows = []
        for key,label,source,test in AREAS + (("contract","生成追踪契约","platform_development.py","platform_acceptance.py"),):
            req = node("req_"+key,DEV.Requirement,label,True)
            capability = node(key+"Capability",CODE.BusinessCapability,label+"能力")
            put(req,ENG.specifiesCapability,capability)
            concept = node(key+"Object",DEV.BusinessConcept,label+"业务对象",True)
            put(concept,BIZ.canonicalId,"platform."+key); put(concept,DEV.statement,label+"的管理对象")
            contract = node(key+"Contract",DEV.SemanticContract,label+"契约",True)
            put(contract,ENG.usesOntology,n.package)
            clause = node(key+"Clause",DEV.Invariant,label+"回归约束",True)
            ac = node(key+"AC",DEV.AcceptanceCriterion,label+"固定验收",True)
            scope = PROFILE+":"+key
            statement = "固定验收通过且源码、模型与证据摘要不漂移："+test
            for s,p,o in ((goal,DEV.motivates,req),(req,DEV.statement,BUSINESS_REQUIREMENTS[key]),(req,DEV.scope,scope),
                          (req,ENG.constrainedBy,contract),(req,DEV.hasAcceptanceCriterion,ac),
                          (contract,DEV.hasClause,clause),(clause,DEV.statement,statement),(clause,DEV.constrains,concept),
                          (ac,DEV.statement,statement),(ac,DEV.scope,scope)): put(s,p,o)
            design = node(key+"Design",DEV.TechnicalRepresentation,label+"实现设计",True)
            for p,o in ((DEV.addresses,clause),(DEV.represents,concept),(DEV.decidedBy,decision),(DEV.source,"src/code_ontology_platform/"+source)): put(design,p,o)
            mapping = node(key+"Mapping",DEV.RealizationMapping,label+"声明映射",True)
            for p,o in ((DEV.mappingSource,req),(DEV.mappingTarget,design),(DEV.mappingRole,"Implements"),(DEV.status,"Declared"),(DEV.rationale,"源码职责声明；通过验收不等于形式化实现证明")): put(mapping,p,o)
            delta = node(key+"Delta",DEV.SemanticDelta,label+"治理接入差异")
            for p,o in ((DEV.baseline,n.baseline),(DEV.targetModel,n.model),(DEV.changeKind,"Add" if key=="contract" else "Reuse"),(DEV.statement,"生成追踪契约" if key=="contract" else "将既有实现纳入固定回归与证据链")): put(delta,p,o)
            obligation = node(key+"Obligation",DEV.VerificationObligation,label+"验收义务")
            task = node(key+"Task",DEV.ImplementationTask,label+"执行任务")
            for s,p,o in ((delta,DEV.createsObligation,obligation),(obligation,DEV.causedBy,delta),(obligation,DEV.addresses,ac),
                          (obligation,DEV.status,"Open"),(obligation,DEV.statement,statement),(plan,DEV.hasObligation,obligation),
                          (plan,DEV.hasTask,task),(task,DEV.fulfills,obligation),(task,DEV.mode,"Template" if key=="contract" else "Reuse")):
                # Multi-valued plan/goal edges must accumulate.
                g.add((s,p,o if isinstance(o,URIRef) else Literal(o)))
            spec = node(key+"Verification",DEV.VerificationSpecification,label+"验证规范"); version(spec)
            for p,o in ((DEV.scope,scope),(DEV.procedure,test),(DEV.expectedResult,"固定用例全部通过；不接受零用例或跳过用例")): put(spec,p,o)
            g.add((spec,DEV.verifies,ac)); g.add((spec,DEV.verifies,clause))
            rows.append({"id":key,"iri":str(req),"label":label,"statement":BUSINESS_REQUIREMENTS[key],"source":"src/code_ontology_platform/"+source,"test":test,"scope":scope})
        # goal motivates is multi-valued (the loop's set only retained its last edge).
        for row in rows: g.add((goal,DEV.motivates,URIRef(row["iri"])))
        spec = node("specification",DEV.GenerationSpecification,"平台追踪契约生成规范")
        for p,o in ((DEV.appliesRule,n.rule),(DEV.inputDesign,n.contractDesign),(DEV.usesTechnology,n.technology),
                    (DEV.preserves,n.contractClause),(DEV.targetPath,"generated/platform_contract.py")): put(spec,p,o)
        put(n.contractTask,DEV.usesSpecification,spec)
        turtle = g.serialize(format="turtle")
        validation = registry.validate_turtle(turtle)
        if not validation["conforms"]: raise invalid("平台模型未通过元模型校验",validation)
        record = {"modelId":model_id,"parentModelId":parent,"title":title.strip(),"createdAt":utc_now(),"binding":registry.ref,
                  "turtle":turtle,"modelHash":digest(turtle.encode()),"baseline":baseline,"requirements":rows,"validation":validation}
        self.store.put_development_record(model_id,"platform-model",record)
        return record

    def models(self):
        return {"models":[{k:r[k] for k in ("modelId","parentModelId","title","createdAt","modelHash")} for r in self.store.development_records("platform-model")]}

    def _current(self, model):
        self.service.metamodel_registry().check_binding(model["binding"])
        if self._snapshot()["hash"] != model["baseline"]["hash"]:
            raise conflict("工作区基线已变化，请保存并审查新模型版本；不会自动沿用旧批准")

    def preview(self, model_id):
        model = self._get("model",model_id); self._current(model)
        g = Graph().parse(data=model["turtle"],format="turtle")
        requirements = sorted([{"iri":str(s),"label":str(g.value(s,RDFS.label)),"scope":str(g.value(s,DEV.scope)),
                                "statement":str(g.value(s,DEV.statement))} for s in g.subjects(RDF.type,DEV.Requirement)],key=lambda r:r["iri"])
        # Only data literals are interpolated using language-safe encoders.
        source = '"""Generated platform requirement contract; do not edit."""\nREQUIREMENTS = '+repr(requirements)+"\n\ndef requirement(iri):\n    return next((r for r in REQUIREMENTS if r['iri'] == iri), None)\n"
        ts = "// Generated from the approved ontology model.\nexport const requirements = "+json.dumps(requirements,ensure_ascii=False,indent=2)+" as const;\nexport type RequirementIRI = typeof requirements[number]['iri'];\n"
        files = {"generated/platform_contract.py":source,"generated/platform-contract.ts":ts}
        approval_hash = digest(canonical_json({"modelHash":model["modelHash"],"baselineHash":model["baseline"]["hash"],"files":files,"profile":PROFILE}).encode())
        return {"modelId":model_id,"approvalHash":approval_hash,"files":files,"requirements":requirements,"profile":PROFILE}

    def approve(self, body):
        preview = self.preview(body.get("modelId"))
        if body.get("approvalHash") != preview["approvalHash"]: raise conflict("批准必须绑定当前预览摘要")
        reason = body.get("reason")
        if not isinstance(reason,str) or not reason.strip() or len(reason)>2000: raise invalid("请填写批准理由（1 至 2000 字符）")
        record = {"approvalId":str(uuid.uuid4()),"modelId":preview["modelId"],"approvalHash":preview["approvalHash"],"reason":reason.strip(),"actor":"local-workbench-operator","createdAt":utc_now()}
        self.store.put_development_record(record["approvalId"],"platform-approval",record)
        return record

    def execute(self, body):
        approval = self._get("approval",body.get("approvalId"))
        model = self._get("model",approval["modelId"])
        preview = self.preview(model["modelId"])
        if approval["approvalHash"] != preview["approvalHash"]: raise conflict("生成输入已变化，必须重新批准")
        run_id = str(uuid.uuid4()); started = utc_now()
        root = Path(self.store.database).resolve().parent / "platform-development-runs" / run_id
        root.mkdir(parents=True,exist_ok=False)
        for path,source in preview["files"].items():
            target=root/path; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(source.encode("utf-8"))
        (root/"model.ttl").write_bytes(model["turtle"].encode("utf-8"))
        expected = {path:digest((root/path).read_bytes()) for path in preview["files"]}
        expected["model.ttl"]=model["modelHash"]
        # Fixed verifier and arguments only. Existing project tests are trusted
        # repository code, not an API for executing user-uploaded programs.
        try:
            result = subprocess.run([sys.executable,"-B",str(self.root/"src/code_ontology_platform/platform_acceptance.py"),str(self.root),str(root)],cwd=self.root,capture_output=True,text=True,timeout=480)
            report=json.loads(result.stdout)
            if not isinstance(report,dict): raise ValueError("验收报告必须是对象")
            if result.returncode != 0 and report.get("passed") is True: raise ValueError("验收退出码不一致")
        except (OSError,ValueError,subprocess.TimeoutExpired) as error:
            report={"passed":False,"cases":[],"error":str(error)}
        expected_ids={row["id"] for row in model["requirements"]}
        cases=report.get("cases",[])
        if not isinstance(cases,list):
            cases=[]; report["cases"]=[]
        valid_report=isinstance(cases,list) and len(cases)==len(expected_ids) and {r.get("id") for r in cases if isinstance(r,dict)}==expected_ids
        unchanged=self._snapshot()["hash"]==model["baseline"]["hash"] and all((root/p).is_file() and digest((root/p).read_bytes())==h for p,h in expected.items())
        binding_current=self.service.metamodel_registry().ref==model["binding"]
        passed=valid_report and report.get("passed") is True and all(r.get("passed") is True and type(r.get("tests")) is int and r["tests"]>0 and r.get("skipped",0)==0 for r in cases) and unchanged and binding_current
        ended=utc_now(); report.update({"passed":passed,"filesUnchanged":unchanged,"bindingCurrent":binding_current,"startedAt":started,"endedAt":ended,"profile":PROFILE})
        report_bytes=(canonical_json(report)+"\n").encode(); (root/"report.json").write_bytes(report_bytes)
        graph=self._evidence(model,approval,run_id,expected,report,started,ended,root)
        validation=self.service.metamodel_registry()._validate_graph(graph)
        status="Ready" if passed and validation["conforms"] else "Blocked"
        for release in graph.subjects(RDF.type,DEV.ReleaseAssessment): graph.set((release,DEV.status,Literal(status)))
        turtle=graph.serialize(format="turtle"); (root/"evidence.ttl").write_bytes(turtle.encode("utf-8"))
        expected.update({"report.json":digest(report_bytes),"evidence.ttl":digest(turtle.encode())})
        record={"runId":run_id,"modelId":model["modelId"],"approvalId":approval["approvalId"],"createdAt":started,"endedAt":ended,
                "status":status,"report":report,"validation":validation,"directory":str(root),"files":expected,"turtle":turtle}
        self.store.put_development_record(run_id,"platform-run",record)
        return self.run(run_id)

    def _evidence(self,model,approval,run_id,files,report,started,ended,root):
        g=Graph().parse(data=model["turtle"],format="turtle")
        n=Namespace(f"urn:platform-development:{model['modelId']}:"); r=Namespace(f"urn:platform-development-run:{run_id}:")
        def put(s,p,o): g.set((s,p,o if isinstance(o,(URIRef,Literal)) else Literal(o)))
        def node(s,kind,label): g.add((s,RDF.type,kind)); put(s,RDFS.label,label)
        # Every execution receives independent plan, obligation and assessment identities.
        runtime={n.plan}|{n[row['id']+"Obligation"] for row in model["requirements"]}
        moved=Graph()
        remap=lambda v: URIRef(str(v).replace(str(n),str(r))) if v in runtime else v
        for s,p,o in g: moved.add((remap(s),p,remap(o)))
        g=moved
        put(r.plan,DEV.status,"Approved"); put(r.plan,DEV.contentHash,approval["approvalHash"])
        node(r.approval,DEV.Approval,"本地操作批准（非多人签名）")
        for p,o in ((DEV.approvalSubject,r.plan),(DEV.status,"Approved"),(DEV.contentHash,approval["approvalHash"]),(DEV.actor,approval["actor"]),(DEV.rationale,approval["reason"])): put(r.approval,p,o)
        put(r.plan,DEV.approvedBy,r.approval)
        node(r.snapshot,DEV.CodeSnapshot,"实际生成产物快照")
        for p,o in ((DEV.forProject,n.project),(DEV.repository,n.repository),(DEV.commit,"workspace:"+digest(canonical_json(files).encode())),(DEV.contentHash,digest(canonical_json(files).encode())),(DEV.scope,"生成追踪契约；源基线见计划 baseline")): put(r.snapshot,p,o)
        def execution(s,kind,success):
            node(s,kind,"固定平台自开发执行")
            for p,o in ((DEV.status,"Succeeded" if success else "Failed"),(DEV.scenario,"Operational"),(DEV.actor,"platform-self-development"),(DEV.executorVersion,PROFILE),(DEV.inputHash,model["modelHash"]),(DEV.startedAt,Literal(started,datatype=XSD.dateTime)),(DEV.endedAt,Literal(ended,datatype=XSD.dateTime))): put(s,p,o)
        execution(r.generation,DEV.GenerationRun,True)
        for p,o in ((DEV.underPlan,r.plan),(DEV.executesTask,n.contractTask),(DEV.usesSpecification,n.specification)): put(r.generation,p,o)
        execution(r.observation,DEV.ObservationRun,True)
        put(r.observation,DEV.evaluatesSnapshot,r.snapshot); put(r.observation,DEV.scope,"generated/")
        node(r.actual,DEV.GraphRevision,"Actual 文件图")
        for p,o in ((DEV.version,run_id),(DEV.source,"generated/"),(DEV.graphRole,"Knowledge"),(DEV.graphSpace,"Actual"),(DEV.inModel,n.model),(DEV.inSnapshot,r.snapshot),(DEV.observedBy,r.observation)): put(r.actual,p,o)
        put(r.observation,DEV.produces,r.actual)
        for i,path in enumerate(p for p in files if p.startswith("generated/")):
            artifact=r["artifact"+str(i)]; node(artifact,DEV.CodeArtifact,path)
            for p,o in ((DEV.targetPath,path),(DEV.contentHash,files[path]),(DEV.inSnapshot,r.snapshot)): put(artifact,p,o)
            g.add((r.generation,DEV.produces,artifact)); g.add((r.actual,DEV.containsEntity,artifact))
        node(r.release,DEV.ReleaseAssessment,"固定平台回归基线就绪判断（非部署）")
        for p,o in ((DEV.underPlan,r.plan),(DEV.evaluatesSnapshot,r.snapshot),(DEV.evaluatesModel,n.model),(DEV.scope,PROFILE),(DEV.status,"Ready" if report["passed"] else "Blocked"),(DEV.actor,"platform-self-development"),(DEV.rationale,"仅固定测试覆盖范围；不构成生产部署或全业务形式化证明")): put(r.release,p,o)
        case_map={c.get("id"):c for c in report.get("cases",[]) if isinstance(c,dict)}
        for row in model["requirements"]:
            key=row["id"]; case=case_map.get(key,{})
            ok=report["passed"] and case.get("passed") is True
            run=r[key+"Verification"]; evidence=r[key+"Evidence"]
            execution(run,DEV.VerificationRun,ok)
            for p,o in ((DEV.usesSpecification,n[key+"Verification"]),(DEV.evaluatesSnapshot,r.snapshot),(DEV.evaluatesModel,n.model),(DEV.produces,evidence)): put(run,p,o)
            node(evidence,DEV.Evidence,row["label"]+"验收报告")
            artifact=r[key+"Report"]
            node(artifact,CODE.ImpactAnalysisEntity,row["label"]+"可审计报告文件")
            put(evidence,ENG.evidenceArtifact,artifact)
            for p,o in ((DEV.generatedBy,run),(DEV.evaluatesSnapshot,r.snapshot),(DEV.evaluatesModel,n.model),(DEV.scope,row["scope"]),(DEV.contentHash,digest((root/"report.json").read_bytes())),(DEV.reportUri,Literal((root/"report.json").as_uri(),datatype=XSD.anyURI))): put(evidence,p,o)
            for suffix in ("AC","Clause"):
                a=r[key+suffix+"Assessment"]; node(a,DEV.SatisfactionAssessment,row["label"]+"判断")
                for p,o in ((DEV.assesses,n[key+suffix]),(DEV.evaluatesSnapshot,r.snapshot),(DEV.evaluatesModel,n.model),(DEV.scope,row["scope"]),(DEV.status,"Satisfied" if ok else "NotSatisfied"),(DEV.actor,"platform-self-development"),(DEV.rationale,"固定验收结果及未变化的源码与定义基线"),(DEV.supportedBy,evidence)): put(a,p,o)
                g.add((r.release,DEV.includesAssessment,a))
            if ok:
                put(r[key+"Obligation"],DEV.status,"Closed"); put(r[key+"Obligation"],DEV.closedBy,r[key+"ACAssessment"])
        return g

    def run(self,run_id):
        record=self._get("run",run_id); model=self._get("model",record["modelId"]); root=Path(record["directory"])
        changed=[p for p,h in record["files"].items() if not (root/p).is_file() or digest((root/p).read_bytes())!=h]
        baseline_current=self._snapshot()["hash"]==model["baseline"]["hash"]
        binding_current=self.service.metamodel_registry().ref==model["binding"]
        return {**record,"currentStatus":record["status"] if not changed and baseline_current and binding_current else "Stale",
                "changedFiles":changed,"baselineCurrent":baseline_current,"bindingCurrent":binding_current}

    def history(self,model_id):
        self._get("model",model_id)
        return {"approvals":[r for r in self.store.development_records("platform-approval") if r["modelId"]==model_id],
                "runs":[{k:r[k] for k in ("runId","modelId","createdAt","status")} for r in self.store.development_records("platform-run") if r["modelId"]==model_id]}
