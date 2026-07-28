from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .errors import invalid
from .store import content_hash

GRAPH_BASELINE_SCHEMA_VERSION = "code-ontology-graph-baseline/v1"
_VOLATILE_KEYS = frozenset(
    {
        "absolutePath",
        "createdAt",
        "revision",
        "revisionId",
        "scannedAt",
        "updatedAt",
        "workspacePath",
    }
)
_REPOSITORY_VOLATILE_KEYS = frozenset({"branch", "dirty", "remote"})


def _is_absolute_path(value: str) -> bool:
    return Path(value).is_absolute() or (
        len(value) > 2 and value[1] == ":" and value[2] in {"\\", "/"}
    )


def _normalize_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for raw_key, item in value.items():
            key = str(raw_key)
            if key in _VOLATILE_KEYS:
                continue
            if key == "path" and isinstance(item, str) and _is_absolute_path(item):
                continue
            normalized[key] = _normalize_value(item)
        return normalized
    if isinstance(value, list):
        return [_normalize_value(item) for item in value]
    return value


def _normalize_node(node: Mapping[str, Any]) -> dict[str, Any]:
    normalized = _normalize_value(node)
    if normalized.get("type") == "Repository":
        for key in _REPOSITORY_VOLATILE_KEYS:
            normalized.pop(key, None)
    return normalized


def _normalize_edge(edge: Mapping[str, Any]) -> dict[str, Any]:
    return _normalize_value(edge)


def build_graph_baseline(
    graph: Mapping[str, Any],
    *,
    repository_id: str,
) -> dict[str, Any]:
    graph_space = str(graph.get("graphSpace") or "current")
    nodes_value = graph.get("nodes")
    edges_value = graph.get("edges")
    if not isinstance(nodes_value, list) or not nodes_value:
        raise invalid("生成图谱基线需要非空 nodes")
    if not isinstance(edges_value, list):
        raise invalid("生成图谱基线需要 edges 数组")
    nodes = sorted(
        (_normalize_node(node) for node in nodes_value if isinstance(node, Mapping)),
        key=lambda item: item["id"],
    )
    edges = sorted(
        (_normalize_edge(edge) for edge in edges_value if isinstance(edge, Mapping)),
        key=lambda item: (
            item["source"],
            item["relation"],
            item["target"],
        ),
    )
    baseline = {
        "schemaVersion": GRAPH_BASELINE_SCHEMA_VERSION,
        "graphSpace": graph_space,
        "repositoryId": repository_id,
        "extractor": graph.get("createdBy"),
        "summary": {
            "nodeCount": len(nodes),
            "edgeCount": len(edges),
        },
        "nodes": nodes,
        "edges": edges,
    }
    baseline["contentHash"] = content_hash(baseline)
    return baseline


def validate_graph_baseline(document: Mapping[str, Any]) -> dict[str, Any]:
    baseline = dict(document)
    if baseline.get("schemaVersion") != GRAPH_BASELINE_SCHEMA_VERSION:
        raise invalid(
            "图谱基线 Schema Version 不受支持",
            {
                "expected": GRAPH_BASELINE_SCHEMA_VERSION,
                "actual": baseline.get("schemaVersion"),
            },
        )
    if not isinstance(baseline.get("nodes"), list) or not isinstance(
        baseline.get("edges"), list
    ):
        raise invalid("图谱基线必须包含 nodes 和 edges 数组")
    if not baseline.get("repositoryId") or not baseline.get("graphSpace"):
        raise invalid("图谱基线缺少 repositoryId 或 graphSpace")
    expected_hash = baseline.get("contentHash")
    without_hash = {
        key: value for key, value in baseline.items() if key != "contentHash"
    }
    actual_hash = content_hash(without_hash)
    if expected_hash != actual_hash:
        raise invalid(
            "图谱基线内容 Hash 校验失败",
            {"expected": expected_hash, "actual": actual_hash},
        )
    return baseline


