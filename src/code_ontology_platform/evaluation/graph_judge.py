from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .models import JudgeResult, canonical_json


def _node_id(node: Any) -> str:
    if isinstance(node, Mapping):
        for key in ("id", "entityId", "targetEntityId", "target", "node"):
            value = node.get(key)
            if isinstance(value, str):
                return value
            if isinstance(value, Mapping):
                for nested in ("id", "entityId"):
                    if isinstance(value.get(nested), str):
                        return value[nested]
    return canonical_json(node)


def _edge_id(edge: Any) -> str:
    if isinstance(edge, Mapping):
        source = edge.get("source") or edge.get("from")
        relation = edge.get("relation") or edge.get("type") or edge.get("rule")
        target = edge.get("target") or edge.get("to")
        if all(value is not None for value in (source, relation, target)):
            return canonical_json([source, relation, target])
    return canonical_json(edge)


def _extract_graph(value: Any) -> tuple[list[Any], list[Any], list[Any]]:
    if not isinstance(value, Mapping):
        return [], [], []
    nodes = value.get("nodes")
    edges = value.get("edges")
    paths = value.get("paths")
    if isinstance(nodes, list) or isinstance(edges, list):
        return (
            nodes if isinstance(nodes, list) else [],
            edges if isinstance(edges, list) else [],
            paths if isinstance(paths, list) else [],
        )

    impacts = value.get("impacts")
    if isinstance(impacts, list):
        impact_nodes: list[Any] = []
        impact_edges: list[Any] = []
        impact_paths: list[Any] = []
        for impact in impacts:
            if not isinstance(impact, Mapping):
                continue
            target = impact.get("target")
            if target is not None:
                impact_nodes.append(target)
            path = impact.get("path")
            if isinstance(path, list):
                impact_paths.append(path)
            impact_edges.append(
                {
                    "source": impact.get("seed"),
                    "relation": impact.get("rule") or impact.get("impactType"),
                    "target": target,
                }
            )
        return impact_nodes, impact_edges, impact_paths
    return [], [], []


def _precision_recall(
    expected: set[str], actual: set[str]
) -> tuple[float, float, set[str], set[str]]:
    overlap = expected & actual
    precision = len(overlap) / max(len(actual), 1)
    recall = len(overlap) / max(len(expected), 1)
    return precision, recall, expected - actual, actual - expected


class GraphJudge:
    def judge(
        self,
        artifact_type: str,
        expected: Any,
        actual: Any,
        *,
        stage: str | None = None,
    ) -> JudgeResult:
        expected_nodes, expected_edges, expected_paths = _extract_graph(expected)
        actual_nodes, actual_edges, actual_paths = _extract_graph(actual)
        expected_node_ids = {_node_id(item) for item in expected_nodes}
        actual_node_ids = {_node_id(item) for item in actual_nodes}
        expected_edge_ids = {_edge_id(item) for item in expected_edges}
        actual_edge_ids = {_edge_id(item) for item in actual_edges}
        expected_path_ids = {canonical_json(item) for item in expected_paths}
        actual_path_ids = {canonical_json(item) for item in actual_paths}

        node_precision, node_recall, missing_nodes, extra_nodes = _precision_recall(
            expected_node_ids, actual_node_ids
        )
        edge_precision, edge_recall, missing_edges, extra_edges = _precision_recall(
            expected_edge_ids, actual_edge_ids
        )
        _, path_recall, missing_paths, _ = _precision_recall(
            expected_path_ids, actual_path_ids
        )

        components = [node_precision, node_recall, edge_precision, edge_recall]
        if expected_path_ids:
            components.append(path_recall)
        score = sum(components) / len(components)
        passed = (
            not missing_nodes
            and not extra_nodes
            and not missing_edges
            and not extra_edges
            and not missing_paths
        )
        return JudgeResult(
            judge="GraphJudge",
            artifact_type=artifact_type,
            status="Passed" if passed else "Failed",
            score=score,
            metrics={
                "nodePrecision": node_precision,
                "nodeRecall": node_recall,
                "edgePrecision": edge_precision,
                "edgeRecall": edge_recall,
                "pathRecall": path_recall,
            },
            missing=sorted(missing_nodes | missing_edges | missing_paths),
            extra=sorted(extra_nodes | extra_edges),
            stage=stage,
        )
