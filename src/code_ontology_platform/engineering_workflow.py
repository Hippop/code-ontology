from __future__ import annotations

import hashlib
from typing import Any, Mapping


ENGINEERING_ONTOLOGY_VERSION = "engineering-semantics-1.0.0"


def materialize_engineering_intent(
    requirement_id: str, ir: Mapping[str, Any]
) -> dict[str, list[dict[str, Any]]]:
    """Project Requirement IR into governed engineering-semantic nodes."""

    requirement_node_id = f"requirement:{requirement_id}"
    capability_id = f"capability:{requirement_id}"
    contract_id = f"contract:{requirement_id}:specification"
    ontology_id = "ontology:code-ontology-engineering"
    semantic_contract_id = f"semantic-contract:{requirement_id}"
    objective_id = f"verification-objective:{requirement_id}"
    desired_entities = [
        dict(item)
        for item in ir.get("desiredEntities", [])
        if isinstance(item, Mapping)
    ]
    business_labels = [
        str(item.get("label"))
        for item in desired_entities
        if item.get("entityType") == "DesiredBusinessEntity" and item.get("label")
    ]
    nodes: list[dict[str, Any]] = [
        {
            "id": requirement_node_id,
            "type": "EngineeringRequirement",
            "label": requirement_id,
            "requirementId": requirement_id,
            "ontologyVersion": ENGINEERING_ONTOLOGY_VERSION,
        },
        {
            "id": capability_id,
            "type": "BusinessCapability",
            "label": business_labels[0] if business_labels else requirement_id,
            "derivedFromRequirement": requirement_id,
        },
        {
            "id": contract_id,
            "type": "SpecificationContract",
            "label": f"Specification contract for {requirement_id}",
            "desiredEntityIds": [str(item.get("entityId")) for item in desired_entities],
            "scope": list(ir.get("scope", [])),
        },
        {
            "id": ontology_id,
            "type": "OntologyAsset",
            "label": "Code Ontology engineering semantics",
            "version": ENGINEERING_ONTOLOGY_VERSION,
        },
        {
            "id": semantic_contract_id,
            "type": "SemanticContract",
            "label": f"Semantic invariants for {requirement_id}",
        },
        {
            "id": objective_id,
            "type": "VerificationObjective",
            "label": f"Verify acceptance of {requirement_id}",
        },
    ]
    edges: list[dict[str, Any]] = [
        {"source": requirement_node_id, "relation": "eng:specifiesCapability", "target": capability_id},
        {"source": requirement_node_id, "relation": "eng:definesContract", "target": contract_id},
        {"source": requirement_node_id, "relation": "eng:constrainedBy", "target": semantic_contract_id},
        {"source": semantic_contract_id, "relation": "eng:usesOntology", "target": ontology_id},
    ]
    for entity in desired_entities:
        entity_id = str(entity.get("entityId", ""))
        if not entity_id:
            continue
        edges.append(
            {
                "source": contract_id,
                "relation": "plan:specifiesDesiredEntity",
                "target": entity_id,
            }
        )
        if entity.get("entityType") != "DesiredTestObligation":
            continue
        digest = hashlib.sha256(entity_id.encode("utf-8")).hexdigest()[:16]
        method_id = f"verification:{requirement_id}:{digest}"
        nodes.append(
            {
                "id": method_id,
                "type": "TestVerification",
                "label": str(entity.get("label", entity_id)),
                "lifecycle": "Planned",
                "desiredEntityId": entity_id,
            }
        )
        edges.extend(
            [
                {"source": method_id, "relation": "eng:derivedFromObjective", "target": objective_id},
                {"source": method_id, "relation": "eng:verifiesRequirement", "target": requirement_node_id},
            ]
        )
    return {"nodes": nodes, "edges": edges}
