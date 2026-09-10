from __future__ import annotations

import json
import unittest
from pathlib import Path

from pyshacl import validate
from rdflib import Graph, Literal, Namespace, RDF, RDFS, OWL


ROOT = Path(__file__).resolve().parents[1]
DEV = Namespace("https://example.org/code-ontology/development#")
ENG = Namespace("https://example.org/code-ontology/engineering#")
T = Namespace("urn:example:task-priority:")


class DevelopmentMetamodelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ontology = Graph()
        cls.shapes = Graph()
        for path in sorted((ROOT / "ontology").glob("*.ttl")):
            cls.ontology.parse(path, format="turtle")
        for path in sorted((ROOT / "shapes").glob("*.ttl")):
            cls.shapes.parse(path, format="turtle")

    def task_graph(self) -> Graph:
        return Graph().parse(ROOT / "examples/development-task-priority.ttl", format="turtle")

    def check_graph(self, graph: Graph) -> tuple[bool, str]:
        conforms, _, report = validate(
            graph + self.ontology,
            shacl_graph=self.shapes,
            ont_graph=self.ontology,
            inference="rdfs",
            advanced=True,
        )
        return bool(conforms), str(report)

    def assert_rejected(self, graph: Graph, message: str) -> None:
        conforms, report = self.check_graph(graph)
        self.assertFalse(conforms, "Invalid development model was accepted")
        self.assertIn(message, report)

    def test_both_examples_conform_with_all_existing_ontologies_and_shapes(self) -> None:
        for path in sorted((ROOT / "examples").glob("development-*.ttl")):
            with self.subTest(path=path.name):
                conforms, report = self.check_graph(Graph().parse(path, format="turtle"))
                self.assertTrue(conforms, report)

    def test_every_new_term_is_documented_and_no_generic_transitivity_is_added(self) -> None:
        ontology = Graph().parse(ROOT / "ontology/ontology-driven-development.ttl", format="turtle")
        for kind in (OWL.Class, OWL.ObjectProperty, OWL.DatatypeProperty, OWL.AnnotationProperty):
            for term in ontology.subjects(RDF.type, kind):
                with self.subTest(term=term):
                    self.assertTrue(list(ontology.objects(term, RDFS.label)))
                    self.assertTrue(list(ontology.objects(term, RDFS.comment)))
        self.assertFalse(list(ontology.triples((None, RDF.type, OWL.TransitiveProperty))))
        self.assertFalse(list(ontology.triples((None, OWL.sameAs, None))))

    def test_manifest_paths_exist_and_version_matches_ontology(self) -> None:
        manifest = json.loads((ROOT / "models/development-metamodel.package.json").read_text(encoding="utf-8"))
        for key in ("ontologyFiles", "shapeFiles", "examples"):
            for path in manifest[key]:
                self.assertTrue((ROOT / path).is_file(), path)
        self.assertTrue((ROOT / manifest["documentation"]).is_file())
        ontology = Graph().parse(ROOT / "ontology/ontology-driven-development.ttl", format="turtle")
        versions = list(ontology.objects(None, OWL.versionInfo))
        self.assertEqual([Literal(manifest["version"])], versions)

    def test_competency_queries_return_meaningful_results(self) -> None:
        graph = self.task_graph() + self.ontology + self.shapes
        paths = sorted((ROOT / "queries/development").glob("*.rq"))
        self.assertEqual(6, len(paths))
        for path in paths:
            with self.subTest(query=path.name):
                rows = list(graph.query(path.read_text(encoding="utf-8")))
                self.assertTrue(rows, path.name)
        trace = list(graph.query(paths[1].read_text(encoding="utf-8")))
        self.assertIn(T.artifact, {row.artifact for row in trace})
        opened = list(graph.query(paths[2].read_text(encoding="utf-8")))
        self.assertEqual({T.change, T.verification}, {row.obligation for row in opened})

    def test_missing_acceptance_criteria_is_rejected(self) -> None:
        graph = self.task_graph()
        graph.remove((T.requirement, DEV.hasAcceptanceCriterion, None))
        self.assert_rejected(graph, "hasAcceptanceCriterion")

    def test_requirement_contract_keeps_single_owner_constraint(self) -> None:
        graph = self.task_graph()
        graph.remove((T.requirement, ENG.definesContract, T.ownedContract))
        self.assert_rejected(graph, "Requirement-owned Contract")

    def test_package_and_requirement_and_task_cycles_are_rejected(self) -> None:
        for subject, predicate, target, message in (
            (T.package, DEV.dependsOnPackage, T.extension, "DEV_PACKAGE_CYCLE"),
            (T.requirement, DEV.refines, T.requirement, "DEV_REQUIREMENT_CYCLE"),
            (T.generateTask, DEV.dependsOnTask, T.testTask, "DEV_TASK_CYCLE"),
        ):
            with self.subTest(message=message):
                graph = self.task_graph()
                graph.add((subject, predicate, target))
                self.assert_rejected(graph, message)

    def test_profile_rejects_unpublished_dependency(self) -> None:
        graph = self.task_graph()
        graph.set((T.package, DEV.status, Literal("Draft")))
        self.assert_rejected(graph, "DEV_PACKAGE_NOT_PUBLISHED")

    def test_default_and_enum_datatype_constraints(self) -> None:
        graph = self.task_graph()
        graph.set((T.valueClause, DEV.defaultValue, Literal("urgent")))
        self.assert_rejected(graph, "DEV_DEFAULT_OUTSIDE_ENUM")
        graph = self.task_graph()
        graph.add((T.valueClause, DEV.allowedValue, Literal(1)))
        self.assert_rejected(graph, "DEV_VALUE_DATATYPE")

    def test_design_cannot_masquerade_as_observed_code(self) -> None:
        graph = self.task_graph()
        graph.add((T.artifact, RDF.type, DEV.DesignElement))
        self.assert_rejected(graph, "NotConstraintComponent")
        graph = self.task_graph()
        graph.set((T.declaredMapping, DEV.status, Literal("Observed")))
        self.assert_rejected(graph, "DEV_OBSERVED_MAPPING")

    def test_plan_changes_invalidate_approval(self) -> None:
        graph = self.task_graph()
        graph.set((T.plan, DEV.contentHash, Literal("a" * 64)))
        self.assert_rejected(graph, "DEV_PLAN_APPROVAL")

    def test_generation_requires_authorized_plan_and_locked_context(self) -> None:
        graph = self.task_graph()
        graph.set((T.plan, DEV.status, Literal("Draft")))
        self.assert_rejected(graph, "DEV_GENERATION_AUTHORITY")
        graph = self.task_graph()
        graph.remove((T.rules, DEV.includesRule, T.rule))
        self.assert_rejected(graph, "DEV_GENERATION_CONTEXT")

    def test_generation_path_and_output_must_match(self) -> None:
        for path in ("../escape.py", "/tmp/escape.py", "C:/escape.py", "src/../../escape.py", "src\\escape.py"):
            with self.subTest(path=path):
                graph = self.task_graph()
                graph.set((T.specification, DEV.targetPath, Literal(path)))
                self.assert_rejected(graph, "DEV_PATH")
        graph = self.task_graph()
        graph.remove((T.generationRun, DEV.produces, T.artifact))
        self.assert_rejected(graph, "DEV_GENERATION_OUTPUT")

    def test_failed_verification_still_needs_report(self) -> None:
        graph = self.task_graph()
        graph.set((T.testRun, DEV.status, Literal("Failed")))
        graph.remove((T.testRun, DEV.produces, T.evidence))
        self.assert_rejected(graph, "DEV_VERIFICATION_REPORT")

    def test_stale_evidence_and_wrong_target_are_rejected(self) -> None:
        graph = self.task_graph()
        graph.set((T.evidence, DEV.evaluatesSnapshot, T.before))
        self.assert_rejected(graph, "DEV_EVIDENCE_VERSION")
        graph = self.task_graph()
        graph.remove((T.verificationSpec, DEV.verifies, T.acInvalid))
        self.assert_rejected(graph, "DEV_ASSESSMENT_SCOPE")

    def test_satisfied_requires_successful_operational_evidence(self) -> None:
        graph = self.task_graph()
        graph.set((T.assessment, DEV.status, Literal("Satisfied")))
        self.assert_rejected(graph, "DEV_ASSESSMENT_EVIDENCE")
        graph.set((T.testRun, DEV.scenario, Literal("Operational")))
        graph.set((T.testRun, DEV.status, Literal("Failed")))
        self.assert_rejected(graph, "DEV_ASSESSMENT_EVIDENCE")
        graph.remove((T.assessment, DEV.supportedBy, None))
        self.assert_rejected(graph, "DEV_ASSESSMENT_EVIDENCE")

    def test_closed_obligation_and_ready_release_need_actual_closure(self) -> None:
        graph = self.task_graph()
        graph.set((T.change, DEV.status, Literal("Closed")))
        self.assert_rejected(graph, "DEV_OBLIGATION_CLOSURE")
        graph = self.task_graph()
        graph.set((T.release, DEV.status, Literal("Ready")))
        self.assert_rejected(graph, "DEV_RELEASE_CLOSURE")

    def test_synthetic_complete_closure_then_snapshot_drift(self) -> None:
        # Test-only synthetic data exercises the allowed path, not a real report.
        graph = self.task_graph()
        graph.set((T.testRun, DEV.scenario, Literal("Operational")))
        graph.set((T.assessment, DEV.status, Literal("Satisfied")))
        for target in (T.acDefault, T.acValid, T.behaviorClause):
            assessment = T[f"assessment-{str(target).rsplit(':', 1)[-1]}"]
            for predicate, value in list(graph.predicate_objects(T.assessment)):
                graph.add((assessment, predicate, value))
            graph.set((assessment, DEV.assesses, target))
            graph.add((T.release, DEV.includesAssessment, assessment))
            if target == T.behaviorClause:
                graph.add((T.change, DEV.closedBy, assessment))
        graph.add((T.verification, DEV.closedBy, T.assessment))
        graph.set((T.change, DEV.status, Literal("Closed")))
        graph.set((T.verification, DEV.status, Literal("Closed")))
        graph.set((T.release, DEV.status, Literal("Ready")))
        conforms, report = self.check_graph(graph)
        self.assertTrue(conforms, report)
        graph.set((T.release, DEV.evaluatesSnapshot, T.before))
        self.assert_rejected(graph, "DEV_RELEASE_CLOSURE")

    def test_cross_project_snapshot_is_rejected(self) -> None:
        graph = self.task_graph()
        graph.add((T.otherProject, RDF.type, DEV.Project))
        graph.add((T.otherProject, RDFS.label, Literal("other")))
        graph.set((T.after, DEV.forProject, T.otherProject))
        self.assert_rejected(graph, "DEV_PROJECT_CONTEXT")

    def test_fact_graph_rejects_design_nodes_and_wrong_snapshot(self) -> None:
        graph = self.task_graph()
        graph.add((T.actualGraph, DEV.containsEntity, T.design))
        self.assert_rejected(graph, "DEV_FACT_DESIGN_SEPARATION")
        graph = self.task_graph()
        graph.set((T.artifact, DEV.inSnapshot, T.before))
        self.assert_rejected(graph, "DEV_FACT_DESIGN_SEPARATION")

    def test_generation_cannot_silently_skip_verifying_preserved_semantics(self) -> None:
        graph = self.task_graph()
        graph.remove((T.verificationSpec, DEV.verifies, T.valueClause))
        self.assert_rejected(graph, "DEV_PRESERVATION_VERIFICATION")


if __name__ == "__main__":
    unittest.main()
