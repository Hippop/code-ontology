from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import tempfile
import uuid
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .errors import PlatformError, conflict

GRAPH_TEXT_SCHEMA_VERSION = "code-ontology-graph-snapshot/v1"


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def content_hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _safe_graph_filename(revision: str) -> str:
    readable = re.sub(r"[^A-Za-z0-9._-]+", "-", revision).strip("-._")
    readable = readable[:80] or "revision"
    digest = hashlib.sha256(revision.encode("utf-8")).hexdigest()[:16]
    return f"{readable}--{digest}.graph.json"


def build_graph_text_snapshot(
    *,
    graph_space: str,
    revision: str,
    nodes: Iterable[Mapping[str, Any]],
    edges: Iterable[Mapping[str, Any]],
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    node_values = sorted(
        (dict(node) for node in nodes),
        key=lambda item: item["id"],
    )
    edge_values = sorted(
        (dict(edge) for edge in edges),
        key=lambda item: (
            item["source"],
            item["relation"],
            item["target"],
        ),
    )
    snapshot = {
        "schemaVersion": GRAPH_TEXT_SCHEMA_VERSION,
        "graphSpace": graph_space,
        "revision": revision,
        "metadata": dict(metadata or {}),
        "summary": {
            "nodeCount": len(node_values),
            "edgeCount": len(edge_values),
        },
        "nodes": node_values,
        "edges": edge_values,
    }
    snapshot["contentHash"] = content_hash(snapshot)
    return snapshot


class SQLiteStore:
    """Small durable store that keeps graph spaces and Agent artifacts separate."""

    def __init__(
        self,
        database: str | Path,
        graph_text_root: str | Path | None = None,
    ) -> None:
        self.database = str(database)
        if self.database != ":memory:":
            database_path = Path(self.database).resolve()
            database_path.parent.mkdir(parents=True, exist_ok=True)
            configured_root = graph_text_root or os.environ.get(
                "CODE_ONTOLOGY_GRAPH_TEXT_ROOT"
            )
            self.graph_text_root = (
                Path(configured_root).resolve()
                if configured_root is not None
                else database_path.parent / f"{database_path.stem}.graphs"
            )
            self.graph_text_root.mkdir(parents=True, exist_ok=True)
        else:
            self.graph_text_root = (
                Path(graph_text_root).resolve() if graph_text_root is not None else None
            )
            if self.graph_text_root is not None:
                self.graph_text_root.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def graph_text_snapshot_path(self, graph_space: str, revision: str) -> Path | None:
        if self.graph_text_root is None:
            return None
        return (
            self.graph_text_root
            / re.sub(r"[^A-Za-z0-9._-]+", "-", graph_space)
            / _safe_graph_filename(revision)
        )

    def graph_text_snapshot_info(
        self, graph_space: str, revision: str
    ) -> dict[str, Any] | None:
        path = self.graph_text_snapshot_path(graph_space, revision)
        if path is None or not path.is_file():
            return None
        document = self._load_graph_text_document(path, graph_space, revision)
        return {
            "format": "application/json",
            "schemaVersion": document["schemaVersion"],
            "relativePath": path.relative_to(self.graph_text_root).as_posix(),
            "contentHash": document["contentHash"],
        }

    def read_graph_text_snapshot(
        self, graph_space: str, revision: str
    ) -> dict[str, Any] | None:
        path = self.graph_text_snapshot_path(graph_space, revision)
        if path is None or not path.is_file():
            return None
        document = self._load_graph_text_document(path, graph_space, revision)
        expected_hash = document.get("contentHash")
        value_without_hash = {
            key: value for key, value in document.items() if key != "contentHash"
        }
        if expected_hash != content_hash(value_without_hash):
            raise PlatformError(
                409,
                "GRAPH_TEXT_INTEGRITY_ERROR",
                f"图文本快照内容 Hash 校验失败: {graph_space}/{revision}",
            )
        return document

    @staticmethod
    def _load_graph_text_document(
        path: Path,
        graph_space: str,
        revision: str,
    ) -> dict[str, Any]:
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise PlatformError(
                409,
                "GRAPH_TEXT_INTEGRITY_ERROR",
                f"无法读取图文本快照: {graph_space}/{revision}",
            ) from error
        if not isinstance(document, dict):
            raise PlatformError(
                409,
                "GRAPH_TEXT_INTEGRITY_ERROR",
                f"图文本快照根节点不是 JSON Object: {graph_space}/{revision}",
            )
        return document

    def _write_graph_text_snapshot(
        self,
        document: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        graph_space = str(document["graphSpace"])
        revision = str(document["revision"])
        path = self.graph_text_snapshot_path(graph_space, revision)
        if path is None:
            return None
        path.parent.mkdir(parents=True, exist_ok=True)
        serialized = (
            json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary.write(serialized)
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_path = Path(temporary.name)
            os.replace(temporary_path, path)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()
        return {
            "format": "application/json",
            "schemaVersion": document["schemaVersion"],
            "relativePath": path.relative_to(self.graph_text_root).as_posix(),
            "contentHash": document["contentHash"],
        }

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS requirement_contexts (
                    requirement_id TEXT NOT NULL,
                    design_revision_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    context_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (requirement_id, design_revision_id, stage)
                );

                CREATE TABLE IF NOT EXISTS repositories (
                    repository_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    path TEXT NOT NULL UNIQUE,
                    default_branch TEXT,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS repository_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    repository_id TEXT NOT NULL,
                    revision TEXT NOT NULL,
                    commit_id TEXT,
                    branch TEXT,
                    dirty INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE (repository_id, revision),
                    FOREIGN KEY (repository_id)
                        REFERENCES repositories(repository_id)
                );

                CREATE TABLE IF NOT EXISTS extraction_runs (
                    run_id TEXT PRIMARY KEY,
                    repository_id TEXT NOT NULL,
                    snapshot_id TEXT NOT NULL,
                    revision TEXT NOT NULL,
                    status TEXT NOT NULL,
                    extractor_version TEXT NOT NULL,
                    coverage_json TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (repository_id)
                        REFERENCES repositories(repository_id),
                    FOREIGN KEY (snapshot_id)
                        REFERENCES repository_snapshots(snapshot_id)
                );

                CREATE TABLE IF NOT EXISTS design_documents (
                    document_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    owner TEXT,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS design_revisions (
                    revision_id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    revision_number TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    content TEXT NOT NULL,
                    parsed_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE (document_id, content_hash),
                    FOREIGN KEY (document_id)
                        REFERENCES design_documents(document_id)
                );

                CREATE TABLE IF NOT EXISTS requirements (
                    requirement_id TEXT PRIMARY KEY,
                    design_revision_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    ir_json TEXT NOT NULL,
                    desired_graph_revision TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (design_revision_id)
                        REFERENCES design_revisions(revision_id)
                );

                CREATE TABLE IF NOT EXISTS workflow_runs (
                    workflow_id TEXT PRIMARY KEY,
                    requirement_id TEXT,
                    repository_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    pending_gate TEXT,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (repository_id)
                        REFERENCES repositories(repository_id)
                );

                CREATE TABLE IF NOT EXISTS review_decisions (
                    review_id TEXT PRIMARY KEY,
                    resource_type TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    gate TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    rationale TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS alignment_runs (
                    run_id TEXT PRIMARY KEY,
                    requirement_id TEXT NOT NULL,
                    current_revision TEXT NOT NULL,
                    desired_revision TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS alignment_candidates (
                    candidate_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    desired_entity_id TEXT NOT NULL,
                    current_entity_id TEXT,
                    review_status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (run_id)
                        REFERENCES alignment_runs(run_id)
                );

                CREATE TABLE IF NOT EXISTS change_plans (
                    plan_id TEXT PRIMARY KEY,
                    requirement_id TEXT NOT NULL,
                    alignment_run_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (alignment_run_id)
                        REFERENCES alignment_runs(run_id)
                );

                CREATE TABLE IF NOT EXISTS agent_runs (
                    run_id TEXT PRIMARY KEY,
                    plan_id TEXT NOT NULL,
                    requirement_id TEXT NOT NULL,
                    repository_id TEXT NOT NULL,
                    base_commit TEXT NOT NULL,
                    status TEXT NOT NULL,
                    session_id TEXT,
                    worktree_path TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (plan_id) REFERENCES change_plans(plan_id),
                    FOREIGN KEY (repository_id)
                        REFERENCES repositories(repository_id)
                );

                CREATE TABLE IF NOT EXISTS reconciliation_contexts (
                    reconciliation_run_id TEXT PRIMARY KEY,
                    context_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS reconciliation_runs (
                    run_id TEXT PRIMARY KEY,
                    agent_run_id TEXT NOT NULL,
                    plan_id TEXT NOT NULL,
                    requirement_id TEXT NOT NULL,
                    actual_revision TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (agent_run_id) REFERENCES agent_runs(run_id),
                    FOREIGN KEY (plan_id) REFERENCES change_plans(plan_id)
                );

                CREATE TABLE IF NOT EXISTS impact_runs (
                    run_id TEXT PRIMARY KEY,
                    reconciliation_run_id TEXT NOT NULL,
                    requirement_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (reconciliation_run_id)
                        REFERENCES reconciliation_runs(run_id)
                );

                CREATE TABLE IF NOT EXISTS runtime_evidence (
                    evidence_id TEXT PRIMARY KEY,
                    requirement_id TEXT NOT NULL,
                    impact_run_id TEXT NOT NULL,
                    environment TEXT NOT NULL,
                    deployment_version TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (impact_run_id) REFERENCES impact_runs(run_id)
                );

                CREATE TABLE IF NOT EXISTS graph_snapshots (
                    graph_space TEXT NOT NULL,
                    revision TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (graph_space, revision)
                );

                CREATE TABLE IF NOT EXISTS graph_metadata (
                    graph_space TEXT NOT NULL,
                    revision TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    PRIMARY KEY (graph_space, revision),
                    FOREIGN KEY (graph_space, revision)
                        REFERENCES graph_snapshots(graph_space, revision)
                        ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS graph_entities (
                    graph_space TEXT NOT NULL,
                    revision TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (graph_space, revision, entity_id),
                    FOREIGN KEY (graph_space, revision)
                        REFERENCES graph_snapshots(graph_space, revision)
                        ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS graph_edges (
                    graph_space TEXT NOT NULL,
                    revision TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (
                        graph_space, revision, source_id, relation, target_id
                    ),
                    FOREIGN KEY (graph_space, revision)
                        REFERENCES graph_snapshots(graph_space, revision)
                        ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS graph_edges_source_idx
                    ON graph_edges(graph_space, revision, source_id);
                CREATE INDEX IF NOT EXISTS graph_edges_target_idx
                    ON graph_edges(graph_space, revision, target_id);

                CREATE TABLE IF NOT EXISTS agent_artifacts (
                    artifact_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    requirement_id TEXT,
                    artifact_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    agent_name TEXT,
                    session_id TEXT,
                    payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS agent_artifacts_run_idx
                    ON agent_artifacts(run_id, created_at);

                CREATE TABLE IF NOT EXISTS idempotency_records (
                    route TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    request_hash TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (route, idempotency_key)
                );

                CREATE TABLE IF NOT EXISTS audit_events (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    tenant_id TEXT NOT NULL DEFAULT 'default',
                    correlation_id TEXT,
                    run_id TEXT,
                    requirement_id TEXT,
                    payload_json TEXT NOT NULL,
                    previous_event_hash TEXT,
                    event_hash TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS repository_snapshots_repo_idx
                    ON repository_snapshots(repository_id, created_at);
                CREATE INDEX IF NOT EXISTS extraction_runs_repo_idx
                    ON extraction_runs(repository_id, created_at);
                CREATE INDEX IF NOT EXISTS design_revisions_document_idx
                    ON design_revisions(document_id, created_at);
                CREATE INDEX IF NOT EXISTS review_decisions_resource_idx
                    ON review_decisions(resource_type, resource_id, created_at);
                CREATE INDEX IF NOT EXISTS workflow_runs_requirement_idx
                    ON workflow_runs(requirement_id, created_at);
                CREATE INDEX IF NOT EXISTS workflow_runs_repository_idx
                    ON workflow_runs(repository_id, created_at);
                CREATE INDEX IF NOT EXISTS alignment_runs_requirement_idx
                    ON alignment_runs(requirement_id, created_at);
                CREATE INDEX IF NOT EXISTS alignment_candidates_run_idx
                    ON alignment_candidates(run_id, desired_entity_id);
                CREATE INDEX IF NOT EXISTS change_plans_requirement_idx
                    ON change_plans(requirement_id, created_at);
                CREATE INDEX IF NOT EXISTS agent_runs_plan_idx
                    ON agent_runs(plan_id, created_at);
                CREATE INDEX IF NOT EXISTS reconciliation_agent_idx
                    ON reconciliation_runs(agent_run_id, created_at);
                CREATE INDEX IF NOT EXISTS impact_reconciliation_idx
                    ON impact_runs(reconciliation_run_id, created_at);
                CREATE INDEX IF NOT EXISTS runtime_evidence_requirement_idx
                    ON runtime_evidence(requirement_id, created_at);
                """
            )
            self._ensure_column(connection, "audit_events", "actor", "TEXT")
            self._ensure_column(connection, "audit_events", "repository_id", "TEXT")
            self._ensure_column(connection, "audit_events", "revision", "TEXT")
            self._ensure_column(
                connection,
                "audit_events",
                "tenant_id",
                "TEXT NOT NULL DEFAULT 'default'",
            )
            self._ensure_column(
                connection, "audit_events", "previous_event_hash", "TEXT"
            )
            self._ensure_column(connection, "audit_events", "event_hash", "TEXT")

    @staticmethod
    def _ensure_column(
        connection: sqlite3.Connection,
        table: str,
        column: str,
        declaration: str,
    ) -> None:
        existing = {
            row["name"]
            for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in existing:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")

    def put_repository(self, repository: Mapping[str, Any]) -> dict[str, Any]:
        now = utc_now()
        value = dict(repository)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO repositories(
                    repository_id, name, path, default_branch,
                    metadata_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(repository_id)
                DO UPDATE SET
                    name = excluded.name,
                    path = excluded.path,
                    default_branch = excluded.default_branch,
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at
                """,
                (
                    value["repositoryId"],
                    value["name"],
                    value["path"],
                    value.get("defaultBranch"),
                    canonical_json(value.get("metadata", {})),
                    now,
                    now,
                ),
            )
        return self.get_repository(value["repositoryId"]) or value

    def get_repository(self, repository_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT repository_id, name, path, default_branch,
                       metadata_json, created_at, updated_at
                FROM repositories
                WHERE repository_id = ?
                """,
                (repository_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "repositoryId": row["repository_id"],
            "name": row["name"],
            "path": row["path"],
            "defaultBranch": row["default_branch"],
            "metadata": json.loads(row["metadata_json"]),
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    def put_repository_snapshot(self, snapshot: Mapping[str, Any]) -> dict[str, Any]:
        now = utc_now()
        value = dict(snapshot)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO repository_snapshots(
                    snapshot_id, repository_id, revision, commit_id,
                    branch, dirty, status, payload_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(repository_id, revision)
                DO UPDATE SET
                    commit_id = excluded.commit_id,
                    branch = excluded.branch,
                    dirty = excluded.dirty,
                    status = excluded.status,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    value["snapshotId"],
                    value["repositoryId"],
                    value["revision"],
                    value.get("commit"),
                    value.get("branch"),
                    int(bool(value.get("dirty"))),
                    value["status"],
                    canonical_json(value),
                    now,
                    now,
                ),
            )
            row = connection.execute(
                """
                SELECT payload_json
                FROM repository_snapshots
                WHERE repository_id = ? AND revision = ?
                """,
                (value["repositoryId"], value["revision"]),
            ).fetchone()
        return json.loads(row["payload_json"])

    def get_repository_snapshot(self, snapshot_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json
                FROM repository_snapshots
                WHERE snapshot_id = ?
                """,
                (snapshot_id,),
            ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def update_snapshot_status(self, snapshot_id: str, status: str) -> None:
        now = utc_now()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json
                FROM repository_snapshots
                WHERE snapshot_id = ?
                """,
                (snapshot_id,),
            ).fetchone()
            if not row:
                return
            payload = json.loads(row["payload_json"])
            payload["status"] = status
            connection.execute(
                """
                UPDATE repository_snapshots
                SET status = ?, payload_json = ?, updated_at = ?
                WHERE snapshot_id = ?
                """,
                (status, canonical_json(payload), now, snapshot_id),
            )

    def record_extraction_run(self, run: Mapping[str, Any]) -> dict[str, Any]:
        value = dict(run)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO extraction_runs(
                    run_id, repository_id, snapshot_id, revision, status,
                    extractor_version, coverage_json, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id)
                DO UPDATE SET
                    status = excluded.status,
                    coverage_json = excluded.coverage_json,
                    payload_json = excluded.payload_json,
                    created_at = excluded.created_at
                """,
                (
                    value["runId"],
                    value["repositoryId"],
                    value["snapshotId"],
                    value["revision"],
                    value["status"],
                    value["extractorVersion"],
                    canonical_json(value["coverage"]),
                    canonical_json(value),
                    value.get("createdAt", utc_now()),
                ),
            )
        return value

    def list_repository_graph_revisions(
        self, repository_id: str
    ) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT r.payload_json, g.metadata_json
                FROM extraction_runs r
                LEFT JOIN graph_metadata g
                  ON g.graph_space = 'current' AND g.revision = r.revision
                WHERE r.repository_id = ?
                ORDER BY r.created_at DESC
                """,
                (repository_id,),
            ).fetchall()
        result = []
        for row in rows:
            run = json.loads(row["payload_json"])
            run["graph"] = (
                json.loads(row["metadata_json"]) if row["metadata_json"] else None
            )
            result.append(run)
        return result

    def put_design_document(self, document: Mapping[str, Any]) -> dict[str, Any]:
        value = dict(document)
        now = utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO design_documents(
                    document_id, title, owner, metadata_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(document_id)
                DO UPDATE SET
                    title = excluded.title,
                    owner = excluded.owner,
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at
                """,
                (
                    value["documentId"],
                    value["title"],
                    value.get("owner"),
                    canonical_json(value.get("metadata", {})),
                    now,
                    now,
                ),
            )
        return self.get_design_document(value["documentId"]) or value

    def get_design_document(self, document_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT document_id, title, owner, metadata_json,
                       created_at, updated_at
                FROM design_documents
                WHERE document_id = ?
                """,
                (document_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "documentId": row["document_id"],
            "title": row["title"],
            "owner": row["owner"],
            "metadata": json.loads(row["metadata_json"]),
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    def put_design_revision(self, revision: Mapping[str, Any]) -> dict[str, Any]:
        value = dict(revision)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO design_revisions(
                    revision_id, document_id, revision_number, content_hash,
                    content, parsed_json, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(document_id, content_hash)
                DO UPDATE SET
                    parsed_json = excluded.parsed_json,
                    status = excluded.status
                """,
                (
                    value["revisionId"],
                    value["documentId"],
                    value["revisionNumber"],
                    value["contentHash"],
                    value["content"],
                    canonical_json(value["parsed"]),
                    value["status"],
                    value.get("createdAt", utc_now()),
                ),
            )
            row = connection.execute(
                """
                SELECT revision_id
                FROM design_revisions
                WHERE document_id = ? AND content_hash = ?
                """,
                (value["documentId"], value["contentHash"]),
            ).fetchone()
        return self.get_design_revision(row["revision_id"]) or value

    def get_design_revision(self, revision_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT revision_id, document_id, revision_number, content_hash,
                       content, parsed_json, status, created_at
                FROM design_revisions
                WHERE revision_id = ?
                """,
                (revision_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "revisionId": row["revision_id"],
            "documentId": row["document_id"],
            "revisionNumber": row["revision_number"],
            "contentHash": row["content_hash"],
            "content": row["content"],
            "parsed": json.loads(row["parsed_json"]),
            "status": row["status"],
            "createdAt": row["created_at"],
        }

    def put_requirement_ir(
        self,
        requirement_id: str,
        design_revision_id: str,
        status: str,
        ir: Mapping[str, Any],
        desired_graph_revision: str | None,
    ) -> dict[str, Any]:
        now = utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO requirements(
                    requirement_id, design_revision_id, status, ir_json,
                    desired_graph_revision, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(requirement_id)
                DO UPDATE SET
                    design_revision_id = excluded.design_revision_id,
                    status = excluded.status,
                    ir_json = excluded.ir_json,
                    desired_graph_revision = excluded.desired_graph_revision,
                    updated_at = excluded.updated_at
                """,
                (
                    requirement_id,
                    design_revision_id,
                    status,
                    canonical_json(ir),
                    desired_graph_revision,
                    now,
                    now,
                ),
            )
        return self.get_requirement_ir(requirement_id) or dict(ir)

    def get_requirement_ir(self, requirement_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT requirement_id, design_revision_id, status, ir_json,
                       desired_graph_revision, created_at, updated_at
                FROM requirements
                WHERE requirement_id = ?
                """,
                (requirement_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "requirementId": row["requirement_id"],
            "designRevisionId": row["design_revision_id"],
            "status": row["status"],
            "ir": json.loads(row["ir_json"]),
            "desiredGraphRevision": row["desired_graph_revision"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    def update_requirement_status(
        self, requirement_id: str, status: str
    ) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT ir_json FROM requirements WHERE requirement_id = ?",
                (requirement_id,),
            ).fetchone()
            if not row:
                return None
            ir = json.loads(row["ir_json"])
            ir["status"] = status
            connection.execute(
                """
                UPDATE requirements
                SET status = ?, ir_json = ?, updated_at = ?
                WHERE requirement_id = ?
                """,
                (status, canonical_json(ir), utc_now(), requirement_id),
            )
        return self.get_requirement_ir(requirement_id)

    def put_workflow_run(self, run: Mapping[str, Any]) -> dict[str, Any]:
        value = dict(run)
        now = utc_now()
        value.setdefault("createdAt", now)
        value["updatedAt"] = now
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO workflow_runs(
                    workflow_id, requirement_id, repository_id, status,
                    stage, pending_gate, payload_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(workflow_id)
                DO UPDATE SET
                    requirement_id = excluded.requirement_id,
                    status = excluded.status,
                    stage = excluded.stage,
                    pending_gate = excluded.pending_gate,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    value["workflowId"],
                    value.get("requirementId"),
                    value["repositoryId"],
                    value["status"],
                    value["stage"],
                    value.get("pendingGate"),
                    canonical_json(value),
                    value["createdAt"],
                    now,
                ),
            )
        return value

    def get_workflow_run(self, workflow_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM workflow_runs WHERE workflow_id = ?",
                (workflow_id,),
            ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def list_workflow_runs(
        self,
        *,
        requirement_id: str | None = None,
        repository_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses = []
        parameters: list[Any] = []
        if requirement_id is not None:
            clauses.append("requirement_id = ?")
            parameters.append(requirement_id)
        if repository_id is not None:
            clauses.append("repository_id = ?")
            parameters.append(repository_id)
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        parameters.append(limit)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT payload_json
                FROM workflow_runs
                {where}
                ORDER BY created_at DESC, workflow_id DESC
                LIMIT ?
                """,
                parameters,
            ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def record_review_decision(self, review: Mapping[str, Any]) -> dict[str, Any]:
        value = dict(review)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO review_decisions(
                    review_id, resource_type, resource_id, gate,
                    decision, actor, rationale, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    value["reviewId"],
                    value["resourceType"],
                    value["resourceId"],
                    value["gate"],
                    value["decision"],
                    value["actor"],
                    value["rationale"],
                    canonical_json(value),
                    value.get("createdAt", utc_now()),
                ),
            )
        return value

    def put_alignment_run(self, alignment_run: Mapping[str, Any]) -> dict[str, Any]:
        value = dict(alignment_run)
        now = utc_now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO alignment_runs(
                    run_id, requirement_id, current_revision, desired_revision,
                    status, payload_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id)
                DO UPDATE SET
                    status = excluded.status,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    value["runId"],
                    value["requirementId"],
                    value["currentRevision"],
                    value["desiredRevision"],
                    value["status"],
                    canonical_json(value),
                    now,
                    now,
                ),
            )
            connection.execute(
                "DELETE FROM alignment_candidates WHERE run_id = ?",
                (value["runId"],),
            )
            for item in value["alignments"]:
                for candidate in item["candidates"]:
                    connection.execute(
                        """
                        INSERT INTO alignment_candidates(
                            candidate_id, run_id, desired_entity_id,
                            current_entity_id, review_status,
                            payload_json, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            candidate["candidateId"],
                            value["runId"],
                            candidate["desiredEntityId"],
                            candidate.get("currentEntityId"),
                            candidate["reviewStatus"],
                            canonical_json(candidate),
                            now,
                        ),
                    )
        return value

    def get_alignment_run(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM alignment_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def find_alignment_candidate(
        self, candidate_id: str
    ) -> tuple[str, dict[str, Any]] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT run_id, payload_json
                FROM alignment_candidates
                WHERE candidate_id = ?
                """,
                (candidate_id,),
            ).fetchone()
        return (row["run_id"], json.loads(row["payload_json"])) if row else None

    def put_change_plan(self, plan: Mapping[str, Any]) -> dict[str, Any]:
        value = dict(plan)
        now = utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO change_plans(
                    plan_id, requirement_id, alignment_run_id,
                    status, payload_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(plan_id)
                DO UPDATE SET
                    status = excluded.status,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    value["planId"],
                    value["changeSet"]["requirementId"],
                    value["changeSet"]["alignmentRunId"],
                    value["status"],
                    canonical_json(value),
                    now,
                    now,
                ),
            )
        return value

    def get_change_plan(self, plan_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM change_plans WHERE plan_id = ?",
                (plan_id,),
            ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def put_agent_run(self, run: Mapping[str, Any]) -> dict[str, Any]:
        value = dict(run)
        now = utc_now()
        value.setdefault("createdAt", now)
        value["updatedAt"] = now
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO agent_runs(
                    run_id, plan_id, requirement_id, repository_id,
                    base_commit, status, session_id, worktree_path,
                    payload_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id)
                DO UPDATE SET
                    status = excluded.status,
                    session_id = excluded.session_id,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    value["runId"],
                    value["changePlanId"],
                    value["requirementId"],
                    value["repositoryId"],
                    value["baseCommit"],
                    value["status"],
                    value.get("sessionId"),
                    value["worktreePath"],
                    canonical_json(value),
                    value["createdAt"],
                    now,
                ),
            )
        return value

    def get_agent_run(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM agent_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def put_reconciliation_run(self, run: Mapping[str, Any]) -> dict[str, Any]:
        value = dict(run)
        now = utc_now()
        value.setdefault("createdAt", now)
        value["updatedAt"] = now
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO reconciliation_runs(
                    run_id, agent_run_id, plan_id, requirement_id,
                    actual_revision, status, payload_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id)
                DO UPDATE SET
                    status = excluded.status,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    value["runId"],
                    value["agentRunId"],
                    value["changePlanId"],
                    value["requirementId"],
                    value["actualRevision"],
                    value["status"],
                    canonical_json(value),
                    value["createdAt"],
                    now,
                ),
            )
        return value

    def get_reconciliation_run(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM reconciliation_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def put_impact_run(self, run: Mapping[str, Any]) -> dict[str, Any]:
        value = dict(run)
        now = utc_now()
        value.setdefault("createdAt", now)
        value["updatedAt"] = now
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO impact_runs(
                    run_id, reconciliation_run_id, requirement_id,
                    status, payload_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id)
                DO UPDATE SET
                    status = excluded.status,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    value["runId"],
                    value["reconciliationRunId"],
                    value["requirementId"],
                    value["status"],
                    canonical_json(value),
                    value["createdAt"],
                    now,
                ),
            )
        return value

    def get_impact_run(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM impact_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def put_runtime_evidence(self, evidence: Mapping[str, Any]) -> dict[str, Any]:
        value = dict(evidence)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO runtime_evidence(
                    evidence_id, requirement_id, impact_run_id,
                    environment, deployment_version, status,
                    payload_hash, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    value["evidenceId"],
                    value["requirementId"],
                    value["impactRunId"],
                    value["environment"],
                    value["deploymentVersion"],
                    value["status"],
                    value["payloadHash"],
                    canonical_json(value),
                    value["createdAt"],
                ),
            )
        return value

    def list_runtime_evidence(self, requirement_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload_json
                FROM runtime_evidence
                WHERE requirement_id = ?
                ORDER BY created_at, evidence_id
                """,
                (requirement_id,),
            ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def put_requirement_context(
        self,
        requirement_id: str,
        design_revision_id: str,
        stage: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        context = {
            **dict(payload),
            "requirementId": requirement_id,
            "designRevisionId": design_revision_id,
            "stage": stage,
        }
        context.pop("contextHash", None)
        digest = content_hash(context)
        context["contextHash"] = digest
        now = utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO requirement_contexts (
                    requirement_id, design_revision_id, stage,
                    context_hash, payload_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(requirement_id, design_revision_id, stage)
                DO UPDATE SET
                    context_hash = excluded.context_hash,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    requirement_id,
                    design_revision_id,
                    stage,
                    digest,
                    canonical_json(context),
                    now,
                ),
            )
        return context

    def get_requirement_context(
        self, requirement_id: str, design_revision_id: str, stage: str
    ) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json
                FROM requirement_contexts
                WHERE requirement_id = ?
                  AND design_revision_id = ?
                  AND stage = ?
                """,
                (requirement_id, design_revision_id, stage),
            ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def put_reconciliation_context(
        self, reconciliation_run_id: str, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        context = {**dict(payload), "reconciliationRunId": reconciliation_run_id}
        context.pop("contextHash", None)
        digest = content_hash(context)
        context["contextHash"] = digest
        now = utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO reconciliation_contexts (
                    reconciliation_run_id, context_hash, payload_json, updated_at
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(reconciliation_run_id)
                DO UPDATE SET
                    context_hash = excluded.context_hash,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (reconciliation_run_id, digest, canonical_json(context), now),
            )
        return context

    def get_reconciliation_context(
        self, reconciliation_run_id: str
    ) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json
                FROM reconciliation_contexts
                WHERE reconciliation_run_id = ?
                """,
                (reconciliation_run_id,),
            ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def replace_graph(
        self,
        graph_space: str,
        revision: str,
        nodes: Iterable[Mapping[str, Any]],
        edges: Iterable[Mapping[str, Any]],
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        node_values = [dict(node) for node in nodes]
        edge_values = [dict(edge) for edge in edges]
        snapshot_metadata = dict(metadata or {})
        snapshot_metadata.pop("textSnapshot", None)
        text_document = build_graph_text_snapshot(
            graph_space=graph_space,
            revision=revision,
            nodes=node_values,
            edges=edge_values,
            metadata=snapshot_metadata,
        )
        text_snapshot = self._write_graph_text_snapshot(text_document)
        stored_metadata = dict(snapshot_metadata)
        if text_snapshot is not None:
            stored_metadata["textSnapshot"] = text_snapshot
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO graph_snapshots(graph_space, revision, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(graph_space, revision)
                DO UPDATE SET created_at = excluded.created_at
                """,
                (graph_space, revision, utc_now()),
            )
            connection.execute(
                "DELETE FROM graph_edges WHERE graph_space = ? AND revision = ?",
                (graph_space, revision),
            )
            connection.execute(
                "DELETE FROM graph_entities WHERE graph_space = ? AND revision = ?",
                (graph_space, revision),
            )
            connection.execute(
                "DELETE FROM graph_metadata WHERE graph_space = ? AND revision = ?",
                (graph_space, revision),
            )
            if stored_metadata:
                connection.execute(
                    """
                    INSERT INTO graph_metadata(
                        graph_space, revision, metadata_json
                    ) VALUES (?, ?, ?)
                    """,
                    (graph_space, revision, canonical_json(stored_metadata)),
                )
            for node in node_values:
                connection.execute(
                    """
                    INSERT INTO graph_entities(
                        graph_space, revision, entity_id, payload_json
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        graph_space,
                        revision,
                        node["id"],
                        canonical_json(node),
                    ),
                )
            for edge in edge_values:
                connection.execute(
                    """
                    INSERT INTO graph_edges(
                        graph_space, revision, source_id,
                        relation, target_id, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        graph_space,
                        revision,
                        edge["source"],
                        edge["relation"],
                        edge["target"],
                        canonical_json(edge),
                    ),
                )
        return text_snapshot

    def latest_graph_revision(self, graph_space: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT revision
                FROM graph_snapshots
                WHERE graph_space = ?
                ORDER BY created_at DESC, revision DESC
                LIMIT 1
                """,
                (graph_space,),
            ).fetchone()
        return row["revision"] if row else None

    def list_graph_revisions(
        self, graph_space: str | None = None, limit: int = 500
    ) -> list[dict[str, Any]]:
        where = "WHERE snapshots.graph_space = ?" if graph_space is not None else ""
        parameters: tuple[Any, ...] = (
            (graph_space, limit) if graph_space is not None else (limit,)
        )
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT snapshots.graph_space, snapshots.revision,
                       snapshots.created_at, metadata.metadata_json,
                       (
                           SELECT COUNT(*)
                           FROM graph_entities entities
                           WHERE entities.graph_space = snapshots.graph_space
                             AND entities.revision = snapshots.revision
                       ) AS node_count,
                       (
                           SELECT COUNT(*)
                           FROM graph_edges edges
                           WHERE edges.graph_space = snapshots.graph_space
                             AND edges.revision = snapshots.revision
                       ) AS edge_count
                FROM graph_snapshots snapshots
                LEFT JOIN graph_metadata metadata
                  ON metadata.graph_space = snapshots.graph_space
                 AND metadata.revision = snapshots.revision
                {where}
                ORDER BY snapshots.created_at DESC,
                         snapshots.graph_space,
                         snapshots.revision DESC
                LIMIT ?
                """,
                parameters,
            ).fetchall()
        return [
            {
                "graphSpace": row["graph_space"],
                "revision": row["revision"],
                "createdAt": row["created_at"],
                "nodeCount": row["node_count"],
                "edgeCount": row["edge_count"],
                "metadata": (
                    json.loads(row["metadata_json"])
                    if row["metadata_json"] is not None
                    else {}
                ),
            }
            for row in rows
        ]

    def read_graph(
        self, graph_space: str, revision: str
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        with self._connect() as connection:
            node_rows = connection.execute(
                """
                SELECT payload_json
                FROM graph_entities
                WHERE graph_space = ? AND revision = ?
                ORDER BY entity_id
                """,
                (graph_space, revision),
            ).fetchall()
            edge_rows = connection.execute(
                """
                SELECT payload_json
                FROM graph_edges
                WHERE graph_space = ? AND revision = ?
                ORDER BY source_id, relation, target_id
                """,
                (graph_space, revision),
            ).fetchall()
        return (
            [json.loads(row["payload_json"]) for row in node_rows],
            [json.loads(row["payload_json"]) for row in edge_rows],
        )

    def record_artifact(
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
        request_digest = content_hash(request_body)
        now = utc_now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT request_hash, response_json
                FROM idempotency_records
                WHERE route = ? AND idempotency_key = ?
                """,
                (route, idempotency_key),
            ).fetchone()
            if existing:
                if existing["request_hash"] != request_digest:
                    raise conflict(
                        "同一 Idempotency-Key 已用于不同请求，拒绝覆盖原 Artifact"
                    )
                return json.loads(existing["response_json"]), True

            artifact_id = f"artifact-{uuid.uuid4()}"
            payload_digest = content_hash(payload)
            response = {
                "artifactId": artifact_id,
                "runId": run_id,
                "requirementId": requirement_id,
                "artifactType": artifact_type,
                "status": status,
                "payloadHash": payload_digest,
                "createdAt": now,
            }
            connection.execute(
                """
                INSERT INTO agent_artifacts(
                    artifact_id, run_id, requirement_id, artifact_type,
                    status, agent_name, session_id, payload_json,
                    payload_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact_id,
                    run_id,
                    requirement_id,
                    artifact_type,
                    status,
                    agent_name,
                    session_id,
                    canonical_json(payload),
                    payload_digest,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO idempotency_records(
                    route, idempotency_key, request_hash,
                    response_json, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    route,
                    idempotency_key,
                    request_digest,
                    canonical_json(response),
                    now,
                ),
            )
            previous_row = connection.execute(
                """
                SELECT event_hash
                FROM audit_events
                WHERE tenant_id = 'default'
                ORDER BY rowid DESC
                LIMIT 1
                """
            ).fetchone()
            previous_hash = previous_row["event_hash"] if previous_row else None
            event_id = f"event-{uuid.uuid4()}"
            event_hash = content_hash(
                {
                    "eventId": event_id,
                    "eventType": "AgentArtifactRecorded",
                    "tenantId": "default",
                    "correlationId": correlation_id,
                    "runId": run_id,
                    "requirementId": requirement_id,
                    "repositoryId": None,
                    "revision": None,
                    "actor": None,
                    "payload": response,
                    "previousEventHash": previous_hash,
                    "timestamp": now,
                }
            )
            connection.execute(
                """
                INSERT INTO audit_events(
                    event_id, event_type, tenant_id, correlation_id, run_id,
                    requirement_id, payload_json, previous_event_hash,
                    event_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    "AgentArtifactRecorded",
                    "default",
                    correlation_id,
                    run_id,
                    requirement_id,
                    canonical_json(response),
                    previous_hash,
                    event_hash,
                    now,
                ),
            )
        return response, False

    def list_artifacts(self, run_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT artifact_id, run_id, requirement_id, artifact_type,
                       status, agent_name, session_id, payload_json,
                       payload_hash, created_at
                FROM agent_artifacts
                WHERE run_id = ?
                ORDER BY created_at, artifact_id
                """,
                (run_id,),
            ).fetchall()
        return [
            {
                "artifactId": row["artifact_id"],
                "runId": row["run_id"],
                "requirementId": row["requirement_id"],
                "artifactType": row["artifact_type"],
                "status": row["status"],
                "agentName": row["agent_name"],
                "sessionId": row["session_id"],
                "payload": json.loads(row["payload_json"]),
                "payloadHash": row["payload_hash"],
                "createdAt": row["created_at"],
            }
            for row in rows
        ]

    def append_audit_event(
        self,
        event_type: str,
        payload: Mapping[str, Any],
        *,
        correlation_id: str | None = None,
        run_id: str | None = None,
        requirement_id: str | None = None,
        repository_id: str | None = None,
        revision: str | None = None,
        actor: str | None = None,
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        now = utc_now()
        event = {
            "eventId": f"event-{uuid.uuid4()}",
            "eventType": event_type,
            "tenantId": tenant_id,
            "correlationId": correlation_id,
            "runId": run_id,
            "requirementId": requirement_id,
            "repositoryId": repository_id,
            "revision": revision,
            "actor": actor,
            "payload": dict(payload),
            "timestamp": now,
        }
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            previous = connection.execute(
                """
                SELECT event_hash
                FROM audit_events
                WHERE tenant_id = ?
                ORDER BY rowid DESC
                LIMIT 1
                """,
                (tenant_id,),
            ).fetchone()
            event["previousEventHash"] = previous["event_hash"] if previous else None
            event["eventHash"] = content_hash(event)
            connection.execute(
                """
                INSERT INTO audit_events(
                    event_id, event_type, tenant_id, correlation_id, run_id,
                    requirement_id, payload_json, created_at,
                    actor, repository_id, revision,
                    previous_event_hash, event_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event["eventId"],
                    event_type,
                    tenant_id,
                    correlation_id,
                    run_id,
                    requirement_id,
                    canonical_json(event["payload"]),
                    event["timestamp"],
                    actor,
                    repository_id,
                    revision,
                    event["previousEventHash"],
                    event["eventHash"],
                ),
            )
        return event

    def list_audit_events(
        self,
        *,
        tenant_id: str = "default",
        requirement_id: str | None = None,
        run_id: str | None = None,
        correlation_id: str | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        clauses = ["tenant_id = ?"]
        parameters: list[Any] = [tenant_id]
        for column, value in (
            ("requirement_id", requirement_id),
            ("run_id", run_id),
            ("correlation_id", correlation_id),
        ):
            if value is not None:
                clauses.append(f"{column} = ?")
                parameters.append(value)
        parameters.append(limit)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT rowid AS sequence_no, event_id, event_type, tenant_id,
                       correlation_id, run_id, requirement_id, payload_json,
                       created_at, actor, repository_id, revision,
                       previous_event_hash, event_hash
                FROM audit_events
                WHERE {" AND ".join(clauses)}
                ORDER BY rowid
                LIMIT ?
                """,
                parameters,
            ).fetchall()
        return [
            {
                "sequence": row["sequence_no"],
                "eventId": row["event_id"],
                "eventType": row["event_type"],
                "tenantId": row["tenant_id"],
                "correlationId": row["correlation_id"],
                "runId": row["run_id"],
                "requirementId": row["requirement_id"],
                "repositoryId": row["repository_id"],
                "revision": row["revision"],
                "actor": row["actor"],
                "payload": json.loads(row["payload_json"]),
                "previousEventHash": row["previous_event_hash"],
                "eventHash": row["event_hash"],
                "timestamp": row["created_at"],
            }
            for row in rows
        ]

    def verify_audit_chain(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        previous_hash = None
        failures = []
        for event in events:
            material = {
                key: event.get(key)
                for key in (
                    "eventId",
                    "eventType",
                    "tenantId",
                    "correlationId",
                    "runId",
                    "requirementId",
                    "repositoryId",
                    "revision",
                    "actor",
                    "payload",
                    "timestamp",
                    "previousEventHash",
                )
            }
            calculated = content_hash(material)
            if event.get("previousEventHash") != previous_hash:
                failures.append(
                    {
                        "eventId": event["eventId"],
                        "reason": "PreviousHashMismatch",
                    }
                )
            if event.get("eventHash") != calculated:
                failures.append(
                    {
                        "eventId": event["eventId"],
                        "reason": "EventHashMismatch",
                    }
                )
            previous_hash = event.get("eventHash")
        return {
            "status": "Verified" if not failures else "Invalid",
            "eventCount": len(events),
            "headHash": previous_hash,
            "failures": failures,
        }

    def replay_resources(self, requirement_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            requirement_row = connection.execute(
                """
                SELECT ir_json
                FROM requirements
                WHERE requirement_id = ?
                """,
                (requirement_id,),
            ).fetchone()
            workflows = connection.execute(
                """
                SELECT payload_json
                FROM workflow_runs
                WHERE requirement_id = ?
                ORDER BY created_at
                """,
                (requirement_id,),
            ).fetchall()
            alignments = connection.execute(
                """
                SELECT payload_json
                FROM alignment_runs
                WHERE requirement_id = ?
                ORDER BY created_at
                """,
                (requirement_id,),
            ).fetchall()
            plans = connection.execute(
                """
                SELECT payload_json
                FROM change_plans
                WHERE requirement_id = ?
                ORDER BY created_at
                """,
                (requirement_id,),
            ).fetchall()
            agent_runs = connection.execute(
                """
                SELECT payload_json
                FROM agent_runs
                WHERE requirement_id = ?
                ORDER BY created_at
                """,
                (requirement_id,),
            ).fetchall()
            reconciliations = connection.execute(
                """
                SELECT payload_json
                FROM reconciliation_runs
                WHERE requirement_id = ?
                ORDER BY created_at
                """,
                (requirement_id,),
            ).fetchall()
            impacts = connection.execute(
                """
                SELECT payload_json
                FROM impact_runs
                WHERE requirement_id = ?
                ORDER BY created_at
                """,
                (requirement_id,),
            ).fetchall()
            runtime_evidence = connection.execute(
                """
                SELECT payload_json
                FROM runtime_evidence
                WHERE requirement_id = ?
                ORDER BY created_at
                """,
                (requirement_id,),
            ).fetchall()
            artifacts = connection.execute(
                """
                SELECT artifact_id, run_id, artifact_type, status,
                       payload_hash, created_at
                FROM agent_artifacts
                WHERE requirement_id = ?
                ORDER BY created_at, artifact_id
                """,
                (requirement_id,),
            ).fetchall()
            resource_ids = [
                *[json.loads(row["payload_json"])["runId"] for row in alignments],
                *[json.loads(row["payload_json"])["planId"] for row in plans],
                requirement_id,
            ]
            reviews = []
            if resource_ids:
                placeholders = ",".join("?" for _ in resource_ids)
                reviews = connection.execute(
                    f"""
                    SELECT payload_json
                    FROM review_decisions
                    WHERE resource_id IN ({placeholders})
                       OR resource_id IN (
                           SELECT c.candidate_id
                           FROM alignment_candidates c
                           JOIN alignment_runs r ON r.run_id = c.run_id
                           WHERE r.requirement_id = ?
                       )
                    ORDER BY created_at
                    """,
                    [*resource_ids, requirement_id],
                ).fetchall()

        def payloads(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
            return [json.loads(row["payload_json"]) for row in rows]

        return {
            "requirementIR": (
                json.loads(requirement_row["ir_json"]) if requirement_row else None
            ),
            "workflowRuns": payloads(workflows),
            "alignmentRuns": payloads(alignments),
            "changePlans": payloads(plans),
            "agentRuns": payloads(agent_runs),
            "reconciliationRuns": payloads(reconciliations),
            "impactRuns": payloads(impacts),
            "runtimeEvidence": payloads(runtime_evidence),
            "reviews": payloads(reviews),
            "artifacts": [
                {
                    "artifactId": row["artifact_id"],
                    "runId": row["run_id"],
                    "artifactType": row["artifact_type"],
                    "status": row["status"],
                    "payloadHash": row["payload_hash"],
                    "createdAt": row["created_at"],
                }
                for row in artifacts
            ],
        }
