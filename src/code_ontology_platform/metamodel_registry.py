"""Repository-pinned OWL/SHACL catalogue, projections and read-only queries."""
from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

from pyshacl import validate
from rdflib import BNode, Graph, Literal, Namespace, RDF, RDFS, OWL, URIRef
from rdflib.compare import to_canonical_graph

from .errors import PlatformError, invalid, not_found
from .metamodel_quality import definition_issues, vocabulary_issues

DEV = Namespace("https://example.org/code-ontology/development#")
SH = Namespace("http://www.w3.org/ns/shacl#")
PREFIXES = {
    "code": "https://example.org/code-ontology#",
    "biz": "https://example.org/code-ontology/business#",
    "eng": "https://example.org/code-ontology/engineering#",
    "plan": "https://example.org/code-ontology/planning#",
    "dev": str(DEV), "rdf": str(RDF), "rdfs": str(RDFS), "owl": str(OWL),
    "sh": str(SH), "xsd": "http://www.w3.org/2001/XMLSchema#",
}
KINDS = {OWL.Class: "Class", OWL.ObjectProperty: "ObjectProperty", OWL.DatatypeProperty: "DatatypeProperty"}
# Used only as a cheap preflight for unbound legacy JSON. Bound models are
# validated against the actual installed catalogue, so this list is not an
# identity source of truth.
DEV_SHORT_NAMES = frozenset({
    "Entity", "VersionedAsset", "MetamodelPackage", "DomainExtension", "ConstraintSet", "RuleSet", "Project", "ProjectProfile", "ModelRevision", "CodeSnapshot", "GraphRevision", "MigrationPlan",
    "BusinessGoal", "BusinessConcept", "BusinessAttribute", "BusinessRule", "Requirement", "AcceptanceCriterion", "SemanticContract", "ContractClause", "Invariant", "BehaviorClause", "ValueConstraint",
    "DesignDecision", "DesignElement", "TechnicalRepresentation", "ImplementationSlice", "RealizationMapping", "SemanticDelta", "Obligation", "ChangeObligation", "VerificationObligation", "ChangePlan", "Approval",
    "TechnologyProfile", "TransformationRule", "ImpactRule", "GenerationSpecification", "ImplementationTask", "ExecutionRun", "GenerationRun", "ObservationRun", "CodeArtifact", "VerificationSpecification", "VerificationRun", "Evidence", "SatisfactionAssessment", "ImpactAssessment", "ReleaseAssessment",
})
# These names are also part of the pre-existing engineering JSON vocabulary.
# They remain valid on the legacy endpoint when no metamodel binding is
# present; a bound model is resolved strictly against the catalogue instead.
LEGACY_SHARED_SHORT_NAMES = frozenset({"Requirement", "SemanticContract"})


