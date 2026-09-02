from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from code_ontology_platform.precommit_verification import PreCommitVerifier


def run(repository: Path, *arguments: str) -> None:
    subprocess.run(["git", *arguments], cwd=repository, check=True, stdout=subprocess.PIPE)


def model() -> dict:
    return {
        "graphId": "urn:test:precommit",
        "revision": "v1",
        "nodes": [
            {"id": "cap:service", "type": "BusinessCapability"},
            {"id": "req:service", "type": "EngineeringRequirement"},
            {"id": "contract:service", "type": "BehaviorContract"},
            {"id": "code:service", "type": "Class", "path": "src/service.py"},
            {"id": "test:service", "type": "UnitTest", "path": "tests/test_service.py"},
        ],
        "edges": [
            {"source": "req:service", "relation": "eng:specifiesCapability", "target": "cap:service"},
            {"source": "req:service", "relation": "eng:definesContract", "target": "contract:service"},
            {"source": "code:service", "relation": "code:implementsRequirement", "target": "req:service"},
            {"source": "test:service", "relation": "code:verifies", "target": "req:service"},
        ],
    }


class PreCommitVerifierTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.repository = Path(self.temp.name)
        run(self.repository, "init", "-q")
        run(self.repository, "config", "user.email", "test@example.com")
        run(self.repository, "config", "user.name", "Test")
        (self.repository / "src").mkdir()
        (self.repository / "tests").mkdir()
        (self.repository / "src/service.py").write_text("VALUE = 1\n", encoding="utf-8")
        (self.repository / "tests/test_service.py").write_text("def test_value(): pass\n", encoding="utf-8")
        run(self.repository, "add", ".")
        run(self.repository, "commit", "-qm", "initial")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def verifier(self) -> PreCommitVerifier:
        return PreCommitVerifier(
            self.repository,
            model(),
            planned_changes=[
                {"planId": "change-service", "targetPath": "src/service.py"},
                {"planId": "change-test", "targetPath": "tests/test_service.py"},
            ],
            verification_results=[{"name": "unit", "status": "Passed"}],
        )

    def test_complete_plan_and_actual_change_are_ready(self) -> None:
        (self.repository / "src/service.py").write_text("VALUE = 2\n", encoding="utf-8")
        (self.repository / "tests/test_service.py").write_text("def test_value(): assert True\n", encoding="utf-8")
        result = self.verifier().verify()
        self.assertEqual("ReadyToCommit", result["status"], result)
        self.assertEqual(2, len(result["actualChangeSet"]["items"]))

    def test_stale_snapshot_blocks_commit(self) -> None:
        (self.repository / "src/service.py").write_text("VALUE = 2\n", encoding="utf-8")
        (self.repository / "tests/test_service.py").write_text("def test_value(): assert True\n", encoding="utf-8")
        first = self.verifier().verify()
        old_hash = first["snapshot"]["workingTreeSnapshotHash"]
        (self.repository / "src/service.py").write_text("VALUE = 3\n", encoding="utf-8")
        result = self.verifier().verify(reviewed_snapshot_hash=old_hash)
        self.assertEqual("BlockCommit", result["status"])
        self.assertIn("STALE_REVIEW", {item["code"] for item in result["blockers"]})

    def test_missing_planned_test_blocks_commit(self) -> None:
        (self.repository / "src/service.py").write_text("VALUE = 2\n", encoding="utf-8")
        result = self.verifier().verify()
        self.assertEqual("BlockCommit", result["status"])
        self.assertIn("change-test", result["implementationReconciliation"]["missingPlanIds"])


if __name__ == "__main__":
    unittest.main()
