from __future__ import annotations

import unittest

from code_ontology_platform.precommit_verification import (
    build_actual_change_set,
    build_actual_impact_graph,
    build_impact_obligations,
    build_precommit_review,
    build_simple_reconciliation,
    build_verification_coverage,
    build_worktree_graph_overlay,
)


class PreCommitVerificationTest(unittest.TestCase):
    def _graphs(self):
        current_nodes = [
            {"id": "service", "type": "Method", "signature": "deploy(policy)"},
            {"id": "controller", "type": "Method"},
            {"id": "batch", "type": "Method"},
            {"id": "service-test", "type": "UnitTest", "label": "ServiceTest"},
        ]
        current_edges = [
            {"source": "controller", "relation": "code:callsDirectly", "target": "service"},
            {"source": "batch", "relation": "code:callsDirectly", "target": "service"},
            {"source": "service-test", "relation": "code:verifies", "target": "service"},
        ]
        actual_nodes = [
            {"id": "service", "type": "Method", "signature": "deploy(policy,retryPolicy)"},
            {"id": "controller", "type": "Method"},
            {"id": "batch", "type": "Method"},
            {"id": "service-test", "type": "UnitTest", "label": "ServiceTest"},
        ]
        return current_nodes, current_edges, actual_nodes, list(current_edges)

    def test_missing_callers_are_blocking_impact_obligations(self) -> None:
        current_nodes, current_edges, actual_nodes, actual_edges = self._graphs()
        overlay = build_worktree_graph_overlay(
            base_revision="base",
            actual_revision="actual",
            current_nodes=current_nodes,
            current_edges=current_edges,
            actual_nodes=actual_nodes,
            actual_edges=actual_edges,
            working_tree_hash="sha256:worktree",
        )
        changes = build_actual_change_set(
            base_revision="base",
            actual_revision="actual",
            graph_overlay=overlay,
            working_tree_hash="sha256:worktree",
        )
        impact = build_actual_impact_graph(
            actual_change_set=changes,
            actual_nodes=actual_nodes,
            actual_edges=actual_edges,
        )
        obligations = build_impact_obligations(
            impact,
            actual_nodes,
            changes,
            test_report={"status": "Passed"},
        )

        missing = {
            item["entityId"]
            for item in obligations["obligations"]
            if item["obligationType"] == "RequiredModification"
            and item["status"] == "Unsatisfied"
        }
        self.assertEqual({"batch", "controller"}, missing)

        reconciliation = build_simple_reconciliation(
            planned_artifact={"changes": [{"changeId": "P1", "targetEntityId": "service"}]},
            actual_change_set=changes,
            impact_obligations=obligations,
        )
        coverage = build_verification_coverage(
            impact_obligations=obligations,
            test_report={"status": "Passed"},
        )
        review = build_precommit_review(
            working_tree_hash="sha256:worktree",
            reconciliation=reconciliation,
            verification_coverage=coverage,
            impact_obligations=obligations,
        )

        self.assertEqual("Deviated", reconciliation["status"])
        self.assertFalse(coverage["complete"])
        self.assertEqual("BlockCommit", review["decision"])
        self.assertTrue(
            any(
                item["deviationType"] == "MissingPropagationImplementation"
                for item in review["blockingIssues"]
            )
        )

    def test_all_changed_nodes_and_tests_can_close_precommit_gate(self) -> None:
        current_nodes, current_edges, _, actual_edges = self._graphs()
        actual_nodes = [
            {"id": "service", "type": "Method", "signature": "deploy(policy,retryPolicy)"},
            {"id": "controller", "type": "Method", "adapted": True},
            {"id": "batch", "type": "Method", "adapted": True},
            {"id": "service-test", "type": "UnitTest", "label": "ServiceTest", "updated": True},
        ]
        overlay = build_worktree_graph_overlay(
            base_revision="base",
            actual_revision="actual",
            current_nodes=current_nodes,
            current_edges=current_edges,
            actual_nodes=actual_nodes,
            actual_edges=actual_edges,
            working_tree_hash="sha256:worktree",
        )
        changes = build_actual_change_set(
            base_revision="base",
            actual_revision="actual",
            graph_overlay=overlay,
            working_tree_hash="sha256:worktree",
        )
        impact = build_actual_impact_graph(
            actual_change_set=changes,
            actual_nodes=actual_nodes,
            actual_edges=actual_edges,
        )
        obligations = build_impact_obligations(
            impact,
            actual_nodes,
            changes,
            test_report={"status": "Passed"},
        )
        reconciliation = build_simple_reconciliation(
            planned_artifact={
                "changes": [
                    {"changeId": "P1", "targetEntityId": "service"},
                    {"changeId": "P2", "targetEntityId": "controller"},
                    {"changeId": "P3", "targetEntityId": "batch"},
                    {"changeId": "P4", "targetEntityId": "service-test"},
                ]
            },
            actual_change_set=changes,
            impact_obligations=obligations,
        )
        coverage = build_verification_coverage(
            impact_obligations=obligations,
            test_report={"status": "Passed"},
        )
        review = build_precommit_review(
            working_tree_hash="sha256:worktree",
            reconciliation=reconciliation,
            verification_coverage=coverage,
            impact_obligations=obligations,
        )

        self.assertEqual("Conformed", reconciliation["status"])
        self.assertTrue(coverage["complete"])
        self.assertEqual("ReadyToCommit", review["decision"])


if __name__ == "__main__":
    unittest.main()
