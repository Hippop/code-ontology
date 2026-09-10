"""A persisted task-priority model -> code -> execution evidence vertical slice."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import uuid
from pathlib import Path

from rdflib import Graph, Literal, Namespace, RDF, RDFS, URIRef, XSD

from .development_codegen import DEV, DevelopmentCodeGenerator
from .errors import invalid, not_found
from .store import canonical_json, utc_now

T = Namespace("urn:example:task-priority:")
ENG = Namespace("https://example.org/code-ontology/engineering#")
CODE = Namespace("https://example.org/code-ontology#")


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class DevelopmentSlice:
    def __init__(self, service):
        self.service, self.store = service, service.store

    def _get(self, kind, record_id):
        if not isinstance(record_id, str):
            raise invalid("记录 ID 必须是字符串")
        records = self.store.development_records(kind, record_id)
        if not records:
            raise not_found("未找到开发切片记录")
        return records[0]

    def _base_graph(self, name, default):
        graph = Graph().parse(self.service.project_root / "examples/development-task-priority.ttl", format="turtle")
        # Keep intent/design only. Illustrative executions, hashes and judgments
        # never become operational evidence by relabelling their scenario.
        removed = [T[item] for item in ("after", "artifact", "generationRun", "scanRun", "actualGraph",
                   "observedMapping", "testRun", "report", "evidence", "assessment", "impact", "release", "approval")]
        for node in removed:
            graph.remove((node, None, None)); graph.remove((None, None, node))
        for subject, value in list(graph.subject_objects(DEV.source)):
            if str(value).startswith("fixture:"):
                graph.set((subject, DEV.source, Literal("repository:examples/development-task-priority.ttl")))
        graph.set((T.project, RDFS.label, Literal(name)))
        graph.set((T.plan, DEV.status, Literal("Draft")))
        graph.remove((T.plan, DEV.contentHash, None))
        empty_hash = digest(canonical_json({}).encode())
        graph.set((T.before, DEV.commit, Literal("workspace:" + empty_hash)))
        graph.set((T.before, DEV.contentHash, Literal(empty_hash)))
        graph.set((T.before, DEV.scope, Literal("src/task.py; tests/acceptance.py")))
        graph.set((T.valueClause, DEV.defaultValue, Literal(default)))
        graph.set((T.valueClause, DEV.statement, Literal(f"优先级为 low、medium、high，缺省为 {default}")))
        graph.set((T.acDefault, DEV.statement, Literal(f"未传 priority 时得到 {default}")))
        graph.set((T.acDefault, RDFS.label, Literal(f"缺省采用 {default}")))
        graph.set((T.businessRule, DEV.statement, Literal(f"缺省采用 {default}，未知值必须拒绝")))
        graph.set((T.verificationSpec, DEV.expectedResult, Literal(f"{default}、high、校验错误")))
        graph.set((T.verificationSpec, DEV.procedure, Literal("平台固定 task-priority-v1 验收程序；缺省、三个合法值及四种非法输入")))
        for node in (T.change, T.verification):
            graph.set((node, DEV.status, Literal("Open")))
        graph.set((T.plan, DEV.contentHash, Literal(digest(graph.serialize(format="nt").encode()))))
        return graph

    def save(self, body):
        name, default = body.get("name"), body.get("defaultPriority", "medium")
        if not isinstance(name, str) or not name.strip() or len(name) > 200:
            raise invalid("项目名称必须为 1 至 200 个字符")
        if default not in ("low", "medium", "high"):
            raise invalid("默认优先级必须为 low、medium 或 high")
        registry = self.service.metamodel_registry()
        graph = self._base_graph(name.strip(), default)
        model_id = str(uuid.uuid4())
        # Each persisted revision has its own RDF identity as well as storage ID.
        remapped = Graph()
        for s, p, o in graph:
            def term(v):
                return URIRef(str(v).replace(str(T), f"urn:task-project:{model_id}:")) if isinstance(v, URIRef) else v
            remapped.add((term(s), p, term(o)))
        turtle = remapped.serialize(format="turtle")
        validation = registry.validate_turtle(turtle)
        if not validation["conforms"]:
            raise invalid("项目模型未通过校验", validation)
        record = {"modelId": model_id, "name": name.strip(), "defaultPriority": default,
                  "createdAt": utc_now(), "binding": registry.ref, "turtle": turtle,
                  "modelHash": digest(turtle.encode()), "profile": "task-priority-v1"}
        self.store.put_development_record(model_id, "model", record)
        return record

    def models(self):
        return {"models": [{k: v for k, v in r.items() if k != "turtle"} for r in self.store.development_records("model")]}

    def execute(self, body):
        model = self._get("model", body.get("modelId"))
        registry = self.service.metamodel_registry()
        registry.check_binding(model["binding"])
        run_id = str(uuid.uuid4())
        root = Path(self.store.database).resolve().parent / "development-runs" / run_id
        root.mkdir(parents=True, exist_ok=False)
        n = Namespace(f"urn:task-project:{model['modelId']}:")
        graph = Graph().parse(data=model["turtle"], format="turtle")
        started = utc_now()
        actor = "local-workbench-operator"
        def put(subject, predicate, value):
            graph.set((subject, predicate, value))
        def node(subject, kind, label):
            graph.add((subject, RDF.type, kind)); put(subject, RDFS.label, Literal(label))
        def snapshot(subject, hash_value):
            node(subject, DEV.CodeSnapshot, "执行目录文件快照")
            for p, v in ((DEV.forProject,n.project),(DEV.repository,n.repository),(DEV.commit,Literal("workspace:"+hash_value)),
                         (DEV.contentHash,Literal(hash_value)),(DEV.scope,Literal("src/task.py; tests/acceptance.py"))): put(subject,p,v)
        put(n.repository, RDFS.label, Literal(str(root)))
        put(n.plan, DEV.status, Literal("Approved"))
        # The execute action approves exactly the persisted model document.
        put(n.plan, DEV.contentHash, Literal(model["modelHash"]))
        node(n.approval, DEV.Approval, "工作台执行操作批准")
        for p,v in ((DEV.approvalSubject,n.plan),(DEV.status,Literal("Approved")),(DEV.actor,Literal(actor)),
                    (DEV.contentHash,graph.value(n.plan,DEV.contentHash)),(DEV.rationale,Literal("执行已保存任务输入切片；仅写入新建执行目录"))): put(n.approval,p,v)
        put(n.plan,DEV.approvedBy,n.approval)
        approved_validation = registry._validate_graph(graph)
        if not approved_validation["conforms"]:
            raise invalid("执行模型未通过校验", approved_validation)
        approved_turtle = graph.serialize(format="turtle")
        (root / "model.ttl").write_bytes(model["turtle"].encode("utf-8"))
        generated = DevelopmentCodeGenerator(graph).generate(root, apply=True)
        generated_at = utc_now()
        source = root / "src/task.py"
        test_path = root / "tests/acceptance.py"
        test_path.parent.mkdir()
        test_path.write_bytes(Path(__file__).with_name("task_acceptance.py").read_bytes())
        files = {path.relative_to(root).as_posix(): digest(path.read_bytes()) for path in (source, test_path)}
        snapshot_hash = digest(canonical_json(files).encode())
        test_started = utc_now()
        try:
            process = subprocess.run([sys.executable, "-I", "-B", str(test_path), str(source), model["defaultPriority"]],
                                     cwd=root, capture_output=True, text=True, timeout=20)
            report = json.loads(process.stdout)
            report["exitCode"] = process.returncode
            report["stderr"] = process.stderr[:4000]
            success = process.returncode == 0 and report.get("passed") is True and len(report.get("cases", [])) == 8
        except (subprocess.TimeoutExpired, OSError, ValueError) as error:
            report, success = {"passed": False, "cases": [], "error": str(error)}, False
        ended = utc_now()
        unchanged = all((root / path).is_file() and digest((root / path).read_bytes()) == h for path,h in files.items())
        success = success and unchanged
        report.update({"snapshotHash": snapshot_hash, "modelHash": model["modelHash"], "startedAt": test_started,
                       "endedAt": ended, "filesUnchanged": unchanged, "passed": success, "verifier": "task-priority-v1"})
        report_bytes = (canonical_json(report) + "\n").encode()
        (root / "report.json").write_bytes(report_bytes)
        snapshot(n.after, snapshot_hash)
        def execution(subject, kind, begin, end, status):
            node(subject, kind, "真实执行 " + str(kind).split("#")[-1])
            for p,v in ((DEV.status,Literal(status)),(DEV.scenario,Literal("Operational")),(DEV.actor,Literal("platform-task-slice")),
                        (DEV.executorVersion,Literal("task-priority-v1")),(DEV.inputHash,Literal(model["modelHash"])),
                        (DEV.startedAt,Literal(begin,datatype=XSD.dateTime)),(DEV.endedAt,Literal(end,datatype=XSD.dateTime))): put(subject,p,v)
        execution(n.generationRun, DEV.GenerationRun, started, generated_at, "Succeeded")
        for p,v in ((DEV.underPlan,n.plan),(DEV.executesTask,n.generateTask),(DEV.usesSpecification,n.specification),(DEV.produces,n.artifact)): put(n.generationRun,p,v)
        node(n.artifact, DEV.CodeArtifact, "实际 Task 源码")
        for p,v in ((DEV.targetPath,Literal("src/task.py")),(DEV.contentHash,Literal(files["src/task.py"])),(DEV.inSnapshot,n.after)): put(n.artifact,p,v)
        execution(n.scanRun, DEV.ObservationRun, generated_at, test_started, "Succeeded")
        for p,v in ((DEV.evaluatesSnapshot,n.after),(DEV.scope,Literal("src/task.py; tests/acceptance.py")),(DEV.produces,n.actualGraph)): put(n.scanRun,p,v)
        node(n.actualGraph, DEV.GraphRevision, "真实文件采集图（文件粒度）")
        for p,v in ((DEV.version,Literal(run_id)),(DEV.source,Literal(str(source))),(DEV.graphRole,Literal("Knowledge")),
                    (DEV.graphSpace,Literal("Actual")),(DEV.inModel,n.model),(DEV.inSnapshot,n.after),(DEV.observedBy,n.scanRun),(DEV.containsEntity,n.artifact)): put(n.actualGraph,p,v)
        execution(n.testRun, DEV.VerificationRun, test_started, ended, "Succeeded" if success else "Failed")
        for p,v in ((DEV.usesSpecification,n.verificationSpec),(DEV.evaluatesSnapshot,n.after),(DEV.evaluatesModel,n.model),(DEV.produces,n.evidence)): put(n.testRun,p,v)
        node(n.evidence,DEV.Evidence,"真实验收报告")
        node(n.report,CODE.ImpactAnalysisEntity,"可检索报告文件")
        for p,v in ((DEV.generatedBy,n.testRun),(DEV.evaluatesSnapshot,n.after),(DEV.evaluatesModel,n.model),(DEV.scope,Literal("task creation")),
                    (DEV.reportUri,Literal((root/"report.json").as_uri(),datatype=XSD.anyURI)),(DEV.contentHash,Literal(digest(report_bytes))),
                    (ENG.evidenceArtifact,n.report)): put(n.evidence,p,v)
        assessments = []
        for target in (n.acDefault,n.acValid,n.acInvalid,n.valueClause,n.behaviorClause):
            assessment = URIRef(str(target)+":assessment")
            node(assessment,DEV.SatisfactionAssessment,"输入切片验收判断")
            for p,v in ((DEV.assesses,target),(DEV.evaluatesSnapshot,n.after),(DEV.evaluatesModel,n.model),(DEV.scope,Literal("task creation")),
                        (DEV.status,Literal("Satisfied" if success else "NotSatisfied")),(DEV.actor,Literal("platform-task-slice")),
                        (DEV.rationale,Literal("依据固定 task-priority-v1 验收测试及相同文件快照；不含调度")),(DEV.supportedBy,n.evidence)): put(assessment,p,v)
            assessments.append({"target": str(target), "status": "Satisfied" if success else "NotSatisfied"})
        for obligation, target in ((n.change,n.behaviorClause),(n.verification,n.acInvalid)):
            put(obligation,DEV.status,Literal("Closed" if success else "Open"))
            if success: put(obligation,DEV.closedBy,URIRef(str(target)+":assessment"))
        node(n.release,DEV.ReleaseAssessment,"任务输入切片交付判断")
        for p,v in ((DEV.underPlan,n.plan),(DEV.evaluatesSnapshot,n.after),(DEV.evaluatesModel,n.model),(DEV.scope,Literal("task creation")),
                    (DEV.status,Literal("Ready" if success else "Blocked")),(DEV.actor,Literal("platform-task-slice")),
                    (DEV.rationale,Literal("只评估任务优先级输入；未部署或发布任何应用"))): put(n.release,p,v)
        for a in assessments: graph.add((n.release,DEV.includesAssessment,URIRef(a["target"]+":assessment")))
        validation = registry._validate_graph(graph)
        status = "Ready" if success and validation["conforms"] else "Blocked"
        put(n.release, DEV.status, Literal(status))
        # Runtime identities are unique even when the same saved model runs
        # twice. Business requirements keep their immutable model identities.
        runtime_nodes = {n[key] for key in ("plan", "approval", "generationRun", "artifact", "scanRun", "actualGraph", "after",
                         "testRun", "evidence", "report", "release", "change", "verification")}
        runtime_nodes.update(URIRef(a["target"]+":assessment") for a in assessments)
        def runtime_term(value):
            if value in runtime_nodes:
                return URIRef(str(value).replace(str(n), f"urn:task-execution:{run_id}:"))
            return value
        execution_graph = Graph()
        for s,p,o in graph:
            execution_graph.add((runtime_term(s),p,runtime_term(o)))
        turtle = execution_graph.serialize(format="turtle")
        (root/"evidence.ttl").write_bytes(turtle.encode("utf-8"))
        record = {"runId":run_id,"modelId":model["modelId"],"modelHash":model["modelHash"],"binding":model["binding"],
                  "startedAt":started,"endedAt":ended,"status":status,"directory":str(root),"files":files,"snapshotHash":snapshot_hash,
                  "reportHash":digest(report_bytes),"report":report,"assessments":assessments,"validation":validation,"turtle":turtle,
                  "source":source.read_text(encoding="utf-8"),"evidenceHash":digest(turtle.encode()),"approvedTurtle":approved_turtle}
        self.store.put_development_record(run_id,"run",record)
        return self.run(run_id)

    def run(self, run_id):
        record = self._get("run",run_id)
        root = Path(record["directory"])
        expected = {**record["files"],"report.json":record["reportHash"],"evidence.ttl":record["evidenceHash"],"model.ttl":record["modelHash"]}
        changed = [path for path,h in expected.items() if not (root/path).is_file() or digest((root/path).read_bytes()) != h]
        binding_current = self.service.metamodel_registry().ref == record["binding"]
        return {**record,"currentStatus":record["status"] if not changed and binding_current else "Stale",
                "changedFiles":changed,"bindingCurrent":binding_current}

    def runs(self, model_id):
        self._get("model",model_id)
        return {"runs":[{k:v for k,v in r.items() if k in {"runId","modelId","status","startedAt","endedAt"}}
                        for r in self.store.development_records("run") if r["modelId"] == model_id]}
