import tempfile
import unittest
from pathlib import Path

from code_ontology_platform.errors import PlatformError
from code_ontology_platform.metamodel_authoring import MetamodelAuthoring
from code_ontology_platform.metamodel_registry import MetamodelRegistry
from code_ontology_platform.store import SQLiteStore

ROOT = Path(__file__).resolve().parents[1]


class MetamodelAuthoringTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = MetamodelRegistry(ROOT)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database = Path(self.directory.name) / "drafts.db"
        self.authoring = MetamodelAuthoring(self.registry, SQLiteStore(self.database))

    def test_history_persists_and_stale_writer_cannot_overwrite(self):
        template = self.authoring.template()
        first = self.authoring.save(template)
        second = self.authoring.save({**first, "ontology": first["ontology"] + "\n# second revision\n"})
        with self.assertRaises(PlatformError) as raised:
            self.authoring.save(first)
        self.assertEqual(409, raised.exception.status)
        reopened = MetamodelAuthoring(self.registry, SQLiteStore(self.database))
        revisions = reopened.history(first["draftId"])["revisions"]
        self.assertEqual([2, 1], [item["revision"] for item in revisions])
        self.assertNotEqual(first["contentHash"], second["contentHash"])
        self.assertEqual(template["ontology"], reopened.template()["ontology"])

    def test_draft_validation_uses_candidate_shapes_and_preserves_installed_model(self):
        template = self.authoring.template()
        self.assertTrue(self.authoring.check(template)["conforms"])
        template["shapes"] += '''
dev:DraftBreakingShape a sh:NodeShape ; sh:targetClass dev:Requirement ;
    sh:property [ sh:path dev:statement ; sh:hasValue "impossible requirement" ] .
'''
        checked = self.authoring.check(template)
        self.assertFalse(checked["conforms"])
        self.assertTrue(any(not item["conforms"] for item in checked["examples"]))
        self.assertTrue(self.registry.validate_turtle(self.registry.example("development-task-priority")["turtle"])["conforms"])

    def test_invalid_work_in_progress_can_save_but_cannot_pass_validation(self):
        template = self.authoring.template()
        template["ontology"] = "not turtle"
        saved = self.authoring.save(template)
        self.assertEqual("syntax", self.authoring.check(saved)["stage"])
        saved["baseBinding"] = {**saved["baseBinding"], "contentHash": "stale"}
        with self.assertRaises(PlatformError) as raised:
            self.authoring.save(saved)
        self.assertEqual(409, raised.exception.status)
