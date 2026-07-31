#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from code_ontology_platform.agent_runtime import CodexAdapter
from code_ontology_platform.service import PlatformService
from code_ontology_platform.store import SQLiteStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the governed requirement-to-code workflow with the local "
            "Codex CLI. Human gates are automated only when explicitly enabled."
        )
    )
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--design", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--worktree-root", type=Path, required=True)
    parser.add_argument("--rules", type=Path, required=True)
    parser.add_argument("--repository-id", default="repo-codex-workflow")
    parser.add_argument("--workflow-id", default="codex-requirement-workflow")
    parser.add_argument("--requirement-id")
    parser.add_argument("--actor", default="codex-workflow-demo")
    parser.add_argument(
        "--sandbox",
        choices=("workspace-write", "danger-full-access"),
        default=os.environ.get(
            "CODE_ONTOLOGY_CODEX_SANDBOX", "workspace-write"
        ),
    )
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument(
        "--approve-gates",
        action="store_true",
        help=(
            "Explicitly simulate all human decisions: confirm the requirement, "
            "select top alignment candidates, accept architecture, and approve "
            "the controlled implementation."
        ),
    )
    parser.add_argument(
        "--allowed-file",
        action="append",
        dest="allowed_files",
        default=[],
    )
    parser.add_argument(
        "--forbidden-file",
        action="append",
        dest="forbidden_files",
        default=[],
    )
    parser.add_argument(
        "--required-test",
        action="append",
        dest="required_tests",
        default=[],
    )
    parser.add_argument("--report", type=Path)
    return parser


def _workflow_summary(
    service: PlatformService, workflow: dict[str, Any]
) -> dict[str, Any]:
    resources = workflow.get("resourceIds", {})
    agent_run = (
        service.get_agent_run(resources["agentRunId"])
        if resources.get("agentRunId")
        else None
    )
    reconciliation = (
        service.get_reconciliation_run(resources["reconciliationRunId"])
        if resources.get("reconciliationRunId")
        else None
    )
    impact = (
        service.get_impact_run(resources["impactRunId"])
        if resources.get("impactRunId")
        else None
    )
    replay = (
        service.replay_requirement(workflow["requirementId"])
        if workflow.get("requirementId")
        else None
    )
    return {
        "workflowId": workflow["workflowId"],
        "status": workflow["status"],
        "stage": workflow["stage"],
        "pendingGate": workflow.get("pendingGate"),
        "error": workflow.get("error"),
        "nextActions": workflow.get("nextActions", []),
        "requirementId": workflow.get("requirementId"),
        "currentRevision": workflow.get("currentRevision"),
        "resourceIds": resources,
        "result": workflow.get("result"),
        "steps": workflow.get("steps", []),
        "agentRuns": workflow.get("agentRuns", []),
        "implementation": (
            {
                "status": agent_run["status"],
                "runtime": agent_run.get("runtime"),
                "runtimeVersion": agent_run.get("runtimeVersion"),
                "sessionId": agent_run.get("sessionId"),
                "worktreePath": agent_run.get("worktreePath"),
                "changedFiles": agent_run.get("diff", {}).get("changedFiles", []),
                "patchHash": agent_run.get("diff", {}).get("patchHash"),
                "executionPolicy": agent_run.get("executionPolicy"),
                "testReport": agent_run.get("testReport"),
                "error": agent_run.get("error"),
            }
            if agent_run
            else None
        ),
        "reconciliation": reconciliation,
        "impact": impact,
        "auditChain": replay.get("auditChain") if replay else None,
    }