class MetamodelRegistry:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        manifest_path = self.root / "models/development-metamodel.package.json"
        manifest_bytes = manifest_path.read_bytes()
        self.manifest = json.loads(manifest_bytes)
        self.ontology, self.shapes = Graph(), Graph()
        self.sources: dict[str, set[str]] = {}
        self.files: list[dict[str, Any]] = []
        digest = hashlib.sha256(manifest_bytes)
        for key, destination in (("ontologyFiles", self.ontology), ("shapeFiles", self.shapes)):
            for relative in self.manifest[key]:
                raw = self._path(relative).read_bytes()
                digest.update(relative.encode() + b"\0" + raw)
                # Stable blank-node ids make constraint details stable across requests.
                parsed = to_canonical_graph(Graph().parse(data=raw.decode("utf-8"), format="turtle"))
                # Scope blank nodes per document, including identical shapes in different files.
                prefix = hashlib.sha256(relative.encode()).hexdigest()[:16]
                def scoped(term: Any) -> Any:
                    return BNode(prefix + str(term)) if isinstance(term, BNode) else term
                for subject, predicate, obj in parsed:
                    s, p, o = scoped(subject), predicate, scoped(obj)
                    destination.add((s, p, o))
                    self.sources.setdefault(str(s), set()).add(relative)
                self.files.append({"path": relative, "kind": key, "tripleCount": len(parsed), "contentHash": hashlib.sha256(raw).hexdigest()})
        self.ref = {"id": self.manifest["id"], "version": self.manifest["version"], "contentHash": digest.hexdigest()}
        self.terms = {
            str(term): kind for rdf_type, kind in KINDS.items()
            for term in self.ontology.subjects(RDF.type, rdf_type) if isinstance(term, URIRef)
        }
        self.graph = self.ontology + self.shapes
        self.definition_issues = definition_issues(self.ontology, self.shapes)

    def _path(self, relative: str) -> Path:
        path = (self.root / relative).resolve()
        if self.root not in path.parents or not path.is_file():
            raise invalid("元模型清单引用了无效的仓库文件", {"path": relative})
        return path

    def check_revision(self, revision: str | None) -> None:
        if revision is not None and revision != self.ref["contentHash"]:
            raise PlatformError(409, "METAMODEL_REVISION_CHANGED", "元模型文件已变化，请重新装载并复核模型绑定")

    def check_binding(self, value: Any) -> None:
        if not isinstance(value, Mapping) or any(value.get(k) != v for k, v in self.ref.items()):
            raise PlatformError(409, "METAMODEL_BINDING_MISMATCH", "模型绑定的元模型版本或内容已失效，请重新绑定并校验")

    def compact(self, iri: str) -> str:
        for prefix, namespace in sorted(PREFIXES.items(), key=lambda item: -len(item[1])):
            if iri.startswith(namespace):
                return f"{prefix}:{iri[len(namespace):]}"
        return iri

    def resolve(self, value: Any, kind: str | None = None) -> URIRef:
        if not isinstance(value, str):
            raise invalid("类型或属性标识必须是字符串")
        iri = value
        if ":" in value and value.split(":", 1)[0] in PREFIXES:
            prefix, local = value.split(":", 1)
            iri = PREFIXES[prefix] + local
        if iri not in self.terms and ":" not in value:
            matches = [term for term in self.terms if self.compact(term).split(":")[-1] == value and (kind is None or self.terms[term] == kind)]
            if len(matches) != 1:
                raise invalid("短名称不存在或有歧义，请使用完整 IRI", {"term": value, "candidates": sorted(matches)})
            iri = matches[0]
        if iri not in self.terms or (kind is not None and self.terms[iri] != kind):
            raise invalid("元模型中不存在该类型或属性", {"term": value, "expectedKind": kind})
        return URIRef(iri)

    def ancestors(self, term: URIRef) -> list[URIRef]:
        found, pending = {term}, [term]
        while pending:
            current = pending.pop()
            for parent in self.ontology.objects(current, RDFS.subClassOf):
                if isinstance(parent, URIRef) and parent not in found:
                    found.add(parent)
                    pending.append(parent)
        return sorted(found, key=str)

    def text(self, term: URIRef, predicate: URIRef) -> str:
        values = list(self.ontology.objects(term, predicate))
        values.sort(key=lambda v: (getattr(v, "language", None) != "zh", str(v)))
        return str(values[0]) if values else ""

    def summary(self, iri: str) -> dict[str, Any]:
        term = URIRef(iri)
        ancestors = self.ancestors(term)
        return {
            "iri": iri, "name": self.compact(iri), "kind": self.terms[iri],
            "label": self.text(term, RDFS.label) or self.compact(iri),
            "description": self.text(term, RDFS.comment),
            "parents": sorted(str(p) for p in self.ontology.objects(term, RDFS.subClassOf) if isinstance(p, URIRef)),
            "layers": sorted({str(v) for a in ancestors for v in self.ontology.objects(a, DEV.semanticLayer)}),
            "sources": sorted(self.sources.get(iri, [])),
        }

    def catalog(self) -> dict[str, Any]:
        return {"binding": self.ref, "terms": [self.summary(iri) for iri in sorted(self.terms)],
                "files": self.files, "examples": [Path(p).stem for p in self.manifest["examples"]],
                "queries": [p.stem for p in sorted(self._query_paths())],
                "storage": "Repository files; one installed revision", "prefixes": PREFIXES,
                "definitionIssues": self.definition_issues}

    def _node(self, value: Any, seen: frozenset = frozenset()) -> Any:
        if isinstance(value, Literal):
            return {"value": str(value), "datatype": str(value.datatype) if value.datatype else None, "language": value.language}
        if not isinstance(value, BNode):
            return str(value)
        if value in seen or len(seen) > 16:
            return {"reference": str(value)}
        seen = seen | {value}
        return {str(p): [self._node(v, seen) for v in sorted(self.graph.objects(value, p), key=str)]
                for p in sorted(set(self.graph.predicates(value)), key=str)}

    def detail(self, iri: str, revision: str | None = None) -> dict[str, Any]:
        self.check_revision(revision)
        term = self.resolve(iri)
        result = self.summary(str(term))
        ancestors = self.ancestors(term)
        result["binding"] = self.ref
        result["ancestors"] = [self.summary(str(a)) for a in ancestors if a != term and str(a) in self.terms]
        result["children"] = [self.summary(str(c)) for c in sorted(self.ontology.subjects(RDFS.subClassOf, term), key=str) if str(c) in self.terms]
        result["relations"] = []
        seen_relations: set[tuple[str, str]] = set()
        for prop, kind in sorted(self.terms.items()):
            if kind == "Class":
                continue
            for role, predicate in (("domain", RDFS.domain), ("range", RDFS.range)):
                targets = set(self.ontology.objects(URIRef(prop), predicate))
                relation_key = (prop, role)
                if targets.intersection(ancestors) and relation_key not in seen_relations:
                    seen_relations.add(relation_key)
                    result["relations"].append({**self.summary(prop), "role": role})
        result["definition"] = {self.compact(str(p)): [self._node(v) for v in sorted(self.ontology.objects(term, p), key=str)]
                                for p in sorted(set(self.ontology.predicates(term)), key=str)}
        result["constraints"] = []
        for ancestor in ancestors:
            for shape in sorted(self.shapes.subjects(SH.targetClass, ancestor), key=str):
                properties = []
                for prop in sorted(self.shapes.objects(shape, SH.property), key=str):
                    properties.append({"id": str(prop), "definition": {self.compact(str(p)): [self._node(v) for v in sorted(self.shapes.objects(prop, p), key=str)] for p in sorted(set(self.shapes.predicates(prop)), key=str)}})
                result["constraints"].append({"iri": str(shape), "targetClass": str(ancestor), "inherited": ancestor != term,
                    "sources": sorted(self.sources.get(str(shape), [])), "properties": properties,
                    "rules": {self.compact(str(p)): [self._node(v) for v in sorted(self.shapes.objects(shape, p), key=str)] for p in sorted(set(self.shapes.predicates(shape)) - {SH.property}, key=str)}})
        # Applicability is also specified by SHACL. Missing domain/range does
        # not mean a property is unavailable (nor should we invent domains).
        for constraint in result["constraints"]:
            shape = URIRef(constraint["iri"])
            for property_shape in self.shapes.objects(shape, SH.property):
                path = self.shapes.value(property_shape, SH.path)
                role = "domain"
                if isinstance(path, BNode):
                    path = self.shapes.value(path, SH.inversePath)
                    role = "range"
                if isinstance(path, URIRef) and str(path) in self.terms:
                    key = (str(path), role)
                    if key not in seen_relations:
                        seen_relations.add(key)
                        result["relations"].append({**self.summary(str(path)), "role": role,
                            "applicability": "SHACL", "sourceShape": str(shape)})
        result["relations"].sort(key=lambda item: (item["iri"], item["role"]))
        result["usage"] = self.usage(term)
        return result

    def usage(self, term: URIRef) -> list[dict[str, str]]:
        found = []
        for relative in self.manifest["examples"]:
            graph = Graph().parse(self._path(relative), format="turtle")
            # Usage evidence is the file's explicit RDF assertions, never inferred production state.
            for subject, predicate, obj in graph:
                if obj == term and predicate in {RDF.type, DEV.definesTerm, RDFS.subClassOf}:
                    found.append({"source": relative, "entityId": str(subject), "relation": self.compact(str(predicate)), "scope": "Example / target model"})
        return sorted(found, key=lambda item: (item["source"], item["entityId"], item["relation"]))

    def _example_path(self, name: str) -> Path:
        matches = [p for p in self.manifest["examples"] if Path(p).stem == name]
        if not matches:
            raise not_found("未知元模型实例")
        return self._path(matches[0])

    def example(self, name: str) -> dict[str, Any]:
        path = self._example_path(name)
        return {"name": name, "binding": self.ref, "source": str(path.relative_to(self.root)), "turtle": path.read_text(encoding="utf-8")}

    def _query_paths(self) -> list[Path]:
        directory = (self.root / self.manifest["queryDirectory"]).resolve()
        if self.root not in directory.parents:
            raise invalid("查询目录不在仓库内")
        return list(directory.glob("*.rq"))

    def query(self, name: str, example: str) -> dict[str, Any]:
        paths = [p for p in self._query_paths() if p.stem == name]
        if not paths:
            raise not_found("未知能力查询")
        graph = self.graph + Graph().parse(self._example_path(example), format="turtle")
        result = graph.query(paths[0].read_text(encoding="utf-8"))
        rows = []
        for row in result:
            if len(rows) == 500:
                break
            rows.append({str(k): str(v) for k, v in row.asdict().items()})
        return {"binding": self.ref, "columns": [str(v) for v in result.vars], "rows": rows, "limit": 500, "example": example}

    def validate_turtle(self, turtle: str) -> dict[str, Any]:
        try:
            graph = Graph().parse(data=turtle, format="turtle")
        except Exception as error:
            raise invalid("Turtle 语法错误", {"reason": str(error)[:600]}) from error
        return self._validate_graph(graph)

    def _validate_graph(self, graph: Graph) -> dict[str, Any]:
        conforms, report, _ = validate(graph + self.ontology, shacl_graph=self.shapes, ont_graph=self.ontology, inference="rdfs", advanced=True)
        issues = [*self.definition_issues, *vocabulary_issues(graph, self.ontology)]
        for result in report.subjects(RDF.type, SH.ValidationResult):
            issues.append({"entityId": str(report.value(result, SH.focusNode) or ""), "path": str(report.value(result, SH.resultPath) or ""),
                           "shape": str(report.value(result, SH.sourceShape) or ""), "message": "；".join(str(x) for x in report.objects(result, SH.resultMessage))})
        issues.sort(key=lambda issue: (issue["entityId"], issue["shape"], issue["message"]))
        return {"conforms": bool(conforms) and not issues, "issueCount": len(issues), "issues": issues,
                "binding": self.ref, "tripleCount": len(graph),
                "completeness": {"status": "Empty" if len(graph) == 0 else "NotEvaluated",
                    "message": "符合性校验不等于项目完整性或需求满足性。"}}

    def bind_legacy(self, model: Mapping[str, Any]) -> dict[str, Any]:
        """Explicit v0 adapter; never silently resolve colliding names in strict models."""
        from .engineering_semantics import CODE, CONTRACTS, VERIFICATION_METHODS, VERIFICATION_OBJECTIVES, VERIFICATION_EVIDENCE
        result = copy.deepcopy(dict(model))
        for node in result.get("nodes", []):
            value = node.get("type", "")
            if not isinstance(value, str):
                raise invalid("实体 type 必须是字符串")
            if ":" not in value:
                if value == "Requirement":
                    # The legacy engineering JSON vocabulary uses the generic
                    # code requirement class.  Keep that meaning explicit;
                    # dev:Requirement is a stricter, model-bound concept.
                    value = "code:Requirement"
                elif value in CODE or value in {"BusinessCapability", "UnitTest", "IntegrationTest", "ContractTest", "TestCase", "EndToEndTest"}:
                    value = "code:" + value
                elif value in CONTRACTS | VERIFICATION_METHODS | VERIFICATION_OBJECTIVES | VERIFICATION_EVIDENCE | {"EngineeringRequirement", "SemanticContract", "OntologyAsset"}:
                    value = "eng:" + value
            node["type"] = str(self.resolve(value, "Class"))
        for edge in result.get("edges", []):
            edge["relation"] = str(self.resolve(edge.get("relation"), "ObjectProperty"))
        result["metamodelRef"] = self.ref
        result["bindingAdapter"] = "engineering-json-v0-explicit"
        return result

    @staticmethod
    def require_supported_generator(model: Mapping[str, Any], registry: MetamodelRegistry | None = None) -> None:
        # The legacy executor does not implement dev obligations or generation rules.
        # Reject them even if a caller removes the binding from an exported model.
        values = [node.get("type", "") for node in model["nodes"]]
        values += [edge.get("relation", "") for edge in model["edges"]]
        for node in model["nodes"]:
            props = node.get("properties", {})
            if not isinstance(props, Mapping):
                raise invalid("properties 必须是对象")
            values.extend(props)
        for value in values:
            if str(value).startswith(("dev:", str(DEV))):
                raise invalid("当前生成后端支持 eng 需求契约模板；dev 生成规范请使用开发本体生成器")
            # Keep the unbound legacy path cheap.  A short name is only a
            # conservative guard here; bound models are checked against the
            # installed catalogue below.  This avoids loading all OWL/SHACL
            # assets for the historical engineering endpoint.
            if isinstance(value, str) and value in DEV_SHORT_NAMES and value not in LEGACY_SHARED_SHORT_NAMES:
                raise invalid("当前生成后端支持 eng 需求契约模板；dev 生成规范请使用开发本体生成器")
            if registry is not None:
                try:
                    resolved = registry.resolve(value)
                except PlatformError:
                    # Legacy unbound models may contain an intentionally
                    # ambiguous short name (for example BusinessCapability).
                    continue
                if str(resolved).startswith(str(DEV)):
                    raise invalid("当前生成后端支持 eng 需求契约模板；dev 生成规范请使用开发本体生成器")

    @staticmethod
    def contains_dev_short_name(model: Mapping[str, Any]) -> bool:
        values: list[Any] = [node.get("type", "") for node in model.get("nodes", []) if isinstance(node, Mapping)]
        values.extend(edge.get("relation", "") for edge in model.get("edges", []) if isinstance(edge, Mapping))
        for node in model.get("nodes", []):
            if isinstance(node, Mapping) and isinstance(node.get("properties"), Mapping):
                values.extend(node["properties"])
        return any(isinstance(value, str) and value in DEV_SHORT_NAMES for value in values)

    def validate_model(self, model: Mapping[str, Any]) -> dict[str, Any]:
        self.check_binding(model.get("metamodelRef"))
        graph = Graph()
        ids = set()
        nodes, edges = model.get("nodes"), model.get("edges")
        if not isinstance(nodes, list) or not isinstance(edges, list):
            raise invalid("模型必须包含 nodes 与 edges 数组")
        for node in nodes:
            if not isinstance(node, Mapping) or not isinstance(node.get("id"), str) or not node["id"].strip():
                raise invalid("每个实体必须具有非空字符串 ID")
            if node["id"] in ids:
                raise invalid("实体 ID 重复", {"entityId": node["id"]})
            ids.add(node["id"])
        expanded_ids = {value: value if ":" in value else "urn:engineering-node:" + value for value in ids}
        for value, iri in expanded_ids.items():
            if not re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", str(iri)) or re.search(r'[\s<>"{}|\\^`]', str(iri)):
                raise invalid("实体 ID 不能包含非法 IRI 字符", {"entityId": value})
        if len(set(expanded_ids.values())) != len(expanded_ids):
            raise invalid("MM_NORMALIZED_ID_UNIQUE: 不同实体 ID 规范化后发生碰撞")
        node_iris = {value: URIRef(iri) for value, iri in expanded_ids.items()}
        for node in nodes:
            subject = node_iris[node["id"]]
            graph.add((subject, RDF.type, self.resolve(node.get("type"), "Class")))
            if node.get("label"):
                graph.add((subject, RDFS.label, Literal(str(node["label"]))))
            props = node.get("properties", {})
            if not isinstance(props, Mapping):
                raise invalid("properties 必须是以属性 IRI 为键的对象")
            for name, value in props.items():
                predicate = self.resolve(name, "DatatypeProperty")
                values = value if isinstance(value, list) else [value]
                for item in values:
                    if isinstance(item, Mapping) and "value" in item:
                        if item.get("datatype") and item.get("language"):
                            raise invalid("literal 不可同时指定 datatype 与 language")
                        literal = Literal(item["value"], datatype=URIRef(item["datatype"]) if item.get("datatype") else None, lang=item.get("language"))
                    elif isinstance(item, (str, int, float, bool)):
                        literal = Literal(item)
                    else:
                        raise invalid("属性值必须是 literal 或带 value/datatype 的对象")
                    graph.add((subject, predicate, literal))
            if "executionStatus" in node:
                graph.add((subject, URIRef(PREFIXES["eng"] + "executionStatus"), Literal(str(node["executionStatus"]))))
        for edge in edges:
            if not isinstance(edge, Mapping) or edge.get("source") not in ids or edge.get("target") not in ids:
                raise invalid("关系两端必须指向模型中存在的实体")
            graph.add((node_iris[edge["source"]], self.resolve(edge.get("relation"), "ObjectProperty"), node_iris[edge["target"]]))
        return self._validate_graph(graph)
