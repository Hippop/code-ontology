from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from code_ontology_platform.agent_runtime import (
    GitWorktreeManager,
    ScriptedAgentAdapter,
    collect_worktree_diff,
    validate_changed_paths,
    validate_test_command,
)
from code_ontology_platform.errors import PlatformError
from code_ontology_platform.service import PlatformService
from code_ontology_platform.store import SQLiteStore

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "rules" / "requirement-change-planning-rules.yaml"
JAVA_SAMPLE = ROOT / "examples" / "java-spring-sample"
DESIGN_SAMPLE = ROOT / "examples" / "designs" / "sdn-minimum-bandwidth.md"


def _git(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


class ExecutionWorkflowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.repository = self.root / "repository"
        shutil.copytree(JAVA_SAMPLE, self.repository)
        wrapper = self.repository / "mvnw"
        wrapper.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        wrapper.chmod(0o755)
        _git(self.repository, "init")
        _git(self.repository, "checkout", "-b", "main")
        _git(self.repository, "config", "user.name", "Platform Test")
        _git(self.repository, "config", "user.email", "platform@example.invalid")
        _git(self.repository, "add", ".")
        _git(self.repository, "commit", "-m", "fixture")
        self.base_commit = _git(self.repository, "rev-parse", "HEAD")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _approved_service(self, action) -> tuple[PlatformService, dict]:
        service = PlatformService(
            SQLiteStore(self.root / "platform.db"),
            RULES,
            repository_roots=[self.root],
            worktree_root=self.root / "worktrees",
            agent_adapter=ScriptedAgentAdapter(action),
        )
        repository = service.register_repository(
            {"repositoryId": "repo-execution", "path": str(self.repository)}
        )
        scan = service.scan_repository(repository["repositoryId"], {})
        self.assertEqual(self.base_commit, scan["revision"])
        document = service.create_design_document(
            {"documentId": "DESIGN-EXECUTION", "title": "Execution design"}
        )
        revision = service.create_design_revision(
            document["documentId"],
            {
                "revisionNumber": "1",
                "content": DESIGN_SAMPLE.read_text(encoding="utf-8"),
            },
        )
        service.extract_design_revision(revision["revisionId"], {})
        service.review_requirement(
            "REQ-SDN-2026-001",
            {
                "decision": "Confirm",
                "actor": "architect",
                "rationale": "Confirmed for execution test.",
            },
        )
        alignment = service.create_alignment_run(
            {
                "requirementId": "REQ-SDN-2026-001",
                "repositoryId": repository["repositoryId"],
                "currentRevision": scan["revision"],
            }
        )
        for item in list(alignment["alignments"]):
            alignment = service.review_alignment(
                item["candidates"][0]["candidateId"],
                {
                    "decision": "Confirm",
                    "actor": "developer",
                    "rationale": "Confirmed from source evidence.",
                },
            )
        plan = service.create_change_plan({"alignmentRunId": alignment["runId"]})
        service.review_change_plan(
            plan["planId"],
            {
                "decision": "Accept",
                "actor": "independent-architect",
                "rationale": "Architecture reviewed.",
            },
        )
        plan = service.approve_change_plan(
            plan["planId"],
            {
                "actor": "change-board",
                "rationale": "Approved for isolated implementation.",
                "allowedFiles": ["src/main/**", "src/test/**"],
                "forbiddenFiles": [".git/**", "deploy/prod/**"],
                "requiredTests": ["./mvnw test"],
                "securityDataApproved": True,
            },
        )
        return service, plan

    def test_agent_worktree_actual_reconciliation_and_impact_loop(self) -> None:
        def implement(worktree: Path, _prompt: str):
            target = worktree / "src/main/java/org/example/sdn/PolicyService.java"
            target.write_text(
                target.read_text(encoding="utf-8")
                + "\n// approved minimum bandwidth implementation\n",
                encoding="utf-8",
            )
            return {"status": "implemented"}

        service, plan = self._approved_service(implement)
        run = service.create_agent_run(
            {
                "runId": "agent-run-conformant",
                "changePlanId": plan["planId"],
                "repositoryId": "repo-execution",
                "baseCommit": self.base_commit,
                "actor": "implementation-owner",
            }
        )

        self.assertEqual("Completed", run["status"])
        self.assertTrue(run["diff"]["headUnchanged"])
        self.assertEqual("Passed", run["executionPolicy"]["status"])
        self.assertEqual("Passed", run["testReport"]["status"])
        self.assertEqual(
            [
                "src/main/java/org/example/sdn/PolicyService.java",
            ],
            run["diff"]["changedFiles"],
        )
        self.assertEqual(self.base_commit, _git(self.repository, "rev-parse", "HEAD"))
        artifacts = service.list_artifacts(run["runId"])["artifacts"]
        self.assertEqual(
            {"ImplementationPatch", "TestExecutionReport"},
            {item["artifactType"] for item in artifacts},
        )

        reconciliation = service.create_reconciliation_run(
            {"agentRunId": run["runId"], "actor": "verification-owner"}
        )
        self.assertTrue(reconciliation["actualRevision"].startswith("actual:"))
        self.assertIn(
            "code:repo-execution:java:org.example.sdn.PolicyService",
            reconciliation["graphDelta"]["modifiedEntityIds"],
        )
        self.assertTrue(reconciliation["proposalResults"])
        self.assertTrue(reconciliation["verificationResults"])

        impact = service.create_impact_run(
            {
                "reconciliationRunId": reconciliation["runId"],
                "actor": "release-owner",
            }
        )
        self.assertEqual("Completed", impact["status"])
        self.assertGreater(impact["impactSummary"]["Direct"], 0)
        self.assertTrue(impact["releasePlan"]["requiresHumanReleaseGate"])
        self.assertIn(
            impact["releasePlan"]["decision"], {"Blocked", "Canary", "Standard"}
        )
        impact_nodes, _ = service.store.read_graph("impact", impact["runId"])
        self.assertTrue(impact_nodes)
        runtime = service.record_runtime_evidence(
            {
                "requirementId": "REQ-SDN-2026-001",
                "impactRunId": impact["runId"],
                "environment": "staging",
                "deploymentVersion": "sdn-service:1.2.3-rc1",
                "configurationSnapshot": {
                    "metrics.maxAgeSeconds": 30,
                    "southbound.password": "must-not-leak",
                },
                "verificationChecks": [
                    {
                        "name": "minimum-bandwidth-smoke",
                        "status": "Passed",
                        "evidence": {"traceId": "trace-staging-1"},
                    }
                ],
                "metrics": {"rejectedStalePaths": 3},
                "actor": "sre",
            }
        )
        self.assertEqual("Verified", runtime["status"])
        self.assertTrue(
            runtime["configurationSnapshot"]["southbound.password"]["redacted"]
        )
        self.assertNotIn("must-not-leak", str(runtime))
        with self.assertRaises(PlatformError):
            service.record_runtime_evidence(
                {
                    "requirementId": "REQ-SDN-2026-001",
                    "impactRunId": impact["runId"],
                    "environment": "production",
                    "deploymentVersion": "sdn-service:1.2.3",
                    "verificationChecks": [{"name": "smoke", "status": "Failed"}],
                    "releaseApproval": {
                        "decision": "Approve",
                        "actor": "release-owner",
                        "rationale": "Ready.",
                    },
                }
            )
        replay = service.replay_requirement("REQ-SDN-2026-001")
        self.assertEqual("Verified", replay["auditChain"]["status"])
        self.assertTrue(replay["resources"]["agentRuns"])
        self.assertTrue(replay["resources"]["reconciliationRuns"])
        self.assertTrue(replay["resources"]["impactRuns"])
        self.assertTrue(replay["resources"]["runtimeEvidence"])
        self.assertTrue(replay["replayHash"].startswith("sha256:"))

    def test_multi_agent_requirement_workflow_pauses_and_resumes_all_gates(
        self,
    ) -> None:
        role_calls: list[str] = []
        architecture_attempts = 0

        def role(_repository: Path, prompt: str):
            nonlocal architecture_attempts
            role_calls.append(prompt)
            if "`architecture-reviewer`" in prompt:
                architecture_attempts += 1
                if architecture_attempts == 1:
                    raise PlatformError(
                        504,
                        "OPENCODE_RUN_TIMEOUT",
                        "simulated bounded architecture timeout",
                    )
            return {"status": "reviewed", "evidence": ["platform-context"]}

        def implement(worktree: Path, _prompt: str):
            target = worktree / "src/main/java/org/example/sdn/PolicyService.java"
            target.write_text(
                target.read_text(encoding="utf-8") + "\n// workflow implementation\n",
                encoding="utf-8",
            )
            return {"status": "implemented"}

        service = PlatformService(
            SQLiteStore(self.root / "workflow.db"),
            RULES,
            repository_roots=[self.root],
            worktree_root=self.root / "workflow-worktrees",
            agent_adapter=ScriptedAgentAdapter(implement),
            role_agent_adapter=ScriptedAgentAdapter(role),
        )
        repository = service.register_repository(
            {"repositoryId": "repo-workflow", "path": str(self.repository)}
        )
        scan = service.scan_repository(repository["repositoryId"], {})
        workflow = service.create_requirement_workflow(
            {
                "workflowId": "requirement-workflow-complete",
                "repositoryId": repository["repositoryId"],
                "currentRevision": scan["revision"],
                "requirementId": "REQ-SDN-2026-001",
                "actor": "product-owner",
                "agentMode": "required",
                "document": {
                    "documentId": "DESIGN-WORKFLOW",
                    "title": "Workflow design",
                },
                "revision": {
                    "revisionNumber": "1",
                    "content": DESIGN_SAMPLE.read_text(encoding="utf-8"),
                },
            }
        )
        self.assertEqual("NeedsHumanReview", workflow["status"])
        self.assertEqual("RequirementReview", workflow["pendingGate"])
        self.assertEqual(1, len(workflow["agentRuns"]))

        workflow = service.resume_requirement_workflow(
            workflow["workflowId"],
            {
                "gate": "RequirementReview",
                "decision": "Confirm",
                "actor": "product-owner",
                "rationale": "Requirement semantics confirmed.",
            },
        )
        self.assertEqual("AlignmentReview", workflow["pendingGate"])
        self.assertTrue(workflow["pendingItems"])

        selections = [
            {
                "candidateId": item["candidates"][0]["candidateId"],
                "decision": "Confirm",
            }
            for item in workflow["pendingItems"]
        ]
        workflow = service.resume_requirement_workflow(
            workflow["workflowId"],
            {
                "gate": "AlignmentReview",
                "actor": "domain-architect",
                "rationale": "Mappings confirmed from evidence.",
                "selections": selections,
            },
        )
        self.assertEqual("Failed", workflow["status"])
        self.assertEqual("architecture-reviewer", workflow["stage"])
        self.assertIn("RetryFailedStage", workflow["nextActions"])

        workflow = service.retry_requirement_workflow(
            workflow["workflowId"],
            {
                "actor": "platform-operator",
                "rationale": "Retry the isolated failed role with the same evidence.",
            },
        )
        self.assertEqual("ArchitectureReview", workflow["pendingGate"])
        self.assertEqual(5, len(workflow["agentRuns"]))

        workflow = service.resume_requirement_workflow(
            workflow["workflowId"],
            {
                "gate": "ArchitectureReview",
                "decision": "Accept",
                "actor": "independent-architect",
                "rationale": "Architecture, contract, and data changes reviewed.",
                "findings": [],
            },
        )
        self.assertEqual("ChangeApproval", workflow["pendingGate"])

        workflow = service.resume_requirement_workflow(
            workflow["workflowId"],
            {
                "gate": "ChangeApproval",
                "decision": "Approve",
                "actor": "change-board",
                "rationale": "Approved for controlled implementation.",
                "allowedFiles": ["src/main/**", "src/test/**"],
                "forbiddenFiles": [".git/**", "deploy/prod/**"],
                "requiredTests": ["./mvnw test"],
                "securityDataApproved": True,
            },
        )
        self.assertEqual("Completed", workflow["status"])
        self.assertIsNone(workflow["pendingGate"])
        self.assertEqual(6, len(role_calls))
        self.assertEqual(7, len(workflow["agentRuns"]))
        self.assertEqual(2, architecture_attempts)
        self.assertIn("agentRunId", workflow["resourceIds"])
        self.assertIn("reconciliationRunId", workflow["resourceIds"])
        self.assertIn("impactRunId", workflow["resourceIds"])
        loaded = service.get_requirement_workflow(workflow["workflowId"])
        self.assertEqual(workflow["resourceIds"], loaded["resourceIds"])
        replay = service.replay_requirement("REQ-SDN-2026-001")
        self.assertTrue(replay["resources"]["workflowRuns"])
        self.assertEqual("Verified", replay["auditChain"]["status"])

    def test_outside_allowlist_is_rejected_and_tests_are_not_run(self) -> None:
        def violate(worktree: Path, _prompt: str):
            (worktree / "README.md").write_text("unauthorized\n", encoding="utf-8")
            return {"status": "attempted"}

        service, plan = self._approved_service(violate)
        run = service.create_agent_run(
            {
                "runId": "agent-run-policy-violation",
                "changePlanId": plan["planId"],
                "repositoryId": "repo-execution",
                "baseCommit": self.base_commit,
            }
        )
        self.assertEqual("PolicyViolation", run["status"])
        self.assertEqual(
            ["README.md"],
            run["executionPolicy"]["pathValidation"]["outsideAllowlist"],
        )
        self.assertEqual("Skipped", run["testReport"]["status"])
        with self.assertRaises(PlatformError):
            service.create_reconciliation_run({"agentRunId": run["runId"]})

    def test_worktree_and_command_policies_are_deterministic(self) -> None:
        manager = GitWorktreeManager(self.root / "direct-worktrees")
        worktree = manager.create(self.repository, "agent-run-direct", self.base_commit)
        target = worktree.path / "src/main/java/New.java"
        target.write_text("class New {}\n", encoding="utf-8")
        diff = collect_worktree_diff(worktree.path, self.base_commit)
        validation = validate_changed_paths(
            diff["changedFiles"], ["src/main/**"], [".git/**"]
        )
        self.assertEqual("Passed", validation["status"])
        self.assertEqual(["./mvnw", "test"], validate_test_command("./mvnw test"))
        with self.assertRaises(PlatformError):
            validate_test_command("git push origin main")
        manager.remove(worktree)


if __name__ == "__main__":
    unittest.main()