def run(arguments: argparse.Namespace) -> dict[str, Any]:
    repository = arguments.repository.resolve()
    design = arguments.design.resolve()
    service = PlatformService(
        SQLiteStore(arguments.database.resolve()),
        arguments.rules.resolve(),
        repository_roots=[repository],
        worktree_root=arguments.worktree_root.resolve(),
        agent_adapter=CodexAdapter(
            sandbox_mode=arguments.sandbox,
            run_timeout_seconds=arguments.timeout,
        ),
    )
    registered = service.register_repository(
        {
            "repositoryId": arguments.repository_id,
            "path": str(repository),
        }
    )
    scan = service.scan_repository(registered["repositoryId"], {})
    request: dict[str, Any] = {
        "workflowId": arguments.workflow_id,
        "repositoryId": registered["repositoryId"],
        "currentRevision": scan["revision"],
        "actor": arguments.actor,
        "agentMode": "required",
        "document": {
            "documentId": f"design-{arguments.workflow_id}",
            "title": design.stem,
            "owner": arguments.actor,
        },
        "revision": {
            "revisionNumber": "1",
            "content": design.read_text(encoding="utf-8"),
        },
    }
    if arguments.requirement_id:
        request["requirementId"] = arguments.requirement_id
    workflow = service.create_requirement_workflow(request)
    if not arguments.approve_gates:
        return _workflow_summary(service, workflow)

    allowed_files = arguments.allowed_files or [
        "src/main/**",
        "src/test/**",
        "pom.xml",
    ]
    forbidden_files = arguments.forbidden_files or [
        ".git/**",
        "target/**",
        "deploy/prod/**",
    ]
    required_tests = arguments.required_tests or ["mvn test"]

    while workflow["status"] == "NeedsHumanReview":
        gate = workflow["pendingGate"]
        if gate == "RequirementReview":
            body = {
                "gate": gate,
                "decision": "Confirm",
                "actor": arguments.actor,
                "rationale": "Explicit end-to-end acceptance run.",
                "acceptUnresolved": True,
            }
        elif gate == "AlignmentReview":
            selections = []
            for item in workflow.get("pendingItems", []):
                candidates = item.get("candidates", [])
                if not candidates:
                    raise RuntimeError(
                        "Alignment gate has an item without candidates: "
                        + str(item.get("desiredEntityId"))
                    )
                selections.append(
                    {
                        "candidateId": candidates[0]["candidateId"],
                        "decision": "Confirm",
                        "rationale": "Top deterministic graph candidate selected.",
                    }
                )
            body = {
                "gate": gate,
                "actor": arguments.actor,
                "rationale": "Top deterministic graph candidates accepted.",
                "selections": selections,
            }
        elif gate == "ArchitectureReview":
            body = {
                "gate": gate,
                "decision": "Accept",
                "actor": arguments.actor,
                "rationale": "Architecture accepted for the isolated demo run.",
                "findings": [],
            }
        elif gate == "ChangeApproval":
            body = {
                "gate": gate,
                "decision": "Approve",
                "actor": arguments.actor,
                "rationale": "Approved for the isolated Codex worktree.",
                "allowedFiles": allowed_files,
                "forbiddenFiles": forbidden_files,
                "requiredTests": required_tests,
                "securityDataApproved": True,
            }
        else:
            raise RuntimeError(f"Unsupported human gate: {gate}")
        workflow = service.resume_requirement_workflow(
            workflow["workflowId"], body
        )
        if workflow["status"] == "Failed":
            break
    return _workflow_summary(service, workflow)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    if not arguments.repository.is_dir():
        parser.error(f"--repository is not a directory: {arguments.repository}")
    for option, path in (
        ("--design", arguments.design),
        ("--rules", arguments.rules),
    ):
        if not path.is_file():
            parser.error(f"{option} is not a file: {path}")
    result = run(arguments)
    output = json.dumps(result, ensure_ascii=False, indent=2)
    if arguments.report:
        arguments.report.parent.mkdir(parents=True, exist_ok=True)
        arguments.report.write_text(output + "\n", encoding="utf-8")
    print(output)
    return 0 if result["status"] == "Completed" else 1


if __name__ == "__main__":
    sys.exit(main())
