from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from rdflib import Graph, Literal, RDF

from code_ontology_platform.development_codegen import DEV, DevelopmentCodeGenerator
from code_ontology_platform.errors import PlatformError
from code_ontology_platform.http_api import handler_for
from code_ontology_platform.service import PlatformService
from code_ontology_platform.store import SQLiteStore

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "rules/requirement-change-planning-rules.yaml"
TASK_TURTLE = (ROOT / "examples/development-task-priority.ttl").read_text(encoding="utf-8")
PLATFORM_TURTLE = (ROOT / "examples/development-code-ontology.ttl").read_text(encoding="utf-8")


class DevelopmentCodeGeneratorTest(unittest.TestCase):
    def graph(self, text: str = TASK_TURTLE) -> Graph:
        return Graph().parse(data=text, format="turtle")

    def test_supported_rule_projects_semantics_into_executable_python(self) -> None:
        result = DevelopmentCodeGenerator(self.graph()).generate(".")
        source = result["artifacts"][0]["source"]
        self.assertEqual("python-enum-dataclass-v1", result["adapter"])
        self.assertEqual("src/task.py", result["artifacts"][0]["targetPath"])
        self.assertIn("class Task:", source)
        self.assertIn("ALLOWED_PRIORITY = ('low', 'medium', 'high')", source)
        compile(source, "src/task.py", "exec")
        namespace: dict[str, object] = {}
        exec(compile(source, "src/task.py", "exec"), namespace)
        self.assertEqual("medium", namespace["Task"]().priority)
        self.assertEqual("high", namespace["Task"]("high").priority)
        with self.assertRaises(ValueError):
            namespace["Task"]("urgent")

    def test_draft_plan_is_not_generation_authority(self) -> None:
        with self.assertRaises(PlatformError) as error:
            DevelopmentCodeGenerator(self.graph(PLATFORM_TURTLE)).generate(".")
        self.assertEqual(400, error.exception.status)
        self.assertIn("已批准计划", error.exception.message)

    def test_apply_requires_explicit_illustrative_override_and_is_safe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(PlatformError) as error:
                DevelopmentCodeGenerator(self.graph()).generate(directory, apply=True, overwrite=True)
            self.assertEqual("ILLUSTRATIVE_EXECUTION", error.exception.code)
            result = DevelopmentCodeGenerator(self.graph()).generate(directory, apply=True, overwrite=True, allow_illustrative=True)
            target = Path(directory) / "src/task.py"
            self.assertEqual("Created", result["artifacts"][0]["status"])
            self.assertEqual(result["artifacts"][0]["source"], target.read_text(encoding="utf-8"))
            repeated = DevelopmentCodeGenerator(self.graph()).generate(directory, apply=True, overwrite=True, allow_illustrative=True)
            self.assertEqual("Unchanged", repeated["artifacts"][0]["status"])

    def test_invalid_target_and_missing_preserved_clause_fail_closed(self) -> None:
        graph = self.graph()
        specification = next(graph.subjects(RDF.type, DEV.GenerationSpecification))
        graph.set((specification, DEV.targetPath, Literal("../escape.py")))
        with self.assertRaises(PlatformError):
            DevelopmentCodeGenerator(graph).generate(".")


class DevelopmentCodegenHttpTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.service = PlatformService(SQLiteStore(Path(self.directory.name) / "test.db"), RULES)
        self.service.store.put_repository({"repositoryId": "dev-test", "name": "dev test", "path": self.directory.name, "defaultBranch": "main", "metadata": {}})
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(self.service))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.shutdown)
        self.addCleanup(self.server.server_close)

    def request(self, path: str, body: dict) -> tuple[int, dict]:
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.server.server_port}{path}",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            response = urllib.request.urlopen(request, timeout=30)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read())

    def test_preview_returns_validation_binding_and_source(self) -> None:
        status, result = self.request("/api/development-code-generation/preview", {"turtle": TASK_TURTLE})
        self.assertEqual(200, status, result)
        self.assertFalse(result["applied"])
        self.assertTrue(result["validation"]["conforms"])
        self.assertEqual(1, result["artifactCount"])
        self.assertEqual("python-enum-dataclass-v1", result["adapter"])

    def test_apply_requires_repository_and_writes_only_with_override(self) -> None:
        body = {"turtle": TASK_TURTLE, "repositoryId": "dev-test", "overwrite": True}
        status, result = self.request("/api/development-code-generation/apply", body)
        self.assertEqual(409, status)
        self.assertEqual("ILLUSTRATIVE_EXECUTION", result["error"]["code"])
        body["allowIllustrative"] = True
        status, result = self.request("/api/development-code-generation/apply", body)
        self.assertEqual(200, status, result)
        self.assertTrue((Path(self.directory.name) / "src/task.py").is_file())
        body["overwrite"] = False
        status, result = self.request("/api/development-code-generation/apply", body)
        self.assertEqual(409, status)
        self.assertEqual("GENERATION_CONFLICT", result["error"]["code"])

    def test_invalid_turtle_and_nonconforming_graph_are_rejected(self) -> None:
        status, result = self.request("/api/development-code-generation/preview", {"turtle": "invalid"})
        self.assertEqual(400, status)
        self.assertEqual("VALIDATION_ERROR", result["error"]["code"])


if __name__ == "__main__":
    unittest.main()
