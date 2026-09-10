import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rdflib import Graph, RDF, Literal

from code_ontology_platform.development_codegen import DEV
from code_ontology_platform.development_slice import DevelopmentSlice
from code_ontology_platform.errors import PlatformError
from code_ontology_platform.metamodel_registry import MetamodelRegistry
from code_ontology_platform.service import PlatformService
from code_ontology_platform.store import SQLiteStore

ROOT = Path(__file__).resolve().parents[1]


class DevelopmentSliceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = MetamodelRegistry(ROOT)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database = Path(self.directory.name)/"slice.db"
        self.service = PlatformService(SQLiteStore(self.database), ROOT/"rules/requirement-change-planning-rules.yaml")
        self.service.metamodel_registry = lambda: self.registry
        self.slice = DevelopmentSlice(self.service)

    def test_real_execution_persistence_and_tampered_snapshot_invalidates_assessment(self):
        model = self.slice.save({"name":"任务输入", "defaultPriority":"high"})
        self.assertNotIn('"Illustrative"', model["turtle"])
        run = self.slice.execute({"modelId":model["modelId"]})
        self.assertEqual("Ready",run["currentStatus"])
        self.assertEqual(8,len(run["report"]["cases"]))
        self.assertTrue(self.registry.validate_turtle(run["turtle"])["conforms"])
        graph = Graph().parse(data=run["turtle"],format="turtle")
        self.assertTrue(list(graph.subjects(RDF.type,DEV.VerificationRun)))
        self.assertFalse(list(graph.subjects(DEV.scenario,Literal("Illustrative"))))
        reopened = SQLiteStore(self.database)
        self.assertEqual(run["report"],reopened.development_records("run",run["runId"])[0]["report"])
        path = Path(run["directory"])/"src/task.py"
        path.write_text(path.read_text(encoding="utf-8")+"\n# changed after test\n", encoding="utf-8")
        stale = self.slice.run(run["runId"])
        self.assertEqual("Stale",stale["currentStatus"])
        self.assertEqual(["src/task.py"],stale["changedFiles"])
        self.assertEqual("Ready",stale["status"])  # historical decision is preserved

    def test_failing_verification_keeps_report_and_open_obligations(self):
        model = self.slice.save({"name":"失败路径"})
        failed = subprocess.CompletedProcess([],1,json.dumps({"passed":False,"cases":[{"name":"default","passed":False}]}),"")
        with patch("code_ontology_platform.development_slice.subprocess.run",return_value=failed):
            run = self.slice.execute({"modelId":model["modelId"]})
        self.assertEqual("Blocked",run["currentStatus"])
        self.assertTrue(Path(run["directory"],"report.json").is_file())
        self.assertTrue(self.registry.validate_turtle(run["turtle"])["conforms"])
        graph = Graph().parse(data=run["turtle"],format="turtle")
        self.assertFalse(list(graph.subjects(DEV.status,Literal("Closed"))))
        self.assertTrue(list(graph.subjects(RDF.type,DEV.Evidence)))

    def test_stale_binding_blocks_before_execution_and_inputs_are_bounded(self):
        with self.assertRaises(PlatformError):
            self.slice.save({"name":"任务", "defaultPriority":"urgent"})
        model = self.slice.save({"name":"旧绑定"})
        current = self.registry.ref
        try:
            self.registry.ref = {**current,"contentHash":"changed"}
            with self.assertRaises(PlatformError) as raised:
                self.slice.execute({"modelId":model["modelId"]})
            self.assertEqual(409,raised.exception.status)
            self.assertFalse((Path(self.directory.name)/"development-runs").exists())
        finally:
            self.registry.ref = current