def load_graph_baseline(path: str | Path) -> dict[str, Any]:
    baseline_path = Path(path).resolve()
    try:
        document = json.loads(baseline_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise invalid(f"图谱基线文件不存在: {baseline_path}") from error
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise invalid(f"无法读取图谱基线: {error}") from error
    if not isinstance(document, dict):
        raise invalid("图谱基线根节点必须是 JSON Object")
    return validate_graph_baseline(document)


def write_graph_baseline(
    path: str | Path,
    baseline: Mapping[str, Any],
) -> Path:
    validated = validate_graph_baseline(baseline)
    baseline_path = Path(path).resolve()
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    serialized = (
        json.dumps(validated, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=baseline_path.parent,
            prefix=f".{baseline_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(serialized)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, baseline_path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return baseline_path


def _field_changes(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
) -> list[str]:
    return [
        field
        for field in sorted(before.keys() | after.keys())
        if content_hash(before.get(field)) != content_hash(after.get(field))
    ]


def compare_graph_baseline(
    expected_value: Mapping[str, Any],
    actual_graph: Mapping[str, Any],
    *,
    limit: int = 200,
) -> dict[str, Any]:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 2000:
        raise invalid("limit 必须是 1 到 2000 的整数")
    expected = validate_graph_baseline(expected_value)
    actual = build_graph_baseline(
        actual_graph,
        repository_id=str(expected["repositoryId"]),
    )
    baseline_field_changes = _field_changes(
        {
            "schemaVersion": expected["schemaVersion"],
            "graphSpace": expected["graphSpace"],
            "repositoryId": expected["repositoryId"],
            "extractor": expected.get("extractor"),
        },
        {
            "schemaVersion": actual["schemaVersion"],
            "graphSpace": actual["graphSpace"],
            "repositoryId": actual["repositoryId"],
            "extractor": actual.get("extractor"),
        },
    )
    expected_nodes = {node["id"]: node for node in expected["nodes"]}
    actual_nodes = {node["id"]: node for node in actual["nodes"]}
    node_differences: list[dict[str, Any]] = []
    node_counts = {"Added": 0, "Removed": 0, "Modified": 0, "Unchanged": 0}
    for entity_id in sorted(expected_nodes.keys() | actual_nodes.keys()):
        before = expected_nodes.get(entity_id)
        after = actual_nodes.get(entity_id)
        if before is None:
            status = "Added"
        elif after is None:
            status = "Removed"
        elif content_hash(before) != content_hash(after):
            status = "Modified"
        else:
            status = "Unchanged"
        node_counts[status] += 1
        if status != "Unchanged":
            node_differences.append(
                {
                    "entityId": entity_id,
                    "status": status,
                    "changedFields": (
                        _field_changes(before, after)
                        if before is not None and after is not None
                        else []
                    ),
                    "expected": before,
                    "actual": after,
                }
            )

    def edge_key(edge: Mapping[str, Any]) -> tuple[str, str, str]:
        return (
            str(edge["source"]),
            str(edge["relation"]),
            str(edge["target"]),
        )

    expected_edges = {edge_key(edge): edge for edge in expected["edges"]}
    actual_edges = {edge_key(edge): edge for edge in actual["edges"]}
    edge_differences: list[dict[str, Any]] = []
    edge_counts = {"Added": 0, "Removed": 0, "Modified": 0, "Unchanged": 0}
    for key in sorted(expected_edges.keys() | actual_edges.keys()):
        before = expected_edges.get(key)
        after = actual_edges.get(key)
        if before is None:
            status = "Added"
        elif after is None:
            status = "Removed"
        elif content_hash(before) != content_hash(after):
            status = "Modified"
        else:
            status = "Unchanged"
        edge_counts[status] += 1
        if status != "Unchanged":
            edge_differences.append(
                {
                    "source": key[0],
                    "relation": key[1],
                    "target": key[2],
                    "status": status,
                    "changedFields": (
                        _field_changes(before, after)
                        if before is not None and after is not None
                        else []
                    ),
                    "expected": before,
                    "actual": after,
                }
            )

    difference_count = (
        len(baseline_field_changes) + len(node_differences) + len(edge_differences)
    )
    return {
        "status": "Matched" if difference_count == 0 else "Drifted",
        "schemaVersion": GRAPH_BASELINE_SCHEMA_VERSION,
        "repositoryId": expected["repositoryId"],
        "graphSpace": expected["graphSpace"],
        "expectedContentHash": expected["contentHash"],
        "actualContentHash": actual["contentHash"],
        "summary": {
            "nodeChanges": node_counts,
            "edgeChanges": edge_counts,
            "baselineFieldChanges": baseline_field_changes,
            "differenceCount": difference_count,
        },
        "nodeDifferences": node_differences[:limit],
        "edgeDifferences": edge_differences[:limit],
        "truncated": len(node_differences) > limit or len(edge_differences) > limit,
    }
