from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from code_ontology_platform.evaluation.loader import EvaluationLoader
from code_ontology_platform.evaluation.platform_backends import (
    PlatformWorkflowBackend,
    _prepare_git_base,
)
from code_ontology_platform.evaluation.runner import BatchEvaluationRunner


class EvaluationPlatformBackendTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_prepare_git_base_initializes_non_git_fixture(self) -> None:
        repository = self.root / "fixture"
        repository.mkdir()
        (repository / "README.md").write_text("fixture\n", encoding="utf-8")

        commit = _prepare_git_base(repository, "HEAD")

        self.assertTrue((repository / ".git").is_dir())
        self.assertTrue(commit)
        self.assertEqual(
            commit,
            __import__("subprocess")
            .run(
                ["git", "-C", str(repository), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            )
            .stdout.strip(),
        )

    def test_platform_precommit_backend_blocks_missing_callers(self) -> None:
        fixture = self.root / "retry-service"
        repo = fixture / "repo"
        source = repo / "src" / "main" / "java" / "eval" / "retry"
        tests = repo / "src" / "test" / "java" / "eval" / "retry"
        source.mkdir(parents=True)
        tests.mkdir(parents=True)
        (repo / "pom.xml").write_text(
            "<project xmlns=\"http://maven.apache.org/POM/4.0.0\">"
            "<modelVersion>4.0.0</modelVersion>"
            "<groupId>eval</groupId><artifactId>retry-service</artifactId>"
            "<version>1.0.0</version></project>",
            encoding="utf-8",
        )
        (source / "DeployService.java").write_text(
            "package eval.retry; public class DeployService { "
            "public String deploy(String policy) { return \"READY\"; } }",
            encoding="utf-8",
        )
        (source / "DeployController.java").write_text(
            "package eval.retry; public class DeployController { "
            "private final DeployService service; "
            "public DeployController(DeployService service) { this.service=service; } "
            "public String handle(String policy) { return service.deploy(policy); } }",
            encoding="utf-8",
        )
        (source / "BatchDeployJob.java").write_text(
            "package eval.retry; public class BatchDeployJob { "
            "private final DeployService service; "
            "public BatchDeployJob(DeployService service) { this.service=service; } "
            "public String execute(String policy) { return service.deploy(policy); } }",
            encoding="utf-8",
        )
        (tests / "DeployServiceTest.java").write_text(
            "package eval.retry; import org.junit.jupiter.api.Test; "
            "public class DeployServiceTest { private final DeployService service=new DeployService(); "
            "@Test void deploysPolicy(){ service.deploy(\"policy\"); } }",
            encoding="utf-8",
        )

        patch = self.root / "service.patch"
        patch.write_text(
            "diff --git a/src/main/java/eval/retry/DeployService.java "
            "b/src/main/java/eval/retry/DeployService.java\n"
            "--- a/src/main/java/eval/retry/DeployService.java\n"
            "+++ b/src/main/java/eval/retry/DeployService.java\n"
            "@@ -1 +1 @@\n"
            "-package eval.retry; public class DeployService { public String deploy(String policy) { return \"READY\"; } }\n"
            "+package eval.retry; public class DeployService { public String deploy(String policy) { return \"READY_RETRY\"; } }\n",
            encoding="utf-8",
        )
        expected = self.root / "expected.json"
        expected.write_text(
            json.dumps(
                {
                    "decision": "BlockCommit",
                    "blockingIssues": [
                        {"deviationType": "MissingPropagationImplementation"}
                    ],
                }
            ),
            encoding="utf-8",
        )
        scenario_path = self.root / "scenario.yaml"
        scenario_path.write_text(
            f"""schemaVersion: evaluation-scenario/v1
scenarioId: PLATFORM-PRECOMMIT-TEST
workflow: precommit
fixture:
  id: retry-service
  path: {fixture.as_posix()}
  revision: HEAD
  level: micro
input:
  workingTreePatch: {patch.as_posix()}
  testReport:
    status: Passed
    executions: []
expected:
  preCommitReview:
    path: {expected.as_posix()}
    oracle: deterministic
    compare: constraint
expectedDecision: BlockCommit
""",
            encoding="utf-8",
        )

        loader = EvaluationLoader()
        scenario = loader.load_scenario(scenario_path)
        run = BatchEvaluationRunner(
            PlatformWorkflowBackend(loader=loader), loader
        ).run_scenario(scenario)

        self.assertEqual("Passed", run.status)
        self.assertEqual("BlockCommit", run.final_decision)
        self.assertEqual(0.0, run.metrics["falseReadyRate"])


if __name__ == "__main__":
    unittest.main()
