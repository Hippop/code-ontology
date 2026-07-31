from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from code_ontology_platform.agent_runtime import CodexAdapter, collect_worktree_diff
from code_ontology_platform.errors import PlatformError


def _successful_output(message: str = "completed") -> str:
    events = [
        {"type": "thread.started", "thread_id": "thread-codex-test"},
        {"type": "turn.started"},
        {
            "type": "item.completed",
            "item": {
                "id": "message-1",
                "type": "agent_message",
                "text": message,
            },
        },
        {
            "type": "turn.completed",
            "usage": {
                "input_tokens": 10,
                "cached_input_tokens": 0,
                "output_tokens": 2,
            },
        },
    ]
    return "\n".join(json.dumps(event) for event in events) + "\n"


class CodexAdapterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.repository = self.root / "repository"
        self.repository.mkdir()
        subprocess.run(
            ["git", "init", "-q", str(self.repository)],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(self.repository), "config", "user.name", "Test"],
            check=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(self.repository),
                "config",
                "user.email",
                "test@example.com",
            ],
            check=True,
        )
        (self.repository / "README.md").write_text("sample\n", encoding="utf-8")
        subprocess.run(
            ["git", "-C", str(self.repository), "add", "README.md"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(self.repository), "commit", "-qm", "initial"],
            check=True,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_exec_contract_uses_stdin_jsonl_and_governed_config(self) -> None:
        calls: list[dict[str, object]] = []

        def runner(command, **kwargs):
            calls.append({"command": command, **kwargs})
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=_successful_output("implemented"),
                stderr="warning tail",
            )

        adapter = CodexAdapter(
            sys.executable,
            sandbox_mode="danger-full-access",
            runner=runner,
        )
        result = adapter.execute(
            worktree=self.repository,
            run_id="agent-run-codex",
            prompt="Implement the approved change.",
            agent_name="implementation-agent",
            allowed_files=["README.md"],
            forbidden_files=[".git/**"],
            required_tests=[],
        )

        self.assertEqual("Codex", result["runtime"])
        self.assertEqual("thread-codex-test", result["sessionId"])
        self.assertEqual("implemented", result["message"]["text"])
        self.assertEqual(1, len(calls))
        command = calls[0]["command"]
        self.assertIn("--ignore-user-config", command)
        self.assertIn("--ephemeral", command)
        self.assertIn("--json", command)
        self.assertEqual("-", command[-1])
        self.assertIn("approval_policy", " ".join(command))
        self.assertIn("governed platform stage", str(calls[0]["input"]))

    def test_read_only_role_uses_disposable_detached_worktree(self) -> None:
        run_directories: list[Path] = []

        def runner(command, **kwargs):
            run_directories.append(Path(kwargs["cwd"]).resolve())
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=_successful_output("reviewed"),
                stderr="",
            )

        adapter = CodexAdapter(
            sys.executable,
            sandbox_mode="danger-full-access",
            runner=runner,
        )
        result = adapter.execute(
            worktree=self.repository,
            run_id="workflow-role-1",
            prompt="Review the supplied graph evidence.",
            agent_name="code-graph-analyst",
            allowed_files=[],
            forbidden_files=["**"],
            required_tests=[],
            read_only=True,
        )

        self.assertNotEqual(self.repository.resolve(), run_directories[0])
        self.assertFalse(run_directories[0].exists())
        self.assertEqual("Passed", result["readOnlyIsolation"]["status"])
        self.assertEqual(
            "sample\n",
            (self.repository / "README.md").read_text(encoding="utf-8"),
        )

    def test_read_only_role_change_is_rejected_and_cleaned(self) -> None:
        run_directories: list[Path] = []

        def runner(command, **kwargs):
            directory = Path(kwargs["cwd"]).resolve()
            run_directories.append(directory)
            (directory / "README.md").write_text("changed\n", encoding="utf-8")
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=_successful_output("reviewed"),
                stderr="",
            )

        adapter = CodexAdapter(
            sys.executable,
            sandbox_mode="danger-full-access",
            runner=runner,
        )
        with self.assertRaises(PlatformError) as captured:
            adapter.execute(
                worktree=self.repository,
                run_id="workflow-role-violation",
                prompt="Review only.",
                agent_name="architecture-reviewer",
                allowed_files=[],
                forbidden_files=["**"],
                required_tests=[],
                read_only=True,
            )

        self.assertEqual("CODEX_READ_ONLY_VIOLATION", captured.exception.code)
        self.assertFalse(run_directories[0].exists())
        self.assertEqual(
            "sample\n",
            (self.repository / "README.md").read_text(encoding="utf-8"),
        )

    def test_incomplete_jsonl_is_rejected(self) -> None:
        def runner(command, **kwargs):
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps(
                    {"type": "thread.started", "thread_id": "incomplete"}
                ),
                stderr="",
            )

        adapter = CodexAdapter(sys.executable, runner=runner)
        with self.assertRaises(PlatformError) as captured:
            adapter.execute(
                worktree=self.repository,
                run_id="agent-run-incomplete",
                prompt="No operation.",
                agent_name="implementation-agent",
                allowed_files=[],
                forbidden_files=[],
                required_tests=[],
            )
        self.assertEqual("CODEX_INVALID_RESPONSE", captured.exception.code)

    def test_untracked_build_outputs_are_not_patch_inputs(self) -> None:
        base_commit = subprocess.run(
            ["git", "-C", str(self.repository), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        (self.repository / "README.md").write_text("changed\n", encoding="utf-8")
        target = self.repository / "target" / "classes"
        target.mkdir(parents=True)
        (target / "Generated.class").write_bytes(b"\xca\xfe\xba\xbe")

        diff = collect_worktree_diff(self.repository, base_commit)

        self.assertEqual(["README.md"], diff["changedFiles"])
        self.assertNotIn("Generated.class", diff["patch"])


if __name__ == "__main__":
    unittest.main()
