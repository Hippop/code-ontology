from __future__ import annotations

import hashlib
import os
import re
import subprocess
import uuid
from collections import deque
from collections.abc import Mapping
from itertools import pairwise
from pathlib import Path
from typing import Any

from .code_intelligence import (
    CodeGraphSidecar,
    compare_codegraph_to_baseline,
)
from .agent_runtime import (
    AgentAdapter,
    GitWorktreeManager,
    build_agent_prompt,
    collect_worktree_diff,
    default_agent_adapter,
    run_required_tests,
    validate_changed_paths,
    validate_test_command,
)
from .analysis_workflow import (
    build_change_plan,
    build_implementation_slices,
    compute_semantic_diff,
    generate_alignment_run,
)
from .document_ingestion import (
    EXTRACTOR_VERSION as DOCUMENT_EXTRACTOR_VERSION,
)
from .document_ingestion import (
    extract_requirement_ir,
    parse_design_document,
)
from .errors import PlatformError, conflict, invalid, not_found
from .graph_analysis import (
    build_contract_graph,
    detect_communities,
    detect_processes,
    hybrid_graph_search,
)
from .models import (
    ARTIFACT_TYPES,
    GRAPH_SPACES,
    QUERY_TYPES,
    STAGES,
    enum_value,
    list_value,
    object_value,
    string_value,
    validate_artifact_payload,
)
from .planning import PlanningRules
from .repository_scan import (
    EXTRACTOR_VERSION,
    RepositoryScanner,
    inspect_repository,
)
from .store import SQLiteStore, content_hash, utc_now
from .verification_workflow import (
    build_impact_analysis,
    reconcile_approved_actual,
    stable_graph_item,
)
from .workflow_orchestration import RequirementWorkflowOrchestrator

_RELATION_POLICIES: dict[str, tuple[str, ...] | None] = {
    "GRAPH_OVERVIEW": None,
    "ENTITY_NEIGHBORHOOD": None,
    "IMPLEMENTATION_SLICE": (
        "implement",
        "contain",
        "support",
        "entry",
        "declar",
        "call",
        "read",
        "write",
        "map",
        "run",
    ),
    "BUSINESS_TRACE": (
        "business",
        "implement",
        "realize",
        "enforce",
        "represent",
        "store",
        "verify",
        "support",
        "slice",
    ),
    "CALL_PATH": ("call",),
    "CONTRACT_CONSUMERS": (
        "consume",
        "producer",
        "schema",
        "contract",
        "request",
        "response",
        "operation",
    ),
    "DATA_DEPENDENCIES": (
        "read",
        "write",
        "flow",
        "map",
        "store",
        "column",
        "field",
        "parameter",
        "return",
    ),
    "CHANGE_CONTEXT": None,
    "IMPACT_PATHS": None,
}
_BUSINESS_ENTITY_TYPES = frozenset(
    {
        "BusinessCapability",
        "BusinessProcess",
        "BusinessProcessStep",
        "BusinessRule",
        "BusinessEntity",
        "DesiredBusinessEntity",
    }
)
_SAFE_GIT_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/@{}^~:+-]{0,255}$")


