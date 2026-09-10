"""Persist revisioned definition drafts and validate them without installing them."""
from __future__ import annotations

import hashlib
import uuid
from typing import Any

from pyshacl import validate
from rdflib import Graph, OWL, RDF, URIRef

from .errors import invalid, not_found
from .metamodel_registry import DEV, MetamodelRegistry
from .store import SQLiteStore, canonical_json
from .metamodel_quality import definition_issues, negative_regressions

ONTOLOGY_FILE = "ontology/ontology-driven-development.ttl"
SHAPES_FILE = "shapes/ontology-driven-development-shapes.ttl"


class MetamodelAuthoring:
    def __init__(self, registry: MetamodelRegistry, store: SQLiteStore):
        self.registry, self.store = registry, store

    def template(self) -> dict[str, Any]:
        return {"draftId": "", "revision": 0, "name": "开发元模型修订草稿",
                "baseBinding": self.registry.ref,
                "ontology": self.registry._path(ONTOLOGY_FILE).read_text(encoding="utf-8"),
                "shapes": self.registry._path(SHAPES_FILE).read_text(encoding="utf-8")}

    def document(self, body: dict[str, Any]) -> dict[str, Any]:
        self.registry.check_binding(body.get("baseBinding"))
        for key in ("name", "ontology", "shapes"):
            if not isinstance(body.get(key), str) or not body[key].strip():
                raise invalid(f"{key} 必须是非空文本")
        revision = body.get("revision", 0)
        if type(revision) is not int or revision < 0:
            raise invalid("revision 必须是非负整数")
        draft_id = body.get("draftId") or str(uuid.uuid4())
        if not isinstance(draft_id, str) or len(draft_id) > 100:
            raise invalid("draftId 非法")
        return {key: body[key] for key in ("name", "ontology", "shapes", "baseBinding")} | {
            "draftId": draft_id, "revision": revision}

    def save(self, body: dict[str, Any]) -> dict[str, Any]:
        document = self.document(body)
        # Invalid syntax is intentionally saveable as a work-in-progress draft.
        document["contentHash"] = hashlib.sha256(canonical_json({
            key: document[key] for key in ("ontology", "shapes", "baseBinding")
        }).encode()).hexdigest()
        return self.store.save_metamodel_draft(document, document["revision"])

    def history(self, draft_id: str) -> dict[str, Any]:
        revisions = self.store.metamodel_drafts(draft_id)
        if not revisions:
            raise not_found("未找到元模型草稿")
        return {"revisions": revisions}

    def check(self, body: dict[str, Any]) -> dict[str, Any]:
        document = self.document(body)
        ontology, shapes = Graph(), Graph()
        try:
            ontology.parse(data=document["ontology"], format="turtle")
            shapes.parse(data=document["shapes"], format="turtle")
        except Exception as error:
            return {"conforms": False, "stage": "syntax", "report": str(error)[:2000], "examples": []}
        if not any(ontology.subjects(RDF.type, OWL.Class)):
            return {"conforms": False, "stage": "definitions", "report": "定义草稿至少需要一个 owl:Class", "examples": []}
        # Fixed files are replaced in memory; clients cannot select filesystem paths.
        for relative in self.registry.manifest["ontologyFiles"]:
            if relative != ONTOLOGY_FILE:
                ontology.parse(self.registry._path(relative), format="turtle")
        for relative in self.registry.manifest["shapeFiles"]:
            if relative != SHAPES_FILE:
                shapes.parse(self.registry._path(relative), format="turtle")
        results = []
        issues = definition_issues(ontology, shapes)
        if issues:
            return {"conforms": False, "stage": "definitions", "issues": issues,
                    "report": "候选定义存在未声明的类型或属性引用", "examples": []}
        negative_results = []
        try:
            # Validate SHACL syntax before running every installed example against
            # the candidate schema. This is a regression check, not OWL consistency.
            for index, relative in enumerate(self.registry.manifest["examples"]):
                graph = Graph().parse(self.registry._path(relative), format="turtle")
                conforms, _, report = validate(graph + ontology, ont_graph=ontology,
                    shacl_graph=shapes, inference="rdfs", advanced=True, meta_shacl=index == 0)
                results.append({"source": relative, "conforms": bool(conforms), "report": str(report)[:12000]})
            if all(item["conforms"] for item in results):
                negative_results = negative_regressions(ontology, shapes,
                    self.registry._example_path("development-task-priority"))
        except Exception as error:
            return {"conforms": False, "stage": "shapes", "report": str(error)[:3000], "examples": results}
        terms = sorted(str(term) for term in ontology.subjects(RDF.type, OWL.Class)
                       if isinstance(term, URIRef) and str(term).startswith(str(DEV)))
        passed = all(item["conforms"] for item in results) and bool(negative_results) and all(item["passed"] for item in negative_results)
        return {"conforms": passed, "stage": "examples" if passed or not negative_results else "negative-regression",
                "report": ("已检查正例及关键反例；草稿未安装，也不代表已通过完整兼容性或发布审批。"
                           if negative_results else "正例未通过，尚未运行关键反例；草稿未安装。"),
                "examples": results, "negativeExamples": negative_results, "classes": terms}
