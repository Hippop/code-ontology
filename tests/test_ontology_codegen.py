from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from code_ontology_platform.ontology_codegen import OntologyCodeGenerator, load_model


def model(target: str = "generated/entities.py") -> dict:
    return {
        "graphId": "urn:test:model",
        "revision": "v1",
        "nodes": [
            {"id": "cap:generation", "type": "BusinessCapability"},
            {"id": "req:entity", "type": "EngineeringRequirement", "label": "Generate entity"},
            {
                "id": "contract:entity",
                "type": "SpecificationContract",
                "generation": {
                    "kind": "python-dataclass",
                    "targetPath": target,
                    "symbol": "GeneratedEntity",
                    "fields": [
                        {"name": "entity_id", "type": "str"},
                        {"name": "enabled", "type": "bool", "default": True},
                    ],
                },
            },
        ],
        "edges": [
            {"source": "req:entity", "relation": "eng:specifiesCapability", "target": "cap:generation"},
            {"source": "req:entity", "relation": "eng:definesContract", "target": "contract:entity"},
        ],
    }


class OntologyCodeGeneratorTest(unittest.TestCase):
    def test_dry_run_is_deterministic_and_compilable(self) -> None:
        first = OntologyCodeGenerator(model()).generate(".")
        second = OntologyCodeGenerator(model()).generate(".")
        self.assertEqual(first["inputHash"], second["inputHash"])
        self.assertEqual(first["artifacts"][0]["contentHash"], second["artifacts"][0]["contentHash"])
        compile(first["artifacts"][0]["source"], "generated/entities.py", "exec")

    def test_apply_creates_artifact_and_second_run_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            generator = OntologyCodeGenerator(model())
            result = generator.generate(directory, apply=True)
            self.assertEqual("Created", result["artifacts"][0]["status"])
            target = Path(directory) / "generated/entities.py"
            self.assertTrue(target.is_file())
            repeated = generator.generate(directory, apply=True)
            self.assertEqual("Unchanged", repeated["artifacts"][0]["status"])

    def test_refuses_path_traversal(self) -> None:
        with self.assertRaises(ValueError):
            OntologyCodeGenerator(model("../escape.py")).generate(".")

    def test_registry_is_generated_from_requirement_relationships(self) -> None:
        value = model("generated/registry.py")
        value["nodes"][2]["generation"] = {
            "kind": "python-engineering-registry",
            "targetPath": "generated/registry.py",
        }
        result = OntologyCodeGenerator(value).generate(".")
        source = result["artifacts"][0]["source"]
        self.assertIn("req:entity", source)
        self.assertIn("cap:generation", source)
        self.assertIn("contract:entity", source)

    def test_repository_registry_matches_self_model(self) -> None:
        root = Path(__file__).resolve().parents[1]
        engineering_model = load_model(
            root / "models/code-ontology.engineering-model.json"
        )
        result = OntologyCodeGenerator(engineering_model).generate(root)
        artifact = result["artifacts"][0]
        generated = (root / artifact["targetPath"]).read_text(encoding="utf-8")
        self.assertEqual(artifact["source"], generated)


if __name__ == "__main__":
    unittest.main()
