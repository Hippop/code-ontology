from __future__ import annotations

import copy
import json
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from code_ontology_platform.errors import PlatformError
from code_ontology_platform.http_api import handler_for
from code_ontology_platform.metamodel_registry import MetamodelRegistry, PREFIXES
from code_ontology_platform.service import PlatformService
from code_ontology_platform.store import SQLiteStore

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "rules/requirement-change-planning-rules.yaml"


def sample_model() -> dict:
    return {
        "graphId": "urn:test:metamodel", "revision": "1",
        "nodes": [
            {"id": "urn:test:cap", "type": "BusinessCapability"},
            {"id": "urn:test:req", "type": "EngineeringRequirement"},
            {"id": "urn:test:contract", "type": "SpecificationContract", "generation": {
                "kind": "python-dataclass", "symbol": "Task", "targetPath": "generated/task.py",
                "fields": [{"name": "title", "type": "str"}],
            }},
        ],
        "edges": [
            {"source": "urn:test:req", "relation": "eng:specifiesCapability", "target": "urn:test:cap"},
            {"source": "urn:test:req", "relation": "eng:definesContract", "target": "urn:test:contract"},
        ],
    }


class MetamodelRegistryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = MetamodelRegistry(ROOT)

    def test_catalog_uses_real_definitions_and_disambiguates_names(self) -> None:
        catalog = self.registry.catalog()
        self.assertEqual(9, len(catalog["files"]))
        self.assertEqual(49, sum(t["kind"] == "Class" and t["name"].startswith("dev:") for t in catalog["terms"]))
        self.assertNotEqual(self.registry.resolve("code:BusinessCapability"), self.registry.resolve("biz:BusinessCapability"))
        with self.assertRaises(PlatformError) as error:
            self.registry.resolve("BusinessCapability")
        self.assertEqual(400, error.exception.status)
        self.assertGreaterEqual(len(error.exception.details["candidates"]), 2)

    def test_detail_includes_inherited_shapes_and_property_paths(self) -> None:
        detail = self.registry.detail("dev:Requirement")
        self.assertIn(PREFIXES["eng"] + "EngineeringRequirement", [t["iri"] for t in detail["ancestors"]])
        inherited = [c for c in detail["constraints"] if c["inherited"]]
        self.assertTrue(inherited)
        self.assertTrue(any("sh:path" in p["definition"] for c in inherited for p in c["properties"]))
        self.assertTrue(detail["usage"])
        self.assertTrue(all(c["sources"] for c in detail["constraints"]))

    def test_hash_and_constraint_identifiers_are_deterministic(self) -> None:
        repeated = MetamodelRegistry(ROOT)
        self.assertEqual(self.registry.ref, repeated.ref)
        self.assertEqual(self.registry.detail("dev:Requirement"), repeated.detail("dev:Requirement"))

    def test_installed_file_change_invalidates_old_binding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = ["models/development-metamodel.package.json"] + self.registry.manifest["ontologyFiles"] + self.registry.manifest["shapeFiles"]
            for relative in paths:
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, target)
            target = root / self.registry.manifest["ontologyFiles"][0]
            target.write_text(target.read_text(encoding="utf-8") + "\n# revision test\n", encoding="utf-8")
            changed = MetamodelRegistry(root)
            with self.assertRaises(PlatformError) as error:
                changed.check_binding(self.registry.ref)
            self.assertEqual(409, error.exception.status)

    def test_binding_is_explicit_and_does_not_mutate_input(self) -> None:
        original = sample_model()
        result = self.registry.bind_legacy(original)
        self.assertNotIn("metamodelRef", original)
        self.assertEqual(PREFIXES["code"] + "BusinessCapability", result["nodes"][0]["type"])
        self.assertEqual(self.registry.ref, result["metamodelRef"])
        self.assertTrue(self.registry.validate_model(result)["conforms"])

    def test_bound_self_model_conforms(self) -> None:
        source = json.loads((ROOT / "models/code-ontology.engineering-model.json").read_text(encoding="utf-8"))
        self.assertTrue(self.registry.validate_model(self.registry.bind_legacy(source))["conforms"])

    def test_missing_capability_owner_is_a_real_shacl_violation(self) -> None:
        model = self.registry.bind_legacy(sample_model())
        model["edges"].pop(0)
        result = self.registry.validate_model(model)
        self.assertFalse(result["conforms"])
        self.assertTrue(any(i["entityId"] == "urn:test:req" for i in result["issues"]))

    def test_invalid_identity_binding_and_references_are_rejected(self) -> None:
        base = self.registry.bind_legacy(sample_model())
        for mutation in (
            lambda m: m.update(metamodelRef={}),
            lambda m: m["nodes"].append(copy.deepcopy(m["nodes"][0])),
            lambda m: m["nodes"][0].update(type="biz:Nonexistent"),
            lambda m: m["edges"][0].update(target="missing"),
            lambda m: m["nodes"][0].update(properties={"dev:noSuchProperty": "x"}),
        ):
            with self.subTest(mutation=mutation):
                model = copy.deepcopy(base)
                mutation(model)
                with self.assertRaises(PlatformError):
                    self.registry.validate_model(model)

    def test_example_validation_and_all_read_only_queries(self) -> None:
        example = self.registry.catalog()["examples"][0]
        source = self.registry.example(example)["turtle"]
        self.assertTrue(self.registry.validate_turtle(source)["conforms"])
        for name in self.registry.catalog()["queries"]:
            result = self.registry.query(name, example)
            self.assertTrue(result["columns"], name)
            self.assertLessEqual(len(result["rows"]), 500)
            self.assertEqual(self.registry.ref, result["binding"])
        self.assertEqual(source, self.registry.example(example)["turtle"])

    def test_query_and_example_allowlists_and_turtle_syntax(self) -> None:
        with self.assertRaises(PlatformError):
            self.registry.query("SELECT * WHERE {?s ?p ?o}", "development-task-priority")
        with self.assertRaises(PlatformError):
            self.registry.example("../../README")
        with self.assertRaises(PlatformError):
            self.registry.validate_turtle("not valid turtle")
        # Strict validation also accepts unambiguous short names; generator guards
        # must resolve those identities, not only compare literal namespace prefixes.
        with self.assertRaises(PlatformError):
            MetamodelRegistry.require_supported_generator({"nodes": [{"type": "BusinessGoal"}], "edges": []}, self.registry)


class MetamodelHttpTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = MetamodelRegistry(ROOT)

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.service = PlatformService(SQLiteStore(Path(self.directory.name) / "test.db"), RULES)
        # HTTP contract tests use a pinned loaded registry; file reload is covered above.
        self.service.metamodel_registry = lambda: self.registry
        self.service.store.put_repository({"repositoryId": "test", "name": "Test", "path": self.directory.name, "defaultBranch": "main", "metadata": {}})
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(self.service, api_token="test-token"))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)

    def request(self, path: str, body=None, *, authenticated=True) -> tuple[int, dict]:
        request = urllib.request.Request(f"http://127.0.0.1:{self.server.server_port}{path}",
            data=None if body is None else json.dumps(body).encode(),
            headers={"Content-Type": "application/json", **({"Authorization": "Bearer test-token"} if authenticated else {})})
        try:
            response = urllib.request.urlopen(request, timeout=30)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read())

    def test_catalog_authentication_and_detail_routes(self) -> None:
        self.assertEqual(401, self.request("/api/metamodel/catalog", authenticated=False)[0])
        status, catalog = self.request("/api/metamodel/catalog")
        self.assertEqual(200, status)
        self.assertEqual(self.registry.ref, catalog["binding"])
        self.assertEqual(200, self.request("/api/metamodel/term?iri=dev:Requirement")[0])
        self.assertEqual(409, self.request("/api/metamodel/term?iri=dev:Requirement&revision=stale")[0])
        self.assertEqual(200, self.request("/api/metamodel/example?name=development-task-priority")[0])

    def test_bind_validate_preview_and_apply_real_code(self) -> None:
        status, binding = self.request("/api/metamodel/bind", {"model": sample_model(), "revision": self.registry.ref["contentHash"]})
        self.assertEqual(200, status)
        model = binding["model"]
        status, validation = self.request("/api/metamodel/validate", {"model": model})
        self.assertEqual(200, status)
        self.assertTrue(validation["conforms"])
        body = {"model": model, "repositoryId": "test"}
        status, preview = self.request("/api/ontology-code-generation/preview", body)
        self.assertEqual(200, status, preview)
        self.assertEqual(self.registry.ref, preview["metamodelRef"])
        target = Path(self.directory.name) / "generated/task.py"
        self.assertFalse(target.exists())
        compile(preview["artifacts"][0]["source"], str(target), "exec")
        status, applied = self.request("/api/ontology-code-generation/apply", body)
        self.assertEqual(200, status, applied)
        self.assertTrue(target.exists())
        self.assertEqual(preview["artifacts"][0]["source"], target.read_text(encoding="utf-8"))

    def test_invalid_model_is_blocked_before_writes(self) -> None:
        model = self.registry.bind_legacy(sample_model())
        model["edges"].pop(0)
        status, result = self.request("/api/engineering-semantics/analyze", {"model": model})
        self.assertEqual(200, status)
        self.assertFalse(result["metamodelValidation"]["conforms"])
        status, _ = self.request("/api/ontology-code-generation/apply", {"repositoryId": "test", "model": model})
        self.assertEqual(400, status)
        self.assertFalse((Path(self.directory.name) / "generated").exists())

    def test_stale_binding_and_unbound_dev_cannot_bypass_generation(self) -> None:
        model = self.registry.bind_legacy(sample_model())
        model["metamodelRef"] = {**model["metamodelRef"], "contentHash": "stale"}
        self.assertEqual(409, self.request("/api/ontology-code-generation/apply", {"repositoryId": "test", "model": model})[0])
        model.pop("metamodelRef")
        model["nodes"].append({"id": "urn:test:obligation", "type": "dev:ChangeObligation"})
        self.assertEqual(400, self.request("/api/ontology-code-generation/apply", {"repositoryId": "test", "model": model})[0])
        self.assertFalse((Path(self.directory.name) / "generated").exists())
        model["nodes"][-1]["type"] = "BusinessGoal"
        self.assertEqual(400, self.request("/api/ontology-code-generation/apply", {"repositoryId": "test", "model": model})[0])

    def test_precommit_merges_metamodel_violation(self) -> None:
        model = self.registry.bind_legacy(sample_model())
        model["edges"].pop(0)
        with patch("code_ontology_platform.service.PreCommitVerifier") as verifier:
            verifier.return_value.verify.return_value = {"status": "ReadyToCommit", "blockers": []}
            result = self.service.verify_precommit({"repositoryId": "test", "model": model})
        self.assertEqual("BlockCommit", result["status"])
        self.assertEqual("METAMODEL_CONSTRAINT_VIOLATION", result["blockers"][0]["code"])

    def test_query_endpoint_and_error_contracts(self) -> None:
        query = self.registry.catalog()["queries"][1]
        self.assertEqual(200, self.request("/api/metamodel/query", {"query": query, "example": "development-task-priority"})[0])
        self.assertEqual(404, self.request("/api/metamodel/query", {"query": "../escape", "example": "development-task-priority"})[0])
        self.assertEqual(400, self.request("/api/metamodel/validate", {"turtle": "bad turtle"})[0])
        self.assertEqual(400, self.request("/api/metamodel/bind", {"model": {"nodes": [{"type": None}], "edges": []}})[0])


if __name__ == "__main__":
    unittest.main()
