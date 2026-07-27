from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from pyshacl import validate
from rdflib import Graph

from .errors import invalid


def _paths(values: Iterable[str | Path], name: str) -> list[Path]:
    result = [Path(value) for value in values]
    if not result:
        raise invalid(f"{name} 至少需要一个 Turtle 文件")
    missing = [str(path) for path in result if not path.is_file()]
    if missing:
        raise invalid(f"{name} 包含不存在的文件", {"missing": missing})
    return result


def _load_graph(paths: list[Path]) -> Graph:
    graph = Graph()
    for path in paths:
        try:
            graph.parse(path, format="turtle")
        except Exception as error:
            raise invalid(f"Turtle 解析失败: {path}: {error}") from error
    return graph


def validate_semantic_assets(
    *,
    ontology_files: Iterable[str | Path],
    shape_files: Iterable[str | Path],
    data_files: Iterable[str | Path],
) -> dict[str, Any]:
    """Parse ontologies and run every data graph against the combined SHACL graph."""

    ontologies = _paths(ontology_files, "ontology_files")
    shapes = _paths(shape_files, "shape_files")
    data = _paths(data_files, "data_files")
    ontology_graph = _load_graph(ontologies)
    shape_graph = _load_graph(shapes)

    results: list[dict[str, Any]] = []
    for path in data:
        data_graph = _load_graph([path])
        conforms, report_graph, report_text = validate(
            data_graph + ontology_graph,
            shacl_graph=shape_graph,
            ont_graph=ontology_graph,
            inference="rdfs",
            advanced=True,
            abort_on_first=False,
        )
        result: dict[str, Any] = {
            "file": str(path),
            "conforms": bool(conforms),
            "dataTripleCount": len(data_graph),
            "reportTripleCount": len(report_graph),
        }
        if not conforms:
            result["report"] = report_text
        results.append(result)

    return {
        "conforms": all(item["conforms"] for item in results),
        "ontologyFiles": [str(path) for path in ontologies],
        "shapeFiles": [str(path) for path in shapes],
        "ontologyTripleCount": len(ontology_graph),
        "shapeTripleCount": len(shape_graph),
        "results": results,
    }
