from __future__ import annotations

import unittest

from code_ontology_platform.document_ingestion import (
    extract_requirement_ir,
    parse_design_document,
)
from code_ontology_platform.verification_workflow import reconcile_approved_actual
from code_ontology_platform.verification_workflow import build_impact_analysis


class RequirementExtractionTest(unittest.TestCase):
    def test_explicit_non_change_is_scope_not_positive_database_change(self) -> None:
        parsed = parse_design_document(
            "# Data\n\n- 不新增数据库表。\n\n"
            "# API Contract\n\n- POST `/items` 保持原操作。\n"
        )

        result = extract_requirement_ir(
            requirement_id="REQ-NO-DATABASE-CHANGE",
            design_revision_id="design@1",
            parsed_document=parsed,
        )

        self.assertIn("不新增数据库表。", result["scope"])
        self.assertNotIn(
            "DesiredDatabaseObject",
            {item["entityType"] for item in result["desiredEntities"]},
        )


class ReconciliationTest(unittest.TestCase):
    def test_passed_changed_test_satisfies_matching_test_proposal_only(self) -> None:
        test_entity_id = "code:repo:java:PolicyServiceTest#acceptance()"
        plan = {
            "planId": "plan-1",
            "changeSet": {"currentRevision": "base-1"},
            "proposals": [
                {
                    "proposalId": "proposal-acceptance-test",
                    "changeType": "ProposedTestChange",
                    "role": "ImplementDesiredTestObligation",
                    "desiredEntityId": "desired:test:acceptance",
                    "targetCurrentEntityId": "code:repo:java:ConstraintEvaluator",
                    "evidenceRefs": ["evidence:test"],
                },
                {
                    "proposalId": "proposal-event-contract-test",
                    "changeType": "ProposedTestChange",
                    "role": "AddMessageContractTest",
                    "desiredEntityId": "desired:event:rejected",
                    "targetCurrentEntityId": "code:repo:java:NetworkPolicy",
                    "evidenceRefs": ["evidence:event"],
                },
                {
                    "proposalId": "proposal-event-schema",
                    "changeType": "ProposedContractChange",
                    "role": "AddMessageSchema",
                    "desiredEntityId": "desired:event:rejected",
                    "desiredEntity": {
                        "entityId": "desired:event:rejected",
                        "entityType": "DesiredEventType",
                        "label": "Publish `NetworkPolicyRejected`.",
                        "designTokens": ["NetworkPolicyRejected"],
                    },
                    "targetCurrentEntityId": "code:repo:java:NetworkPolicy",
                    "evidenceRefs": ["evidence:event"],
                },
                {
                    "proposalId": "proposal-token-event-contract-test",
                    "changeType": "ProposedTestChange",
                    "role": "AddMessageContractTest",
                    "desiredEntityId": "desired:event:rejected",
                    "desiredEntity": {
                        "entityId": "desired:event:rejected",
                        "entityType": "DesiredEventType",
                        "label": "Publish `NetworkPolicyRejected`.",
                        "designTokens": ["NetworkPolicyRejected"],
                    },
                    "targetCurrentEntityId": "code:repo:java:NetworkPolicy",
                    "evidenceRefs": ["evidence:event"],
                },
                {
                    "proposalId": "proposal-deployment-order",
                    "changeType": "ProposedDeploymentChange",
                    "role": "AddConsumerProducerOrdering",
                    "desiredEntityId": "desired:event:rejected",
                    "targetCurrentEntityId": "code:repo:java:NetworkPolicy",
                    "evidenceRefs": ["evidence:event"],
                },
            ],
            "implementationTasks": [
                {
                    "proposalId": "proposal-acceptance-test",
                    "suggestedFiles": [],
                },
                {
                    "proposalId": "proposal-event-contract-test",
                    "suggestedFiles": [],
                },
                {
                    "proposalId": "proposal-event-schema",
                    "suggestedFiles": [],
                },
                {
                    "proposalId": "proposal-token-event-contract-test",
                    "suggestedFiles": [],
                },
                {
                    "proposalId": "proposal-deployment-order",
                    "suggestedFiles": [],
                },
            ],
            "verificationObligations": [
                {
                    "obligationId": "verify-acceptance",
                    "desiredEntityId": "desired:test:acceptance",
                    "description": "Acceptance behavior is covered.",
                    "evidenceRefs": ["evidence:test"],
                }
            ],
        }
        agent_run = {
            "runId": "agent-1",
            "requirementId": "REQ-1",
            "repositoryId": "repo",
            "status": "Completed",
            "testReport": {"status": "Passed"},
        }

        result = reconcile_approved_actual(
            reconciliation_run_id="reconciliation-1",
            agent_run=agent_run,
            plan=plan,
            current_nodes=[
                {
                    "id": "code:repo:repository",
                    "type": "Repository",
                    "label": "repo",
                }
            ],
            current_edges=[],
            actual_nodes=[
                {
                    "id": "code:repo:repository",
                    "type": "Repository",
                    "label": "repo changed aggregate",
                },
                {
                    "id": "code:repo:file:PolicyServiceTest.java",
                    "type": "SourceFile",
                },
                {"id": test_entity_id, "type": "UnitTest"},
                {
                    "id": "code:repo:java:NetworkPolicyRejected",
                    "type": "Class",
                    "label": "NetworkPolicyRejected",
                },
                {
                    "id": "code:repo:java:MessageField:reason",
                    "type": "Field",
                    "label": "reason",
                },
                {
                    "id": (
                        "code:repo:java:NetworkPolicyRejectedContractTest"
                        "#preservesSchema()"
                    ),
                    "type": "UnitTest",
                    "label": "NetworkPolicyRejectedContractTest.preservesSchema",
                },
                {
                    "id": "code:repo:java:UnrelatedHelper",
                    "type": "Class",
                    "label": "UnrelatedHelper",
                },
            ],
            actual_edges=[
                {
                    "source": "code:repo:java:NetworkPolicyRejected",
                    "relation": "code:declares",
                    "target": "code:repo:java:MessageField:reason",
                }
            ],
            actual_revision="actual-1",
            coverage={"failedJavaFiles": 0},
        )

        by_id = {item["proposalId"]: item for item in result["proposalResults"]}
        self.assertEqual("Conformed", by_id["proposal-acceptance-test"]["status"])
        self.assertIn(
            test_entity_id,
            by_id["proposal-acceptance-test"]["matchedActualEntityIds"],
        )
        self.assertEqual("Missing", by_id["proposal-event-contract-test"]["status"])
        self.assertEqual("Conformed", by_id["proposal-event-schema"]["status"])
        self.assertEqual(
            "Conformed",
            by_id["proposal-token-event-contract-test"]["status"],
        )
        self.assertEqual(
            "DeferredToReleaseGate",
            by_id["proposal-deployment-order"]["status"],
        )
        self.assertFalse(
            any(
                item.get("proposalId") == "proposal-deployment-order"
                and item["deviationType"] == "MissingApprovedChange"
                for item in result["deviations"]
            )
        )
        self.assertIn(
            "code:repo:java:MessageField:reason",
            result["claimCoverage"]["graphClosureEntityIds"],
        )
        unexpected = {
            item.get("entityId")
            for item in result["deviations"]
            if item["deviationType"] == "UnexpectedActualChange"
        }
        self.assertIn("code:repo:java:UnrelatedHelper", unexpected)
        self.assertNotIn(
            "code:repo:java:MessageField:reason",
            unexpected,
        )
        self.assertFalse(
            any(
                item.get("entityId")
                in {
                    "code:repo:repository",
                    "code:repo:file:PolicyServiceTest.java",
                }
                for item in result["deviations"]
            )
        )


