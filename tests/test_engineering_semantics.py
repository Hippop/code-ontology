from __future__ import annotations

import unittest

from code_ontology_platform.engineering_semantics import EngineeringSemantics


def graph() -> dict:
    return {
        "nodes": [
            {"id": "cap:auth", "type": "BusinessCapability"},
            {"id": "req:token", "type": "EngineeringRequirement"},
            {"id": "contract:spec", "type": "SpecificationContract"},
            {"id": "contract:semantic", "type": "SemanticContract"},
            {"id": "ontology:auth", "type": "OntologyAsset"},
            {"id": "verification:objective", "type": "VerificationObjective"},
            {"id": "verification:test", "type": "TestVerification"},
            {"id": "evidence:test-run", "type": "TestExecutionEvidence"},
            {"id": "code:validator", "type": "Method"},
            {"id": "code:caller", "type": "Method"},
            {"id": "test:token", "type": "UnitTest"},
        ],
        "edges": [
            {"source": "req:token", "relation": "eng:specifiesCapability", "target": "cap:auth"},
            {"source": "req:token", "relation": "eng:definesContract", "target": "contract:spec"},
            {"source": "req:token", "relation": "eng:constrainedBy", "target": "contract:semantic"},
            {"source": "contract:semantic", "relation": "eng:usesOntology", "target": "ontology:auth"},
            {"source": "verification:test", "relation": "eng:derivedFromObjective", "target": "verification:objective"},
            {"source": "verification:test", "relation": "eng:verifiesRequirement", "target": "req:token"},
            {"source": "verification:test", "relation": "eng:satisfiedByEvidence", "target": "evidence:test-run"},
            {"source": "evidence:test-run", "relation": "eng:evidenceArtifact", "target": "test:token"},
            {"source": "code:validator", "relation": "code:implementsRequirement", "target": "req:token"},
            {"source": "test:token", "relation": "code:verifies", "target": "req:token"},
            {"source": "test:token", "relation": "code:covers", "target": "code:validator"},
            {"source": "code:caller", "relation": "code:callsDirectly", "target": "code:validator"},
        ],
    }


class EngineeringSemanticsTest(unittest.TestCase):
    def test_valid_graph_conforms(self) -> None:
        result = EngineeringSemantics(graph()).validate()
        self.assertTrue(result["conforms"], result)

    def test_legacy_requirement_is_not_forced_into_new_governance(self) -> None:
        result = EngineeringSemantics(
            {"nodes": [{"id": "req:legacy", "type": "Requirement"}], "edges": []}
        ).validate()
        self.assertTrue(result["conforms"], result)

    def test_coverage_separates_implementation_and_verification(self) -> None:
        result = EngineeringSemantics(graph()).coverage()
        self.assertEqual(1.0, result["implementation"]["ratio"])
        self.assertEqual(1.0, result["verification"]["ratio"])
        self.assertEqual(1.0, result["verificationEvidence"]["ratio"])

    def test_code_change_crosses_into_requirement_and_verification(self) -> None:
        result = EngineeringSemantics(graph()).impact(["code:validator"], max_depth=4)
        targets = {item["target"] for item in result["impacts"]}
        self.assertIn("code:caller", targets)
        self.assertIn("req:token", targets)
        self.assertIn("contract:spec", targets)
        self.assertIn("verification:test", targets)

    def test_collect_returns_engineering_context_not_arbitrary_neighbors(self) -> None:
        result = EngineeringSemantics(graph()).collect("req:token", depth=2)
        ids = {node["id"] for node in result["nodes"]}
        self.assertIn("cap:auth", ids)
        self.assertIn("contract:spec", ids)
        self.assertIn("code:validator", ids)
        self.assertIn("verification:test", ids)

    def test_invalid_contract_owner_is_reported(self) -> None:
        value = graph()
        value["edges"] = [edge for edge in value["edges"] if edge["target"] != "contract:spec"]
        result = EngineeringSemantics(value).validate()
        self.assertFalse(result["conforms"])
        self.assertIn("CONTRACT_SINGLE_OWNER", {item["code"] for item in result["issues"]})

    def test_ontology_change_propagates_through_semantic_contract(self) -> None:
        result = EngineeringSemantics(graph()).impact(["ontology:auth"], max_depth=4)
        targets = {item["target"] for item in result["impacts"]}
        self.assertIn("contract:semantic", targets)
        self.assertIn("req:token", targets)
        self.assertIn("code:validator", targets)

    def test_verification_change_does_not_fan_out_to_implementation(self) -> None:
        result = EngineeringSemantics(graph()).impact(["verification:test"], max_depth=4)
        targets = {item["target"] for item in result["impacts"]}
        self.assertIn("req:token", targets)
        self.assertNotIn("code:validator", targets)
        self.assertNotIn("contract:spec", targets)

    def test_verification_evidence_requires_auditable_artifact(self) -> None:
        value = graph()
        value["edges"] = [
            edge
            for edge in value["edges"]
            if not (
                edge["source"] == "evidence:test-run"
                and edge["relation"] == "eng:evidenceArtifact"
            )
        ]
        result = EngineeringSemantics(value).validate()
        self.assertFalse(result["conforms"])
        self.assertIn("EVIDENCE_ARTIFACT", {item["code"] for item in result["issues"]})


if __name__ == "__main__":
    unittest.main()