def _git_changed_files(repository: Path, base_ref: str | None) -> dict[str, Any]:
    if base_ref is not None and not _SAFE_GIT_REF.fullmatch(base_ref):
        raise invalid("baseRef 格式不安全或不受支持")

    def run(*arguments: str) -> subprocess.CompletedProcess[bytes]:
        try:
            return subprocess.run(
                ["git", "-C", str(repository), *arguments],
                check=False,
                capture_output=True,
                timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise PlatformError(
                503,
                "GIT_UNAVAILABLE",
                "无法读取 Git 变更",
                {"reason": str(error)},
            ) from error

    probe = run("rev-parse", "--is-inside-work-tree")
    if probe.returncode != 0 or probe.stdout.strip() != b"true":
        return {"source": "filesystem", "baseRef": base_ref, "files": []}

    commands: list[tuple[str, ...]] = []
    if base_ref is not None:
        commands.append(
            (
                "diff",
                "--name-only",
                "-z",
                "--relative",
                "--no-renames",
                f"{base_ref}...HEAD",
                "--",
            )
        )
    commands.extend(
        [
            (
                "diff",
                "--name-only",
                "-z",
                "--relative",
                "--no-renames",
                "HEAD",
                "--",
            ),
            ("ls-files", "--others", "--exclude-standard", "-z", "--"),
        ]
    )
    paths: set[str] = set()
    for arguments in commands:
        completed = run(*arguments)
        if completed.returncode != 0:
            message = completed.stderr.decode("utf-8", errors="replace")[-2000:]
            if base_ref is not None and arguments[0] == "diff":
                raise invalid(
                    "baseRef 无法用于 Git 对比",
                    {"baseRef": base_ref, "stderr": message},
                )
            continue
        paths.update(
            item.decode("utf-8", errors="replace").replace("\\", "/")
            for item in completed.stdout.split(b"\0")
            if item
        )
    return {"source": "git", "baseRef": base_ref, "files": sorted(paths)}


def _relation_name(relation: str) -> str:
    for separator in ("#", "/", ":"):
        if separator in relation:
            relation = relation.rsplit(separator, 1)[-1]
    return relation.lower()


def _relation_allowed(query_type: str, relation: str) -> bool:
    tokens = _RELATION_POLICIES[query_type]
    if tokens is None:
        return True
    name = _relation_name(relation)
    return any(token in name for token in tokens)


def _redact_sensitive(value: Any, key: str = "") -> Any:
    sensitive = any(
        token in key.lower()
        for token in ("password", "passwd", "secret", "token", "api_key", "apikey")
    )
    if sensitive and value is not None:
        return {
            "redacted": True,
            "valueHash": content_hash({"value": str(value)}),
        }
    if isinstance(value, Mapping):
        return {
            str(item_key): _redact_sensitive(item_value, str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [_redact_sensitive(item, key) for item in value]
    return value


class PlatformService:
    def __init__(
        self,
        store: SQLiteStore,
        rules_path: str | Path,
        repository_roots: list[str | Path] | None = None,
        *,
        worktree_root: str | Path | None = None,
        agent_adapter: AgentAdapter | None = None,
        role_agent_adapter: AgentAdapter | None = None,
        codegraph_sidecar: CodeGraphSidecar | None = None,
    ) -> None:
        self.store = store
        self.planning_rules = PlanningRules(rules_path)
        self.repository_roots = [
            Path(root).resolve() for root in (repository_roots or [Path.cwd()])
        ]
        project_root = Path(__file__).resolve().parents[2]
        self.project_root = project_root
        self.worktree_manager = GitWorktreeManager(
            worktree_root or project_root / "data" / "agent-worktrees"
        )
        self.agent_adapter = agent_adapter or default_agent_adapter(project_root)
        self.role_agent_adapter = role_agent_adapter or self.agent_adapter
        self.codegraph_sidecar = codegraph_sidecar or CodeGraphSidecar(store)
        self.workflow_orchestrator = RequirementWorkflowOrchestrator(self)

    def _repository_path(self, value: Any) -> Path:
        path = Path(string_value(value, "path")).resolve()
        if not path.is_dir():
            raise invalid(f"仓库目录不存在: {path}")
        if not any(path.is_relative_to(root) for root in self.repository_roots):
            raise invalid(
                "仓库路径不在允许的根目录内",
                {
                    "path": str(path),
                    "allowedRoots": [str(root) for root in self.repository_roots],
                },
            )
        return path

    def register_repository(
        self, body_value: Any, correlation_id: str | None = None
    ) -> dict[str, Any]:
        body = object_value(body_value, "request")
        path = self._repository_path(body.get("path"))
        repository_id_value = body.get("repositoryId")
        repository_id = (
            string_value(repository_id_value, "repositoryId")
            if repository_id_value is not None
            else "repo-" + hashlib.sha256(str(path).encode()).hexdigest()[:16]
        )
        identity = inspect_repository(path, repository_id)
        repository = self.store.put_repository(
            {
                "repositoryId": repository_id,
                "name": (
                    string_value(body["name"], "name")
                    if body.get("name") is not None
                    else path.name
                ),
                "path": str(path),
                "defaultBranch": body.get("defaultBranch") or identity["branch"],
                "metadata": {
                    "remote": identity["remote"],
                    "registeredRevision": identity["revision"],
                },
            }
        )
        self.store.append_audit_event(
            "RepositoryRegistered",
            repository,
            correlation_id=correlation_id,
            repository_id=repository_id,
            revision=identity["revision"],
            actor=body.get("actor"),
        )
        return repository

    def get_repository(self, repository_id: str) -> dict[str, Any]:
        repository_id = string_value(repository_id, "repositoryId")
        repository = self.store.get_repository(repository_id)
        if repository is None:
            raise not_found(f"未找到仓库: {repository_id}")
        return repository

    def list_repositories(self, body_value: Any | None = None) -> dict[str, Any]:
        body = object_value(body_value or {}, "request")
        limit = body.get("limit", 100)
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 500
        ):
            raise invalid("limit 必须是 1 到 500 的整数")
        repositories = self.store.list_repositories(limit + 1)
        truncated = len(repositories) > limit
        repositories = repositories[:limit]
        return {
            "repositories": repositories,
            "count": len(repositories),
            "truncated": truncated,
        }

    def repository_context(self, repository_id: str) -> dict[str, Any]:
        repository = self.get_repository(repository_id)
        identity = inspect_repository(repository["path"], repository_id)
        revisions = self.store.list_repository_graph_revisions(repository_id)
        latest_revision = revisions[0] if revisions else None
        try:
            index = self.codegraph_sidecar.status(repository_id, repository["path"])
        except PlatformError as error:
            index = {
                "provider": "codegraph",
                "repositoryId": repository_id,
                "status": "Error",
                "error": {
                    "code": error.code,
                    "message": error.message,
                    "details": error.details,
                },
            }
        return {
            "repository": repository,
            "workspace": identity,
            "currentGraph": (
                {
                    "revision": latest_revision.get("revision"),
                    "status": latest_revision.get("status"),
                    "extractorVersion": latest_revision.get("extractorVersion"),
                    "coverage": latest_revision.get("coverage"),
                    "metadata": latest_revision.get("graph"),
                }
                if latest_revision is not None
                else None
            ),
            "codegraphIndex": index,
            "capabilities": {
                "graphQuery": latest_revision is not None,
                "hybridSearch": latest_revision is not None,
                "communities": latest_revision is not None,
                "processes": latest_revision is not None,
                "codegraphQueries": index.get("status") in {"Fresh", "Stale"},
            },
        }

    def create_repository_snapshot(
        self,
        repository_id: str,
        body_value: Any,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        body = object_value(body_value, "request")
        repository = self.get_repository(repository_id)
        identity = inspect_repository(repository["path"], repository_id)
        requested_commit = body.get("commit")
        if requested_commit is not None and requested_commit != identity["commit"]:
            raise conflict(
                "请求 Commit 与当前仓库 Base Commit 不一致，拒绝创建漂移快照"
            )
        requested_branch = body.get("branch")
        if requested_branch is not None and requested_branch != identity["branch"]:
            raise conflict("请求 Branch 与当前仓库 Branch 不一致")
        snapshot_id = (
            "snapshot-"
            + hashlib.sha256(
                f"{repository_id}|{identity['revision']}".encode()
            ).hexdigest()[:20]
        )
        snapshot = self.store.put_repository_snapshot(
            {
                "snapshotId": snapshot_id,
                "repositoryId": repository_id,
                "revision": identity["revision"],
                "commit": identity["commit"],
                "branch": identity["branch"],
                "dirty": identity["dirty"],
                "status": "Captured",
                "remote": identity["remote"],
                "createdBy": body.get("actor", "system"),
            }
        )
        self.store.append_audit_event(
            "RepositorySnapshotCreated",
            snapshot,
            correlation_id=correlation_id,
            repository_id=repository_id,
            revision=identity["revision"],
            actor=body.get("actor"),
        )
        return snapshot

    def scan_repository(
        self,
        repository_id: str,
        body_value: Any,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        body = object_value(body_value, "request")
        repository = self.get_repository(repository_id)
        snapshot_id_value = body.get("snapshotId")
        if snapshot_id_value is None:
            snapshot = self.create_repository_snapshot(
                repository_id, {"actor": body.get("actor")}, correlation_id
            )
        else:
            snapshot_id = string_value(snapshot_id_value, "snapshotId")
            snapshot = self.store.get_repository_snapshot(snapshot_id)
            if snapshot is None or snapshot["repositoryId"] != repository_id:
                raise not_found("未找到属于该仓库的 RepositorySnapshot")
        identity = inspect_repository(repository["path"], repository_id)
        if identity["revision"] != snapshot["revision"]:
            raise conflict("RepositorySnapshot 创建后仓库内容已漂移，必须重新创建快照")

        result = RepositoryScanner().scan(repository["path"], repository_id)
        graph = result["graph"]
        repository_revision = graph["revision"]
        existing_metadata = self.store.get_graph_metadata(
            "current", repository_revision
        )
        if (
            existing_metadata is not None
            and existing_metadata.get("repositoryId") not in {None, repository_id}
        ):
            graph["revision"] = (
                f"{repository_revision}@repo="
                + hashlib.sha256(repository_id.encode("utf-8")).hexdigest()[:12]
            )
        graph["repositoryRevision"] = repository_revision
        graph_metadata = {
            key: value for key, value in graph.items() if key not in {"nodes", "edges"}
        }
        graph_text_snapshot = self.replace_graph(
            "current",
            graph["revision"],
            graph["nodes"],
            graph["edges"],
            metadata=graph_metadata,
        )
        status = (
            "Completed"
            if result["coverage"]["failedJavaFiles"] == 0
            else "CompletedWithWarnings"
        )
        run_id = (
            "extract-"
            + hashlib.sha256(
                f"{snapshot['snapshotId']}|{EXTRACTOR_VERSION}".encode()
            ).hexdigest()[:20]
        )
        run = self.store.record_extraction_run(
            {
                "runId": run_id,
                "repositoryId": repository_id,
                "snapshotId": snapshot["snapshotId"],
                "revision": graph["revision"],
                "status": status,
                "extractorVersion": EXTRACTOR_VERSION,
                "coverage": result["coverage"],
                "graphId": graph["graphId"],
                "graphTextSnapshot": graph_text_snapshot,
                "createdAt": graph["createdAt"],
            }
        )
        self.store.update_snapshot_status(snapshot["snapshotId"], "Scanned")
        self.store.append_audit_event(
            "ExtractionCompleted",
            run,
            correlation_id=correlation_id,
            run_id=run_id,
            repository_id=repository_id,
            revision=graph["revision"],
            actor=body.get("actor"),
        )
        self.store.append_audit_event(
            "CurrentGraphPublished",
            graph_metadata,
            correlation_id=correlation_id,
            run_id=run_id,
            repository_id=repository_id,
            revision=graph["revision"],
            actor=body.get("actor"),
        )
        response = {**run, "buildModel": result["buildModel"]}
        if body.get("includeGraph") is True:
            response["graph"] = graph
        return response

    def repository_graph_revisions(self, repository_id: str) -> dict[str, Any]:
        repository = self.get_repository(repository_id)
        return {
            "repositoryId": repository["repositoryId"],
            "revisions": self.store.list_repository_graph_revisions(repository_id),
        }

    def create_design_document(
        self, body_value: Any, correlation_id: str | None = None
    ) -> dict[str, Any]:
        body = object_value(body_value, "request")
        title = string_value(body.get("title"), "title")
        document_id_value = body.get("documentId")
        document_id = (
            string_value(document_id_value, "documentId")
            if document_id_value is not None
            else f"design-{uuid.uuid4()}"
        )
        document = self.store.put_design_document(
            {
                "documentId": document_id,
                "title": title,
                "owner": body.get("owner"),
                "metadata": object_value(body.get("metadata", {}), "metadata"),
            }
        )
        self.store.append_audit_event(
            "DesignDocumentCreated",
            document,
            correlation_id=correlation_id,
            actor=body.get("owner"),
        )
        return document

    def create_design_revision(
        self,
        document_id: str,
        body_value: Any,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        body = object_value(body_value, "request")
        document_id = string_value(document_id, "documentId")
        if self.store.get_design_document(document_id) is None:
            raise not_found(f"未找到设计文档: {document_id}")
        content_value = body.get("content")
        if content_value is None:
            file_value = body.get("filePath")
            if file_value is None:
                raise invalid("content 和 filePath 必须提供一个")
            file_path = Path(string_value(file_value, "filePath")).resolve()
            if not file_path.is_file() or not any(
                file_path.is_relative_to(root) for root in self.repository_roots
            ):
                raise invalid("设计文档文件不存在或不在允许目录")
            try:
                content = file_path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as error:
                raise invalid(f"无法读取设计文档: {error}") from error
        else:
            content = string_value(content_value, "content")
        parsed = parse_design_document(content)
        revision_number = str(
            body.get("revisionNumber")
            or parsed["metadata"].get("revision")
            or parsed["contentHash"].split(":", 1)[-1][:12]
        )
        revision_id = (
            f"{document_id}@{revision_number}-"
            f"{parsed['contentHash'].split(':', 1)[-1][:12]}"
        )
        revision = self.store.put_design_revision(
            {
                "revisionId": revision_id,
                "documentId": document_id,
                "revisionNumber": revision_number,
                "contentHash": parsed["contentHash"],
                "content": content,
                "parsed": parsed,
                "status": "Parsed",
            }
        )
        self.store.append_audit_event(
            "DesignRevisionCreated",
            {key: value for key, value in revision.items() if key != "content"},
            correlation_id=correlation_id,
            revision=revision_id,
            actor=body.get("actor"),
        )
        return revision

    def extract_design_revision(
        self,
        revision_id: str,
        body_value: Any,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        body = object_value(body_value, "request")
        revision_id = string_value(revision_id, "designRevisionId")
        revision = self.store.get_design_revision(revision_id)
        if revision is None:
            raise not_found(f"未找到 DesignRevision: {revision_id}")
        metadata = revision["parsed"]["metadata"]
        requirement_id_value = body.get("requirementId") or metadata.get(
            "requirementId"
        )
        requirement_id = string_value(requirement_id_value, "requirementId")
        ir = extract_requirement_ir(
            requirement_id=requirement_id,
            design_revision_id=revision_id,
            parsed_document=revision["parsed"],
        )
        desired_revision = revision_id
        desired_nodes: list[dict[str, Any]] = [
            {
                "id": f"requirement:{requirement_id}",
                "type": "Requirement",
                "label": requirement_id,
                "revision": desired_revision,
            },
            {
                "id": f"design-revision:{revision_id}",
                "type": "DesignRevision",
                "label": revision_id,
                "contentHash": revision["contentHash"],
                "revision": desired_revision,
            },
        ]
        desired_edges: list[dict[str, Any]] = []
        for item in ir["documentEvidence"]:
            desired_nodes.append(
                {
                    "id": item["evidenceId"],
                    "type": "DocumentEvidence",
                    **item,
                }
            )
        for entity in ir["desiredEntities"]:
            node = {
                "id": entity["entityId"],
                "type": entity["entityType"],
                **{
                    key: value
                    for key, value in entity.items()
                    if key not in {"entityId", "entityType"}
                },
            }
            desired_nodes.append(node)
            desired_edges.append(
                {
                    "source": f"requirement:{requirement_id}",
                    "relation": "plan:definesDesiredEntity",
                    "target": entity["entityId"],
                }
            )
            desired_edges.append(
                {
                    "source": entity["entityId"],
                    "relation": "plan:derivedFromRevision",
                    "target": f"design-revision:{revision_id}",
                }
            )
            for evidence_ref in entity["evidenceRefs"]:
                desired_edges.append(
                    {
                        "source": entity["entityId"],
                        "relation": "plan:supportedByDesignEvidence",
                        "target": evidence_ref,
                    }
                )
            if entity.get("processEntityId"):
                desired_edges.append(
                    {
                        "source": entity["processEntityId"],
                        "relation": "business:containsStep",
                        "target": entity["entityId"],
                    }
                )
        steps_by_process: dict[str, list[dict[str, Any]]] = {}
        for entity in ir["desiredEntities"]:
            process_id = entity.get("processEntityId")
            if process_id:
                steps_by_process.setdefault(process_id, []).append(entity)
        for steps in steps_by_process.values():
            ordered_steps = sorted(steps, key=lambda item: item["sequence"])
            for previous, following in pairwise(ordered_steps):
                desired_edges.append(
                    {
                        "source": previous["entityId"],
                        "relation": "business:nextStep",
                        "target": following["entityId"],
                    }
                )
        self.replace_graph(
            "desired",
            desired_revision,
            desired_nodes,
            desired_edges,
            metadata={
                "graphId": (f"urn:graph:desired:{requirement_id}:{desired_revision}"),
                "graphType": "Desired",
                "baseRevision": revision_id,
                "createdBy": f"extractor:{DOCUMENT_EXTRACTOR_VERSION}",
                "sourceArtifact": revision["documentId"],
                "status": "Draft",
                "validationStatus": "StructurallyValidated",
            },
        )
        self._publish_business_graph(
            requirement_id=requirement_id,
            revision=desired_revision,
            desired_nodes=desired_nodes,
            desired_edges=desired_edges,
            status="Draft",
            validation_status="StructurallyValidated",
            created_by=f"extractor:{DOCUMENT_EXTRACTOR_VERSION}",
            source_artifact=revision["documentId"],
        )
        result = self.store.put_requirement_ir(
            requirement_id,
            revision_id,
            "Draft",
            ir,
            desired_revision,
        )
        self.put_requirement_context(
            requirement_id,
            revision_id,
            "extract",
            {
                "approvalState": "Draft",
                "allowedActions": ["ReviewRequirementIR"],
                "relevantArtifacts": [f"requirement-ir:{requirement_id}"],
                "requirementRevision": revision_id,
                "extractorVersion": DOCUMENT_EXTRACTOR_VERSION,
            },
        )
        self.store.append_audit_event(
            "RequirementIRDrafted",
            {
                "requirementId": requirement_id,
                "designRevisionId": revision_id,
                "desiredEntityCount": len(ir["desiredEntities"]),
                "unresolvedQuestionCount": len(ir["unresolvedQuestions"]),
            },
            correlation_id=correlation_id,
            requirement_id=requirement_id,
            revision=revision_id,
            actor=body.get("actor"),
        )
        return result

    def _publish_business_graph(
        self,
        *,
        requirement_id: str,
        revision: str,
        desired_nodes: list[dict[str, Any]],
        desired_edges: list[dict[str, Any]],
        status: str,
        validation_status: str,
        created_by: str,
        source_artifact: str,
    ) -> None:
        requirement_node_id = f"requirement:{requirement_id}"
        business_ids = {
            node["id"]
            for node in desired_nodes
            if node.get("type") in _BUSINESS_ENTITY_TYPES
            or str(node.get("type", "")).startswith("Business")
        }
        evidence_ids = {
            edge["target"]
            for edge in desired_edges
            if edge["source"] in business_ids
            and edge["relation"] == "plan:supportedByDesignEvidence"
        }
        selected_ids = {requirement_node_id, *business_ids, *evidence_ids}
        business_nodes = [node for node in desired_nodes if node["id"] in selected_ids]
        business_edges = [
            edge
            for edge in desired_edges
            if edge["source"] in selected_ids and edge["target"] in selected_ids
        ]
        self.replace_graph(
            "business",
            revision,
            business_nodes,
            business_edges,
            metadata={
                "graphId": f"urn:graph:business:{requirement_id}:{revision}",
                "graphType": "Business",
                "baseRevision": revision,
                "createdBy": created_by,
                "sourceArtifact": source_artifact,
                "status": status,
                "validationStatus": validation_status,
            },
        )

    def get_requirement_ir(self, requirement_id: str) -> dict[str, Any]:
        requirement_id = string_value(requirement_id, "requirementId")
        result = self.store.get_requirement_ir(requirement_id)
        if result is None:
            raise not_found(f"未找到 Requirement IR: {requirement_id}")
        return result

    def review_requirement(
        self,
        requirement_id: str,
        body_value: Any,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        body = object_value(body_value, "request")
        requirement = self.get_requirement_ir(requirement_id)
        decision = enum_value(
            body.get("decision"),
            "decision",
            frozenset({"Confirm", "Reject", "NeedsRevision"}),
        )
        actor = string_value(body.get("actor"), "actor")
        rationale = string_value(body.get("rationale"), "rationale")
        unresolved = requirement["ir"].get("unresolvedQuestions", [])
        if (
            decision == "Confirm"
            and unresolved
            and body.get("acceptUnresolved") is not True
        ):
            raise invalid(
                "Requirement IR 仍有未解决问题；确认前必须解决或明确接受",
                {"unresolvedQuestionIds": [item["questionId"] for item in unresolved]},
            )
        status = {
            "Confirm": "Confirmed",
            "Reject": "Rejected",
            "NeedsRevision": "NeedsRevision",
        }[decision]
        review = self.store.record_review_decision(
            {
                "reviewId": f"review-{uuid.uuid4()}",
                "resourceType": "RequirementIR",
                "resourceId": requirement_id,
                "gate": "RequirementReview",
                "decision": decision,
                "actor": actor,
                "rationale": rationale,
                "acceptedUnresolved": body.get("acceptUnresolved") is True,
            }
        )
        updated = self.store.update_requirement_status(requirement_id, status)
        if status == "Confirmed":
            revision_id = requirement["designRevisionId"]
            nodes, edges = self.store.read_graph("desired", revision_id)
            self.replace_graph(
                "desired",
                revision_id,
                nodes,
                edges,
                metadata={
                    "graphId": (f"urn:graph:desired:{requirement_id}:{revision_id}"),
                    "graphType": "Desired",
                    "baseRevision": revision_id,
                    "createdBy": f"extractor:{DOCUMENT_EXTRACTOR_VERSION}",
                    "sourceArtifact": revision_id,
                    "status": "Published",
                    "validationStatus": "HumanConfirmed",
                },
            )
            self._publish_business_graph(
                requirement_id=requirement_id,
                revision=revision_id,
                desired_nodes=nodes,
                desired_edges=edges,
                status="Published",
                validation_status="HumanConfirmed",
                created_by=actor,
                source_artifact=revision_id,
            )
            self.put_requirement_context(
                requirement_id,
                revision_id,
                "align",
                {
                    "approvalState": "RequirementConfirmed",
                    "allowedActions": [
                        "ReadDesiredGraph",
                        "QueryCurrentGraph",
                        "CreateAlignmentCandidates",
                    ],
                    "relevantArtifacts": [f"requirement-ir:{requirement_id}"],
                    "requirementRevision": revision_id,
                },
            )
            self.store.append_audit_event(
                "RequirementIRConfirmed",
                review,
                correlation_id=correlation_id,
                requirement_id=requirement_id,
                revision=revision_id,
                actor=actor,
            )
            self.store.append_audit_event(
                "DesiredGraphPublished",
                {"graphSpace": "desired", "revision": revision_id},
                correlation_id=correlation_id,
                requirement_id=requirement_id,
                revision=revision_id,
                actor=actor,
            )
            self.store.append_audit_event(
                "BusinessGraphPublished",
                {"graphSpace": "business", "revision": revision_id},
                correlation_id=correlation_id,
                requirement_id=requirement_id,
                revision=revision_id,
                actor=actor,
            )
        else:
            self.store.append_audit_event(
                "RequirementReviewRecorded",
                review,
                correlation_id=correlation_id,
                requirement_id=requirement_id,
                revision=requirement["designRevisionId"],
                actor=actor,
            )
        return {"requirement": updated, "review": review}

    def create_alignment_run(
        self, body_value: Any, correlation_id: str | None = None
    ) -> dict[str, Any]:
        body = object_value(body_value, "request")
        requirement_id = string_value(body.get("requirementId"), "requirementId")
        requirement = self.get_requirement_ir(requirement_id)
        if requirement["status"] != "Confirmed":
            raise conflict("Requirement IR 未通过 Requirement Review Gate")
        current_revision = string_value(body.get("currentRevision"), "currentRevision")
        current_nodes, _ = self.store.read_graph("current", current_revision)
        if not current_nodes:
            raise not_found(f"Current Graph Revision 不存在: {current_revision}")
        run_id = (
            "alignment-run-"
            + hashlib.sha256(
                (
                    requirement_id
                    + "|"
                    + current_revision
                    + "|"
                    + requirement["desiredGraphRevision"]
                ).encode()
            ).hexdigest()[:20]
        )
        run = generate_alignment_run(
            run_id=run_id,
            requirement=requirement,
            current_revision=current_revision,
            current_nodes=current_nodes,
        )
        run["repositoryId"] = body.get("repositoryId")
        self.store.put_alignment_run(run)
        self.store.append_audit_event(
            "AlignmentDrafted",
            {
                "runId": run_id,
                "candidateGroupCount": len(run["alignments"]),
                "modelVersion": run["modelVersion"],
            },
            correlation_id=correlation_id,
            run_id=run_id,
            requirement_id=requirement_id,
            repository_id=body.get("repositoryId"),
            revision=current_revision,
            actor=body.get("actor"),
        )
        return run

    def get_alignment_run(self, run_id: str) -> dict[str, Any]:
        run_id = string_value(run_id, "alignmentRunId")
        run = self.store.get_alignment_run(run_id)
        if run is None:
            raise not_found(f"未找到 Alignment Run: {run_id}")
        return run

    def review_alignment(
        self,
        candidate_id: str,
        body_value: Any,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        body = object_value(body_value, "request")
        candidate_id = string_value(candidate_id, "alignmentId")
        located = self.store.find_alignment_candidate(candidate_id)
        if located is None:
            raise not_found(f"未找到 CandidateAlignment: {candidate_id}")
        run_id, _ = located
        run = self.get_alignment_run(run_id)
        decision = enum_value(
            body.get("decision"),
            "decision",
            frozenset({"Confirm", "Reject"}),
        )
        actor = string_value(body.get("actor"), "actor")
        rationale = string_value(body.get("rationale"), "rationale")
        matched = False
        for item in run["alignments"]:
            for candidate in item["candidates"]:
                if candidate["candidateId"] != candidate_id:
                    continue
                matched = True
                candidate["reviewStatus"] = (
                    "Confirmed" if decision == "Confirm" else "Rejected"
                )
                candidate["reviewedBy"] = actor
                candidate["reviewRationale"] = rationale
                if decision == "Confirm":
                    item["selectedCandidateId"] = candidate_id
                    item["reviewStatus"] = "Confirmed"
                    for alternative in item["candidates"]:
                        if alternative["candidateId"] != candidate_id:
                            alternative["reviewStatus"] = "Alternative"
                elif item.get("selectedCandidateId") == candidate_id:
                    item["selectedCandidateId"] = None
                    item["reviewStatus"] = "Candidate"
                break
        if not matched:
            raise not_found(f"Candidate 不属于 Alignment Run: {candidate_id}")
        complete = all(
            item.get("selectedCandidateId") is not None for item in run["alignments"]
        )
        run["status"] = "Confirmed" if complete else "UnderReview"
        if complete:
            current_nodes, current_edges = self.store.read_graph(
                "current", run["currentRevision"]
            )
            run["implementationSlices"] = build_implementation_slices(
                run, current_nodes, current_edges
            )
        self.store.put_alignment_run(run)
        review = self.store.record_review_decision(
            {
                "reviewId": f"review-{uuid.uuid4()}",
                "resourceType": "CandidateAlignment",
                "resourceId": candidate_id,
                "gate": "AlignmentReview",
                "decision": decision,
                "actor": actor,
                "rationale": rationale,
            }
        )
        if complete:
            requirement = self.get_requirement_ir(run["requirementId"])
            self.put_requirement_context(
                run["requirementId"],
                requirement["designRevisionId"],
                "plan",
                {
                    "approvalState": "AlignmentConfirmed",
                    "allowedActions": [
                        "ReadPlanningContext",
                        "CreateChangePlanDraft",
                    ],
                    "currentRevision": run["currentRevision"],
                    "desiredRevision": run["desiredRevision"],
                    "alignmentRunId": run_id,
                    "relevantArtifacts": [
                        f"alignment-run:{run_id}",
                        *[
                            f"implementation-slice:{item['sliceId']}"
                            for item in run["implementationSlices"]
                        ],
                    ],
                },
            )
            self.store.append_audit_event(
                "AlignmentConfirmed",
                {"runId": run_id, "review": review},
                correlation_id=correlation_id,
                run_id=run_id,
                requirement_id=run["requirementId"],
                repository_id=run.get("repositoryId"),
                revision=run["currentRevision"],
                actor=actor,
            )
        return run

    def create_change_plan(
        self, body_value: Any, correlation_id: str | None = None
    ) -> dict[str, Any]:
        body = object_value(body_value, "request")
        alignment_run_id = string_value(body.get("alignmentRunId"), "alignmentRunId")
        alignment_run = self.get_alignment_run(alignment_run_id)
        if alignment_run["status"] != "Confirmed":
            raise conflict("Alignment Review Gate 尚未完成")
        requirement = self.get_requirement_ir(alignment_run["requirementId"])
        semantic_diff = compute_semantic_diff(alignment_run)
        plan_id = (
            "change-plan-"
            + hashlib.sha256(
                (
                    alignment_run_id
                    + "|"
                    + self.planning_rules.version
                    + "|"
                    + semantic_diff["diffId"]
                ).encode()
            ).hexdigest()[:20]
        )
        context = object_value(body.get("context", {}), "context")
        context.setdefault("repositoryId", alignment_run.get("repositoryId"))
        plan = build_change_plan(
            plan_id=plan_id,
            requirement=requirement,
            alignment_run=alignment_run,
            semantic_diff=semantic_diff,
            implementation_slices=alignment_run.get("implementationSlices", []),
            planning_rules=self.planning_rules,
            context=context,
        )
        plan["changeSet"]["repositoryId"] = context.get("repositoryId")
        plan["context"] = context
        plan["governance"] = {
            "requiresArchitectureReview": True,
            "requiresSecurityDataReview": any(
                item["changeType"]
                in {
                    "ProposedDataMigration",
                    "ProposedConstraintChange",
                }
                for item in plan["proposals"]
            ),
            "requiresReleaseReview": True,
        }
        self._publish_proposed_graph(
            plan,
            created_by=str(body.get("actor") or "change-planner"),
        )
        self.store.put_change_plan(plan)
        self.store.append_audit_event(
            "ChangePlanDrafted",
            {
                "planId": plan_id,
                "differenceCount": len(plan["semanticDiff"]["differences"]),
                "proposalCount": len(plan["proposals"]),
                "taskCount": len(plan["implementationTasks"]),
                "ruleSetVersion": self.planning_rules.version,
            },
            correlation_id=correlation_id,
            run_id=plan_id,
            requirement_id=requirement["requirementId"],
            repository_id=alignment_run.get("repositoryId"),
            revision=alignment_run["currentRevision"],
            actor=body.get("actor"),
        )
        return plan

    def _publish_proposed_graph(self, plan: dict[str, Any], *, created_by: str) -> None:
        plan_id = plan["planId"]
        root_id = f"change-set:{plan_id}"
        node_by_id: dict[str, dict[str, Any]] = {
            root_id: {
                "id": root_id,
                "type": "DesignChangeSet",
                "label": plan_id,
                "status": plan["status"],
                "requirementId": plan["changeSet"]["requirementId"],
                "ruleSetVersion": plan["changeSet"]["ruleSetVersion"],
            }
        }
        edges: list[dict[str, Any]] = []

        def reference(entity_id: str | None, reference_type: str) -> None:
            if entity_id is None or entity_id in node_by_id:
                return
            node_by_id[entity_id] = {
                "id": entity_id,
                "type": reference_type,
                "label": entity_id,
                "externalReference": True,
            }

        for difference in plan["semanticDiff"]["differences"]:
            difference_id = difference["differenceId"]
            node_by_id[difference_id] = {
                "id": difference_id,
                "type": difference["differenceType"],
                **difference,
            }
            edges.append(
                {
                    "source": root_id,
                    "relation": "plan:containsDifference",
                    "target": difference_id,
                }
            )
            desired_id = difference.get("desiredEntityId")
            current_id = difference.get("currentEntityId")
            reference(desired_id, "DesiredEntityReference")
            reference(current_id, "CurrentEntityReference")
            if desired_id:
                edges.append(
                    {
                        "source": difference_id,
                        "relation": "plan:targetsDesiredEntity",
                        "target": desired_id,
                    }
                )
            if current_id:
                edges.append(
                    {
                        "source": difference_id,
                        "relation": "plan:comparesCurrentEntity",
                        "target": current_id,
                    }
                )
        for proposal in plan["proposals"]:
            proposal_id = proposal["proposalId"]
            node_by_id[proposal_id] = {
                "id": proposal_id,
                "type": proposal["changeType"],
                **proposal,
                "proposalStatus": plan["status"],
            }
            edges.append(
                {
                    "source": root_id,
                    "relation": "plan:containsProposedChange",
                    "target": proposal_id,
                }
            )
            desired_id = proposal.get("desiredEntityId")
            current_id = proposal.get("targetCurrentEntityId")
            reference(desired_id, "DesiredEntityReference")
            reference(current_id, "CurrentEntityReference")
            if desired_id:
                edges.append(
                    {
                        "source": proposal_id,
                        "relation": "plan:implementsDesiredEntity",
                        "target": desired_id,
                    }
                )
            if current_id:
                edges.append(
                    {
                        "source": proposal_id,
                        "relation": "plan:targetsCurrentEntity",
                        "target": current_id,
                    }
                )
        for proposal in plan["proposals"]:
            for dependency in proposal.get("dependsOn", []):
                if dependency in node_by_id:
                    edges.append(
                        {
                            "source": proposal["proposalId"],
                            "relation": "plan:dependsOnChange",
                            "target": dependency,
                        }
                    )
        for task in plan["implementationTasks"]:
            node_by_id[task["taskId"]] = {
                "id": task["taskId"],
                "type": "ImplementationTask",
                **task,
            }
            edges.append(
                {
                    "source": task["taskId"],
                    "relation": "plan:implementsProposedChange",
                    "target": task["proposalId"],
                }
            )
        for obligation in plan["verificationObligations"]:
            node_by_id[obligation["obligationId"]] = {
                "id": obligation["obligationId"],
                "type": "VerificationObligation",
                **obligation,
            }
            edges.append(
                {
                    "source": obligation["obligationId"],
                    "relation": "plan:verifiesChangeSet",
                    "target": root_id,
                }
            )
        self.replace_graph(
            "proposed",
            plan_id,
            list(node_by_id.values()),
            edges,
            metadata={
                "graphId": f"urn:graph:proposed:{plan_id}",
                "graphType": "Proposed",
                "baseRevision": plan["changeSet"]["currentRevision"],
                "createdBy": created_by,
                "sourceArtifact": plan_id,
                "status": plan["status"],
                "validationStatus": (
                    "ArchitectureReviewed"
                    if plan["status"] == "ArchitectureReviewed"
                    else "Draft"
                ),
            },
        )

    def get_change_plan(self, plan_id: str) -> dict[str, Any]:
        plan_id = string_value(plan_id, "changePlanId")
        plan = self.store.get_change_plan(plan_id)
        if plan is None:
            raise not_found(f"未找到 Change Plan: {plan_id}")
        return plan

    def review_change_plan(
        self,
        plan_id: str,
        body_value: Any,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        body = object_value(body_value, "request")
        plan = self.get_change_plan(plan_id)
        if plan["status"] not in {"Draft", "NeedsRevision"}:
            raise conflict(f"当前状态不允许架构评审: {plan['status']}")
        decision = enum_value(
            body.get("decision"),
            "decision",
            frozenset({"Accept", "Reject", "NeedsRevision"}),
        )
        actor = string_value(body.get("actor"), "actor")
        rationale = string_value(body.get("rationale"), "rationale")
        findings = list_value(body.get("findings", []), "findings")
        status = {
            "Accept": "ArchitectureReviewed",
            "Reject": "Rejected",
            "NeedsRevision": "NeedsRevision",
        }[decision]
        review = self.store.record_review_decision(
            {
                "reviewId": f"review-{uuid.uuid4()}",
                "resourceType": "ChangePlan",
                "resourceId": plan_id,
                "gate": "ArchitectureReview",
                "decision": decision,
                "actor": actor,
                "rationale": rationale,
                "findings": findings,
            }
        )
        plan["status"] = status
        plan["architectureReview"] = review
        self._publish_proposed_graph(plan, created_by=actor)
        self.store.put_change_plan(plan)
        self.store.append_audit_event(
            "ArchitectureReviewRecorded",
            review,
            correlation_id=correlation_id,
            run_id=plan_id,
            requirement_id=plan["changeSet"]["requirementId"],
            revision=plan["changeSet"]["currentRevision"],
            actor=actor,
        )
        return plan

    def approve_change_plan(
        self,
        plan_id: str,
        body_value: Any,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        body = object_value(body_value, "request")
        plan = self.get_change_plan(plan_id)
        if plan["status"] != "ArchitectureReviewed":
            raise conflict("Architecture Review Gate 尚未接受")
        actor = string_value(body.get("actor"), "actor")
        rationale = string_value(body.get("rationale"), "rationale")
        allowed_files = [
            string_value(item, "allowedFiles item")
            for item in list_value(
                body.get("allowedFiles"), "allowedFiles", nonempty=True
            )
        ]
        forbidden_files = [
            string_value(item, "forbiddenFiles item")
            for item in list_value(
                body.get("forbiddenFiles"), "forbiddenFiles", nonempty=True
            )
        ]
        required_tests = [
            string_value(item, "requiredTests item")
            for item in list_value(
                body.get("requiredTests"), "requiredTests", nonempty=True
            )
        ]
        for command in required_tests:
            validate_test_command(command)
        if (
            plan["governance"]["requiresSecurityDataReview"]
            and body.get("securityDataApproved") is not True
        ):
            raise invalid("该计划强制要求 Security / Data Gate 批准")
        approval = self.store.record_review_decision(
            {
                "reviewId": f"review-{uuid.uuid4()}",
                "resourceType": "ChangePlan",
                "resourceId": plan_id,
                "gate": "ChangeApproval",
                "decision": "Approve",
                "actor": actor,
                "rationale": rationale,
                "securityDataApproved": body.get("securityDataApproved") is True,
            }
        )
        for task in plan["implementationTasks"]:
            task["allowedFiles"] = allowed_files
            task["forbiddenFiles"] = forbidden_files
            task["requiredTests"] = sorted({*task["requiredTests"], *required_tests})
            task["status"] = "Approved"
        plan["status"] = "Approved"
        plan["approval"] = approval
        approved_nodes = [
            {
                "id": f"change-set:{plan_id}",
                "type": "DesignChangeSet",
                "status": "Approved",
                "requirementId": plan["changeSet"]["requirementId"],
            }
        ]
        approved_edges: list[dict[str, Any]] = []
        for proposal in plan["proposals"]:
            approved_nodes.append(
                {
                    "id": proposal["proposalId"],
                    "type": proposal["changeType"],
                    **proposal,
                    "proposalStatus": "Approved",
                }
            )
            approved_edges.append(
                {
                    "source": f"change-set:{plan_id}",
                    "relation": "plan:containsProposedChange",
                    "target": proposal["proposalId"],
                }
            )
        for task in plan["implementationTasks"]:
            approved_nodes.append(
                {
                    "id": task["taskId"],
                    "type": "ImplementationTask",
                    **task,
                }
            )
            approved_edges.append(
                {
                    "source": task["taskId"],
                    "relation": "plan:implementsProposedChange",
                    "target": task["proposalId"],
                }
            )
        self.replace_graph(
            "approved",
            plan_id,
            approved_nodes,
            approved_edges,
            metadata={
                "graphId": f"urn:graph:approved:{plan_id}",
                "graphType": "Approved",
                "baseRevision": plan["changeSet"]["currentRevision"],
                "createdBy": actor,
                "sourceArtifact": plan_id,
                "status": "Approved",
                "validationStatus": "HumanApproved",
            },
        )
        self.store.put_change_plan(plan)
        requirement = self.get_requirement_ir(plan["changeSet"]["requirementId"])
        self.put_requirement_context(
            requirement["requirementId"],
            requirement["designRevisionId"],
            "implement",
            {
                "approvalState": "Approved",
                "allowedActions": ["CreateAgentRun", "GeneratePatch"],
                "approvedChangeRevision": plan_id,
                "baseRevision": plan["changeSet"]["currentRevision"],
                "allowedFiles": allowed_files,
                "forbiddenFiles": forbidden_files,
                "requiredTests": required_tests,
                "implementationTasks": plan["implementationTasks"],
                "acceptanceCriteria": [
                    item["description"] for item in plan["verificationObligations"]
                ],
            },
        )
        self.store.append_audit_event(
            "ChangePlanApproved",
            {
                "planId": plan_id,
                "approval": approval,
                "allowedFiles": allowed_files,
                "forbiddenFiles": forbidden_files,
                "requiredTests": required_tests,
            },
            correlation_id=correlation_id,
            run_id=plan_id,
            requirement_id=requirement["requirementId"],
            revision=plan["changeSet"]["currentRevision"],
            actor=actor,
        )
        return plan

    def create_agent_run(
        self, body_value: Any, correlation_id: str | None = None
    ) -> dict[str, Any]:
        body = object_value(body_value, "request")
        plan_id = string_value(body.get("changePlanId"), "changePlanId")
        plan = self.get_change_plan(plan_id)
        if plan["status"] != "Approved":
            raise conflict("只有 Approved Change 才能创建 Agent Run")
        requirement = self.get_requirement_ir(plan["changeSet"]["requirementId"])
        context = self.requirement_context(
            requirement["requirementId"],
            requirement["designRevisionId"],
            "implement",
        )
        if context.get("approvalState") != "Approved":
            raise conflict("Implement Context 未通过批准")
        repository_id = string_value(
            body.get("repositoryId")
            or plan["changeSet"].get("repositoryId")
            or plan.get("context", {}).get("repositoryId"),
            "repositoryId",
        )
        repository = self.get_repository(repository_id)
        identity = inspect_repository(repository["path"], repository_id)
        if identity["dirty"]:
            raise conflict("创建 Agent Run 前 Repository Snapshot 必须是干净提交")
        base_commit = string_value(
            body.get("baseCommit") or identity.get("commit"), "baseCommit"
        )
        if identity["commit"] != base_commit:
            raise conflict("Agent Run Base Commit 与当前 Repository HEAD 不一致")
        if plan["changeSet"]["currentRevision"] != base_commit:
            raise conflict("Approved Change Base Revision 与 Agent Base Commit 不一致")
        run_id_value = body.get("runId")
        run_id = (
            string_value(run_id_value, "runId")
            if run_id_value is not None
            else f"agent-run-{uuid.uuid4()}"
        )
        existing = self.store.get_agent_run(run_id)
        if existing is not None:
            return existing
        worktree = self.worktree_manager.create(repository["path"], run_id, base_commit)
        run = {
            "runId": run_id,
            "changePlanId": plan_id,
            "requirementId": requirement["requirementId"],
            "repositoryId": repository_id,
            "baseCommit": worktree.base_commit,
            "worktreePath": str(worktree.path),
            "status": "Running",
            "agentName": "implementation-agent",
            "skillName": "implement-approved-change",
            "policy": {
                "allowedFiles": context["allowedFiles"],
                "forbiddenFiles": context["forbiddenFiles"],
                "requiredTests": context["requiredTests"],
                "forbiddenCommands": [
                    "git commit",
                    "git push",
                    "git merge",
                    "git rebase",
                    "git tag",
                    "kubectl",
                    "helm",
                    "terraform",
                ],
            },
        }
        self.store.put_agent_run(run)
        self.store.append_audit_event(
            "AgentRunStarted",
            {
                "changePlanId": plan_id,
                "baseCommit": base_commit,
                "worktreePath": str(worktree.path),
                "agentName": run["agentName"],
                "skillName": run["skillName"],
                "policy": run["policy"],
            },
            correlation_id=correlation_id,
            run_id=run_id,
            requirement_id=requirement["requirementId"],
            repository_id=repository_id,
            revision=base_commit,
            actor=body.get("actor"),
        )
        try:
            execution = self.agent_adapter.execute(
                worktree=worktree.path,
                run_id=run_id,
                prompt=build_agent_prompt(plan, context),
                agent_name=run["agentName"],
                allowed_files=context["allowedFiles"],
                forbidden_files=context["forbiddenFiles"],
                required_tests=context["requiredTests"],
            )
            diff = collect_worktree_diff(worktree.path, worktree.base_commit)
            path_validation = validate_changed_paths(
                diff["changedFiles"],
                context["allowedFiles"],
                context["forbiddenFiles"],
            )
            execution_policy = {
                "status": (
                    "Passed"
                    if diff["headUnchanged"] and path_validation["status"] == "Passed"
                    else "Rejected"
                ),
                "headUnchanged": diff["headUnchanged"],
                "pathValidation": path_validation,
                "forbiddenCommandsEnforced": True,
            }
            test_report = (
                run_required_tests(worktree.path, context["requiredTests"])
                if execution_policy["status"] == "Passed"
                else {"status": "Skipped", "executions": []}
            )
            run.update(
                {
                    "sessionId": execution.get("sessionId"),
                    "runtime": execution.get("runtime"),
                    "runtimeVersion": execution.get("runtimeVersion"),
                    "execution": execution,
                    "diff": diff,
                    "executionPolicy": execution_policy,
                    "testReport": test_report,
                    "status": (
                        "Completed"
                        if execution_policy["status"] == "Passed"
                        and test_report["status"] == "Passed"
                        else (
                            "PolicyViolation"
                            if execution_policy["status"] == "Rejected"
                            else "VerificationFailed"
                        )
                    ),
                }
            )
        except PlatformError as error:
            interrupted_diff = collect_worktree_diff(
                worktree.path, worktree.base_commit
            )
            interrupted_paths = validate_changed_paths(
                interrupted_diff["changedFiles"],
                context["allowedFiles"],
                context["forbiddenFiles"],
            )
            run.update(
                {
                    "status": (
                        "TimedOut"
                        if error.code in {"OPENCODE_RUN_TIMEOUT", "CODEX_RUN_TIMEOUT"}
                        else "Blocked"
                    ),
                    "sessionId": (
                        error.details.get("sessionId")
                        if isinstance(error.details, dict)
                        else None
                    ),
                    "diff": interrupted_diff,
                    "executionPolicy": {
                        "status": (
                            "Passed"
                            if interrupted_diff["headUnchanged"]
                            and interrupted_paths["status"] == "Passed"
                            else "Rejected"
                        ),
                        "headUnchanged": interrupted_diff["headUnchanged"],
                        "pathValidation": interrupted_paths,
                        "forbiddenCommandsEnforced": True,
                        "executionCompleted": False,
                    },
                    "testReport": {
                        "status": "Skipped",
                        "reason": "Agent execution did not complete.",
                        "executions": [],
                    },
                    "error": {
                        "code": error.code,
                        "message": error.message,
                        "details": error.details,
                    },
                }
            )
        except Exception as error:  # noqa: BLE001 - persist all adapter failures.
            run.update(
                {
                    "status": "Failed",
                    "error": {
                        "code": "AGENT_EXECUTION_FAILED",
                        "message": str(error)[:1000],
                    },
                }
            )
        self.store.put_agent_run(run)
        artifact_status = "Produced" if run["status"] == "Completed" else run["status"]
        if run.get("diff") is not None:
            self.store.record_artifact(
                route="/internal/agent-runs/implementation-patch",
                idempotency_key=f"{run_id}:patch",
                request_body={"runId": run_id, "diffHash": run["diff"]["patchHash"]},
                run_id=run_id,
                requirement_id=requirement["requirementId"],
                artifact_type="ImplementationPatch",
                status=artifact_status,
                payload={
                    "diff": run["diff"],
                    "executionPolicy": run["executionPolicy"],
                    "changePlanId": plan_id,
                },
                agent_name=run["agentName"],
                session_id=run.get("sessionId"),
                correlation_id=correlation_id,
            )
            self.store.record_artifact(
                route="/internal/agent-runs/test-report",
                idempotency_key=f"{run_id}:tests",
                request_body={"runId": run_id, "tests": context["requiredTests"]},
                run_id=run_id,
                requirement_id=requirement["requirementId"],
                artifact_type="TestExecutionReport",
                status=artifact_status,
                payload=run["testReport"],
                agent_name=run["agentName"],
                session_id=run.get("sessionId"),
                correlation_id=correlation_id,
            )
        self.store.append_audit_event(
            "AgentRunFinished",
            {
                "status": run["status"],
                "sessionId": run.get("sessionId"),
                "runtime": run.get("runtime"),
                "executionPolicy": run.get("executionPolicy"),
                "testStatus": run.get("testReport", {}).get("status"),
                "error": run.get("error"),
            },
            correlation_id=correlation_id,
            run_id=run_id,
            requirement_id=requirement["requirementId"],
            repository_id=repository_id,
            revision=base_commit,
            actor=body.get("actor"),
        )
        if run["status"] == "Completed":
            self.put_requirement_context(
                requirement["requirementId"],
                requirement["designRevisionId"],
                "verify",
                {
                    "approvalState": "ImplementationCompleted",
                    "agentRunId": run_id,
                    "changePlanId": plan_id,
                    "baseCommit": base_commit,
                    "worktreePath": str(worktree.path),
                    "patchHash": run["diff"]["patchHash"],
                    "allowedActions": [
                        "RegenerateActualGraph",
                        "ReconcileApprovedAndActual",
                    ],
                },
            )
        return run

    def get_agent_run(self, run_id: str) -> dict[str, Any]:
        run_id = string_value(run_id, "agentRunId")
        run = self.store.get_agent_run(run_id)
        if run is None:
            raise not_found(f"未找到 Agent Run: {run_id}")
        return run

    def agent_run_diff(self, run_id: str) -> dict[str, Any]:
        run = self.get_agent_run(run_id)
        if "diff" not in run:
            raise not_found(f"Agent Run 尚未生成 Diff: {run_id}")
        return {
            "runId": run_id,
            "status": run["status"],
            "diff": run["diff"],
            "executionPolicy": run["executionPolicy"],
        }

    def respond_agent_permission(
        self,
        run_id: str,
        permission_id: str,
        body_value: Any,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        body = object_value(body_value, "request")
        run = self.get_agent_run(run_id)
        if not run.get("sessionId"):
            raise conflict("Agent Run 没有可响应的 OpenCode Session")
        response = enum_value(
            body.get("response"),
            "response",
            frozenset({"once", "always", "reject"}),
        )
        if response == "always":
            raise invalid("平台禁止持久化 Agent 权限，仅允许 once 或 reject")
        accepted = self.agent_adapter.respond_permission(
            run["sessionId"], permission_id, response
        )
        event = self.store.append_audit_event(
            "AgentPermissionResponded",
            {
                "permissionId": permission_id,
                "response": response,
                "accepted": accepted,
            },
            correlation_id=correlation_id,
            run_id=run_id,
            requirement_id=run["requirementId"],
            repository_id=run["repositoryId"],
            revision=run["baseCommit"],
            actor=body.get("actor"),
        )
        return {"accepted": accepted, "auditEventId": event["eventId"]}

    def create_reconciliation_run(
        self, body_value: Any, correlation_id: str | None = None
    ) -> dict[str, Any]:
        body = object_value(body_value, "request")
        agent_run_id = string_value(body.get("agentRunId"), "agentRunId")
        agent_run = self.get_agent_run(agent_run_id)
        if agent_run["status"] != "Completed":
            raise conflict("只有完成并通过策略与测试的 Agent Run 才能执行对账")
        plan = self.get_change_plan(agent_run["changePlanId"])
        worktree = Path(agent_run["worktreePath"]).resolve()
        if not worktree.is_relative_to(self.worktree_manager.root):
            raise conflict("Agent Worktree 不属于平台受控目录")
        if not worktree.is_dir():
            raise not_found(f"Agent Worktree 不存在: {agent_run_id}")
        current_diff = collect_worktree_diff(worktree, agent_run["baseCommit"])
        if current_diff["patchHash"] != agent_run["diff"]["patchHash"]:
            raise conflict("Agent Run 完成后 Worktree 内容已漂移")
        if not current_diff["headUnchanged"]:
            raise conflict("Worktree HEAD 已改变，拒绝对账")
        result = RepositoryScanner().scan(worktree, agent_run["repositoryId"])
        actual_graph = result["graph"]
        raw_revision = actual_graph["revision"]
        reconciliation_run_id = (
            "reconciliation-"
            + hashlib.sha256(
                f"{agent_run_id}|{current_diff['patchHash']}".encode()
            ).hexdigest()[:20]
        )
        actual_revision = (
            f"actual:{agent_run_id}:"
            + hashlib.sha256(raw_revision.encode()).hexdigest()[:16]
        )
        current_nodes, current_edges = self.store.read_graph(
            "current", plan["changeSet"]["currentRevision"]
        )
        if not current_nodes:
            raise not_found("Approved Change 引用的 Current Graph 不存在")
        self.replace_graph(
            "actual",
            actual_revision,
            actual_graph["nodes"],
            actual_graph["edges"],
            metadata={
                "graphId": f"urn:graph:actual:{agent_run_id}",
                "graphType": "Actual",
                "baseRevision": agent_run["baseCommit"],
                "worktreeRevision": raw_revision,
                "sourceArtifact": agent_run_id,
                "createdBy": f"extractor:{EXTRACTOR_VERSION}",
                "status": "Extracted",
                "validationStatus": (
                    "Complete"
                    if result["coverage"]["failedJavaFiles"] == 0
                    else "Incomplete"
                ),
            },
        )
        reconciliation = reconcile_approved_actual(
            reconciliation_run_id=reconciliation_run_id,
            agent_run=agent_run,
            plan=plan,
            current_nodes=current_nodes,
            current_edges=current_edges,
            actual_nodes=actual_graph["nodes"],
            actual_edges=actual_graph["edges"],
            actual_revision=actual_revision,
            coverage=result["coverage"],
        )
        self.store.put_reconciliation_run(reconciliation)
        context = self.put_reconciliation_context(
            reconciliation_run_id,
            {
                "approvalState": reconciliation["status"],
                "agentRunId": agent_run_id,
                "changePlanId": plan["planId"],
                "baseRevision": plan["changeSet"]["currentRevision"],
                "approvedRevision": plan["planId"],
                "actualRevision": actual_revision,
                "proposalResults": reconciliation["proposalResults"],
                "verificationResults": reconciliation["verificationResults"],
                "deviations": reconciliation["deviations"],
                "allowedActions": ["AnalyzeImpact", "PrepareReleaseAdvice"],
            },
        )
        reconciliation["contextHash"] = context["contextHash"]
        self.store.put_reconciliation_run(reconciliation)
        self.store.append_audit_event(
            "ActualGraphPublished",
            {
                "actualRevision": actual_revision,
                "worktreeRevision": raw_revision,
                "coverage": result["coverage"],
            },
            correlation_id=correlation_id,
            run_id=reconciliation_run_id,
            requirement_id=agent_run["requirementId"],
            repository_id=agent_run["repositoryId"],
            revision=actual_revision,
            actor=body.get("actor"),
        )
        self.store.append_audit_event(
            "ReconciliationCompleted",
            {
                "status": reconciliation["status"],
                "resultHash": reconciliation["resultHash"],
                "deviationCount": len(reconciliation["deviations"]),
            },
            correlation_id=correlation_id,
            run_id=reconciliation_run_id,
            requirement_id=agent_run["requirementId"],
            repository_id=agent_run["repositoryId"],
            revision=actual_revision,
            actor=body.get("actor"),
        )
        return reconciliation

    def get_reconciliation_run(self, run_id: str) -> dict[str, Any]:
        run_id = string_value(run_id, "reconciliationRunId")
        run = self.store.get_reconciliation_run(run_id)
        if run is None:
            raise not_found(f"未找到 Reconciliation Run: {run_id}")
        return run

    def create_impact_run(
        self, body_value: Any, correlation_id: str | None = None
    ) -> dict[str, Any]:
        body = object_value(body_value, "request")
        reconciliation_run_id = string_value(
            body.get("reconciliationRunId"), "reconciliationRunId"
        )
        reconciliation = self.get_reconciliation_run(reconciliation_run_id)
        plan = self.get_change_plan(reconciliation["changePlanId"])
        actual_nodes, actual_edges = self.store.read_graph(
            "actual", reconciliation["actualRevision"]
        )
        if not actual_nodes:
            raise not_found("Reconciliation 引用的 Actual Graph 不存在")
        depth = body.get("depth", 5)
        limit = body.get("limit", 500)
        if not isinstance(depth, int) or not 1 <= depth <= 8:
            raise invalid("depth 必须是 1 到 8 的整数")
        if not isinstance(limit, int) or not 1 <= limit <= 2000:
            raise invalid("limit 必须是 1 到 2000 的整数")
        impact_run_id = (
            "impact-"
            + hashlib.sha256(
                (
                    reconciliation_run_id
                    + "|"
                    + reconciliation["resultHash"]
                    + f"|{depth}|{limit}"
                ).encode()
            ).hexdigest()[:20]
        )
        impact = build_impact_analysis(
            impact_run_id=impact_run_id,
            reconciliation=reconciliation,
            plan=plan,
            actual_nodes=actual_nodes,
            actual_edges=actual_edges,
            depth=depth,
            limit=limit,
        )
        self.replace_graph(
            "impact",
            impact_run_id,
            impact["graph"]["nodes"],
            impact["graph"]["edges"],
            metadata={
                "graphId": f"urn:graph:impact:{impact_run_id}",
                "graphType": "Impact",
                "baseRevision": reconciliation["actualRevision"],
                "sourceArtifact": reconciliation_run_id,
                "createdBy": f"impact-engine:{impact['engineVersion']}",
                "status": "Analyzed",
                "validationStatus": "Deterministic",
            },
        )
        self.store.put_impact_run(impact)
        requirement = self.get_requirement_ir(impact["requirementId"])
        self.put_requirement_context(
            requirement["requirementId"],
            requirement["designRevisionId"],
            "impact",
            {
                "approvalState": "ImpactAnalyzed",
                "impactRunId": impact_run_id,
                "reconciliationRunId": reconciliation_run_id,
                "actualRevision": reconciliation["actualRevision"],
                "releaseDecision": impact["releasePlan"]["decision"],
                "selectedTests": impact["selectedTests"],
                "allowedActions": ["ReviewReleasePlan"],
            },
        )
        self.store.append_audit_event(
            "ImpactAnalysisCompleted",
            {
                "impactRunId": impact_run_id,
                "resultHash": impact["resultHash"],
                "summary": impact["impactSummary"],
                "releaseDecision": impact["releasePlan"]["decision"],
            },
            correlation_id=correlation_id,
            run_id=impact_run_id,
            requirement_id=impact["requirementId"],
            repository_id=reconciliation["repositoryId"],
            revision=reconciliation["actualRevision"],
            actor=body.get("actor"),
        )
        return impact

    def get_impact_run(self, run_id: str) -> dict[str, Any]:
        run_id = string_value(run_id, "impactRunId")
        run = self.store.get_impact_run(run_id)
        if run is None:
            raise not_found(f"未找到 Impact Run: {run_id}")
        return run

    def audit_events(
        self,
        *,
        requirement_id: str | None = None,
        run_id: str | None = None,
        correlation_id: str | None = None,
        limit: int = 1000,
    ) -> dict[str, Any]:
        if not isinstance(limit, int) or not 1 <= limit <= 5000:
            raise invalid("limit 必须是 1 到 5000 的整数")
        all_events = self.store.list_audit_events(limit=5000)
        selected = [
            event
            for event in all_events
            if (requirement_id is None or event["requirementId"] == requirement_id)
            and (run_id is None or event["runId"] == run_id)
            and (correlation_id is None or event["correlationId"] == correlation_id)
        ][:limit]
        return {
            "events": selected,
            "count": len(selected),
            "chainVerification": self.store.verify_audit_chain(all_events),
        }

    def replay_requirement(self, requirement_id: str) -> dict[str, Any]:
        requirement_id = string_value(requirement_id, "requirementId")
        requirement = self.get_requirement_ir(requirement_id)
        events = self.store.list_audit_events(requirement_id=requirement_id, limit=5000)
        all_events = self.store.list_audit_events(limit=5000)
        resources = self.store.replay_resources(requirement_id)
        package = {
            "requirementId": requirement_id,
            "designRevisionId": requirement["designRevisionId"],
            "events": events,
            "resources": resources,
            "versions": {
                "planningRuleSet": self.planning_rules.rule_set,
                "planningRuleSetVersion": self.planning_rules.version,
                "repositoryExtractorVersion": EXTRACTOR_VERSION,
                "documentExtractorVersion": DOCUMENT_EXTRACTOR_VERSION,
            },
            "auditChain": self.store.verify_audit_chain(all_events),
        }
        package["replayHash"] = content_hash(package)
        return package

    def record_runtime_evidence(
        self, body_value: Any, correlation_id: str | None = None
    ) -> dict[str, Any]:
        body = object_value(body_value, "request")
        requirement_id = string_value(body.get("requirementId"), "requirementId")
        self.get_requirement_ir(requirement_id)
        impact_run_id = string_value(body.get("impactRunId"), "impactRunId")
        impact = self.get_impact_run(impact_run_id)
        if impact["requirementId"] != requirement_id:
            raise conflict("Impact Run 不属于该 Requirement")
        environment = enum_value(
            body.get("environment"),
            "environment",
            frozenset({"development", "test", "staging", "production"}),
        )
        deployment_version = string_value(
            body.get("deploymentVersion"), "deploymentVersion"
        )
        checks = [
            object_value(item, "verificationChecks item")
            for item in list_value(
                body.get("verificationChecks"),
                "verificationChecks",
                nonempty=True,
            )
        ]
        normalized_checks = []
        for item in checks:
            normalized_checks.append(
                {
                    "name": string_value(item.get("name"), "check.name"),
                    "status": enum_value(
                        item.get("status"),
                        "check.status",
                        frozenset({"Passed", "Failed"}),
                    ),
                    "evidence": _redact_sensitive(
                        object_value(item.get("evidence", {}), "check.evidence")
                    ),
                }
            )
        all_passed = all(item["status"] == "Passed" for item in normalized_checks)
        release_approval = body.get("releaseApproval")
        if environment == "production":
            if impact["releasePlan"]["decision"] == "Blocked":
                raise conflict("Release Plan 为 Blocked，禁止登记生产运行证据")
            approval = object_value(release_approval, "releaseApproval")
            if approval.get("decision") != "Approve":
                raise invalid("生产运行证据必须引用人工 Release Approval")
            string_value(approval.get("actor"), "releaseApproval.actor")
            string_value(approval.get("rationale"), "releaseApproval.rationale")
            if not all_passed:
                raise invalid("生产运行证据的所有 Verification Check 必须通过")
        evidence = {
            "evidenceId": f"runtime-evidence-{uuid.uuid4()}",
            "requirementId": requirement_id,
            "impactRunId": impact_run_id,
            "environment": environment,
            "deploymentVersion": deployment_version,
            "configurationSnapshot": _redact_sensitive(
                object_value(
                    body.get("configurationSnapshot", {}),
                    "configurationSnapshot",
                )
            ),
            "verificationChecks": normalized_checks,
            "metrics": _redact_sensitive(
                object_value(body.get("metrics", {}), "metrics")
            ),
            "releaseApproval": _redact_sensitive(release_approval),
            "status": "Verified" if all_passed else "Failed",
            "createdAt": utc_now(),
        }
        evidence["payloadHash"] = content_hash(evidence)
        self.store.put_runtime_evidence(evidence)
        self.store.append_audit_event(
            "RuntimeEvidenceRecorded",
            {
                "evidenceId": evidence["evidenceId"],
                "impactRunId": impact_run_id,
                "environment": environment,
                "deploymentVersion": deployment_version,
                "status": evidence["status"],
                "payloadHash": evidence["payloadHash"],
            },
            correlation_id=correlation_id,
            run_id=impact_run_id,
            requirement_id=requirement_id,
            revision=deployment_version,
            actor=body.get("actor"),
        )
        return evidence

    def runtime_evidence(self, requirement_id: str) -> dict[str, Any]:
        requirement_id = string_value(requirement_id, "requirementId")
        self.get_requirement_ir(requirement_id)
        values = self.store.list_runtime_evidence(requirement_id)
        return {
            "requirementId": requirement_id,
            "evidence": values,
            "count": len(values),
        }

    def create_requirement_workflow(
        self, body_value: Any, correlation_id: str | None = None
    ) -> dict[str, Any]:
        return self.workflow_orchestrator.create(body_value, correlation_id)

    def get_requirement_workflow(self, workflow_id: str) -> dict[str, Any]:
        return self.workflow_orchestrator.get(workflow_id)

    def list_requirement_workflows(
        self,
        *,
        requirement_id: str | None = None,
        repository_id: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        return self.workflow_orchestrator.list(
            requirement_id=requirement_id,
            repository_id=repository_id,
            limit=limit,
        )

    def resume_requirement_workflow(
        self,
        workflow_id: str,
        body_value: Any,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        return self.workflow_orchestrator.resume(
            workflow_id, body_value, correlation_id
        )

    def retry_requirement_workflow(
        self,
        workflow_id: str,
        body_value: Any,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        return self.workflow_orchestrator.retry(workflow_id, body_value, correlation_id)

    def put_requirement_context(
        self,
        requirement_id: str,
        design_revision_id: str,
        stage: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        requirement_id = string_value(requirement_id, "requirementId")
        design_revision_id = string_value(design_revision_id, "designRevisionId")
        stage = enum_value(stage, "stage", STAGES)
        return self.store.put_requirement_context(
            requirement_id, design_revision_id, stage, payload
        )

    def requirement_context(
        self, requirement_id: str, design_revision_id: str, stage: str
    ) -> dict[str, Any]:
        requirement_id = string_value(requirement_id, "requirementId")
        design_revision_id = string_value(design_revision_id, "designRevisionId")
        stage = enum_value(stage, "stage", STAGES)
        context = self.store.get_requirement_context(
            requirement_id, design_revision_id, stage
        )
        if context is None:
            raise not_found(
                "未找到与 requirementId、designRevisionId 和 stage 完全匹配的上下文"
            )
        return context

    def put_reconciliation_context(
        self, reconciliation_run_id: str, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        reconciliation_run_id = string_value(
            reconciliation_run_id, "reconciliationRunId"
        )
        return self.store.put_reconciliation_context(reconciliation_run_id, payload)

    def reconciliation_context(self, reconciliation_run_id: str) -> dict[str, Any]:
        reconciliation_run_id = string_value(
            reconciliation_run_id, "reconciliationRunId"
        )
        context = self.store.get_reconciliation_context(reconciliation_run_id)
        if context is None:
            raise not_found("未找到 Reconciliation Run 上下文")
        return context

    def replace_graph(
        self,
        graph_space: str,
        revision: str,
        nodes_value: Any,
        edges_value: Any,
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        graph_space = enum_value(graph_space, "graphSpace", GRAPH_SPACES)
        revision = string_value(revision, "revision")
        nodes = list_value(nodes_value, "nodes", nonempty=True)
        edges = list_value(edges_value, "edges")
        normalized_nodes: list[dict[str, Any]] = []
        node_ids: set[str] = set()
        for index, value in enumerate(nodes):
            node = object_value(value, f"nodes[{index}]")
            entity_id = string_value(node.get("id"), f"nodes[{index}].id")
            if entity_id in node_ids:
                raise invalid(f"nodes 存在重复实体 ID: {entity_id}")
            node_ids.add(entity_id)
            node["id"] = entity_id
            normalized_nodes.append(node)
        normalized_edges: list[dict[str, Any]] = []
        edge_ids: set[tuple[str, str, str]] = set()
        for index, value in enumerate(edges):
            edge = object_value(value, f"edges[{index}]")
            source = string_value(edge.get("source"), f"edges[{index}].source")
            relation = string_value(edge.get("relation"), f"edges[{index}].relation")
            target = string_value(edge.get("target"), f"edges[{index}].target")
            missing = [entity for entity in (source, target) if entity not in node_ids]
            if missing:
                raise invalid(
                    f"edges[{index}] 引用了图快照中不存在的实体",
                    {"missingEntityIds": missing},
                )
            edge_id = (source, relation, target)
            if edge_id in edge_ids:
                raise invalid(f"edges 存在重复关系: {edge_id}")
            edge_ids.add(edge_id)
            edge["source"] = source
            edge["relation"] = relation
            edge["target"] = target
            normalized_edges.append(edge)
        return self.store.replace_graph(
            graph_space,
            revision,
            normalized_nodes,
            normalized_edges,
            metadata,
        )

    def graph_catalog(
        self, graph_space: str | None = None, limit: int = 500
    ) -> dict[str, Any]:
        if graph_space is not None:
            graph_space = enum_value(graph_space, "graphSpace", GRAPH_SPACES)
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 500
        ):
            raise invalid("limit 必须是 1 到 500 的整数")
        revisions = self.store.list_graph_revisions(graph_space, limit)
        return {
            "graphSpaces": sorted(GRAPH_SPACES),
            "revisions": revisions,
            "count": len(revisions),
        }

    def graph_compare(self, body_value: Any) -> dict[str, Any]:
        body = object_value(body_value, "request")

        def graph_ref(name: str) -> tuple[str, str]:
            value = object_value(body.get(name), name)
            graph_space = enum_value(
                value.get("graphSpace"), f"{name}.graphSpace", GRAPH_SPACES
            )
            revision_value = value.get("revision")
            revision = (
                string_value(revision_value, f"{name}.revision")
                if revision_value is not None
                else self.store.latest_graph_revision(graph_space)
            )
            if revision is None:
                raise not_found(f"图空间 {graph_space} 尚无快照")
            return graph_space, revision

        base_space, base_revision = graph_ref("base")
        target_space, target_revision = graph_ref("target")
        limit = body.get("limit", 500)
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 500
        ):
            raise invalid("limit 必须是 1 到 500 的整数")
        requested_statuses = {
            enum_value(
                value,
                "changeStatuses item",
                frozenset({"Added", "Removed", "Modified", "Unchanged"}),
            )
            for value in list_value(body.get("changeStatuses", []), "changeStatuses")
        }
        entity_types = {
            string_value(value, "entityTypes item")
            for value in list_value(body.get("entityTypes", []), "entityTypes")
        }
        search_value = body.get("search")
        search = (
            string_value(search_value, "search").lower()
            if search_value is not None
            else None
        )
        base_nodes, base_edges = self.store.read_graph(base_space, base_revision)
        target_nodes, target_edges = self.store.read_graph(
            target_space, target_revision
        )
        if not base_nodes:
            raise not_found(f"Base Graph Revision 不存在: {base_space}/{base_revision}")
        if not target_nodes:
            raise not_found(
                f"Target Graph Revision 不存在: {target_space}/{target_revision}"
            )

        base_by_id = {node["id"]: node for node in base_nodes}
        target_by_id = {node["id"]: node for node in target_nodes}
        status_counts = {
            "Added": 0,
            "Removed": 0,
            "Modified": 0,
            "Unchanged": 0,
        }
        compared_nodes: list[dict[str, Any]] = []
        field_changes: list[dict[str, Any]] = []
        for entity_id in sorted(base_by_id.keys() | target_by_id.keys()):
            before = base_by_id.get(entity_id)
            after = target_by_id.get(entity_id)
            if before is None:
                status = "Added"
            elif after is None:
                status = "Removed"
            elif content_hash(stable_graph_item(before)) != content_hash(
                stable_graph_item(after)
            ):
                status = "Modified"
            else:
                status = "Unchanged"
            status_counts[status] += 1
            changed_fields = []
            if before is not None and after is not None and status == "Modified":
                stable_before = stable_graph_item(before)
                stable_after = stable_graph_item(after)
                for field in sorted(stable_before.keys() | stable_after.keys()):
                    before_value = stable_before.get(field)
                    after_value = stable_after.get(field)
                    if content_hash(before_value) == content_hash(after_value):
                        continue
                    change = {
                        "entityId": entity_id,
                        "field": field,
                        "before": before_value,
                        "after": after_value,
                    }
                    changed_fields.append(change)
                    field_changes.append(change)
            display = dict(after or before or {})
            display.update(
                {
                    "id": entity_id,
                    "changeStatus": status,
                    "changedFields": [item["field"] for item in changed_fields],
                    "comparison": {"base": before, "target": after},
                }
            )
            searchable = " ".join(
                str(display.get(key, ""))
                for key in (
                    "id",
                    "type",
                    "label",
                    "name",
                    "qualifiedName",
                    "path",
                    "key",
                )
            ).lower()
            if requested_statuses and status not in requested_statuses:
                continue
            if entity_types and str(display.get("type")) not in entity_types:
                continue
            if search is not None and search not in searchable:
                continue
            compared_nodes.append(display)

        base_edges_by_key = {
            (edge["source"], edge["relation"], edge["target"]): edge
            for edge in base_edges
        }
        target_edges_by_key = {
            (edge["source"], edge["relation"], edge["target"]): edge
            for edge in target_edges
        }
        edge_status_counts = {
            "Added": 0,
            "Removed": 0,
            "Modified": 0,
            "Unchanged": 0,
        }
        all_compared_edges: list[dict[str, Any]] = []
        for edge_key in sorted(base_edges_by_key.keys() | target_edges_by_key.keys()):
            before = base_edges_by_key.get(edge_key)
            after = target_edges_by_key.get(edge_key)
            if before is None:
                status = "Added"
            elif after is None:
                status = "Removed"
            elif content_hash(stable_graph_item(before)) != content_hash(
                stable_graph_item(after)
            ):
                status = "Modified"
            else:
                status = "Unchanged"
            edge_status_counts[status] += 1
            display = dict(after or before or {})
            display.update(
                {
                    "changeStatus": status,
                    "comparison": {"base": before, "target": after},
                }
            )
            all_compared_edges.append(display)

        selected_nodes = compared_nodes[:limit]
        selected_ids = {node["id"] for node in selected_nodes}
        compared_edges = [
            edge
            for edge in all_compared_edges
            if edge["source"] in selected_ids
            and edge["target"] in selected_ids
            and (not requested_statuses or edge["changeStatus"] in requested_statuses)
        ]
        edge_limit = min(2000, limit * 4)
        selected_edges = compared_edges[:edge_limit]
        base_selected_nodes = [
            base_by_id[entity_id]
            for entity_id in sorted(selected_ids)
            if entity_id in base_by_id
        ]
        target_selected_nodes = [
            target_by_id[entity_id]
            for entity_id in sorted(selected_ids)
            if entity_id in target_by_id
        ]
        base_selected_ids = {node["id"] for node in base_selected_nodes}
        target_selected_ids = {node["id"] for node in target_selected_nodes}
        selected_field_changes = [
            change for change in field_changes if change["entityId"] in selected_ids
        ]
        entity_type_counts: dict[str, int] = {}
        for node in [*base_nodes, *target_nodes]:
            node_type = str(node.get("type", "Unknown"))
            entity_type_counts[node_type] = entity_type_counts.get(node_type, 0) + 1
        return {
            "base": {
                "graphSpace": base_space,
                "revision": base_revision,
                "nodes": base_selected_nodes,
                "edges": [
                    edge
                    for edge in base_edges
                    if edge["source"] in base_selected_ids
                    and edge["target"] in base_selected_ids
                ][:edge_limit],
            },
            "target": {
                "graphSpace": target_space,
                "revision": target_revision,
                "nodes": target_selected_nodes,
                "edges": [
                    edge
                    for edge in target_edges
                    if edge["source"] in target_selected_ids
                    and edge["target"] in target_selected_ids
                ][:edge_limit],
            },
            "nodes": selected_nodes,
            "edges": selected_edges,
            "fieldChanges": selected_field_changes,
            "truncated": (
                len(compared_nodes) > limit or len(compared_edges) > edge_limit
            ),
            "summary": {
                "baseNodes": len(base_nodes),
                "baseEdges": len(base_edges),
                "targetNodes": len(target_nodes),
                "targetEdges": len(target_edges),
                "nodeChanges": status_counts,
                "edgeChanges": edge_status_counts,
                "selectedNodes": len(selected_nodes),
                "selectedEdges": len(selected_edges),
                "fieldChanges": len(field_changes),
                "entityTypes": [
                    {"name": name, "count": entity_type_counts[name]}
                    for name in sorted(entity_type_counts)
                ],
            },
        }

    def codegraph_index(
        self,
        repository_id: str,
        body_value: Any | None = None,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        body = object_value(body_value or {}, "request")
        repository = self.get_repository(repository_id)
        result = self.codegraph_sidecar.index(repository_id, repository["path"])
        self.store.append_audit_event(
            "CodeGraphIndexUpdated",
            {
                "provider": result["provider"],
                "status": result["status"],
                "fingerprint": result["fingerprint"],
                "fileCount": result["fileCount"],
            },
            correlation_id=correlation_id,
            repository_id=repository_id,
            revision=result["revision"],
            actor=body.get("actor"),
        )
        return result

    def codegraph_index_status(self, repository_id: str) -> dict[str, Any]:
        repository = self.get_repository(repository_id)
        return self.codegraph_sidecar.status(repository_id, repository["path"])

    def codegraph_explore(
        self, repository_id: str, body_value: Any
    ) -> dict[str, Any]:
        body = object_value(body_value, "request")
        repository = self.get_repository(repository_id)
        query = string_value(body.get("query"), "query")
        return self.codegraph_sidecar.explore(
            repository_id,
            repository["path"],
            query,
            allow_stale=body.get("allowStale") is True,
        )

    def codegraph_impact(
        self, repository_id: str, body_value: Any
    ) -> dict[str, Any]:
        body = object_value(body_value, "request")
        repository = self.get_repository(repository_id)
        symbol = string_value(body.get("symbol"), "symbol")
        depth = body.get("depth", 3)
        if isinstance(depth, bool) or not isinstance(depth, int) or not 1 <= depth <= 8:
            raise invalid("depth 必须是 1 到 8 的整数")
        return self.codegraph_sidecar.impact(
            repository_id,
            repository["path"],
            symbol,
            depth=depth,
            allow_stale=body.get("allowStale") is True,
        )

    def codegraph_affected_tests(
        self, repository_id: str, body_value: Any
    ) -> dict[str, Any]:
        body = object_value(body_value, "request")
        repository = self.get_repository(repository_id)
        changed_files = [
            string_value(value, "changedFiles item")
            for value in list_value(
                body.get("changedFiles"), "changedFiles", nonempty=True
            )
        ]
        depth = body.get("depth", 3)
        if isinstance(depth, bool) or not isinstance(depth, int) or not 1 <= depth <= 8:
            raise invalid("depth 必须是 1 到 8 的整数")
        return self.codegraph_sidecar.affected_tests(
            repository_id,
            repository["path"],
            changed_files,
            depth=depth,
            allow_stale=body.get("allowStale") is True,
        )

    def codegraph_compare(
        self, repository_id: str, body_value: Any
    ) -> dict[str, Any]:
        body = object_value(body_value, "request")
        repository = self.get_repository(repository_id)
        baseline = object_value(body.get("expectedGraph"), "expectedGraph")
        snapshot = self.codegraph_sidecar.graph_snapshot(
            repository_id,
            repository["path"],
            allow_stale=body.get("allowStale") is True,
        )
        limit = body.get("differenceLimit", 200)
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 1000
        ):
            raise invalid("differenceLimit 必须是 1 到 1000 的整数")
        return compare_codegraph_to_baseline(
            snapshot, baseline, difference_limit=limit
        )

    def _analysis_graph(
        self, body: Mapping[str, Any]
    ) -> tuple[str, str, list[dict[str, Any]], list[dict[str, Any]]]:
        graph_space = enum_value(
            body.get("graphSpace", "current"), "graphSpace", GRAPH_SPACES
        )
        repository_id_value = body.get("repositoryId")
        repository_id = (
            string_value(repository_id_value, "repositoryId")
            if repository_id_value is not None
            else None
        )
        if repository_id is not None:
            self.get_repository(repository_id)
        revision_value = body.get("revision")
        if (
            repository_id is not None
            and graph_space != "current"
            and revision_value is None
        ):
            raise invalid(
                "非 Current Graph 使用 repositoryId 时必须显式提供 revision"
            )
        revision = (
            string_value(revision_value, "revision")
            if revision_value is not None
            else (
                self._repository_current_revision(repository_id)
                if repository_id is not None and graph_space == "current"
                else self.store.latest_graph_revision(graph_space)
            )
        )
        if revision is None:
            raise not_found(f"图空间 {graph_space} 尚无快照")
        self._validate_repository_graph_scope(
            repository_id, graph_space, revision
        )
        nodes, edges = self.store.read_graph(graph_space, revision)
        if not nodes:
            raise not_found(f"图快照不存在: {graph_space}/{revision}")
        return graph_space, revision, nodes, edges

    def _repository_current_revision(self, repository_id: str) -> str | None:
        revisions = self.store.list_repository_graph_revisions(repository_id)
        return str(revisions[0]["revision"]) if revisions else None

    def _validate_repository_graph_scope(
        self,
        repository_id: str | None,
        graph_space: str,
        revision: str,
    ) -> None:
        if repository_id is None:
            return
        if graph_space == "current":
            repository_revisions = {
                str(item["revision"])
                for item in self.store.list_repository_graph_revisions(
                    repository_id
                )
            }
            if revision not in repository_revisions:
                raise not_found(
                    f"仓库 {repository_id} 不包含 Current Graph Revision: {revision}"
                )
            return
        metadata = self.store.get_graph_metadata(graph_space, revision) or {}
        scoped_repository = metadata.get("repositoryId")
        if (
            isinstance(scoped_repository, str)
            and scoped_repository
            and scoped_repository != repository_id
        ):
            raise not_found(
                f"Revision {graph_space}/{revision} 不属于仓库 {repository_id}"
            )

    def symbol_context(self, body_value: Any) -> dict[str, Any]:
        body = object_value(body_value, "request")
        query = string_value(body.get("query"), "query")
        repository_id_value = body.get("repositoryId")
        repository_id = (
            string_value(repository_id_value, "repositoryId")
            if repository_id_value is not None
            else None
        )
        if repository_id is not None:
            self.get_repository(repository_id)
        graph_space = enum_value(
            body.get("graphSpace", "current"), "graphSpace", GRAPH_SPACES
        )
        revision_value = body.get("revision")
        if (
            repository_id is not None
            and graph_space != "current"
            and revision_value is None
        ):
            raise invalid(
                "非 Current Graph 使用 repositoryId 时必须显式提供 revision"
            )
        revision = (
            string_value(revision_value, "revision")
            if revision_value is not None
            else (
                self._repository_current_revision(repository_id)
                if repository_id is not None and graph_space == "current"
                else None
            )
        )
        depth = body.get("depth", 2)
        limit = body.get("limit", 50)
        if isinstance(depth, bool) or not isinstance(depth, int) or not 0 <= depth <= 6:
            raise invalid("depth 必须是 0 到 6 的整数")
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 200
        ):
            raise invalid("limit 必须是 1 到 200 的整数")
        search_body: dict[str, Any] = {
            "graphSpace": graph_space,
            "query": query,
            "limit": min(limit, 20),
        }
        if repository_id is not None:
            search_body["repositoryId"] = repository_id
        if revision is not None:
            search_body["revision"] = revision
        search = self.hybrid_search(search_body)
        requested_entity = body.get("entityId")
        entity_id = (
            string_value(requested_entity, "entityId")
            if requested_entity is not None
            else (
                str(search["results"][0]["node"]["id"])
                if search["results"]
                else None
            )
        )
        if entity_id is None:
            return {
                "repositoryId": repository_id,
                "graphSpace": search["graphSpace"],
                "revision": search["revision"],
                "query": query,
                "selectedEntityId": None,
                "candidates": [],
                "context": None,
            }
        context = self.graph_query(
            {
                "repositoryId": repository_id,
                "graphSpace": search["graphSpace"],
                "revision": search["revision"],
                "queryType": "ENTITY_NEIGHBORHOOD",
                "entityId": entity_id,
                "depth": depth,
                "limit": limit,
            }
        )
        return {
            "repositoryId": repository_id,
            "graphSpace": search["graphSpace"],
            "revision": search["revision"],
            "query": query,
            "selectedEntityId": entity_id,
            "candidates": search["results"],
            "context": context,
        }

    def detect_changes(self, body_value: Any) -> dict[str, Any]:
        body = object_value(body_value, "request")
        repository_id = string_value(body.get("repositoryId"), "repositoryId")
        repository = self.get_repository(repository_id)
        base_ref_value = body.get("baseRef")
        base_ref = (
            string_value(base_ref_value, "baseRef")
            if base_ref_value is not None
            else None
        )
        depth = body.get("depth", 2)
        limit = body.get("limit", 100)
        if isinstance(depth, bool) or not isinstance(depth, int) or not 0 <= depth <= 6:
            raise invalid("depth 必须是 0 到 6 的整数")
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 500
        ):
            raise invalid("limit 必须是 1 到 500 的整数")

        repository_path = Path(repository["path"]).resolve()
        change_set = _git_changed_files(repository_path, base_ref)
        changed_files = list(change_set["files"])
        if change_set["source"] == "filesystem":
            try:
                status = self.codegraph_sidecar.status(
                    repository_id, repository_path
                )
            except PlatformError:
                status = {}
            changed_files = sorted(
                {
                    *status.get("changedFiles", []),
                    *status.get("deletedFiles", []),
                    *status.get("unindexedFiles", []),
                }
            )

        revision = self._repository_current_revision(repository_id)
        if revision is None:
            return {
                "repositoryId": repository_id,
                "baseRef": base_ref,
                "source": change_set["source"],
                "changedFiles": changed_files,
                "changedFileCount": len(changed_files),
                "currentGraph": None,
                "matchedNodes": [],
                "impactedNodes": [],
                "affectedProcesses": [],
                "affectedTests": [],
                "unmappedFiles": changed_files,
                "truncated": False,
            }
        if not changed_files:
            return {
                "repositoryId": repository_id,
                "baseRef": base_ref,
                "source": change_set["source"],
                "changedFiles": [],
                "changedFileCount": 0,
                "currentGraph": {"graphSpace": "current", "revision": revision},
                "matchedNodes": [],
                "impactedNodes": [],
                "affectedProcesses": [],
                "affectedTests": [],
                "unmappedFiles": [],
                "truncated": False,
            }

        nodes, edges = self.store.read_graph("current", revision)
        changed_set = set(changed_files)

        def source_path(node: Mapping[str, Any]) -> str | None:
            evidence = node.get("evidence")
            candidates = [
                node.get("relativePath"),
                node.get("filePath"),
                node.get("path"),
                evidence.get("source") if isinstance(evidence, Mapping) else None,
            ]
            for candidate in candidates:
                if isinstance(candidate, str) and candidate:
                    normalized = candidate.replace("\\", "/")
                    return normalized.removeprefix("./")
            return None

        matched_nodes = [
            dict(node) for node in nodes if source_path(node) in changed_set
        ]
        mapped_files = {
            path
            for node in matched_nodes
            if (path := source_path(node)) is not None
        }
        source_file_nodes = [
            node for node in matched_nodes if str(node.get("type")) == "SourceFile"
        ]
        seeds = source_file_nodes or matched_nodes
        impacted_by_id: dict[str, dict[str, Any]] = {
            str(node["id"]): node for node in matched_nodes
        }
        for seed in seeds[: min(limit, 50)]:
            context = self.graph_query(
                {
                    "graphSpace": "current",
                    "revision": revision,
                    "queryType": "CHANGE_CONTEXT",
                    "entityId": seed["id"],
                    "depth": depth,
                    "limit": limit,
                }
            )
            for node in context["nodes"]:
                impacted_by_id[str(node["id"])] = node
            if len(impacted_by_id) >= limit:
                break
        impacted_nodes = [
            impacted_by_id[node_id]
            for node_id in sorted(impacted_by_id)[:limit]
        ]
        impacted_ids = {str(node["id"]) for node in impacted_nodes}
        process_result = detect_processes(
            nodes, edges, max_depth=max(depth + 2, 2), limit=500
        )
        all_affected_processes = [
            process
            for process in process_result["processes"]
            if any(step["nodeId"] in impacted_ids for step in process["steps"])
        ]
        affected_processes = all_affected_processes[:limit]
        affected_tests = [
            node
            for node in impacted_nodes
            if str(node.get("type"))
            in {"UnitTest", "IntegrationTest", "ContractTest", "TestSuite"}
        ]
        return {
            "repositoryId": repository_id,
            "baseRef": base_ref,
            "source": change_set["source"],
            "changedFiles": changed_files,
            "changedFileCount": len(changed_files),
            "currentGraph": {"graphSpace": "current", "revision": revision},
            "matchedNodes": matched_nodes[:limit],
            "impactedNodes": impacted_nodes,
            "affectedProcesses": affected_processes,
            "affectedTests": affected_tests,
            "unmappedFiles": sorted(changed_set - mapped_files),
            "truncated": (
                len(matched_nodes) > limit
                or len(impacted_by_id) > limit
                or len(all_affected_processes) > limit
            ),
        }

    def hybrid_search(self, body_value: Any) -> dict[str, Any]:
        body = object_value(body_value, "request")
        graph_space, revision, nodes, edges = self._analysis_graph(body)
        query = string_value(body.get("query"), "query")
        limit = body.get("limit", 20)
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 100
        ):
            raise invalid("limit 必须是 1 到 100 的整数")
        entity_types = {
            string_value(value, "entityTypes item")
            for value in list_value(body.get("entityTypes", []), "entityTypes")
        }
        result = hybrid_graph_search(
            nodes,
            edges,
            query,
            limit=limit,
            entity_types=entity_types or None,
        )
        return {
            "repositoryId": body.get("repositoryId"),
            "graphSpace": graph_space,
            "revision": revision,
            **result,
        }

    def graph_communities(self, body_value: Any) -> dict[str, Any]:
        body = object_value(body_value, "request")
        graph_space, revision, nodes, edges = self._analysis_graph(body)
        minimum_size = body.get("minimumSize", 1)
        if (
            isinstance(minimum_size, bool)
            or not isinstance(minimum_size, int)
            or not 1 <= minimum_size <= 100
        ):
            raise invalid("minimumSize 必须是 1 到 100 的整数")
        result = detect_communities(nodes, edges, minimum_size=minimum_size)
        return {
            "repositoryId": body.get("repositoryId"),
            "graphSpace": graph_space,
            "revision": revision,
            **result,
        }

    def graph_processes(self, body_value: Any) -> dict[str, Any]:
        body = object_value(body_value, "request")
        graph_space, revision, nodes, edges = self._analysis_graph(body)
        max_depth = body.get("maxDepth", 6)
        limit = body.get("limit", 100)
        if (
            isinstance(max_depth, bool)
            or not isinstance(max_depth, int)
            or not 1 <= max_depth <= 10
        ):
            raise invalid("maxDepth 必须是 1 到 10 的整数")
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 500
        ):
            raise invalid("limit 必须是 1 到 500 的整数")
        result = detect_processes(
            nodes, edges, max_depth=max_depth, limit=limit
        )
        return {
            "repositoryId": body.get("repositoryId"),
            "graphSpace": graph_space,
            "revision": revision,
            **result,
        }

    def contract_graph(self, body_value: Any) -> dict[str, Any]:
        body = object_value(body_value, "request")
        requested_repositories = {
            string_value(value, "repositoryIds item")
            for value in list_value(body.get("repositoryIds", []), "repositoryIds")
        }
        revisions = self.store.list_graph_revisions("current", 500)
        selected: dict[str, dict[str, Any]] = {}
        for item in revisions:
            metadata = item.get("metadata", {})
            repository_id = str(metadata.get("repositoryId") or "")
            if not repository_id:
                nodes, _ = self.store.read_graph("current", item["revision"])
                repository_node = next(
                    (
                        node
                        for node in nodes
                        if str(node.get("type")) == "Repository"
                    ),
                    None,
                )
                if repository_node:
                    repository_id = str(repository_node["id"]).split(":")[1]
            if (
                not repository_id
                or repository_id in selected
                or (
                    requested_repositories
                    and repository_id not in requested_repositories
                )
            ):
                continue
            nodes, edges = self.store.read_graph("current", item["revision"])
            selected[repository_id] = {
                "repositoryId": repository_id,
                "revision": item["revision"],
                "nodes": nodes,
                "edges": edges,
            }
        missing = sorted(requested_repositories - selected.keys())
        if missing:
            raise not_found(f"以下仓库没有 Current Graph: {', '.join(missing)}")
        return build_contract_graph(list(selected.values()))

    def graph_query(self, body_value: Any) -> dict[str, Any]:
        body = object_value(body_value, "request")
        graph_space = enum_value(
            body.get("graphSpace", "current"), "graphSpace", GRAPH_SPACES
        )
        query_type = enum_value(body.get("queryType"), "queryType", QUERY_TYPES)
        repository_id_value = body.get("repositoryId")
        repository_id = (
            string_value(repository_id_value, "repositoryId")
            if repository_id_value is not None
            else None
        )
        if repository_id is not None:
            self.get_repository(repository_id)
        entity_id_value = body.get("entityId")
        entity_id = (
            string_value(entity_id_value, "entityId")
            if entity_id_value is not None
            else None
        )
        if query_type != "GRAPH_OVERVIEW" and entity_id is None:
            raise invalid(f"{query_type} 必须提供 entityId")
        target_entity_id = body.get("targetEntityId")
        if target_entity_id is not None:
            target_entity_id = string_value(target_entity_id, "targetEntityId")
        depth = body.get("depth", 2)
        limit = body.get("limit", 100)
        if isinstance(depth, bool) or not isinstance(depth, int) or not 0 <= depth <= 6:
            raise invalid("depth 必须是 0 到 6 的整数")
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 500
        ):
            raise invalid("limit 必须是 1 到 500 的整数")

        requested_revision = body.get("revision")
        if (
            repository_id is not None
            and graph_space != "current"
            and requested_revision is None
        ):
            raise invalid(
                "非 Current Graph 使用 repositoryId 时必须显式提供 revision"
            )
        revision = (
            string_value(requested_revision, "revision")
            if requested_revision is not None
            else (
                self._repository_current_revision(repository_id)
                if repository_id is not None and graph_space == "current"
                else self.store.latest_graph_revision(graph_space)
            )
        )
        if revision is None:
            raise not_found(f"图空间 {graph_space} 尚无快照")
        self._validate_repository_graph_scope(
            repository_id, graph_space, revision
        )
        nodes, edges = self.store.read_graph(graph_space, revision)
        nodes_by_id = {node["id"]: node for node in nodes}
        if query_type == "GRAPH_OVERVIEW":
            entity_types = {
                string_value(item, "entityTypes item")
                for item in list_value(body.get("entityTypes", []), "entityTypes")
            }
            relations = {
                string_value(item, "relations item")
                for item in list_value(body.get("relations", []), "relations")
            }
            search_value = body.get("search")
            search = (
                string_value(search_value, "search").lower()
                if search_value is not None
                else None
            )

            def matches(node: dict[str, Any]) -> bool:
                if entity_types and str(node.get("type")) not in entity_types:
                    return False
                if search is None:
                    return True
                searchable = " ".join(
                    str(node.get(key, ""))
                    for key in (
                        "id",
                        "type",
                        "label",
                        "name",
                        "qualifiedName",
                        "path",
                        "key",
                    )
                ).lower()
                return search in searchable

            matching_nodes = [node for node in nodes if matches(node)]
            selected_nodes = matching_nodes[:limit]
            selected_ids = {node["id"] for node in selected_nodes}
            matching_edges = [
                edge
                for edge in edges
                if edge["source"] in selected_ids
                and edge["target"] in selected_ids
                and (not relations or edge["relation"] in relations)
            ]
            edge_limit = min(2000, limit * 4)
            type_counts: dict[str, int] = {}
            relation_counts: dict[str, int] = {}
            for node in nodes:
                node_type = str(node.get("type", "Unknown"))
                type_counts[node_type] = type_counts.get(node_type, 0) + 1
            for edge in edges:
                relation = edge["relation"]
                relation_counts[relation] = relation_counts.get(relation, 0) + 1
            return {
                "repositoryId": repository_id,
                "graphSpace": graph_space,
                "queryType": query_type,
                "revision": revision,
                "startEntityId": None,
                "targetEntityId": None,
                "nodes": selected_nodes,
                "edges": matching_edges[:edge_limit],
                "paths": [],
                "truncated": (
                    len(matching_nodes) > limit or len(matching_edges) > edge_limit
                ),
                "summary": {
                    "totalNodes": len(nodes),
                    "totalEdges": len(edges),
                    "selectedNodes": len(selected_nodes),
                    "selectedEdges": min(len(matching_edges), edge_limit),
                    "entityTypes": [
                        {"name": name, "count": type_counts[name]}
                        for name in sorted(type_counts)
                    ],
                    "relations": [
                        {"name": name, "count": relation_counts[name]}
                        for name in sorted(relation_counts)
                    ],
                },
                "filters": {
                    "entityTypes": sorted(entity_types),
                    "relations": sorted(relations),
                    "search": search,
                },
                "limits": {
                    "nodes": limit,
                    "edges": edge_limit,
                },
            }
        if entity_id is None:
            raise invalid("entityId 不能为空")
        if entity_id not in nodes_by_id:
            raise not_found(
                f"实体 {entity_id} 不存在于 {graph_space}/{revision} 图快照"
            )
        if target_entity_id is not None and target_entity_id not in nodes_by_id:
            raise not_found(
                f"目标实体 {target_entity_id} 不存在于 {graph_space}/{revision} 图快照"
            )

        outgoing: dict[str, list[dict[str, Any]]] = {}
        incoming: dict[str, list[dict[str, Any]]] = {}
        for edge in edges:
            if not _relation_allowed(query_type, edge["relation"]):
                continue
            outgoing.setdefault(edge["source"], []).append(edge)
            incoming.setdefault(edge["target"], []).append(edge)

        directed = query_type in {"CALL_PATH", "IMPACT_PATHS"}
        queue: deque[tuple[str, int, list[str]]] = deque([(entity_id, 0, [entity_id])])
        visited_depth = {entity_id: 0}
        selected_ids = {entity_id}
        selected_edges: dict[tuple[str, str, str], dict[str, Any]] = {}
        paths: list[list[str]] = []
        path_keys: set[tuple[str, ...]] = set()
        truncated = False

        while queue:
            current, current_depth, path = queue.popleft()
            if current_depth >= depth:
                continue
            candidates: list[tuple[dict[str, Any], str]] = [
                (edge, edge["target"]) for edge in outgoing.get(current, [])
            ]
            if not directed:
                candidates.extend(
                    (edge, edge["source"]) for edge in incoming.get(current, [])
                )
            for edge, neighbor in candidates:
                edge_key = (edge["source"], edge["relation"], edge["target"])
                next_path = [*path, neighbor]
                if neighbor not in selected_ids and len(selected_ids) >= limit:
                    truncated = True
                    continue
                selected_ids.add(neighbor)
                selected_edges[edge_key] = edge
                if target_entity_id is not None and neighbor == target_entity_id:
                    path_key = tuple(next_path)
                    if path_key in path_keys:
                        continue
                    path_keys.add(path_key)
                    if len(paths) < limit:
                        paths.append(next_path)
                    else:
                        truncated = True
                next_depth = current_depth + 1
                previous_depth = visited_depth.get(neighbor)
                if previous_depth is None or next_depth < previous_depth:
                    visited_depth[neighbor] = next_depth
                    queue.append((neighbor, next_depth, next_path))

        return {
            "repositoryId": repository_id,
            "graphSpace": graph_space,
            "queryType": query_type,
            "revision": revision,
            "startEntityId": entity_id,
            "targetEntityId": target_entity_id,
            "nodes": [nodes_by_id[item] for item in sorted(selected_ids)],
            "edges": [selected_edges[item] for item in sorted(selected_edges.keys())],
            "paths": paths[:limit],
            "truncated": truncated or len(paths) > limit,
            "limits": {"depth": depth, "nodes": limit, "paths": limit},
        }

    def record_alignment_candidates(
        self,
        body_value: Any,
        idempotency_key: str,
        correlation_id: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        body = object_value(body_value, "request")
        if body.get("status") != "Candidate":
            raise invalid("alignment candidate 写入只允许 status=Candidate")
        run_id = string_value(body.get("runId"), "runId")
        requirement_id = string_value(body.get("requirementId"), "requirementId")
        payload = validate_artifact_payload(
            "CandidateAlignmentDraft", body.get("payload")
        )
        return self._record(
            route="/api/alignments/agent-candidates",
            idempotency_key=idempotency_key,
            request_body=body,
            run_id=run_id,
            requirement_id=requirement_id,
            artifact_type="CandidateAlignmentDraft",
            status="Candidate",
            payload=payload,
            correlation_id=correlation_id,
        )

    def record_change_plan_draft(
        self,
        body_value: Any,
        idempotency_key: str,
        correlation_id: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        body = object_value(body_value, "request")
        if body.get("status") != "Draft":
            raise invalid("change plan 写入只允许 status=Draft")
        run_id = string_value(body.get("runId"), "runId")
        requirement_id = string_value(body.get("requirementId"), "requirementId")
        payload = validate_artifact_payload("ProposedChangeDraft", body.get("payload"))
        return self._record(
            route="/api/change-plans/agent-drafts",
            idempotency_key=idempotency_key,
            request_body=body,
            run_id=run_id,
            requirement_id=requirement_id,
            artifact_type="ProposedChangeDraft",
            status="Draft",
            payload=payload,
            correlation_id=correlation_id,
        )

    def record_agent_artifact(
        self,
        body_value: Any,
        idempotency_key: str,
        correlation_id: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        body = object_value(body_value, "request")
        run_id = string_value(body.get("runId"), "runId")
        artifact_type = enum_value(
            body.get("artifactType"), "artifactType", ARTIFACT_TYPES
        )
        payload = validate_artifact_payload(artifact_type, body.get("payload"))
        requirement_id = body.get("requirementId")
        if requirement_id is not None:
            requirement_id = string_value(requirement_id, "requirementId")
        return self._record(
            route="/api/agent-artifacts",
            idempotency_key=idempotency_key,
            request_body=body,
            run_id=run_id,
            requirement_id=requirement_id,
            artifact_type=artifact_type,
            status="Recorded",
            payload=payload,
            agent_name=body.get("agentName"),
            session_id=body.get("sessionId"),
            correlation_id=correlation_id,
        )

    def _record(
        self,
        *,
        route: str,
        idempotency_key: str,
        request_body: Mapping[str, Any],
        run_id: str,
        requirement_id: str | None,
        artifact_type: str,
        status: str,
        payload: Mapping[str, Any],
        agent_name: str | None = None,
        session_id: str | None = None,
        correlation_id: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        idempotency_key = string_value(idempotency_key, "Idempotency-Key")
        if len(idempotency_key) < 8:
            raise invalid("Idempotency-Key 长度至少为 8")
        if agent_name is not None:
            agent_name = string_value(agent_name, "agentName")
        if session_id is not None:
            session_id = string_value(session_id, "sessionId")
        return self.store.record_artifact(
            route=route,
            idempotency_key=idempotency_key,
            request_body=request_body,
            run_id=run_id,
            requirement_id=requirement_id,
            artifact_type=artifact_type,
            status=status,
            payload=payload,
            agent_name=agent_name,
            session_id=session_id,
            correlation_id=correlation_id,
        )

    def list_artifacts(self, run_id: str) -> dict[str, Any]:
        run_id = string_value(run_id, "runId")
        return {"runId": run_id, "artifacts": self.store.list_artifacts(run_id)}

    def expand_change_plan(self, body_value: Any) -> dict[str, Any]:
        body = object_value(body_value, "request")
        result = self.planning_rules.expand(body.get("difference"), body.get("context"))
        if "changeSet" in body:
            result["changeSet"] = object_value(body["changeSet"], "changeSet")
        return result
