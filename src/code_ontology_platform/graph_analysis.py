from __future__ import annotations

import hashlib
import math
import re
from collections import Counter, defaultdict, deque
from collections.abc import Mapping, Sequence
from typing import Any

from .store import content_hash

ANALYSIS_VERSION = "deterministic-graph-analysis/v1"
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_WORD = re.compile(r"[A-Za-z0-9_.$:/{}-]+|[\u3400-\u9fff]+")
_STRUCTURAL_TYPES = frozenset({"Repository", "Module", "BuildArtifact", "SourceFile"})
_PROCESS_RELATIONS = frozenset(
    {
        "code:callsDirectly",
        "code:dataDependsOn",
        "code:readsConfiguration",
        "code:readsTable",
        "code:writesTable",
        "code:usesPayloadType",
    }
)


def _tokens(value: Any) -> list[str]:
    result: list[str] = []
    for match in _WORD.findall(str(value or "")):
        for part in re.split(r"[_.$:/{}-]+", _CAMEL_BOUNDARY.sub(" ", match)):
            part = part.strip().lower()
            if not part:
                continue
            result.append(part)
            if any("\u3400" <= character <= "\u9fff" for character in part):
                result.extend(part[index : index + 2] for index in range(len(part) - 1))
    return result


def _node_document(node: Mapping[str, Any]) -> tuple[list[str], dict[str, str]]:
    fields: dict[str, str] = {}
    for key, value in node.items():
        if key in {"id", "logicalId", "evidence"}:
            continue
        if isinstance(value, (str, int, float, bool)):
            fields[str(key)] = str(value)
    evidence = node.get("evidence")
    if isinstance(evidence, Mapping):
        for key, value in evidence.items():
            if isinstance(value, (str, int, float, bool)):
                fields[f"evidence.{key}"] = str(value)
    terms: list[str] = []
    for key, value in fields.items():
        weight = 3 if key in {"label", "name", "methodName", "fieldName"} else 1
        terms.extend(_tokens(value) * weight)
    terms.extend(_tokens(node.get("id")))
    return terms, fields


def _feature_vector(tokens: Sequence[str], dimensions: int = 384) -> dict[int, float]:
    vector: dict[int, float] = defaultdict(float)
    features = list(tokens)
    joined = " ".join(tokens)
    features.extend(
        joined[index : index + 3] for index in range(max(0, len(joined) - 2))
    )
    for feature in features:
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest, "big") % dimensions
        sign = 1.0 if digest[0] & 1 else -1.0
        vector[bucket] += sign
    norm = math.sqrt(sum(value * value for value in vector.values()))
    return {key: value / norm for key, value in vector.items()} if norm else {}


def _cosine(left: Mapping[int, float], right: Mapping[int, float]) -> float:
    if len(left) > len(right):
        left, right = right, left
    return sum(value * right.get(key, 0.0) for key, value in left.items())