class ImpactAnalysisTest(unittest.TestCase):
    def test_removed_entity_is_direct_known_impact_not_unresolved(self) -> None:
        result = build_impact_analysis(
            impact_run_id="impact-1",
            reconciliation={
                "runId": "reconciliation-1",
                "requirementId": "REQ-1",
                "actualRevision": "actual-1",
                "status": "Conformed",
                "proposalResults": [],
                "graphDelta": {
                    "addedEntityIds": [],
                    "modifiedEntityIds": [],
                    "removedEntityIds": ["code:repo:java:OldMethod"],
                },
            },
            plan={
                "proposals": [],
                "implementationTasks": [],
                "approval": {"payload": {"requiredTests": []}},
            },
            actual_nodes=[],
            actual_edges=[],
        )

        self.assertEqual(1, result["impactSummary"]["Direct"])
        self.assertEqual(0, result["impactSummary"]["Unresolved"])
        self.assertEqual("Removed", result["impacts"][0]["changeKind"])
        self.assertEqual("Standard", result["releasePlan"]["decision"])

    def test_parallel_source_relations_publish_one_valid_impact_edge(self) -> None:
        result = build_impact_analysis(
            impact_run_id="impact-parallel-relations",
            reconciliation={
                "runId": "reconciliation-parallel-relations",
                "requirementId": "REQ-1",
                "actualRevision": "actual-1",
                "status": "Conformed",
                "proposalResults": [],
                "graphDelta": {
                    "addedEntityIds": [],
                    "modifiedEntityIds": ["code:a"],
                    "removedEntityIds": [],
                },
            },
            plan={
                "proposals": [],
                "implementationTasks": [],
                "approval": {"payload": {"requiredTests": []}},
            },
            actual_nodes=[
                {"id": "code:a", "type": "Class"},
                {"id": "code:b", "type": "Class"},
            ],
            actual_edges=[
                {
                    "source": "code:a",
                    "relation": "code:dependsOn",
                    "target": "code:b",
                },
                {
                    "source": "code:a",
                    "relation": "code:callsDirectly",
                    "target": "code:b",
                },
            ],
        )

        self.assertEqual(1, len(result["graph"]["edges"]))
        self.assertEqual(
            ["code:callsDirectly", "code:dependsOn"],
            result["graph"]["edges"][0]["sourceRelations"],
        )


if __name__ == "__main__":
    unittest.main()
