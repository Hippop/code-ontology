"""Read-only vocabulary audits and negative fixtures for definition revisions.

These checks complement SHACL; positive examples alone cannot detect removed
constraints. Fixtures are trusted repository code, never supplied by clients.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from pyshacl import validate
from rdflib import Graph, Literal, Namespace, OWL, RDF, RDFS, URIRef

DEV = Namespace("https://example.org/code-ontology/development#")
BIZ = Namespace("https://example.org/code-ontology/business#")
SH = Namespace("http://www.w3.org/ns/shacl#")
OWNED = (
    "https://example.org/code-ontology#",
    str(BIZ), str(DEV),
    "https://example.org/code-ontology/engineering#",
    "https://example.org/code-ontology/planning#",
)
KINDS = (OWL.Class, OWL.ObjectProperty, OWL.DatatypeProperty, OWL.AnnotationProperty)


def _issue(subject: Any, predicate: Any, message: str) -> dict[str, str]:
    return {"entityId": str(subject), "path": str(predicate),
            "shape": "MM_TERM_DECLARED", "message": "MM_TERM_DECLARED: " + message}


def vocabulary_issues(data: Graph, ontology: Graph) -> list[dict[str, str]]:
    """Reserve the installed namespaces; do not infer typo terms into existence."""
    classes = set(ontology.subjects(RDF.type, OWL.Class))
    properties = {term for kind in KINDS[1:] for term in ontology.subjects(RDF.type, kind)}
    issues = []
    for subject, predicate, obj in data:
        if str(predicate).startswith(OWNED) and predicate not in properties:
            issues.append(_issue(subject, predicate, "谓词未在安装本体中声明"))
        if predicate == RDF.type and str(obj).startswith(OWNED) and obj not in classes:
            issues.append(_issue(subject, predicate, f"类型未在安装本体中声明：{obj}"))
    return sorted(issues, key=lambda row: (row["entityId"], row["path"], row["message"]))


def definition_issues(ontology: Graph, shapes: Graph) -> list[dict[str, str]]:
    """Audit named class/property references, not arbitrary metadata IRIs."""
    classes = set(ontology.subjects(RDF.type, OWL.Class))
    properties = {term for kind in KINDS[1:] for term in ontology.subjects(RDF.type, kind)}
    checks = (
        (ontology, RDFS.subClassOf, classes), (ontology, RDFS.domain, classes),
        (ontology, RDFS.range, classes), (ontology, RDFS.subPropertyOf, properties),
        (ontology, OWL.inverseOf, properties), (shapes, SH.targetClass, classes),
        (shapes, SH["class"], classes), (shapes, SH.path, properties),
        (shapes, SH.inversePath, properties), (shapes, SH.targetSubjectsOf, properties),
        (shapes, SH.targetObjectsOf, properties),
    )
    issues = []
    for graph, predicate, declared in checks:
        for subject, obj in graph.subject_objects(predicate):
            if isinstance(obj, URIRef) and str(obj).startswith(OWNED) and obj not in declared:
                issues.append(_issue(subject, predicate, f"定义引用未闭合：{obj}"))
    return sorted(issues, key=lambda row: (row["entityId"], row["path"], row["message"]))


def negative_regressions(ontology: Graph, shapes: Graph, example: Path) -> list[dict[str, Any]]:
    """Each mutation must be rejected by its intended rule, not incidental errors."""
    original = Graph().parse(example, format="turtle")
    t = Namespace("urn:example:task-priority:")
    cases: list[tuple[str, Graph, str]] = []

    def case(name: str, expected: str) -> Graph:
        graph = Graph()
        for triple in original:
            graph.add(triple)
        cases.append((name, graph, expected))
        return graph

    g = case("default-outside-enum", "DEV_DEFAULT_OUTSIDE_ENUM")
    g.set((t.valueClause, DEV.defaultValue, Literal("urgent")))
    for subject, name in ((t.goal, "cross-model-goal"), (t.task, "cross-model-attribute")):
        g = case(name, "DEV_MODEL_LINK")
        for p, o in list(g.predicate_objects(t.model)):
            g.add((t.otherModel, p, o))
        g.set((subject, DEV.inModel, t.otherModel))
    g = case("duplicate-business-id", "MM_CANONICAL_ID_UNIQUE")
    for p, o in list(g.predicate_objects(t.priority)):
        g.add((t.duplicatePriority, p, o))
    g = case("missing-clause-target", "MM_REFERENCE_RESOLVED")
    g.set((t.valueClause, DEV.constrains, URIRef("urn:negative:missing")))
    g = case("missing-mapping-source", "MM_REFERENCE_RESOLVED")
    g.set((t.declaredMapping, DEV.mappingSource, URIRef("urn:negative:missing")))
    g = case("unknown-datatype", "MM_DATATYPE_REGISTERED")
    g.remove((t.valueClause, DEV.allowedValue, None))
    g.remove((t.valueClause, DEV.defaultValue, None))
    g.set((t.valueClause, DEV.valueDatatype, URIRef("urn:negative:datatype")))
    g = case("illustrative-evidence-not-satisfied", "DEV_ASSESSMENT_EVIDENCE")
    g.set((t.assessment, DEV.status, Literal("Satisfied")))

    results = []
    for name, graph, expected in cases:
        conforms, _, report = validate(graph + ontology, ont_graph=ontology,
            shacl_graph=shapes, inference="rdfs", advanced=True)
        results.append({"name": name, "expectedRule": expected,
                        "passed": not bool(conforms) and expected in str(report),
                        "conforms": bool(conforms)})
    return results
