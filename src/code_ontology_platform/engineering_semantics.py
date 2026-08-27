from __future__ import annotations

import argparse
import json
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Literal, Mapping

REQUIREMENTS = frozenset({"Requirement", "EngineeringRequirement"})
GOVERNED_REQUIREMENTS = frozenset({"EngineeringRequirement"})
CAPABILITIES = frozenset({"BusinessCapability", "Capability"})
CONTRACTS = frozenset(
    {"RequirementContract", "SpecificationContract", "BehaviorContract", "ConstraintContract", "StateContract", "InputOutputContract"}
)
SEMANTIC_CONTRACTS = frozenset({"SemanticContract"})
VERIFICATION_METHODS = frozenset(
    {"VerificationMethod", "TestVerification", "FormalProofVerification", "AnalysisVerification", "InspectionVerification", "DemonstrationVerification"}
)
VERIFICATION_OBJECTIVES = frozenset({"VerificationObjective"})
VERIFICATION_EVIDENCE = frozenset(
    {"VerificationEvidence", "TestExecutionEvidence", "ProofEvidence", "AnalysisEvidence"}
)
ONTOLOGIES = frozenset({"OntologyAsset"})
CODE = frozenset(
    {
        "Repository", "Module", "SourceFile", "Type", "Class", "Interface", "Enum",
        "Callable", "Method", "Function", "Constructor", "Field", "Parameter",
        "Component", "LogicalService", "APIOperation", "Schema", "SchemaField",
        "Table", "Column", "Query", "ConfigurationKey",
    }
)
TESTS = frozenset({"TestCase", "UnitTest", "IntegrationTest", "ContractTest", "EndToEndTest"})


def local_name(value: Any) -> str:
    text = str(value or "")
    for separator in ("#", "/", ":"):
        if separator in text:
            text = text.rsplit(separator, 1)[-1]
    return text


def node_type(node: Mapping[str, Any] | None) -> str:
    return local_name(node.get("type")) if node else ""


def edge_key(edge: Mapping[str, Any]) -> tuple[str, str, str]:
    return str(edge.get("source", "")), str(edge.get("relation", "")), str(edge.get("target", ""))


@dataclass(frozen=True)
class ImpactRule:
    rule_id: str
    relations: frozenset[str]
    direction: Literal["out", "in"]
    impact_type: str
    source_types: frozenset[str]
    target_types: frozenset[str]
    propagate: bool = True


R = ImpactRule
IMPACT_RULES: tuple[ImpactRule, ...] = (
    R("REQ_CHILD_PROPAGATION", frozenset({"derivesRequirement", "derive"}), "out", "RequirementReview", REQUIREMENTS, REQUIREMENTS),
    R("REQ_PARENT_PROPAGATION", frozenset({"derivesRequirement", "derive"}), "in", "RequirementReview", REQUIREMENTS, REQUIREMENTS),
    R("REQ_CONTRACT_REVIEW", frozenset({"definesContract", "define"}), "out", "ContractReview", REQUIREMENTS, CONTRACTS),
    R("CONTRACT_OWNER_REVIEW", frozenset({"definesContract", "define"}), "in", "RequirementReview", CONTRACTS, REQUIREMENTS),
    R("REQ_SEMANTIC_CONSTRAINT_REVIEW", frozenset({"constrainedBy"}), "out", "SemanticConstraintReview", REQUIREMENTS, SEMANTIC_CONTRACTS),
    R("SEMANTIC_CONTRACT_REQUIREMENT_REVIEW", frozenset({"constrainedBy"}), "in", "RequirementReview", SEMANTIC_CONTRACTS, REQUIREMENTS),
    R("ONTOLOGY_SEMANTIC_CONTRACT_REVIEW", frozenset({"usesOntology"}), "in", "SemanticConstraintReview", ONTOLOGIES, SEMANTIC_CONTRACTS),
    R("REQ_IMPLEMENTATION_REVIEW", frozenset({"implementsRequirement"}), "in", "ImplementationReview", REQUIREMENTS, CODE),
    R("CODE_REQUIREMENT_REVIEW", frozenset({"implementsRequirement"}), "out", "RequirementReview", CODE, REQUIREMENTS),
    R("REQ_VERIFICATION_REVIEW", frozenset({"verifiesRequirement"}), "in", "VerificationReview", REQUIREMENTS, VERIFICATION_METHODS),
    R("VERIFICATION_REQUIREMENT_CONTEXT", frozenset({"verifiesRequirement"}), "out", "RequirementContext", VERIFICATION_METHODS, REQUIREMENTS, False),
    R("REQ_TEST_REVIEW", frozenset({"verifies"}), "in", "TestReview", REQUIREMENTS, TESTS),
    R("TEST_REQUIREMENT_CONTEXT", frozenset({"verifies"}), "out", "RequirementContext", TESTS, REQUIREMENTS, False),
    R("CALLEE_CALLER_PROPAGATION", frozenset({"callsDirectly", "mayCall", "observedCalls"}), "in", "CallerReview", CODE, CODE),
    R("FIELD_READER_PROPAGATION", frozenset({"readsField", "writesField"}), "in", "DataFlowReview", frozenset({"Field"}), CODE),
    R("API_IMPLEMENTATION_PROPAGATION", frozenset({"implementsOperation"}), "in", "ImplementationReview", frozenset({"APIOperation"}), CODE),
    R("CAPABILITY_REQUIREMENT_PROPAGATION", frozenset({"specifiesCapability", "specify"}), "in", "RequirementReview", CAPABILITIES, REQUIREMENTS),
    R("REQ_CAPABILITY_CONTEXT", frozenset({"specifiesCapability", "specify"}), "out", "CapabilityContext", REQUIREMENTS, CAPABILITIES, False),
)

