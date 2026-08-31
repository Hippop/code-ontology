from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from code_ontology_platform.evaluation.graph_judge import GraphJudge
from code_ontology_platform.evaluation.judges import GateJudge
from code_ontology_platform.evaluation.loader import EvaluationLoader
from code_ontology_platform.evaluation.metrics import aggregate_metrics
from code_ontology_platform.evaluation.models import JudgeResult
from code_ontology_platform.evaluation.mutations import (
    MutationDefinition,
    MutationRegistry,
)
from code_ontology_platform.evaluation.reports import compare_run_sets
from code_ontology_platform.evaluation.runner import (
    BatchEvaluationRunner,
    FileArtifactBackend,
)


class EvaluationHarnessTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        (self.root / "fixture").mkdir()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _scenario(
        self,
        *,
        expected: dict,
        actual: dict,
        expected_decision: str = "ReadyToCommit",
        actual_decision: str = "ReadyToCommit",
        compare: str = "graph",
    ) -> Path:
        (self.root / "expected.json").write_text(
            json.dumps(expected), encoding="utf-8"
        )
        (self.root / "actual.json").write_text(
            json.dumps(actual), encoding="utf-8"
        )
        scenario = f"""schemaVersion: evaluation-scenario/v1
scenarioId: PRECOMMIT-TEST-001
workflow: precommit
fixture:
  id: fixture-1
  path: fixture
  revision: base-v1
  level: micro
input:
  actualArtifacts:
    actualImpactGraph: actual.json
  actualDecision: {actual_decision}
expected:
  actualImpactGraph:
    path: expected.json
    oracle: rule-derived
    compare: {compare}
expectedDecision: {expected_decision}
"""
        path = self.root / "scenario.yaml"
        path.write_text(scenario, encoding="utf-8")
        return path

    def test_loader_and_runner_pass_identical_graph(self) -> None:
        graph = {
            "nodes": [{"id": "service"}, {"id": "controller"}],
            "edges": [
                {
                    "source": "controller",
                    "relation": "calls",
                    "target": "service",
                }
            ],
        }
        loader = EvaluationLoader()
        scenario = loader.load_scenario(
            self._scenario(expected=graph, actual=graph)
        )
        run = BatchEvaluationRunner(
            FileArtifactBackend(loader),
            loader,
        ).run_scenario(scenario)

        self.assertEqual("Passed", run.status)
        self.assertEqual(1.0, run.metrics["nodeRecall"])
        self.assertEqual(0.0, run.metrics["falseReadyRate"])
        self.assertIsNone(run.diagnosis)

    def test_graph_judge_detects_missing_impact_node(self) -> None:
        expected = {
            "nodes": [{"id": "controller"}, {"id": "batch-job"}],
            "edges": [],
        }
        actual = {"nodes": [{"id": "controller"}], "edges": []}

        result = GraphJudge().judge(
            "actualImpactGraph",
            expected,
            actual,
            stage="actualImpactGraph",
        )

        self.assertEqual("Failed", result.status)
        self.assertEqual(0.5, result.metrics["nodeRecall"])
        self.assertIn("batch-job", result.missing)

    def test_false_ready_is_explicit_and_penalized(self) -> None:
        gate = GateJudge().judge("BlockCommit", "ReadyToCommit")
        metrics = aggregate_metrics(
            [
                JudgeResult(
                    judge="ArtifactJudge",
                    artifact_type="reconciliation",
                    status="Failed",
                    score=0.5,
                    metrics={"recall": 0.5},
                ),
                gate,
            ]
        )

        self.assertEqual(1.0, gate.metrics["falseReady"])
        self.assertEqual(1.0, metrics["falseReadyRate"])
        self.assertEqual(0.0, metrics["safetyWeightedScore"])

    def test_artifact_mutation_can_drop_expected_item(self) -> None:
        artifact = {
            "impacts": [
                {"impactId": "I1", "target": "controller"},
                {"impactId": "I2", "target": "batch-job"},
            ]
        }
        mutation = MutationDefinition(
            mutation_id="drop-batch",
            kind="artifact",
            operation="RemoveArtifactItem",
            target={"collection": "impacts"},
            selector={"id": "I2"},
        )

        result = MutationRegistry().apply_artifact(mutation, artifact)

        self.assertTrue(result.changed)
        self.assertEqual(
            ["I1"],
            [item["impactId"] for item in result.details["artifact"]["impacts"]],
        )
        self.assertEqual(2, len(artifact["impacts"]))

    def test_run_set_comparison_identifies_regression(self) -> None:
        baseline = {
            "runs": [
                {
                    "scenario_id": "S1",
                    "status": "Passed",
                    "metrics": {"nodeRecall": 1.0},
                }
            ]
        }
        candidate = {
            "runs": [
                {
                    "scenario_id": "S1",
                    "status": "Failed",
                    "metrics": {"nodeRecall": 0.5},
                }
            ]
        }

        comparison = compare_run_sets(baseline, candidate)

        self.assertEqual(1, comparison["regressionCount"])
        self.assertEqual(
            -0.5,
            comparison["regressions"][0]["metricDelta"]["nodeRecall"],
        )


if __name__ == "__main__":
    unittest.main()