def hybrid_graph_search(
    nodes: Sequence[Mapping[str, Any]],
    edges: Sequence[Mapping[str, Any]],
    query: str,
    *,
    limit: int = 20,
    entity_types: set[str] | None = None,
) -> dict[str, Any]:
    candidates = [
        dict(node)
        for node in nodes
        if not entity_types or str(node.get("type")) in entity_types
    ]
    documents = [_node_document(node) for node in candidates]
    query_tokens = _tokens(query)
    query_counts = Counter(query_tokens)
    document_frequency = Counter(
        token for terms, _ in documents for token in set(terms)
    )
    average_length = (
        sum(len(terms) for terms, _ in documents) / len(documents)
        if documents
        else 1.0
    )
    query_vector = _feature_vector(query_tokens)
    degree = Counter()
    candidate_ids = {str(node["id"]) for node in candidates}
    for edge in edges:
        source, target = str(edge["source"]), str(edge["target"])
        if source in candidate_ids:
            degree[source] += 1
        if target in candidate_ids:
            degree[target] += 1
    max_degree = max(degree.values(), default=1)

    rows: list[dict[str, Any]] = []
    total = len(candidates)
    for node, (terms, fields) in zip(candidates, documents, strict=True):
        frequencies = Counter(terms)
        bm25 = 0.0
        for token, query_frequency in query_counts.items():
            frequency = frequencies[token]
            if not frequency:
                continue
            inverse = math.log(
                1.0 + (total - document_frequency[token] + 0.5)
                / (document_frequency[token] + 0.5)
            )
            denominator = frequency + 1.2 * (
                1.0 - 0.75 + 0.75 * len(terms) / max(average_length, 1.0)
            )
            bm25 += query_frequency * inverse * frequency * 2.2 / denominator
        semantic = max(0.0, _cosine(query_vector, _feature_vector(terms)))
        centrality = degree[str(node["id"])] / max_degree
        matched_fields = sorted(
            key
            for key, value in fields.items()
            if set(_tokens(value)) & set(query_tokens)
        )
        rows.append(
            {
                "node": node,
                "bm25": bm25,
                "semantic": semantic,
                "centrality": centrality,
                "matchedFields": matched_fields,
            }
        )

    rankings: dict[str, dict[str, int]] = {}
    for field in ("bm25", "semantic", "centrality"):
        ordered = sorted(
            rows,
            key=lambda row: (-float(row[field]), str(row["node"]["id"])),
        )
        rankings[field] = {
            str(row["node"]["id"]): rank
            for rank, row in enumerate(ordered, start=1)
        }
    weights = {"bm25": 1.0, "semantic": 0.8, "centrality": 0.15}
    for row in rows:
        node_id = str(row["node"]["id"])
        row["score"] = sum(
            weight / (60 + rankings[field][node_id])
            for field, weight in weights.items()
        )
    relevant = [
        row for row in rows if row["bm25"] > 0 or row["semantic"] > 0.02
    ]
    ordered_rows = sorted(
        relevant,
        key=lambda row: (-float(row["score"]), str(row["node"]["id"])),
    )[:limit]
    return {
        "algorithm": {
            "version": ANALYSIS_VERSION,
            "lexical": "BM25",
            "semantic": "deterministic-feature-hashing-cosine",
            "fusion": "weighted-RRF(k=60)",
            "weights": weights,
        },
        "query": query,
        "count": len(ordered_rows),
        "results": [
            {
                "rank": index,
                "score": round(float(row["score"]), 8),
                "scoreBreakdown": {
                    "bm25": round(float(row["bm25"]), 8),
                    "semantic": round(float(row["semantic"]), 8),
                    "centrality": round(float(row["centrality"]), 8),
                },
                "matchedFields": row["matchedFields"],
                "node": row["node"],
            }
            for index, row in enumerate(ordered_rows, start=1)
        ],
    }


def _relation_weight(relation: str) -> float:
    name = relation.rsplit(":", 1)[-1].lower()
    if "call" in name or "implement" in name or "consume" in name:
        return 3.0
    if "data" in name or "read" in name or "write" in name or "verif" in name:
        return 2.0
    if "declar" in name or "contain" in name or "belong" in name:
        return 0.35
    if "artifact" in name:
        return 0.1
    return 1.0


