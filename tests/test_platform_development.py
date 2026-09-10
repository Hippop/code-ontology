import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rdflib import Graph, Literal, RDF

from code_ontology_platform.development_slice import DEV
from code_ontology_platform.errors import PlatformError
from code_ontology_platform.metamodel_registry import MetamodelRegistry
from code_ontology_platform.platform_development import AREAS, PlatformDevelopment
from code_ontology_platform.service import PlatformService
from code_ontology_platform.store import SQLiteStore

ROOT=Path(__file__).resolve().parents[1]


class PlatformDevelopmentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry=MetamodelRegistry(ROOT)

    def setUp(self):
        self.directory=tempfile.TemporaryDirectory(); self.addCleanup(self.directory.cleanup)
        self.store=SQLiteStore(Path(self.directory.name)/"platform.db")
        self.service=PlatformService(self.store,ROOT/"rules/requirement-change-planning-rules.yaml")
        self.service.metamodel_registry=lambda:self.registry
        self.flow=PlatformDevelopment(self.service)

    def approved(self):
        model=self.flow.create({"title":"平台自身业务"})
        preview=self.flow.preview(model["modelId"])
        approval=self.flow.approve({"modelId":model["modelId"],"approvalHash":preview["approvalHash"],"reason":"限定范围测试"})
        return model,preview,approval

    def report(self,model,success=True):
        return {"passed":success,"cases":[{"id":r["id"],"passed":success,"tests":1,"skipped":0} for r in model["requirements"]]}

    def execute_report(self,approval,report):
        result=subprocess.CompletedProcess([],0,json.dumps(report),"")
        with patch("code_ontology_platform.platform_development.subprocess.run",return_value=result):
            return self.flow.execute({"approvalId":approval["approvalId"]})

    def test_model_is_ontology_bound_and_has_nine_distinct_requirement_chains(self):
        model=self.flow.create({})
        graph=Graph().parse(data=model["turtle"],format="turtle")
        self.assertTrue(model["validation"]["conforms"])
        requirements=set(graph.subjects(RDF.type,DEV.Requirement))
        self.assertEqual(9,len(requirements))
        self.assertFalse(requirements & set(graph.subjects(RDF.type,DEV.CodeSnapshot)))
        self.assertFalse(requirements & set(graph.subjects(RDF.type,DEV.ChangePlan)))
        for requirement in requirements:
            self.assertIsNotNone(graph.value(requirement,DEV.hasAcceptanceCriterion))
        self.assertEqual(9,len(set(graph.subjects(RDF.type,DEV.VerificationObligation))))
        self.assertFalse(list(graph.subjects(RDF.type,DEV.Evidence)))
        self.assertFalse(list(graph.subjects(DEV.scenario,Literal("Illustrative"))))
        for _,_,source,test in AREAS:
            self.assertTrue((ROOT/"src/code_ontology_platform"/source).is_file())
            self.assertTrue((ROOT/"tests"/test).is_file())
        child=self.flow.create({"parentModelId":model["modelId"]})
        self.assertEqual(model["modelId"],child["parentModelId"])
        self.assertNotEqual(child["modelId"],model["modelId"])
        self.assertEqual(2,len(self.flow.models()["models"]))

    def test_preview_determinism_explicit_approval_and_stale_baseline(self):
        model,preview,approval=self.approved()
        self.assertEqual(preview,self.flow.preview(model["modelId"]))
        with self.assertRaises(PlatformError): self.flow.execute({"modelId":model["modelId"]})
        with self.assertRaises(PlatformError): self.flow.approve({"modelId":model["modelId"],"approvalHash":"old","reason":"test"})
        with patch.object(self.flow,"_snapshot",return_value={"hash":"changed"}):
            with self.assertRaises(PlatformError) as error: self.flow.execute({"approvalId":approval["approvalId"]})
        self.assertEqual(409,error.exception.status)
        self.assertFalse((Path(self.directory.name)/"platform-development-runs").exists())

    def test_verified_evidence_persists_and_file_tampering_invalidates_current_status(self):
        model,_,approval=self.approved()
        run=self.execute_report(approval,self.report(model))
        self.assertEqual("Ready",run["currentStatus"],run["validation"])
        self.assertTrue(self.registry.validate_turtle(run["turtle"])["conforms"])
        graph=Graph().parse(data=run["turtle"],format="turtle")
        self.assertEqual(9,len(list(graph.subjects(DEV.status,Literal("Closed")))))
        self.assertEqual(9,len(list(graph.subjects(RDF.type,DEV.Evidence))))
        reopened=SQLiteStore(self.store.database)
        self.assertEqual(run["status"],reopened.development_records("platform-run",run["runId"])[0]["status"])
        (Path(run["directory"])/"generated/platform_contract.py").write_text("# tampered\n")
        stale=self.flow.run(run["runId"])
        self.assertEqual("Stale",stale["currentStatus"])
        self.assertEqual("Ready",stale["status"])
        self.assertEqual(["generated/platform_contract.py"],stale["changedFiles"])

    def test_failed_and_empty_reports_never_close_obligations(self):
        model,_,approval=self.approved()
        for report in (self.report(model,False),{"passed":True,"cases":[]}):
            with self.subTest(report=report["passed"]):
                run=self.execute_report(approval,report)
                self.assertEqual("Blocked",run["currentStatus"])
                self.assertTrue(run["validation"]["conforms"],run["validation"])
                graph=Graph().parse(data=run["turtle"],format="turtle")
                self.assertFalse(list(graph.subjects(DEV.status,Literal("Closed"))))
                self.assertTrue((Path(run["directory"])/"report.json").is_file())

    def test_bound_definition_changes_block_execution(self):
        _,_,approval=self.approved()
        with patch.object(self.registry,"ref",{**self.registry.ref,"contentHash":"changed"}):
            with self.assertRaises(PlatformError) as error: self.flow.execute({"approvalId":approval["approvalId"]})
        self.assertEqual(409,error.exception.status)


if __name__=="__main__": unittest.main()