CONTEXT_RELATIONS = frozenset(
    {
        "specifiesCapability", "specify", "derivesRequirement", "derive", "definesContract", "define",
        "constrainedBy", "usesOntology", "derivedFromObjective", "verifiesRequirement", "verifies",
        "implementsRequirement", "satisfiedByEvidence", "evidenceArtifact", "covers", "callsDirectly",
        "mayCall", "observedCalls", "readsField", "writesField", "implementsOperation",
    }
)


class EngineeringSemantics:
    """Deterministic engineering semantics over the platform {nodes, edges} graph shape."""

    def __init__(self, graph: Mapping[str, Any]) -> None:
        nodes, edges = graph.get("nodes", []), graph.get("edges", [])
        if not isinstance(nodes, list) or not isinstance(edges, list):
            raise ValueError("graph.nodes and graph.edges must be arrays")
        self.nodes = [dict(item) for item in nodes if isinstance(item, Mapping)]
        self.edges = [dict(item) for item in edges if isinstance(item, Mapping)]
        self.node_by_id = {str(node["id"]): node for node in self.nodes if node.get("id")}
        self.outgoing: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.incoming: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for edge in self.edges:
            source, _, target = edge_key(edge)
            if source and target:
                self.outgoing[source].append(edge)
                self.incoming[target].append(edge)
        for index in (self.outgoing, self.incoming):
            for values in index.values():
                values.sort(key=edge_key)

    def links(self, entity_id: str, direction: Literal["out", "in"], names: Iterable[str]) -> list[dict[str, Any]]:
        index = self.outgoing if direction == "out" else self.incoming
        allowed = set(names)
        return [edge for edge in index.get(entity_id, []) if local_name(edge.get("relation")) in allowed]

    def typed_links(
        self,
        entity_id: str,
        direction: Literal["out", "in"],
        names: Iterable[str],
        expected_types: frozenset[str],
    ) -> list[dict[str, Any]]:
        side = "target" if direction == "out" else "source"
        return [
            edge for edge in self.links(entity_id, direction, names)
            if node_type(self.node_by_id.get(str(edge.get(side)))) in expected_types
        ]

    def validate(self) -> dict[str, Any]:
        issues: list[dict[str, Any]] = []

        def issue(code: str, entity_id: str, message: str, **details: Any) -> None:
            item: dict[str, Any] = {"code": code, "entityId": entity_id, "message": message}
            if details:
                item["details"] = details
            issues.append(item)

        for entity_id, node in sorted(self.node_by_id.items()):
            kind = node_type(node)
            if kind in GOVERNED_REQUIREMENTS:
                parents = self.typed_links(entity_id, "in", {"derivesRequirement", "derive"}, GOVERNED_REQUIREMENTS)
                capabilities = self.links(entity_id, "out", {"specifiesCapability", "specify"})
                valid = self.typed_links(entity_id, "out", {"specifiesCapability", "specify"}, CAPABILITIES)
                if not parents and len(valid) != 1:
                    issue("REQUIREMENT_CAPABILITY_OWNER", entity_id, "Top-level EngineeringRequirement must specify exactly one Capability.", capabilityCount=len(capabilities), validCapabilityCount=len(valid))
            elif kind in CONTRACTS:
                owners = self.links(entity_id, "in", {"definesContract", "define"})
                valid = self.typed_links(entity_id, "in", {"definesContract", "define"}, GOVERNED_REQUIREMENTS)
                if len(valid) != 1:
                    issue("CONTRACT_SINGLE_OWNER", entity_id, "Requirement-owned Contract must have exactly one EngineeringRequirement owner.", ownerCount=len(owners), validOwnerCount=len(valid))
            elif kind in SEMANTIC_CONTRACTS:
                if not self.typed_links(entity_id, "out", {"usesOntology"}, ONTOLOGIES):
                    issue("SEMANTIC_CONTRACT_ONTOLOGY", entity_id, "SemanticContract must use at least one OntologyAsset.")
                if not self.typed_links(entity_id, "in", {"constrainedBy"}, GOVERNED_REQUIREMENTS):
                    issue("SEMANTIC_CONTRACT_TARGET", entity_id, "SemanticContract must constrain at least one EngineeringRequirement.")
            elif kind in VERIFICATION_METHODS:
                objectives = self.links(entity_id, "out", {"derivedFromObjective"})
                valid_objectives = self.typed_links(entity_id, "out", {"derivedFromObjective"}, VERIFICATION_OBJECTIVES)
                if len(valid_objectives) != 1:
                    issue("VERIFICATION_OBJECTIVE", entity_id, "VerificationMethod must derive from exactly one VerificationObjective.", objectiveCount=len(objectives), validObjectiveCount=len(valid_objectives))
                if not self.typed_links(entity_id, "out", {"verifiesRequirement"}, GOVERNED_REQUIREMENTS):
                    issue("VERIFICATION_REQUIREMENT", entity_id, "VerificationMethod must verify at least one EngineeringRequirement.")
                if not self.typed_links(entity_id, "out", {"satisfiedByEvidence"}, VERIFICATION_EVIDENCE):
                    issue("VERIFICATION_EVIDENCE", entity_id, "VerificationMethod must have concrete evidence.")
            elif kind in VERIFICATION_OBJECTIVES:
                if self.links(entity_id, "out", {"satisfiedByEvidence"}):
                    issue("OBJECTIVE_HAS_EVIDENCE", entity_id, "VerificationObjective cannot directly own evidence.")
            elif kind in VERIFICATION_EVIDENCE:
                if not self.links(entity_id, "out", {"evidenceArtifact"}):
                    issue("EVIDENCE_ARTIFACT", entity_id, "VerificationEvidence must point to at least one auditable artifact.")

        return {"conforms": not issues, "issueCount": len(issues), "issues": issues}

    def coverage(self) -> dict[str, Any]:
        requirements = sorted(entity_id for entity_id, node in self.node_by_id.items() if node_type(node) in GOVERNED_REQUIREMENTS)
        leaves = [
            entity_id for entity_id in requirements
            if not self.typed_links(entity_id, "out", {"derivesRequirement", "derive"}, REQUIREMENTS)
        ]
        implemented = [
            entity_id for entity_id in leaves
            if self.typed_links(entity_id, "in", {"implementsRequirement"}, CODE)
        ]
        verified = [
            entity_id for entity_id in leaves
            if self.typed_links(entity_id, "in", {"verifiesRequirement"}, VERIFICATION_METHODS)
            or self.typed_links(entity_id, "in", {"verifies"}, TESTS)
        ]
        methods = sorted(entity_id for entity_id, node in self.node_by_id.items() if node_type(node) in VERIFICATION_METHODS)
        evidenced = [entity_id for entity_id in methods if self.typed_links(entity_id, "out", {"satisfiedByEvidence"}, VERIFICATION_EVIDENCE)]

        def metric(covered: list[str], total: list[str], missing_key: str) -> dict[str, Any]:
            return {
                "covered": len(covered),
                "total": len(total),
                "ratio": None if not total else round(len(covered) / len(total), 4),
                missing_key: sorted(set(total) - set(covered)),
            }

        return {
            "requirementCount": len(requirements),
            "leafRequirementCount": len(leaves),
            "implementation": metric(implemented, leaves, "missingRequirementIds"),
            "verification": metric(verified, leaves, "missingRequirementIds"),
            "verificationEvidence": metric(evidenced, methods, "missingVerificationIds"),
        }

    def collect(self, entity_id: str, *, depth: int = 2) -> dict[str, Any]:
        if entity_id not in self.node_by_id:
            raise KeyError(entity_id)
        if depth < 0:
            raise ValueError("depth must be >= 0")
        selected_nodes, selected_edges = {entity_id}, set()
        queue: deque[tuple[str, int]] = deque([(entity_id, 0)])
        while queue:
            current, level = queue.popleft()
            if level >= depth:
                continue
            for edge in sorted(self.outgoing.get(current, []) + self.incoming.get(current, []), key=edge_key):
                if local_name(edge.get("relation")) not in CONTEXT_RELATIONS:
                    continue
                source, _, target = edge_key(edge)
                other = target if source == current else source
                selected_edges.add(edge_key(edge))
                if other not in selected_nodes and other in self.node_by_id:
                    selected_nodes.add(other)
                    queue.append((other, level + 1))
        nodes = [self.node_by_id[item] for item in sorted(selected_nodes)]
        edges = sorted((edge for edge in self.edges if edge_key(edge) in selected_edges), key=edge_key)
        counts: dict[str, int] = defaultdict(int)
        for node in nodes:
            counts[node_type(node) or "Unknown"] += 1
        return {"entityId": entity_id, "depth": depth, "nodes": nodes, "edges": edges, "summary": {"nodeCount": len(nodes), "edgeCount": len(edges), "types": dict(sorted(counts.items()))}}

    def impact(self, changed_entity_ids: Iterable[str], *, max_depth: int = 4) -> dict[str, Any]:
        seeds = sorted({str(item) for item in changed_entity_ids})
        missing = [item for item in seeds if item not in self.node_by_id]
        if missing:
            raise KeyError(", ".join(missing))
        if max_depth < 1:
            raise ValueError("max_depth must be >= 1")
        queue: deque[tuple[str, str, int, list[dict[str, Any]]]] = deque((seed, seed, 0, []) for seed in seeds)
        best = {(seed, seed): 0 for seed in seeds}
        impacts: list[dict[str, Any]] = []
        while queue:
            seed, current, depth, path = queue.popleft()
            if depth >= max_depth:
                continue
            current_type = node_type(self.node_by_id.get(current))
            for rule in IMPACT_RULES:
                if current_type not in rule.source_types:
                    continue
                index = self.outgoing if rule.direction == "out" else self.incoming
                for edge in index.get(current, []):
                    if local_name(edge.get("relation")) not in rule.relations:
                        continue
                    source, relation, target = edge_key(edge)
                    next_id = target if rule.direction == "out" else source
                    next_type = node_type(self.node_by_id.get(next_id))
                    if next_type not in rule.target_types:
                        continue
                    next_depth = depth + 1
                    key = seed, next_id
                    if key in best and best[key] <= next_depth:
                        continue
                    best[key] = next_depth
                    step = {"from": current, "relation": relation, "direction": rule.direction, "to": next_id, "ruleId": rule.rule_id}
                    next_path = [*path, step]
                    impacts.append({"seed": seed, "target": next_id, "targetType": next_type, "impactType": rule.impact_type, "ruleId": rule.rule_id, "state": "Confirmed", "confidence": 1.0, "depth": next_depth, "path": next_path})
                    if rule.propagate:
                        queue.append((seed, next_id, next_depth, next_path))
        impacts.sort(key=lambda item: (item["seed"], item["depth"], item["target"], item["ruleId"]))
        return {"seeds": seeds, "maxDepth": max_depth, "impactCount": len(impacts), "impacts": impacts}


def load_graph(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError("graph file must contain a JSON object")
    return dict(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic engineering semantic analyzer")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "coverage"):
        sub.add_parser(name).add_argument("graph", type=Path)
    collect = sub.add_parser("collect")
    collect.add_argument("graph", type=Path)
    collect.add_argument("entity_id")
    collect.add_argument("--depth", type=int, default=2)
    impact = sub.add_parser("impact")
    impact.add_argument("graph", type=Path)
    impact.add_argument("entity_ids", nargs="+")
    impact.add_argument("--depth", type=int, default=4)
    args = parser.parse_args(argv)
    analyzer = EngineeringSemantics(load_graph(args.graph))
    if args.command == "validate":
        result = analyzer.validate()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["conforms"] else 1
    result = analyzer.coverage() if args.command == "coverage" else analyzer.collect(args.entity_id, depth=args.depth) if args.command == "collect" else analyzer.impact(args.entity_ids, max_depth=args.depth)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