def detect_communities(
    nodes: Sequence[Mapping[str, Any]],
    edges: Sequence[Mapping[str, Any]],
    *,
    minimum_size: int = 1,
) -> dict[str, Any]:
    node_by_id = {str(node["id"]): dict(node) for node in nodes}
    adjacency: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for edge in edges:
        source, target = str(edge["source"]), str(edge["target"])
        if source not in node_by_id or target not in node_by_id or source == target:
            continue
        weight = _relation_weight(str(edge["relation"]))
        adjacency[source][target] += weight
        adjacency[target][source] += weight
    community = {node_id: node_id for node_id in node_by_id}
    degree = {
        node_id: sum(adjacency[node_id].values()) for node_id in node_by_id
    }
    total_weight_twice = sum(degree.values()) or 1.0

    for _ in range(30):
        moved = False
        totals = defaultdict(float)
        for node_id, community_id in community.items():
            totals[community_id] += degree[node_id]
        for node_id in sorted(node_by_id):
            current = community[node_id]
            neighboring = defaultdict(float)
            for neighbor, weight in adjacency[node_id].items():
                neighboring[community[neighbor]] += weight
            totals[current] -= degree[node_id]
            best = current
            best_gain = 0.0
            for candidate, internal_weight in sorted(neighboring.items()):
                gain = (
                    internal_weight
                    - degree[node_id] * totals[candidate] / total_weight_twice
                )
                if gain > best_gain + 1e-12:
                    best, best_gain = candidate, gain
            community[node_id] = best
            totals[best] += degree[node_id]
            if best != current:
                moved = True
        if not moved:
            break

    groups: dict[str, list[str]] = defaultdict(list)
    for node_id, community_id in community.items():
        groups[community_id].append(node_id)
    ordered_groups = sorted(
        (
            sorted(members)
            for members in groups.values()
            if len(members) >= minimum_size
        ),
        key=lambda members: (-len(members), members[0]),
    )
    member_to_stable: dict[str, str] = {}
    result_groups: list[dict[str, Any]] = []
    edge_pairs = [
        (str(edge["source"]), str(edge["target"])) for edge in edges
    ]
    for members in ordered_groups:
        stable_id = "community:" + hashlib.sha256(
            "\n".join(members).encode("utf-8")
        ).hexdigest()[:16]
        member_set = set(members)
        for member in members:
            member_to_stable[member] = stable_id
        internal = sum(
            1
            for source, target in edge_pairs
            if source in member_set and target in member_set
        )
        boundary = sum(
            1
            for source, target in edge_pairs
            if (source in member_set) != (target in member_set)
        )
        term_counts = Counter(
            token
            for member in members
            for token in _tokens(
                node_by_id[member].get("label")
                or node_by_id[member].get("name")
                or member
            )
            if len(token) > 2
        )
        representative = sorted(
            (node_by_id[member] for member in members),
            key=lambda node: (
                str(node.get("type")) in _STRUCTURAL_TYPES,
                -degree[str(node["id"])],
                str(node["id"]),
            ),
        )[0]
        result_groups.append(
            {
                "communityId": stable_id,
                "label": str(
                    representative.get("label")
                    or representative.get("name")
                    or representative["id"]
                ),
                "size": len(members),
                "internalEdgeCount": internal,
                "boundaryEdgeCount": boundary,
                "cohesion": round(internal / max(1, internal + boundary), 6),
                "keyTerms": [term for term, _ in term_counts.most_common(8)],
                "members": members,
            }
        )
    cross_edges = [
        {
            "sourceCommunity": member_to_stable.get(str(edge["source"])),
            "targetCommunity": member_to_stable.get(str(edge["target"])),
            "relation": edge["relation"],
            "source": edge["source"],
            "target": edge["target"],
        }
        for edge in edges
        if member_to_stable.get(str(edge["source"]))
        and member_to_stable.get(str(edge["target"]))
        and member_to_stable[str(edge["source"])]
        != member_to_stable[str(edge["target"])]
    ]
    return {
        "algorithm": {
            "version": ANALYSIS_VERSION,
            "name": "deterministic-weighted-local-modularity",
        },
        "communityCount": len(result_groups),
        "communities": result_groups,
        "membership": dict(sorted(member_to_stable.items())),
        "crossCommunityEdges": cross_edges,
    }


