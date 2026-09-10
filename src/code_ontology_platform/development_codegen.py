"""Deterministic execution of the first concrete development metamodel rule.

The adapter is deliberately narrow: it executes the rule represented by a
GenerationSpecification whose design represents a BusinessAttribute backed by
a ValueConstraint and BehaviorClause, and emits a Python dataclass with an
explicit enum/default validation boundary. Unsupported rule patterns fail
closed instead of being interpreted heuristically.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path, PurePosixPath
from typing import Any

from rdflib import Graph, Literal, Namespace, RDF, RDFS, URIRef

from .errors import PlatformError, invalid

DEV = Namespace("https://example.org/code-ontology/development#")
XSD = Namespace("http://www.w3.org/2001/XMLSchema#")


def _local(value: Any) -> str:
    text = str(value or "")
    return re.split(r"[#/:]", text)[-1]


def _label(graph: Graph, subject: URIRef) -> str:
    value = graph.value(subject, RDFS.label)
    return str(value or _local(subject))


def _one(graph: Graph, subject: URIRef, predicate: URIRef, name: str) -> URIRef | Literal:
    values = list(graph.objects(subject, predicate))
    if len(values) != 1:
        raise invalid(f"生成规范 {name} 必须恰好有一个值", {"count": len(values)})
    return values[0]


def _safe_identifier(value: str, *, pascal: bool = False) -> str:
    parts = [part for part in re.split(r"[^A-Za-z0-9]+", value) if part]
    if not parts:
        raise invalid("生成规范无法推导 Python 标识符", {"value": value})
    result = "".join(part[:1].upper() + part[1:] for part in parts) if pascal else "_".join(parts).lower()
    if result[0].isdigit():
        result = "_" + result
    if result in {"class", "def", "from", "import", "pass", "return", "raise", "try", "except", "if", "else"}:
        result += "_"
    return result


def _graph_hash(graph: Graph) -> str:
    triples = sorted(
        f"{subject.n3()} {predicate.n3()} {obj.n3()} ."
        for subject, predicate, obj in graph
    )
    return hashlib.sha256("\n".join(triples).encode("utf-8")).hexdigest()


class DevelopmentCodeGenerator:
    """Execute one explicitly supported dev:TransformationRule adapter."""

    adapter_id = "python-enum-dataclass-v1"

    def __init__(self, graph: Graph) -> None:
        self.graph = graph
        self.input_hash = _graph_hash(graph)

    def specifications(self) -> list[URIRef]:
        return sorted(
            (subject for subject in self.graph.subjects(RDF.type, DEV.GenerationSpecification) if isinstance(subject, URIRef)),
            key=str,
        )

    def _select_specification(self, value: str | None) -> URIRef:
        specs = self.specifications()
        if value:
            selected = URIRef(value)
            if selected not in specs:
                raise invalid("Turtle 中不存在该 GenerationSpecification", {"specification": value})
            return selected
        if len(specs) != 1:
            raise invalid("必须明确选择唯一的 GenerationSpecification", {"candidates": [str(item) for item in specs]})
        return specs[0]

    def _authorized(self, specification: URIRef) -> tuple[URIRef, URIRef]:
        tasks = sorted(self.graph.subjects(DEV.usesSpecification, specification), key=str)
        candidates: list[tuple[URIRef, URIRef]] = []
        for task in tasks:
            if not isinstance(task, URIRef):
                continue
            mode = str(self.graph.value(task, DEV.mode) or "")
            if mode != "Template":
                continue
            for plan in self.graph.subjects(DEV.hasTask, task):
                status = str(self.graph.value(plan, DEV.status) or "")
                if isinstance(plan, URIRef) and status == "Approved":
                    candidates.append((task, plan))
        if len(candidates) != 1:
            raise invalid(
                "生成规范必须由一个已批准计划中的 Template 任务授权",
                {"specification": str(specification), "candidateCount": len(candidates)},
            )
        return candidates[0]

    def _model_projection(self, specification: URIRef) -> dict[str, Any]:
        rule = _one(self.graph, specification, DEV.appliesRule, "appliesRule")
        design = _one(self.graph, specification, DEV.inputDesign, "inputDesign")
        technology = _one(self.graph, specification, DEV.usesTechnology, "usesTechnology")
        if not isinstance(rule, URIRef) or not isinstance(design, URIRef) or not isinstance(technology, URIRef):
            raise invalid("生成规范的规则、设计和技术栈必须是 IRI")
        if str(rule) not in {str(item) for item in self.graph.subjects(RDF.type, DEV.TransformationRule)}:
            raise invalid("生成规范引用的规则不是 TransformationRule")
        output_pattern = str(self.graph.value(rule, DEV.outputPattern) or "")
        language = " ".join(str(value) for value in self.graph.objects(technology, DEV.language))
        if "python" not in f"{output_pattern} {language}".lower() or "数据类" not in output_pattern:
            raise invalid(
                "当前执行器只支持 Python 数据类枚举校验规则",
                {"outputPattern": output_pattern, "adapter": self.adapter_id},
            )
        represented = _one(self.graph, design, DEV.represents, "design.represents")
        if not isinstance(represented, URIRef):
            raise invalid("TechnicalRepresentation 必须表示一个业务属性")
        concepts = [subject for subject in self.graph.subjects(DEV.hasAttribute, represented) if isinstance(subject, URIRef)]
        if len(concepts) != 1:
            raise invalid("业务属性必须恰好属于一个业务概念", {"attribute": str(represented), "count": len(concepts)})
        clauses = [subject for subject in self.graph.subjects(DEV.constrains, represented) if isinstance(subject, URIRef)]
        value_clauses = [subject for subject in clauses if (subject, RDF.type, DEV.ValueConstraint) in self.graph]
        behavior_clauses = [subject for subject in clauses if (subject, RDF.type, DEV.BehaviorClause) in self.graph]
        if len(value_clauses) != 1 or len(behavior_clauses) != 1:
            raise invalid("属性必须有一个 ValueConstraint 和一个 BehaviorClause", {"value": len(value_clauses), "behavior": len(behavior_clauses)})
        value_clause, behavior_clause = value_clauses[0], behavior_clauses[0]
        allowed = [str(value) for value in self.graph.objects(value_clause, DEV.allowedValue)]
        default = self.graph.value(value_clause, DEV.defaultValue)
        if not allowed or default is None or str(default) not in allowed:
            raise invalid("ValueConstraint 必须声明允许值，且默认值必须在允许值中")
        preserved = {str(value) for value in self.graph.objects(specification, DEV.preserves)}
        if str(value_clause) not in preserved or str(behavior_clause) not in preserved:
            raise invalid("生成规范必须显式保留值约束和行为条款")
        target = str(_one(self.graph, specification, DEV.targetPath, "targetPath"))
        path = PurePosixPath(target)
        if path.is_absolute() or ".." in path.parts or path.suffix != ".py":
            raise invalid("targetPath 必须是仓库内相对 Python 文件", {"targetPath": target})
        concept_name = _label(self.graph, concepts[0])
        # Prefer a stable local identifier from the URI when labels contain prose.
        concept_type = next((str(obj) for obj in self.graph.objects(concepts[0], RDF.type) if isinstance(obj, URIRef) and _local(obj) not in {"BusinessConcept", "Entity"}), "")
        class_seed = _local(concept_type) or concept_name.replace("业务对象", "")
        class_seed = re.sub(r"(Concept|Entity)$", "", class_seed) or class_seed
        class_name = _safe_identifier(class_seed, pascal=True)
        canonical = str(self.graph.value(represented, URIRef("https://example.org/code-ontology/business#canonicalId")) or _local(represented))
        field_name = _safe_identifier(canonical.rsplit(".", 1)[-1])
        return {
            "specification": specification,
            "rule": rule,
            "design": design,
            "attribute": represented,
            "valueClause": value_clause,
            "behaviorClause": behavior_clause,
            "className": class_name,
            "fieldName": field_name,
            "allowed": tuple(dict.fromkeys(allowed)),
            "default": str(default),
            "targetPath": path,
            "unsupportedCase": str(self.graph.value(rule, DEV.unsupportedCase) or ""),
            "behavior": str(self.graph.value(behavior_clause, DEV.failureBehavior) or ""),
        }

    def _render(self, projection: dict[str, Any]) -> str:
        allowed = projection["allowed"]
        literal_union = ", ".join(repr(value) for value in allowed)
        allowed_tuple = repr(allowed)
        class_name, field_name = projection["className"], projection["fieldName"]
        return "\n".join([
            '"""Generated from a governed development GenerationSpecification. Do not edit manually."""',
            "",
            "from __future__ import annotations",
            "",
            "from dataclasses import dataclass",
            "from typing import Literal",
            "",
            f"MODEL_INPUT_HASH = {self.input_hash!r}",
            f"GENERATION_ADAPTER = {self.adapter_id!r}",
            f"GENERATION_SPECIFICATION = {str(projection['specification'])!r}",
            f"TRANSFORMATION_RULE = {str(projection['rule'])!r}",
            f"PRESERVED_CLAUSES = {tuple(str(item) for item in (projection['valueClause'], projection['behaviorClause']))!r}",
            f"UNSUPPORTED_CASE = {projection['unsupportedCase']!r}",
            f"FAILURE_BEHAVIOR = {projection['behavior']!r}",
            "",
            f"ALLOWED_{field_name.upper()} = {allowed_tuple}",
            "",
            "@dataclass(frozen=True)",
            f"class {class_name}:",
            f"    {field_name}: Literal[{literal_union}] = {projection['default']!r}",
            "",
            "    def __post_init__(self) -> None:",
            f"        if self.{field_name} not in ALLOWED_{field_name.upper()}:",
            f"            raise ValueError({field_name!r} + \" must be one of \" + repr(ALLOWED_{field_name.upper()}))",
            "",
        ])

    def generate(self, root: str | Path, *, specification: str | None = None, apply: bool = False, overwrite: bool = False, allow_illustrative: bool = False) -> dict[str, Any]:
        selected = self._select_specification(specification)
        task, plan = self._authorized(selected)
        projection = self._model_projection(selected)
        if apply and not allow_illustrative:
            run_subjects = [
                subject
                for subject, kind in self.graph.subject_objects(RDF.type)
                if _local(kind) in {"ExecutionRun", "GenerationRun", "VerificationRun", "ObservationRun"}
            ]
            illustrative = [str(value) for subject in run_subjects for value in self.graph.objects(subject, DEV.scenario)]
            if "Illustrative" in illustrative:
                raise PlatformError(409, "ILLUSTRATIVE_EXECUTION", "示例图包含 Illustrative 执行记录；应用前必须使用 Operational 模型或明确 allowIllustrative")
        root_path = Path(root).resolve()
        target = (root_path / projection["targetPath"]).resolve()
        if root_path not in target.parents:
            raise invalid("生成目标必须位于仓库根目录内")
        source = self._render(projection)
        content_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
        status = "Preview"
        if apply:
            existed = target.exists()
            if existed and not overwrite:
                raise FileExistsError(f"生成目标已存在: {projection['targetPath']}")
            target.parent.mkdir(parents=True, exist_ok=True)
            if existed and target.read_text(encoding="utf-8") == source:
                status = "Unchanged"
            else:
                target.write_bytes(source.encode("utf-8"))
                status = "Updated" if existed else "Created"
        return {
            "applied": apply,
            "artifactCount": 1,
            "inputHash": self.input_hash,
            "adapter": self.adapter_id,
            "specification": str(selected),
            "task": str(task),
            "plan": str(plan),
            "artifacts": [{"targetPath": str(projection["targetPath"]), "contentHash": content_hash, "status": status, "source": source}],
        }
