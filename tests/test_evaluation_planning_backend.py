from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from code_ontology_platform.evaluation.loader import EvaluationLoader
from code_ontology_platform.evaluation.platform_backends import PlatformWorkflowBackend
from code_ontology_platform.evaluation.runner import BatchEvaluationRunner

ROOT = Path(__file__).resolve().parents[1]
JAVA_SAMPLE = ROOT / "examples" / "java-spring-sample"
DESIGN_SAMPLE = ROOT / "examples" / "designs" / "sdn-minimum-bandwidth.md"


class EvaluationPlanningBackendTest(unittest.TestCase):
    def test_platform_planning_backend_reaches_change_plan_review(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            expected = root / "expected.json"
            expected.write_text(
                json.dumps({"decision": "NeedsReview"}), encoding="utf-8"
            )
            scenario_path = root / "scenario.yaml"
            scenario_path.write_text(
                f"""schemaVersion: evaluation-scenario/v1
scenarioId: PLATFORM-PLANNING-TEST
workflow: planning
fixture:
  id: java-spring-sample
  path: {JAVA_SAMPLE.as_posix()}
  revision: HEAD
  level: feature
input:
  requirementId: REQ-SDN-2026-001
  designDocument: {DESIGN_SAMPLE.as_posix()}
  autoConfirmTopCandidate: true
expected:
  changePlanReview:
    path: {expected.as_posix()}
    oracle: deterministic
    compare: constraint
expectedDecision: NeedsReview
""",
                encoding="utf-8",
            )

            loader = EvaluationLoader()
            scenario = loader.load_scenario(scenario_path)
            run = BatchEvaluationRunner(
                PlatformWorkflowBackend(loader=loader), loader
            ).run_scenario(scenario)

            self.assertEqual("Passed", run.status)
            self.assertEqual("NeedsReview", run.final_decision)
            self.assertEqual(0.0, run.metrics["falseReadyRate"])
            stage_types = {stage.stage_type for stage in run.stages}
            self.assertTrue(
                {
                    "designIntent",
                    "alignment",
                    "changeSet",
                    "plannedImpactGraph",
                    "nodeRequirements",
                    "changePlanReview",
                }.issubset(stage_types)
            )


if __name__ == "__main__":
    unittest.main()