def detect_processes(
    nodes: Sequence[Mapping[str, Any]],
    edges: Sequence[Mapping[str, Any]],
    *,
    max_depth: int = 6,
    limit: int = 100,
) -> dict[str, Any]:
    node_by_id = {str(node["id"]): dict(node) for node in nodes}
    outgoing: dict[str, list[dict[str, Any]]] = defaultdict(list)
    incoming: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge_value in edges:
        edge = dict(edge_value)
        outgoing[str(edge["source"])].append(edge)
        incoming[str(edge["target"])].append(edge)
    communities = detect_communities(nodes, edges)
    membership = communities["membership"]
    entries = [
        node
        for node in node_by_id.values()
        if str(node.get("type"))
        in {"APIOperation", "EventType", "UnitTest", "IntegrationTest", "ContractTest"}
    ]
    processes: list[dict[str, Any]] = []
    for entry in sorted(entries, key=lambda node: str(node["id"])):
        entry_id = str(entry["id"])
        entry_type = str(entry.get("type"))
        seeds: list[tuple[str, str]] = []
        if entry_type == "APIOperation":
            seeds = [
                (str(edge["source"]), str(edge["relation"]))
                for edge in incoming[entry_id]
                if str(edge["relation"]) == "code:implementsOperation"
            ]
        elif entry_type == "EventType":
            seeds = [
                (str(edge["source"]), str(edge["relation"]))
                for edge in incoming[entry_id]
                if str(edge["relation"]) == "code:consumesEvent"
            ]
        else:
            seeds = [
                (str(edge["target"]), str(edge["relation"]))
                for edge in outgoing[entry_id]
                if str(edge["relation"]) == "code:verifies"
            ]
        if not seeds:
            continue
        queue = deque(
            (seed, 1, entry_id, relation) for seed, relation in sorted(seeds)
        )
        seen = {entry_id}
        steps = [
            {
                "order": 0,
                "nodeId": entry_id,
                "type": entry_type,
                "label": entry.get("label"),
                "via": "entry",
                "from": None,
                "communityId": membership.get(entry_id),
            }
        ]
        traversed: list[dict[str, Any]] = []
        while queue:
            node_id, depth, predecessor, relation = queue.popleft()
            if node_id in seen or depth > max_depth or node_id not in node_by_id:
                continue
            seen.add(node_id)
            node = node_by_id[node_id]
            steps.append(
                {
                    "order": len(steps),
                    "nodeId": node_id,
                    "type": node.get("type"),
                    "label": node.get("label"),
                    "via": relation,
                    "from": predecessor,
                    "communityId": membership.get(node_id),
                }
            )
            traversed.append(
                {"source": predecessor, "relation": relation, "target": node_id}
            )
            candidates = [
                edge
                for edge in outgoing[node_id]
                if str(edge["relation"]) in _PROCESS_RELATIONS
            ]
            if entry_type in {"UnitTest", "IntegrationTest", "ContractTest"}:
                candidates.extend(
                    edge
                    for edge in outgoing[node_id]
                    if str(edge["relation"]) == "code:verifies"
                )
            for edge in sorted(
                candidates,
                key=lambda value: (
                    str(value["relation"]),
                    str(value["target"]),
                ),
            ):
                queue.append(
                    (
                        str(edge["target"]),
                        depth + 1,
                        node_id,
                        str(edge["relation"]),
                    )
                )
        community_ids = {
            step["communityId"] for step in steps if step["communityId"] is not None
        }
        process_id = "process:" + hashlib.sha256(
            (entry_id + "\n" + "\n".join(step["nodeId"] for step in steps)).encode(
                "utf-8"
            )
        ).hexdigest()[:16]
        processes.append(
            {
                "processId": process_id,
                "kind": (
                    "API"
                    if entry_type == "APIOperation"
                    else "Event"
                    if entry_type == "EventType"
                    else "Test"
                ),
                "entryNodeId": entry_id,
                "label": entry.get("label"),
                "stepCount": len(steps),
                "crossCommunity": len(community_ids) > 1,
                "communityIds": sorted(community_ids),
                "steps": steps,
                "edges": traversed,
            }
        )
    processes = sorted(
        processes,
        key=lambda process: (
            -int(process["stepCount"]),
            str(process["processId"]),
        ),
    )[:limit]
    return {
        "algorithm": {
            "version": ANALYSIS_VERSION,
            "name": "typed-entry-bounded-traversal",
            "maxDepth": max_depth,
        },
        "processCount": len(processes),
        "processes": processes,
    }


def _contract_key(node: Mapping[str, Any]) -> tuple[str, str] | None:
    entity_type = str(node.get("type"))
    if entity_type == "APIOperation":
        method = str(node.get("httpMethod") or "ANY").upper()
        label = str(node.get("label") or "")
        path = str(node.get("path") or "")
        if not path and " " in label:
            path = label.split(" ", 1)[1]
        path = "/" + "/".join(part for part in path.strip().split("/") if part)
        return "http", f"{method} {path or '/'}"
    if entity_type == "EventType":
        return "event", str(node.get("channel") or node.get("label") or node["id"])
    if entity_type == "Schema":
        return "schema", str(
            node.get("schemaName") or node.get("label") or node["id"]
        )
    return None


