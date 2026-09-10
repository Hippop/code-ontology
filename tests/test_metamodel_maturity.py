from __future__ import annotations

import copy
from pathlib import Path
import unittest

from rdflib import Graph, Literal, Namespace, OWL, RDF, RDFS, URIRef

from code_ontology_platform.errors import PlatformError
from code_ontology_platform.metamodel_authoring import MetamodelAuthoring
from code_ontology_platform.metamodel_quality import definition_issues, negative_regressions
from code_ontology_platform.metamodel_registry import DEV, MetamodelRegistry

ROOT = Path(__file__).resolve().parents[1]
T = Namespace("urn:example:task-priority:")
BIZ = Namespace("https://example.org/code-ontology/business#")


class MetamodelMaturityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = MetamodelRegistry(ROOT)

    def graph(self):
        return Graph().parse(ROOT / "examples/development-task-priority.ttl")

    def rejected(self, graph, rule):
        result = self.registry._validate_graph(graph)
        self.assertFalse(result["conforms"])
        self.assertTrue(any(rule in issue["message"] for issue in result["issues"]), result)

    def other_model(self, graph):
        for predicate, value in list(graph.predicate_objects(T.model)):
            graph.add((T.otherModel, predicate, value))

    def test_definition_closure_and_legacy_business_requirement(self):
        self.assertFalse(self.registry.definition_issues)
        self.assertIn((BIZ.Requirement, RDF.type, OWL.Class), self.registry.ontology)
        self.assertIn((BIZ.Requirement, RDFS.subClassOf, BIZ.BusinessEntity), self.registry.ontology)
        ontology = Graph()
        for triple in self.registry.ontology:
            ontology.add(triple)
        ontology.remove((BIZ.Requirement, RDF.type, OWL.Class))
        self.assertTrue(any(str(BIZ.Requirement) in i["message"]
                            for i in definition_issues(ontology, self.registry.shapes)))

    def test_all_classes_have_definitions_without_new_development_behaviors(self):
        classes = set(self.registry.ontology.subjects(RDF.type, OWL.Class))
        self.assertEqual(241, len(classes))
        self.assertEqual(49, sum(str(c).startswith(str(DEV)) for c in classes))
        for term in classes:
            self.assertTrue(self.registry.text(term, RDFS.label), term)
            self.assertTrue(self.registry.text(term, RDFS.comment), term)
        self.assertEqual("2.0.0", self.registry.ref["version"])

    def test_cross_model_goal_and_attribute_are_rejected(self):
        for subject in (T.goal, T.task):
            with self.subTest(subject=subject):
                g = self.graph()
                self.other_model(g)
                g.set((subject, DEV.inModel, T.otherModel))
                self.rejected(g, "DEV_MODEL_LINK")

    def test_canonical_identity_is_unique_only_within_model(self):
        g = self.graph()
        for p, o in list(g.predicate_objects(T.priority)):
            g.add((T.priority2, p, o))
        self.rejected(g, "MM_CANONICAL_ID_UNIQUE")
        self.other_model(g)
        g.set((T.priority2, DEV.inModel, T.otherModel))
        self.assertTrue(self.registry._validate_graph(g)["conforms"])

    def test_semantic_references_cannot_be_missing_or_wrong_type(self):
        for subject, predicate in ((T.valueClause, DEV.constrains), (T.declaredMapping, DEV.mappingSource)):
            for target in (URIRef("urn:missing:target"), T.repository):
                with self.subTest(predicate=predicate, target=target):
                    g = self.graph()
                    g.set((subject, predicate, target))
                    self.rejected(g, "MM_REFERENCE_RESOLVED")

    def test_unknown_datatype_without_values_is_rejected(self):
        g = self.graph()
        g.remove((T.valueClause, DEV.allowedValue, None))
        g.remove((T.valueClause, DEV.defaultValue, None))
        g.set((T.valueClause, DEV.valueDatatype, URIRef("urn:unsupported:type")))
        self.rejected(g, "MM_DATATYPE_REGISTERED")

    def test_unknown_reserved_predicate_and_type_are_rejected(self):
        g = self.graph()
        g.add((T.priority, DEV.misspelledProperty, Literal("typo")))
        self.rejected(g, "MM_TERM_DECLARED")
        g = self.graph()
        g.add((T.priority, RDF.type, DEV.UnknownAttribute))
        self.rejected(g, "MM_TERM_DECLARED")

    def test_normalized_id_collision_and_illegal_iri_fail_before_projection(self):
        for ids in (("a", "urn:engineering-node:a"), ("urn:bad id", "urn:ok")):
            model = {"metamodelRef": self.registry.ref, "nodes": [
                {"id": value, "type": "code:Repository"} for value in ids], "edges": []}
            original = copy.deepcopy(model)
            with self.assertRaises(PlatformError):
                self.registry.validate_model(model)
            self.assertEqual(original, model)

    def test_declared_existing_file_mapping_remains_legal(self):
        g = self.graph()
        g.set((T.declaredMapping, DEV.mappingTarget, T.artifact))
        self.assertTrue(self.registry._validate_graph(g)["conforms"])

    def test_plan_cannot_use_obligation_from_another_baseline(self):
        g = self.graph()
        g.set((T.delta, DEV.baseline, T.after))
        self.rejected(g, "MM_OBLIGATION_CONTEXT")

    def test_shape_defined_relations_appear_without_inventing_domains(self):
        expected = {
            "dev:GenerationSpecification": {"dev:appliesRule", "dev:inputDesign", "dev:preserves", "dev:usesTechnology", "dev:targetPath"},
            "dev:ValueConstraint": {"dev:valueDatatype", "dev:allowedValue", "dev:defaultValue", "dev:constrains"},
        }
        for name, relations in expected.items():
            detail = self.registry.detail(name)
            outgoing = {r["name"] for r in detail["relations"] if r["role"] == "domain"}
            self.assertLessEqual(relations, outgoing)
        self.assertFalse(list(self.registry.ontology.objects(DEV.appliesRule, RDFS.domain)))

    def test_empty_graph_is_not_presented_as_complete_model(self):
        result = self.registry.validate_turtle("")
        self.assertTrue(result["conforms"])
        self.assertEqual("Empty", result["completeness"]["status"])

    def test_negative_regressions_match_expected_rules(self):
        results = negative_regressions(self.registry.ontology, self.registry.shapes,
                                       ROOT / "examples/development-task-priority.ttl")
        self.assertEqual(8, len(results))
        for result in results:
            self.assertTrue(result["passed"], result)

    def test_removing_shapes_cannot_pass_candidate_check(self):
        authoring = MetamodelAuthoring(self.registry, None)
        draft = authoring.template()
        draft["shapes"] = "@prefix sh: <http://www.w3.org/ns/shacl#> ."
        checked = authoring.check(draft)
        self.assertFalse(checked["conforms"])
        self.assertEqual("negative-regression", checked["stage"])
        self.assertTrue(any(not item["passed"] for item in checked["negativeExamples"]))
        self.assertEqual(self.registry.example("development-task-priority")["turtle"],
                         (ROOT / "examples/development-task-priority.ttl").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
