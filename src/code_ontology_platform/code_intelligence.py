from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import sqlite3
import subprocess
import tempfile
import threading
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from contextlib import closing
from pathlib import Path, PurePosixPath
from typing import Any

from .errors import PlatformError, invalid
from .repository_scan import inspect_repository
from .store import SQLiteStore, content_hash, utc_now

CODEGRAPH_PROVIDER = "codegraph"
CODEGRAPH_ADAPTER_VERSION = "codegraph-sidecar/v1"
_SUPPORTED_SUFFIXES = frozenset(
    {
        ".app",
        ".astro",
        ".c",
        ".cbl",
        ".cc",
        ".cfc",
        ".cfm",
        ".cfs",
        ".cob",
        ".cobol",
        ".cpp",
        ".cs",
        ".cshtml",
        ".cts",
        ".cu",
        ".cuh",
        ".cxx",
        ".cpy",
        ".dart",
        ".dfm",
        ".dpk",
        ".dpr",
        ".erl",
        ".escript",
        ".ets",
        ".fmx",
        ".go",
        ".h",
        ".hpp",
        ".hrl",
        ".hxx",
        ".inc",
        ".install",
        ".java",
        ".js",
        ".jsx",
        ".kt",
        ".kts",
        ".liquid",
        ".lpr",
        ".lua",
        ".luau",
        ".m",
        ".metal",
        ".mjs",
        ".mm",
        ".module",
        ".mts",
        ".nix",
        ".pas",
        ".php",
        ".properties",
        ".py",
        ".pyw",
        ".r",
        ".rb",
        ".razor",
        ".rs",
        ".sc",
        ".scala",
        ".sol",
        ".svelte",
        ".swift",
        ".tf",
        ".tfvars",
        ".theme",
        ".ts",
        ".tsx",
        ".twig",
        ".tofu",
        ".vb",
        ".vue",
        ".xml",
        ".xsjs",
        ".xsjslib",
        ".yaml",
        ".yml",
    }
)
_IGNORED_PARTS = frozenset(
    {
        ".codegraph",
        ".git",
        ".gradle",
        ".idea",
        ".mvn",
        "build",
        "dist",
        "node_modules",
        "out",
        "target",
        "vendor",
    }
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_fingerprint(manifest: Mapping[str, str]) -> str:
    return content_hash({"files": sorted(manifest.items())})


def _project_files(repository: Path) -> dict[str, str]:
    supported_suffixes = set(_SUPPORTED_SUFFIXES)
    configuration = repository / "codegraph.json"
    if configuration.is_file():
        try:
            document = json.loads(configuration.read_text(encoding="utf-8"))
            extensions = document.get("extensions", {})
            if isinstance(extensions, Mapping):
                supported_suffixes.update(
                    str(extension).lower()
                    for extension in extensions
                    if str(extension).startswith(".")
                )
        except (OSError, UnicodeError, json.JSONDecodeError):
            pass
    files: dict[str, str] = {}
    for path in sorted(repository.rglob("*")):
        if (
            not path.is_file()
            or (
                path.suffix.lower() not in supported_suffixes
                and not path.name.lower().endswith(".app.src")
            )
            or any(
                part in _IGNORED_PARTS
                for part in path.relative_to(repository).parts
            )
        ):
            continue
        try:
            files[path.relative_to(repository).as_posix()] = _sha256_file(path)
        except OSError:
            continue
    return files


def _json_from_output(output: str) -> dict[str, Any]:
    value = output.strip()
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        starts = [index for index, character in enumerate(value) if character == "{"]
        for index in reversed(starts):
            try:
                parsed = json.loads(value[index:])
                break
            except json.JSONDecodeError:
                continue
        else:
            raise PlatformError(
                502,
                "CODEGRAPH_INVALID_RESPONSE",
                "CodeGraph 未返回有效 JSON",
                {"output": value[-2000:]},
            )
    if not isinstance(parsed, dict):
        raise PlatformError(
            502, "CODEGRAPH_INVALID_RESPONSE", "CodeGraph JSON 根节点必须是 Object"
        )
    return parsed


def _safe_relative_paths(paths: Sequence[str]) -> list[str]:
    normalized: list[str] = []
    for raw_path in paths:
        path = raw_path.replace("\\", "/").removeprefix("./")
        parsed = PurePosixPath(path)
        if (
            not path
            or parsed.is_absolute()
            or ".." in parsed.parts
            or "\x00" in path
        ):
            raise invalid("changedFiles 只能包含安全的仓库相对路径")
        normalized.append(parsed.as_posix())
    return sorted(set(normalized))


class CodeGraphSidecar:
    """Read-only query adapter around CodeGraph's repository-local SQLite index."""

    def __init__(
        self,
        store: SQLiteStore,
        command: str | Sequence[str] | None = None,
        *,
        timeout_seconds: int = 120,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        configured = command or os.environ.get(
            "CODE_ONTOLOGY_CODEGRAPH_COMMAND", "codegraph"
        )
        self.command = (
            shlex.split(configured) if isinstance(configured, str) else list(configured)
        )
        if not self.command:
            raise ValueError("CodeGraph command cannot be empty")
        self.store = store
        self.timeout_seconds = timeout_seconds
        self.runner = runner
        self._lock_guard = threading.Lock()
        self._repository_locks: dict[str, threading.RLock] = {}

    def _repository_lock(self, repository: Path) -> threading.RLock:
        key = str(repository.resolve())
        with self._lock_guard:
            return self._repository_locks.setdefault(key, threading.RLock())

    def _run(
        self,
        repository: Path | None,
        *arguments: str,
        timeout_seconds: int | None = None,
    ) -> subprocess.CompletedProcess[str]:
        try:
            return self.runner(
                [*self.command, *arguments],
                cwd=str(repository) if repository is not None else None,
                check=True,
                capture_output=True,
                text=True,
                timeout=timeout_seconds or self.timeout_seconds,
            )
        except FileNotFoundError as error:
            raise PlatformError(
                503,
                "CODEGRAPH_UNAVAILABLE",
                f"CodeGraph 命令不可用: {self.command[0]}",
            ) from error
        except subprocess.TimeoutExpired as error:
            raise PlatformError(
                504, "CODEGRAPH_TIMEOUT", "CodeGraph 操作超时"
            ) from error
        except subprocess.CalledProcessError as error:
            raise PlatformError(
                502,
                "CODEGRAPH_FAILED",
                "CodeGraph 操作失败",
                {
                    "exitCode": error.returncode,
                    "stderr": (error.stderr or "")[-4000:],
                    "stdout": (error.stdout or "")[-4000:],
                },
            ) from error

    def available(self) -> bool:
        executable = self.command[0]
        return bool(
            Path(executable).is_file()
            if any(separator in executable for separator in ("/", "\\"))
            else shutil.which(executable)
        )

    def version(self) -> str | None:
        try:
            return self._run(None, "version", timeout_seconds=15).stdout.strip()
        except PlatformError:
            return None

    @staticmethod
    def _index_path(repository: Path) -> Path:
        return repository / ".codegraph" / "codegraph.db"

    @staticmethod
    def _read_index(repository: Path) -> tuple[dict[str, str], dict[str, str]]:
        database = CodeGraphSidecar._index_path(repository)
        if not database.is_file():
            return {}, {}
        try:
            with closing(
                sqlite3.connect(
                    f"{database.resolve().as_uri()}?mode=ro&immutable=1",
                    uri=True,
                )
            ) as connection:
                connection.row_factory = sqlite3.Row
                files = {
                    str(row["path"]): str(row["content_hash"])
                    for row in connection.execute(
                        "SELECT path, content_hash FROM files ORDER BY path"
                    )
                }
                metadata = {
                    str(row["key"]): str(row["value"])
                    for row in connection.execute(
                        "SELECT key, value FROM project_metadata ORDER BY key"
                    )
                }
            return files, metadata
        except sqlite3.Error as error:
            raise PlatformError(
                409,
                "CODEGRAPH_INDEX_INVALID",
                "CodeGraph 索引无法读取",
                {"path": str(database), "reason": str(error)},
            ) from error

    def index(self, repository_id: str, repository_path: str | Path) -> dict[str, Any]:
        repository = Path(repository_path).resolve()
        with self._repository_lock(repository):
            return self._index_unlocked(repository_id, repository)

    def _index_unlocked(
        self, repository_id: str, repository: Path
    ) -> dict[str, Any]:
        identity = inspect_repository(repository, repository_id)
        database = self._index_path(repository)
        command = "sync" if database.is_file() else "init"
        completed = self._run(repository, command, str(repository))
        indexed_manifest, metadata = self._read_index(repository)
        current_manifest = _project_files(repository)
        configuration_path = repository / "codegraph.json"
        configuration_hash = (
            _sha256_file(configuration_path) if configuration_path.is_file() else None
        )
        changed = sorted(
            path
            for path in indexed_manifest.keys() & current_manifest.keys()
            if indexed_manifest[path] != current_manifest[path]
        )
        deleted = sorted(indexed_manifest.keys() - current_manifest.keys())
        unindexed = sorted(current_manifest.keys() - indexed_manifest.keys())
        fingerprint = _manifest_fingerprint(indexed_manifest)
        state = {
            "provider": CODEGRAPH_PROVIDER,
            "adapterVersion": CODEGRAPH_ADAPTER_VERSION,
            "providerVersion": self.version() or metadata.get("indexed_with_version"),
            "repositoryId": repository_id,
            "repositoryPath": str(repository),
            "revision": identity["revision"],
            "indexPath": str(database),
            "status": (
                "Stale" if changed or deleted or unindexed else "Fresh"
            ),
            "fingerprint": fingerprint,
            "fileCount": len(indexed_manifest),
            "currentFileCount": len(current_manifest),
            "configurationHash": configuration_hash,
            "changedFiles": changed,
            "deletedFiles": deleted,
            "unindexedFiles": unindexed,
            "indexMetadata": metadata,
            "command": command,
            "updatedAt": utc_now(),
            "readOnlyQueries": True,
            "provenance": {
                "provider": CODEGRAPH_PROVIDER,
                "indexFingerprint": fingerprint,
                "repositoryRevision": identity["revision"],
            },
        }
        self.store.put_code_intelligence_index(state)
        snapshot = self.graph_snapshot(
            repository_id, repository, allow_stale=True
        )
        text_snapshot = self._write_text_snapshot(snapshot)
        if text_snapshot is not None:
            state["textSnapshot"] = text_snapshot
            self.store.put_code_intelligence_index(state)
        return {**state, "output": completed.stdout.strip()[-4000:]}

    def _write_text_snapshot(
        self, snapshot: Mapping[str, Any]
    ) -> dict[str, Any] | None:
        root = self.store.graph_text_root
        if root is None:
            return None
        repository_key = hashlib.sha256(
            str(snapshot["repositoryId"]).encode("utf-8")
        ).hexdigest()[:16]
        revision_key = hashlib.sha256(
            str(snapshot["revision"]).encode("utf-8")
        ).hexdigest()[:20]
        path = root / "codegraph" / repository_key / f"{revision_key}.graph.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        serialized = (
            json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )
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
        try:
            os.replace(temporary_path, path)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()
        return {
            "format": "application/json",
            "schemaVersion": snapshot["schemaVersion"],
            "relativePath": path.relative_to(root).as_posix(),
            "contentHash": snapshot["contentHash"],
        }

    def status(
        self, repository_id: str, repository_path: str | Path
    ) -> dict[str, Any]:
        repository = Path(repository_path).resolve()
        with self._repository_lock(repository):
            return self._status_unlocked(repository_id, repository)

    def _status_unlocked(
        self, repository_id: str, repository: Path
    ) -> dict[str, Any]:
        database = self._index_path(repository)
        record = self.store.latest_code_intelligence_index(
            CODEGRAPH_PROVIDER, repository_id
        )
        if not database.is_file():
            return {
                "provider": CODEGRAPH_PROVIDER,
                "adapterVersion": CODEGRAPH_ADAPTER_VERSION,
                "repositoryId": repository_id,
                "repositoryPath": str(repository),
                "status": "Missing",
                "indexPath": str(database),
                "recordedIndex": record,
                "readOnlyQueries": True,
            }
        indexed_manifest, metadata = self._read_index(repository)
        current_manifest = _project_files(repository)
        changed = sorted(
            path
            for path in indexed_manifest.keys() & current_manifest.keys()
            if indexed_manifest[path] != current_manifest[path]
        )
        deleted = sorted(indexed_manifest.keys() - current_manifest.keys())
        unindexed = sorted(current_manifest.keys() - indexed_manifest.keys())
        identity = inspect_repository(repository, repository_id)
        recorded_revision = record.get("revision") if record else None
        configuration_path = repository / "codegraph.json"
        configuration_hash = (
            _sha256_file(configuration_path) if configuration_path.is_file() else None
        )
        configuration_changed = bool(
            record is not None
            and record.get("configurationHash") != configuration_hash
        )
        manifest_stale = bool(changed or deleted or unindexed)
        stale = bool(
            manifest_stale
            or configuration_changed
            or (
                recorded_revision is not None
                and recorded_revision != identity["revision"]
            )
        )
        effective_indexed_revision = recorded_revision or (
            None if manifest_stale else identity["revision"]
        )
        fingerprint = _manifest_fingerprint(indexed_manifest)
        return {
            "provider": CODEGRAPH_PROVIDER,
            "adapterVersion": CODEGRAPH_ADAPTER_VERSION,
            "providerVersion": metadata.get("indexed_with_version")
            or (record or {}).get("providerVersion"),
            "repositoryId": repository_id,
            "repositoryPath": str(repository),
            "revision": identity["revision"],
            "indexedRevision": effective_indexed_revision,
            "status": "Stale" if stale else "Fresh",
            "indexPath": str(database),
            "fingerprint": fingerprint,
            "fileCount": len(indexed_manifest),
            "currentFileCount": len(current_manifest),
            "configurationHash": configuration_hash,
            "configurationChanged": configuration_changed,
            "changedFiles": changed,
            "deletedFiles": deleted,
            "unindexedFiles": unindexed,
            "indexMetadata": metadata,
            "recordedIndex": record,
            "readOnlyQueries": True,
            "provenance": {
                "provider": CODEGRAPH_PROVIDER,
                "indexFingerprint": fingerprint,
                "repositoryRevision": effective_indexed_revision,
            },
        }

    def _require_fresh(
        self,
        repository_id: str,
        repository: Path,
        *,
        allow_stale: bool,
    ) -> dict[str, Any]:
        status = self.status(repository_id, repository)
        if status["status"] == "Missing":
            raise PlatformError(
                409,
                "CODE_INDEX_MISSING",
                "CodeGraph 索引不存在，请先执行索引",
                status,
            )
        if status["status"] == "Stale" and not allow_stale:
            raise PlatformError(
                409,
                "CODE_INDEX_STALE",
                "CodeGraph 索引已陈旧，拒绝返回可能错误的查询结果",
                status,
            )
        return status

    def explore(
        self,
        repository_id: str,
        repository_path: str | Path,
        query: str,
        *,
        allow_stale: bool = False,
    ) -> dict[str, Any]:
        repository = Path(repository_path).resolve()
        with self._repository_lock(repository):
            status = self._require_fresh(
                repository_id, repository, allow_stale=allow_stale
            )
            completed = self._run(
                repository, "explore", "--path", str(repository), "--", query
            )
            return {
                "provider": CODEGRAPH_PROVIDER,
                "operation": "explore",
                "query": query,
                "result": completed.stdout.strip(),
                "index": status,
                "readOnly": True,
            }

    def impact(
        self,
        repository_id: str,
        repository_path: str | Path,
        symbol: str,
        *,
        depth: int = 3,
        allow_stale: bool = False,
    ) -> dict[str, Any]:
        repository = Path(repository_path).resolve()
        with self._repository_lock(repository):
            status = self._require_fresh(
                repository_id, repository, allow_stale=allow_stale
            )
            completed = self._run(
                repository,
                "impact",
                "--path",
                str(repository),
                "--depth",
                str(depth),
                "--json",
                "--",
                symbol,
            )
            return {
                "provider": CODEGRAPH_PROVIDER,
                "operation": "impact",
                "result": _json_from_output(completed.stdout),
                "index": status,
                "readOnly": True,
            }

    def affected_tests(
        self,
        repository_id: str,
        repository_path: str | Path,
        changed_files: Sequence[str],
        *,
        depth: int = 3,
        allow_stale: bool = False,
    ) -> dict[str, Any]:
        if not changed_files:
            raise invalid("changedFiles 不能为空")
        safe_files = _safe_relative_paths(changed_files)
        repository = Path(repository_path).resolve()
        with self._repository_lock(repository):
            status = self._require_fresh(
                repository_id, repository, allow_stale=allow_stale
            )
            completed = self._run(
                repository,
                "affected",
                "--path",
                str(repository),
                "--depth",
                str(depth),
                "--json",
                "--",
                *safe_files,
            )
            return {
                "provider": CODEGRAPH_PROVIDER,
                "operation": "affected-tests",
                "result": _json_from_output(completed.stdout),
                "index": status,
                "readOnly": True,
            }

    def graph_snapshot(
        self,
        repository_id: str,
        repository_path: str | Path,
        *,
        allow_stale: bool = False,
    ) -> dict[str, Any]:
        repository = Path(repository_path).resolve()
        with self._repository_lock(repository):
            return self._graph_snapshot_unlocked(
                repository_id, repository, allow_stale=allow_stale
            )

    def _graph_snapshot_unlocked(
        self,
        repository_id: str,
        repository: Path,
        *,
        allow_stale: bool,
    ) -> dict[str, Any]:
        status = self._require_fresh(
            repository_id, repository, allow_stale=allow_stale
        )
        database = self._index_path(repository)
        try:
            with closing(
                sqlite3.connect(
                    f"{database.resolve().as_uri()}?mode=ro&immutable=1",
                    uri=True,
                )
            ) as connection:
                connection.row_factory = sqlite3.Row
                nodes = [
                    dict(row) for row in connection.execute("SELECT * FROM nodes")
                ]
                edges = [
                    dict(row) for row in connection.execute("SELECT * FROM edges")
                ]
        except sqlite3.Error as error:
            raise PlatformError(
                409,
                "CODEGRAPH_INDEX_INVALID",
                "CodeGraph 图索引无法读取",
                {"reason": str(error)},
            ) from error
        for node in nodes:
            for field in ("is_exported", "is_async", "is_static", "is_abstract"):
                node[field] = bool(node.get(field))
        snapshot = {
            "schemaVersion": "codegraph-snapshot/v1",
            "provider": CODEGRAPH_PROVIDER,
            "providerVersion": status.get("providerVersion"),
            "repositoryId": repository_id,
            "revision": status.get("indexedRevision") or status.get("revision"),
            "indexFingerprint": status["fingerprint"],
            "summary": {"nodeCount": len(nodes), "edgeCount": len(edges)},
            "nodes": sorted(nodes, key=lambda item: str(item["id"])),
            "edges": sorted(
                edges,
                key=lambda item: (
                    str(item["source"]),
                    str(item["kind"]),
                    str(item["target"]),
                ),
            ),
        }
        snapshot["contentHash"] = content_hash(snapshot)
        return snapshot


_TYPE_KIND_MAP: dict[str, frozenset[str]] = {
    "SourceFile": frozenset({"file"}),
    "Class": frozenset({"class", "struct", "enum"}),
    "Interface": frozenset({"interface", "trait"}),
    "Method": frozenset({"method", "function"}),
    "Constructor": frozenset({"method", "function"}),
    "UnitTest": frozenset({"method", "function"}),
    "Field": frozenset({"field", "property"}),
    "ConfigurationKey": frozenset({"constant"}),
    "APIOperation": frozenset({"route"}),
}
_RELATION_KIND_MAP: dict[str, frozenset[str]] = {
    "code:callsDirectly": frozenset({"calls"}),
    "code:declares": frozenset({"contains"}),
    "code:contains": frozenset({"contains"}),
    "code:exposes": frozenset({"references", "contains"}),
    "code:implementsOperation": frozenset({"references", "contains"}),
}


def _expected_name(node: Mapping[str, Any]) -> str:
    return str(
        node.get("methodName")
        or node.get("fieldName")
        or node.get("schemaName")
        or node.get("label")
        or ""
    )


def _expected_source(node: Mapping[str, Any]) -> str:
    evidence = node.get("evidence")
    if isinstance(evidence, Mapping):
        return str(evidence.get("source") or "")
    return str(node.get("relativePath") or "")


def compare_codegraph_to_baseline(
    codegraph: Mapping[str, Any],
    baseline: Mapping[str, Any],
    *,
    difference_limit: int = 200,
) -> dict[str, Any]:
    side_nodes = [dict(item) for item in codegraph.get("nodes", [])]
    side_edges = [dict(item) for item in codegraph.get("edges", [])]
    expected_nodes = [dict(item) for item in baseline.get("nodes", [])]
    expected_edges = [dict(item) for item in baseline.get("edges", [])]
    side_by_id = {str(node["id"]): node for node in side_nodes}
    matched: dict[str, str] = {}
    used_side_ids: set[str] = set()

    for expected in expected_nodes:
        kinds = _TYPE_KIND_MAP.get(str(expected.get("type")))
        if not kinds:
            continue
        source = _expected_source(expected)
        name = _expected_name(expected)
        candidates = []
        for side in side_nodes:
            side_id = str(side["id"])
            if side_id in used_side_ids or str(side.get("kind")) not in kinds:
                continue
            path_match = not source or str(side.get("file_path") or "") == source
            names = {
                str(side.get("name") or ""),
                str(side.get("qualified_name") or "").rsplit(".", 1)[-1],
            }
            name_match = name in names
            if expected.get("type") == "SourceFile":
                name_match = (
                    str(side.get("file_path") or "") == source
                    or str(side.get("name") or "") == name
                )
            elif expected.get("type") == "APIOperation":
                path_match = True
            if path_match and name_match:
                candidates.append(side)
        if candidates:
            chosen = sorted(candidates, key=lambda item: str(item["id"]))[0]
            matched[str(expected["id"])] = str(chosen["id"])
            used_side_ids.add(str(chosen["id"]))

    type_rows: list[dict[str, Any]] = []
    expected_type_counts = Counter(str(node.get("type")) for node in expected_nodes)
    for entity_type in sorted(expected_type_counts):
        type_ids = {
            str(node["id"])
            for node in expected_nodes
            if str(node.get("type")) == entity_type
        }
        matched_count = len(type_ids & matched.keys())
        type_rows.append(
            {
                "entityType": entity_type,
                "expected": len(type_ids),
                "matched": matched_count,
                "coverage": round(matched_count / len(type_ids), 6),
                "sidecarKinds": sorted(_TYPE_KIND_MAP.get(entity_type, [])),
            }
        )

    side_edge_keys = {
        (str(edge["source"]), str(edge["kind"]), str(edge["target"]))
        for edge in side_edges
    }
    matched_edge_ids: set[tuple[str, str, str]] = set()
    relation_counts = Counter(str(edge["relation"]) for edge in expected_edges)
    matched_relation_counts: Counter[str] = Counter()
    for edge in expected_edges:
        source = matched.get(str(edge["source"]))
        target = matched.get(str(edge["target"]))
        relation = str(edge["relation"])
        if source is None or target is None:
            continue
        direct_match = any(
            (source, kind, target) in side_edge_keys
            for kind in _RELATION_KIND_MAP.get(relation, frozenset())
        )
        reverse_match = relation in {
            "code:implementsOperation",
            "code:exposes",
        } and any(
            (target, kind, source) in side_edge_keys
            for kind in _RELATION_KIND_MAP.get(relation, frozenset())
        )
        if direct_match or reverse_match:
            matched_edge_ids.add(
                (str(edge["source"]), relation, str(edge["target"]))
            )
            matched_relation_counts[relation] += 1

    missing_expected = [
        {
            "id": str(node["id"]),
            "type": node.get("type"),
            "label": node.get("label"),
            "reason": (
                "unsupported-by-codegraph-model"
                if str(node.get("type")) not in _TYPE_KIND_MAP
                else "not-matched"
            ),
        }
        for node in expected_nodes
        if str(node["id"]) not in matched
    ]
    unmatched_sidecar = [
        {
            "id": str(node["id"]),
            "kind": node.get("kind"),
            "name": node.get("name"),
            "filePath": node.get("file_path"),
        }
        for node in side_nodes
        if str(node["id"]) not in used_side_ids
    ]
    relation_rows = [
        {
            "relation": relation,
            "expected": count,
            "matched": matched_relation_counts[relation],
            "coverage": round(matched_relation_counts[relation] / count, 6),
            "sidecarKinds": sorted(_RELATION_KIND_MAP.get(relation, [])),
        }
        for relation, count in sorted(relation_counts.items())
    ]
    expected_count = len(expected_nodes)
    expected_edge_count = len(expected_edges)
    result = {
        "schemaVersion": "codegraph-baseline-comparison/v1",
        "status": "Compared",
        "provider": CODEGRAPH_PROVIDER,
        "providerVersion": codegraph.get("providerVersion"),
        "repositoryId": baseline.get("repositoryId")
        or codegraph.get("repositoryId"),
        "expected": {
            "nodeCount": expected_count,
            "edgeCount": expected_edge_count,
            "contentHash": baseline.get("contentHash"),
        },
        "actual": {
            "nodeCount": len(side_nodes),
            "edgeCount": len(side_edges),
            "indexFingerprint": codegraph.get("indexFingerprint"),
        },
        "delta": {
            "nodeCount": len(side_nodes) - expected_count,
            "edgeCount": len(side_edges) - expected_edge_count,
        },
        "semanticCoverage": {
            "matchedExpectedNodes": len(matched),
            "expectedNodeCoverage": round(
                len(matched) / expected_count if expected_count else 1.0, 6
            ),
            "matchedSidecarNodes": len(used_side_ids),
            "sidecarNodeCoverage": round(
                len(used_side_ids) / len(side_nodes) if side_nodes else 1.0, 6
            ),
            "matchedExpectedEdges": len(matched_edge_ids),
            "expectedEdgeCoverage": round(
                len(matched_edge_ids) / expected_edge_count
                if expected_edge_count
                else 1.0,
                6,
            ),
        },
        "typeCoverage": type_rows,
        "relationCoverage": relation_rows,
        "differences": {
            "missingExpectedNodes": missing_expected[:difference_limit],
            "unmatchedSidecarNodes": unmatched_sidecar[:difference_limit],
            "truncated": len(missing_expected) > difference_limit
            or len(unmatched_sidecar) > difference_limit,
        },
        "mapping": {
            "expectedToSidecar": dict(sorted(matched.items())),
            "modelNote": (
                "CodeGraph 聚焦源码符号/调用；平台基线还包含参数、构建依赖、"
                "配置、API Schema、表列、事件等业务与契约实体。"
            ),
        },
    }
    result["contentHash"] = content_hash(result)
    return result
