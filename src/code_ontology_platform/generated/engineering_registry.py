"""Generated from the governed engineering ontology model. Do not edit manually."""

from __future__ import annotations

from dataclasses import dataclass

MODEL_ID = 'urn:graph:engineering:code-ontology'
MODEL_REVISION = '1.0.0'
GENERATION_CONTRACT_ID = 'contract:ontology-code-generation'


@dataclass(frozen=True)
class EngineeringRequirementRecord:
    requirement_id: str
    label: str
    capability_ids: tuple[str, ...]
    contract_ids: tuple[str, ...]
    implementation_ids: tuple[str, ...]
    verification_ids: tuple[str, ...]


ENGINEERING_REQUIREMENTS = (
    EngineeringRequirementRecord(
        requirement_id='req:audit-replay',
        label='Persist artifacts, decisions and hashes in a verifiable replay chain',
        capability_ids=('cap:audit-replay',),
        contract_ids=('contract:audit-replay',),
        implementation_ids=('code:audit-store',),
        verification_ids=('test:audit-replay', 'verification:audit-replay'),
    ),
    EngineeringRequirementRecord(
        requirement_id='req:controlled-agent',
        label='Generate implementation only inside an approved isolated Worktree and execution policy',
        capability_ids=('cap:controlled-agent',),
        contract_ids=('contract:controlled-agent',),
        implementation_ids=('code:agent-runtime',),
        verification_ids=('test:controlled-agent', 'verification:controlled-agent'),
    ),
    EngineeringRequirementRecord(
        requirement_id='req:graph-intelligence',
        label='Provide version-aware search, graph traversal, change detection and impact analysis',
        capability_ids=('cap:graph-intelligence',),
        contract_ids=('contract:graph-intelligence',),
        implementation_ids=('code:code-intelligence', 'code:graph-analysis'),
        verification_ids=('test:graph-intelligence', 'verification:graph-intelligence'),
    ),
    EngineeringRequirementRecord(
        requirement_id='req:ontology-code-generation',
        label='Generate deterministic compilable Python artifacts from governed RequirementContract nodes',
        capability_ids=('cap:ontology-code-generation',),
        contract_ids=('contract:ontology-code-generation',),
        implementation_ids=('code:ontology-codegen',),
        verification_ids=('test:ontology-code-generation', 'verification:ontology-code-generation'),
    ),
    EngineeringRequirementRecord(
        requirement_id='req:ontology-lifecycle-workbench',
        label='Provide an operable ontology-to-code lifecycle UI with model authoring, generation preview and exact-snapshot commit gates',
        capability_ids=('cap:ontology-lifecycle-workbench',),
        contract_ids=('contract:ontology-lifecycle-workbench',),
        implementation_ids=('code:ontology-lifecycle-styles', 'code:ontology-lifecycle-workbench', 'code:web-document', 'code:web-shared-styles'),
        verification_ids=('test:ontology-lifecycle-workbench', 'verification:ontology-lifecycle-workbench'),
    ),
    EngineeringRequirementRecord(
        requirement_id='req:platform-access',
        label='Expose graph and workflow capabilities through governed HTTP, MCP and Web interfaces',
        capability_ids=('cap:platform-access',),
        contract_ids=('contract:platform-access',),
        implementation_ids=('code:http-api', 'code:mcp-gateway', 'code:web-workbench'),
        verification_ids=('test:platform-access', 'verification:platform-access'),
    ),
    EngineeringRequirementRecord(
        requirement_id='req:precommit-verification',
        label='Bind plan-to-actual reconciliation and impact closure to an exact Working Tree snapshot',
        capability_ids=('cap:precommit-verification',),
        contract_ids=('contract:precommit-verification',),
        implementation_ids=('code:precommit-verification',),
        verification_ids=('test:precommit-verification', 'verification:precommit-verification'),
    ),
    EngineeringRequirementRecord(
        requirement_id='req:repository-facts',
        label='Extract versioned repository facts without AI-authored Current Graph data',
        capability_ids=('cap:repository-facts',),
        contract_ids=('contract:repository-facts',),
        implementation_ids=('code:repository-scan',),
        verification_ids=('test:repository-facts', 'verification:repository-facts'),
    ),
    EngineeringRequirementRecord(
        requirement_id='req:requirement-planning',
        label='Transform confirmed Requirement IR into an approved versioned change plan',
        capability_ids=('cap:requirement-planning',),
        contract_ids=('contract:requirement-planning',),
        implementation_ids=('code:workflow-orchestration',),
        verification_ids=('test:requirement-planning', 'verification:requirement-planning'),
    ),
    EngineeringRequirementRecord(
        requirement_id='req:semantic-governance',
        label='Validate engineering ownership, contracts, verification and evidence',
        capability_ids=('cap:semantic-governance',),
        contract_ids=('contract:semantic-governance',),
        implementation_ids=('code:engineering-semantics',),
        verification_ids=('test:semantic-governance', 'verification:semantic-governance'),
    ),
    EngineeringRequirementRecord(
        requirement_id='req:verification-release',
        label='Reconcile Approved and Actual graphs and retain a human release gate',
        capability_ids=('cap:verification-release',),
        contract_ids=('contract:verification-release',),
        implementation_ids=('code:deployment', 'code:verification-workflow'),
        verification_ids=('test:verification-release', 'verification:verification-release'),
    ),
)

REQUIREMENT_BY_ID = {item.requirement_id: item for item in ENGINEERING_REQUIREMENTS}


def get_requirement(requirement_id: str) -> EngineeringRequirementRecord:
    return REQUIREMENT_BY_ID[requirement_id]
