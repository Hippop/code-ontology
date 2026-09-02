from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Iterable, Mapping

from .engineering_semantics import EngineeringSemantics, node_type
from .ontology_codegen import load_model


def _git(repository: Path, *arguments: str) -> bytes:
    process = subprocess.run(
        ["git", *arguments],
        cwd=repository,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if process.returncode != 0:
        raise ValueError(process.stderr.decode("utf-8", errors="replace").strip())
    return process.stdout


def _changed_entries(repository: Path) -> list[dict[str, str]]:
    values = _git(repository, "diff", "--name-status", "-z", "HEAD").split(b"\0")
    values = [value.decode("utf-8", errors="surrogateescape") for value in values if value]
    entries: list[dict[str, str]] = []
    index = 0
    while index < len(values):
        status = values[index]
        index += 1
        if status.startswith(("R", "C")):
            if index + 1 >= len(values):
                raise ValueError("Incomplete Git rename/copy record")
            old_path, path = values[index], values[index + 1]
            index += 2
            entries.append(
                {"status": status[0], "path": path, "oldPath": old_path}
            )
        else:
            if index >= len(values):
                raise ValueError("Incomplete Git change record")
            entries.append({"status": status[0], "path": values[index]})
            index += 1
    tracked = {entry["path"] for entry in entries}
    untracked = _git(
        repository, "ls-files", "--others", "--exclude-standard", "-z"
    ).split(b"\0")
    for value in untracked:
        if not value:
            continue
        path = value.decode("utf-8", errors="surrogateescape")
        if path not in tracked:
            entries.append({"status": "A", "path": path, "untracked": "true"})
    return sorted(entries, key=lambda item: (item["path"], item["status"]))


def capture_worktree_snapshot(repository: str | Path) -> dict[str, Any]:
    root = Path(repository).resolve()
    if not (root / ".git").exists() and not _git(root, "rev-parse", "--git-dir"):
        raise ValueError(f"Not a Git repository: {root}")
    base_revision = _git(root, "rev-parse", "HEAD").decode().strip()
    status = _git(root, "status", "--porcelain=v1", "-z")
    patch = _git(root, "diff", "--binary", "--no-ext-diff", "HEAD")
    entries = _changed_entries(root)
    digest = hashlib.sha256()
    digest.update(base_revision.encode("ascii"))
    digest.update(status)
    digest.update(patch)
    for entry in entries:
        digest.update(json.dumps(entry, sort_keys=True).encode("utf-8"))
        path = root / entry["path"]
        if entry.get("untracked") == "true" and path.is_file():
            digest.update(path.read_bytes())
    return {
        "baseRevision": base_revision,
        "workingTreeSnapshotHash": digest.hexdigest(),
        "changedFiles": entries,
        "patchHash": hashlib.sha256(patch).hexdigest(),
        "clean": not entries,
    }


class PreCommitVerifier:
    """Deterministic pre-commit plan/actual/impact closure and snapshot gate."""

    def __init__(
        self,
        repository: str | Path,
        engineering_model: Mapping[str, Any],
        *,
        planned_changes: Iterable[Mapping[str, Any]] = (),
        verification_results: Iterable[Mapping[str, Any]] = (),
    ) -> None:
        self.repository = Path(repository).resolve()
        self.model = dict(engineering_model)
        self.semantics = EngineeringSemantics(engineering_model)
        self.planned_changes = [dict(item) for item in planned_changes]
        self.verification_results = [dict(item) for item in verification_results]
        self.nodes_by_path: dict[str, list[dict[str, Any]]] = {}
        for node in self.semantics.nodes:
            path = node.get("path")
            if isinstance(path, str) and path:
                self.nodes_by_path.setdefault(path.replace("\\", "/"), []).append(node)

    def _actual_change_set(self, snapshot: Mapping[str, Any]) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        seeds: set[str] = set()
        for change in snapshot["changedFiles"]:
            path = str(change["path"]).replace("\\", "/")
            matched = self.nodes_by_path.get(path, [])
            entity_ids = sorted(str(node["id"]) for node in matched)
            seeds.update(entity_ids)
            items.append(
                {
                    "path": path,
                    "operation": change["status"],
                    "entityIds": entity_ids,
                    "classification": "Mapped" if entity_ids else "Unmapped",
                }
            )
        return {"items": items, "seedEntityIds": sorted(seeds)}

    def _reconcile(self, actual: Mapping[str, Any]) -> dict[str, Any]:
        changed_paths = {str(item["path"]) for item in actual["items"]}
        changed_entities = {
            entity_id for item in actual["items"] for entity_id in item["entityIds"]
        }
        results: list[dict[str, Any]] = []
        for index, planned in enumerate(self.planned_changes):
            plan_id = str(planned.get("planId") or planned.get("proposalId") or f"planned-{index + 1}")
            target_path = planned.get("targetPath")
            target_entity = planned.get("targetEntityId")
            matched = (
                isinstance(target_path, str) and target_path in changed_paths
            ) or (
                isinstance(target_entity, str) and target_entity in changed_entities
            )
            results.append(
                {
                    "planId": plan_id,
                    "targetPath": target_path,
                    "targetEntityId": target_entity,
                    "status": "Conformed" if matched else "MissingImplementation",
                }
            )
        return {
            "results": results,
            "missingPlanIds": [
                item["planId"]
                for item in results
                if item["status"] == "MissingImplementation"
            ],
        }

    @staticmethod
    def _impact_obligations(impact: Mapping[str, Any]) -> list[dict[str, Any]]:
        obligations: list[dict[str, Any]] = []
        for item in impact.get("impacts", []):
            target_type = str(item.get("targetType", ""))
            if "Test" in target_type or "Verification" in target_type:
                obligation_type = "RequiredTest"
            elif "Contract" in target_type or target_type in {"APIOperation", "Schema", "SchemaField"}:
                obligation_type = "CompatibilityVerification"
            elif target_type in {"EngineeringRequirement", "Requirement", "BusinessCapability"}:
                obligation_type = "RequiredReview"
            else:
                obligation_type = "RequiredModification"
            obligations.append(
                {
                    "targetEntityId": item["target"],
                    "obligationType": obligation_type,
                    "ruleId": item["ruleId"],
                    "path": item["path"],
                }
            )
        return obligations

    def verify(self, *, reviewed_snapshot_hash: str | None = None) -> dict[str, Any]:
        snapshot = capture_worktree_snapshot(self.repository)
        validation = self.semantics.validate()
        coverage = self.semantics.coverage()
        actual = self._actual_change_set(snapshot)
        impact = (
            self.semantics.impact(actual["seedEntityIds"], max_depth=6)
            if actual["seedEntityIds"]
            else {"seeds": [], "impactCount": 0, "impacts": []}
        )
        obligations = self._impact_obligations(impact)
        reconciliation = self._reconcile(actual)
        failed_checks = [
            str(item.get("name") or item.get("id") or "verification")
            for item in self.verification_results
            if str(item.get("status", "")).lower() not in {"passed", "pass", "success"}
        ]
        blockers: list[dict[str, Any]] = []
        if reviewed_snapshot_hash is not None and reviewed_snapshot_hash != snapshot["workingTreeSnapshotHash"]:
            blockers.append({"code": "STALE_REVIEW", "message": "Working Tree changed after review."})
        if snapshot["clean"]:
            blockers.append({"code": "NO_ACTUAL_CHANGE", "message": "Working Tree has no changes to verify."})
        if not validation["conforms"]:
            blockers.append({"code": "MODEL_INVALID", "message": "Engineering model does not conform."})
        if reconciliation["missingPlanIds"]:
            blockers.append(
                {
                    "code": "MISSING_IMPLEMENTATION",
                    "planIds": reconciliation["missingPlanIds"],
                }
            )
        if failed_checks:
            blockers.append({"code": "VERIFICATION_FAILED", "checks": failed_checks})
        unexpected = [
            item["path"]
            for item in actual["items"]
            if item["classification"] == "Unmapped"
            and not any(plan.get("targetPath") == item["path"] for plan in self.planned_changes)
        ]
        if unexpected:
            blockers.append({"code": "UNEXPECTED_IMPLEMENTATION", "paths": unexpected})
        return {
            "status": "ReadyToCommit" if not blockers else "BlockCommit",
            "snapshot": snapshot,
            "actualChangeSet": actual,
            "actualImpactGraph": impact,
            "impactObligations": obligations,
            "implementationReconciliation": reconciliation,
            "verificationCoverage": coverage,
            "modelValidation": validation,
            "verificationResults": self.verification_results,
            "blockers": blockers,
        }


def _load_array(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list) or not all(isinstance(item, Mapping) for item in value):
        raise ValueError(f"{path} must contain a JSON array of objects")
    return [dict(item) for item in value]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="code-ontology-precommit")
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--planned", type=Path)
    parser.add_argument("--verification-results", type=Path)
    parser.add_argument("--reviewed-snapshot-hash")
    arguments = parser.parse_args(argv)
    result = PreCommitVerifier(
        arguments.repository,
        load_model(arguments.model),
        planned_changes=_load_array(arguments.planned),
        verification_results=_load_array(arguments.verification_results),
    ).verify(reviewed_snapshot_hash=arguments.reviewed_snapshot_hash)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "ReadyToCommit" else 1


if __name__ == "__main__":
    raise SystemExit(main())