def build_contract_graph(
    graphs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    contracts: dict[tuple[str, str], dict[str, Any]] = {}
    usages: list[dict[str, Any]] = []
    for graph in graphs:
        repository_id = str(graph["repositoryId"])
        revision = str(graph["revision"])
        nodes = [dict(node) for node in graph.get("nodes", [])]
        edges = [dict(edge) for edge in graph.get("edges", [])]
        by_id = {str(node["id"]): node for node in nodes}
        for node in nodes:
            key = _contract_key(node)
            if key is None:
                continue
            contract_id = "contract:" + hashlib.sha256(
                f"{key[0]}:{key[1]}".encode("utf-8")
            ).hexdigest()[:20]
            contract = contracts.setdefault(
                key,
                {
                    "contractId": contract_id,
                    "kind": key[0],
                    "key": key[1],
                    "definitions": [],
                },
            )
            contract["definitions"].append(
                {
                    "repositoryId": repository_id,
                    "revision": revision,
                    "nodeId": node["id"],
                }
            )
            contract_node_id = str(node["id"])
            relations = []
            if key[0] == "http":
                relations = [
                    ("code:implementsOperation", "Provider"),
                    ("code:exposes", "Provider"),
                    ("code:consumesOperation", "Consumer"),
                    ("code:callsOperation", "Consumer"),
                ]
            elif key[0] == "event":
                relations = [
                    ("code:consumesEvent", "Consumer"),
                    ("code:producesEvent", "Provider"),
                ]
            elif key[0] == "schema":
                relations = [
                    ("code:usesPayloadType", "Consumer"),
                    ("code:returnsSchema", "Provider"),
                ]
            for relation, role in relations:
                for edge in edges:
                    if (
                        str(edge["target"]) == contract_node_id
                        and str(edge["relation"]) == relation
                    ):
                        owner = by_id.get(str(edge["source"]))
                        usages.append(
                            {
                                "usageId": "usage:"
                                + hashlib.sha256(
                                    (
                                        f"{repository_id}|{revision}|{edge['source']}|"
                                        f"{role}|{contract_id}"
                                    ).encode("utf-8")
                                ).hexdigest()[:20],
                                "repositoryId": repository_id,
                                "revision": revision,
                                "role": role,
                                "ownerNodeId": edge["source"],
                                "ownerLabel": (owner or {}).get("label"),
                                "contractId": contract_id,
                                "evidenceRelation": relation,
                            }
                        )
    links: list[dict[str, Any]] = []
    usages_by_contract: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for usage in usages:
        usages_by_contract[str(usage["contractId"])].append(usage)
    for contract_id, values in usages_by_contract.items():
        providers = [value for value in values if value["role"] == "Provider"]
        consumers = [value for value in values if value["role"] == "Consumer"]
        for provider in providers:
            for consumer in consumers:
                if provider["repositoryId"] == consumer["repositoryId"]:
                    continue
                links.append(
                    {
                        "sourceUsageId": provider["usageId"],
                        "targetUsageId": consumer["usageId"],
                        "contractId": contract_id,
                        "relation": "cross-repo-contract",
                    }
                )
    contract_values = sorted(
        contracts.values(), key=lambda item: (str(item["kind"]), str(item["key"]))
    )
    result = {
        "schemaVersion": "cross-repository-contract-graph/v1",
        "algorithmVersion": ANALYSIS_VERSION,
        "repositoryCount": len({str(graph["repositoryId"]) for graph in graphs}),
        "contractCount": len(contract_values),
        "usageCount": len(usages),
        "crossRepositoryLinkCount": len(links),
        "contracts": contract_values,
        "usages": sorted(usages, key=lambda item: str(item["usageId"])),
        "links": sorted(
            links,
            key=lambda item: (
                str(item["contractId"]),
                str(item["sourceUsageId"]),
                str(item["targetUsageId"]),
            ),
        ),
    }
    result["contentHash"] = content_hash(result)
    return result
