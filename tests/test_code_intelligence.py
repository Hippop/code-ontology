from __future__ import annotations

import hashlib
import io
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from code_ontology_platform.code_intelligence import CodeGraphSidecar
from code_ontology_platform.errors import PlatformError
from code_ontology_platform.graph_analysis import (
    build_contract_graph,
    detect_communities,
    detect_processes,
    hybrid_graph_search,
)
from code_ontology_platform.http_api import handler_for
from code_ontology_platform.mcp_gateway import (
    MCP_PROTOCOL_VERSION,
    ReadOnlyMcpGateway,
    serve_stdio,
)
from code_ontology_platform.service import PlatformService
from code_ontology_platform.store import SQLiteStore

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = ROOT / "examples" / "expected-graphs"


class CodeGraphIndexFreshnessTest(unittest.TestCase):
    def test_index_freshness_detects_content_drift_and_blocks_queries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory) / "repository"
            repository.mkdir()
            source = repository / "Example.java"
            source.write_text("class Example {}\n", encoding="utf-8")
            index_root = repository / ".codegraph"
            index_root.mkdir()
            database = index_root / "codegraph.db"
            connection = sqlite3.connect(database)
            connection.executescript(
                """
                CREATE TABLE files(
                    path TEXT PRIMARY KEY,
                    content_hash TEXT NOT NULL,
                    language TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    modified_at INTEGER NOT NULL,
                    indexed_at INTEGER NOT NULL,
                    node_count INTEGER DEFAULT 0,
                    errors TEXT
                );
                CREATE TABLE project_metadata(
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE TABLE nodes(
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    name TEXT NOT NULL
                );
                CREATE TABLE edges(
                    source TEXT NOT NULL,
                    target TEXT NOT NULL,
                    kind TEXT NOT NULL
                );
                """
            )
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            connection.execute(
                """
                INSERT INTO files(
                    path, content_hash, language, size, modified_at, indexed_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                ("Example.java", digest, "java", source.stat().st_size, 1, 1),
            )
            connection.execute(
                "INSERT INTO project_metadata VALUES (?, ?, ?)",
                ("indexed_with_version", "1.5.0", 1),
            )
            connection.execute(
                "INSERT INTO nodes VALUES (?, ?, ?)",
                ("class:Example", "class", "Example"),
            )
            connection.commit()
            connection.close()

            store = SQLiteStore(Path(directory) / "platform.db")
            sidecar = CodeGraphSidecar(
                store,
                command=["unused-codegraph"],
                runner=lambda arguments, **_: subprocess.CompletedProcess(
                    arguments,
                    0,
                    stdout=("1.5.0\n" if arguments[-1] == "version" else "synced\n"),
                    stderr="",
                ),
            )
            indexed = sidecar.index("repo-example", repository)
            text_snapshot = indexed["textSnapshot"]
            self.assertTrue(
                (store.graph_text_root / text_snapshot["relativePath"]).is_file()
            )
            fresh = sidecar.status("repo-example", repository)
            self.assertEqual("Fresh", fresh["status"])
            self.assertEqual("1.5.0", fresh["providerVersion"])
            with self.assertRaises(PlatformError) as unsafe:
                sidecar.affected_tests(
                    "repo-example", repository, ["../outside.java"]
                )
            self.assertEqual("VALIDATION_ERROR", unsafe.exception.code)

            source.write_text("class Example { int value; }\n", encoding="utf-8")
            stale = sidecar.status("repo-example", repository)
            self.assertEqual("Stale", stale["status"])
            self.assertEqual(["Example.java"], stale["changedFiles"])
            with self.assertRaises(PlatformError) as raised:
                sidecar.impact("repo-example", repository, "Example")
            self.assertEqual("CODE_INDEX_STALE", raised.exception.code)

    def test_real_codegraph_snapshot_is_auditable_against_72_95_baseline(self) -> None:
        snapshot = json.loads(
            (EXPECTED / "java-spring-sample.codegraph-1.5.0.graph.json").read_text(
                encoding="utf-8"
            )
        )
        comparison = json.loads(
            (
                EXPECTED
                / "java-spring-sample.codegraph-1.5.0.comparison.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual({"nodeCount": 66, "edgeCount": 70}, snapshot["summary"])
        self.assertEqual(
            {"nodeCount": 72, "edgeCount": 95},
            {
                "nodeCount": comparison["expected"]["nodeCount"],
                "edgeCount": comparison["expected"]["edgeCount"],
            },
        )
        self.assertEqual({"nodeCount": -6, "edgeCount": -25}, comparison["delta"])
        self.assertGreater(
            comparison["semanticCoverage"]["matchedExpectedNodes"], 30
        )
        self.assertIn("expectedToSidecar", comparison["mapping"])


class GraphAnalysisTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.graph = json.loads(
            (EXPECTED / "java-spring-sample.current.graph.json").read_text(
                encoding="utf-8"
            )
        )

    def test_hybrid_search_community_and_process_detection(self) -> None:
        search = hybrid_graph_search(
            self.graph["nodes"],
            self.graph["edges"],
            "PolicyService deploy",
        )
        self.assertIn("PolicyService.deploy", search["results"][0]["node"]["label"])
        self.assertEqual("BM25", search["algorithm"]["lexical"])
        self.assertIn("semantic", search["results"][0]["scoreBreakdown"])

        communities = detect_communities(
            self.graph["nodes"], self.graph["edges"]
        )
        self.assertGreater(communities["communityCount"], 1)
        self.assertEqual(len(self.graph["nodes"]), len(communities["membership"]))

        processes = detect_processes(self.graph["nodes"], self.graph["edges"])
        kinds = {process["kind"] for process in processes["processes"]}
        self.assertEqual({"API", "Event", "Test"}, kinds)
        api_process = next(
            process
            for process in processes["processes"]
            if process["kind"] == "API"
        )
        labels = {step["label"] for step in api_process["steps"]}
        self.assertIn("org.example.sdn.PolicyService.deploy", labels)
        self.assertIn("org.example.sdn.PolicyRepository.savePolicy", labels)

    def test_cross_repository_contract_graph_links_provider_and_consumer(self) -> None:
        event_a = {
            "id": "event:a:policy-rejected",
            "type": "EventType",
            "label": "policy-rejected",
        }
        event_b = {
            "id": "event:b:policy-rejected",
            "type": "EventType",
            "label": "policy-rejected",
        }
        graph = build_contract_graph(
            [
                {
                    "repositoryId": "producer",
                    "revision": "a1",
                    "nodes": [
                        event_a,
                        {
                            "id": "method:a:publish",
                            "type": "Method",
                            "label": "publish",
                        },
                    ],
                    "edges": [
                        {
                            "source": "method:a:publish",
                            "relation": "code:producesEvent",
                            "target": event_a["id"],
                        }
                    ],
                },
                {
                    "repositoryId": "consumer",
                    "revision": "b1",
                    "nodes": [
                        event_b,
                        {
                            "id": "method:b:onEvent",
                            "type": "Method",
                            "label": "onEvent",
                        },
                    ],
                    "edges": [
                        {
                            "source": "method:b:onEvent",
                            "relation": "code:consumesEvent",
                            "target": event_b["id"],
                        }
                    ],
                },
            ]
        )
        self.assertEqual(2, graph["repositoryCount"])
        self.assertEqual(1, graph["contractCount"])
        self.assertEqual(1, graph["crossRepositoryLinkCount"])

    def test_equal_repository_revisions_do_not_collide_in_current_graph(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "first"
            second = root / "second"
            shutil.copytree(ROOT / "examples" / "java-spring-sample", first)
            shutil.copytree(ROOT / "examples" / "java-spring-sample", second)
            service = PlatformService(
                SQLiteStore(root / "platform.db"),
                ROOT / "rules" / "requirement-change-planning-rules.yaml",
                repository_roots=[root],
            )
            for repository_id, path in (("repo-first", first), ("repo-second", second)):
                service.register_repository(
                    {"repositoryId": repository_id, "path": str(path)}
                )
                service.scan_repository(repository_id, {})
            revisions = service.graph_catalog("current")["revisions"]
            self.assertEqual(2, len(revisions))
            self.assertEqual(
                {"repo-first", "repo-second"},
                {
                    revision["metadata"]["repositoryId"]
                    for revision in revisions
                },
            )
            search = service.hybrid_search({"query": "PolicyService deploy"})
            self.assertIn("PolicyService", search["results"][0]["node"]["label"])
            scoped_search = service.hybrid_search(
                {
                    "repositoryId": "repo-first",
                    "query": "PolicyService deploy",
                }
            )
            self.assertEqual("repo-first", scoped_search["repositoryId"])
            self.assertIn(
                "repo-first", scoped_search["results"][0]["node"]["id"]
            )
            scoped_overview = service.graph_query(
                {
                    "repositoryId": "repo-first",
                    "graphSpace": "current",
                    "queryType": "GRAPH_OVERVIEW",
                    "limit": 500,
                }
            )
            self.assertFalse(
                any("repo-second" in node["id"] for node in scoped_overview["nodes"])
            )
            second_revision = next(
                revision["revision"]
                for revision in revisions
                if revision["metadata"]["repositoryId"] == "repo-second"
            )
            with self.assertRaises(PlatformError) as wrong_scope:
                service.graph_query(
                    {
                        "repositoryId": "repo-first",
                        "graphSpace": "current",
                        "revision": second_revision,
                        "queryType": "GRAPH_OVERVIEW",
                    }
                )
            self.assertEqual("NOT_FOUND", wrong_scope.exception.code)
            self.assertGreater(
                service.graph_communities({})["communityCount"], 1
            )
            self.assertGreater(service.graph_processes({})["processCount"], 0)
            contracts = service.contract_graph(
                {"repositoryIds": ["repo-first", "repo-second"]}
            )
            self.assertEqual(2, contracts["repositoryCount"])
            self.assertGreater(contracts["contractCount"], 0)

    def test_repository_context_symbol_context_and_git_change_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = root / "repository"
            shutil.copytree(ROOT / "examples" / "java-spring-sample", repository)
            subprocess.run(
                ["git", "init", "-q", str(repository)],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "-C", str(repository), "config", "user.email", "test@example.com"],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(repository), "config", "user.name", "Test"],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(repository), "add", "."],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(repository), "commit", "-qm", "baseline"],
                check=True,
            )
            service = PlatformService(
                SQLiteStore(root / "platform.db"),
                ROOT / "rules" / "requirement-change-planning-rules.yaml",
                repository_roots=[root],
            )
            service.register_repository(
                {"repositoryId": "repo-change", "path": str(repository)}
            )
            service.scan_repository("repo-change", {})

            catalog = service.list_repositories()
            self.assertEqual("repo-change", catalog["repositories"][0]["repositoryId"])
            context = service.repository_context("repo-change")
            self.assertEqual("Missing", context["codegraphIndex"]["status"])
            symbol = service.symbol_context(
                {
                    "repositoryId": "repo-change",
                    "query": "PolicyService deploy",
                }
            )
            self.assertTrue(
                any(
                    "PolicyService" in node["id"]
                    for node in symbol["context"]["nodes"]
                )
            )

            changed_path = (
                repository
                / "src/main/java/org/example/sdn/PolicyService.java"
            )
            changed_path.write_text(
                changed_path.read_text(encoding="utf-8") + "\n",
                encoding="utf-8",
            )
            changes = service.detect_changes(
                {"repositoryId": "repo-change", "depth": 2}
            )
            relative = "src/main/java/org/example/sdn/PolicyService.java"
            self.assertIn(relative, changes["changedFiles"])
            self.assertTrue(changes["matchedNodes"])
            self.assertTrue(changes["impactedNodes"])
            self.assertFalse(changes["unmappedFiles"])


class _McpService:
    planning_rules = SimpleNamespace(rule_set="test", version="1")

    def graph_catalog(self, *_: Any) -> dict[str, Any]:
        return {"graphSpaces": ["current"], "revisions": [], "count": 0}

    def list_repositories(self, *_: Any) -> dict[str, Any]:
        return {
            "repositories": [
                {
                    "repositoryId": "repo-a",
                    "name": "alpha",
                    "path": "/workspace/alpha",
                }
            ],
            "count": 1,
            "truncated": False,
        }

    def repository_context(self, repository_id: str) -> dict[str, Any]:
        return {"repository": {"repositoryId": repository_id}}

    def symbol_context(self, body: Any) -> dict[str, Any]:
        return {"symbol": body}

    def detect_changes(self, body: Any) -> dict[str, Any]:
        return {"changes": body}

    def codegraph_index_status(self, repository_id: str) -> dict[str, Any]:
        return {"repositoryId": repository_id, "status": "Fresh"}

    def graph_query(self, body: Any) -> dict[str, Any]:
        return {"query": body}

    def hybrid_search(self, body: Any) -> dict[str, Any]:
        return {"search": body}

    def codegraph_explore(self, repository_id: str, body: Any) -> dict[str, Any]:
        return {"repositoryId": repository_id, "body": body}

    codegraph_impact = codegraph_explore
    codegraph_affected_tests = codegraph_explore

    def graph_communities(self, body: Any) -> dict[str, Any]:
        return {"communities": body}

    def graph_processes(self, body: Any) -> dict[str, Any]:
        return {"processes": body}

    def contract_graph(self, body: Any) -> dict[str, Any]:
        return {"contracts": body}


class McpGatewayTest(unittest.TestCase):
    def test_gateway_exposes_only_read_tools_and_structured_results(self) -> None:
        gateway = ReadOnlyMcpGateway(_McpService())  # type: ignore[arg-type]
        initialized = gateway.handle(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        )
        self.assertEqual(
            MCP_PROTOCOL_VERSION,
            initialized["result"]["protocolVersion"],  # type: ignore[index]
        )
        listed = gateway.handle(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
        )
        tools = listed["result"]["tools"]  # type: ignore[index]
        names = {tool["name"] for tool in tools}
        self.assertNotIn("index", names)
        self.assertNotIn("write", " ".join(names))
        self.assertTrue(all(tool["annotations"]["readOnlyHint"] for tool in tools))
        called = gateway.handle(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "index_status",
                    "arguments": {"repositoryId": "repo-a"},
                },
            }
        )
        self.assertEqual(
            "Fresh",
            called["result"]["structuredContent"]["status"],  # type: ignore[index]
        )
        self.assertIsNone(
            gateway.handle(
                {"jsonrpc": "2.0", "method": "notifications/initialized"}
            )
        )

    def test_stdio_transport_resources_prompts_and_argument_validation(self) -> None:
        gateway = ReadOnlyMcpGateway(_McpService())  # type: ignore[arg-type]
        source = io.StringIO(
            "\n".join(
                [
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": 1,
                            "method": "initialize",
                            "params": {},
                        }
                    ),
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "method": "notifications/initialized",
                        }
                    ),
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": 2,
                            "method": "resources/templates/list",
                            "params": {},
                        }
                    ),
                ]
            )
            + "\n"
        )
        destination = io.StringIO()
        self.assertEqual(0, serve_stdio(gateway, source, destination))
        responses = [
            json.loads(line) for line in destination.getvalue().splitlines()
        ]
        self.assertEqual([1, 2], [response["id"] for response in responses])
        self.assertIn(
            "{repositoryId}",
            responses[1]["result"]["resourceTemplates"][0]["uriTemplate"],
        )
        self.assertIsNone(
            gateway.handle(
                {"jsonrpc": "2.0", "id": 99, "result": {"accepted": True}}
            )
        )
        self.assertIsNone(
            gateway.handle(
                {
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized",
                    "params": "ignored-invalid-notification-params",
                }
            )
        )

        resources = gateway.handle(
            {"jsonrpc": "2.0", "id": 3, "method": "resources/list", "params": {}}
        )
        resource_uris = {
            resource["uri"] for resource in resources["result"]["resources"]  # type: ignore[index]
        }
        self.assertIn("code-ontology://repositories", resource_uris)
        self.assertIn(
            "code-ontology://repositories/repo-a/context", resource_uris
        )
        prompt = gateway.handle(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "prompts/get",
                "params": {
                    "name": "detect_impact",
                    "arguments": {"repositoryId": "repo-a"},
                },
            }
        )
        self.assertIn(
            "detect_changes",
            prompt["result"]["messages"][0]["content"]["text"],  # type: ignore[index]
        )

        invalid = gateway.handle(
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {
                    "name": "index_status",
                    "arguments": {"repositoryId": "repo-a", "unknown": True},
                },
            }
        )
        self.assertTrue(invalid["result"]["isError"])  # type: ignore[index]
        self.assertEqual(
            "MCP_INVALID_TOOL_ARGUMENTS",
            invalid["result"]["structuredContent"]["error"]["code"],  # type: ignore[index]
        )
        traced = gateway.handle(
            {
                "jsonrpc": "2.0",
                "id": 51,
                "method": "tools/call",
                "params": {
                    "name": "trace",
                    "arguments": {
                        "sourceEntityId": "source",
                        "targetEntityId": "target",
                    },
                },
            }
        )
        self.assertEqual(
            "CALL_PATH",
            traced["result"]["structuredContent"]["query"]["queryType"],  # type: ignore[index]
        )

        bounded = gateway.handle(
            {
                "jsonrpc": "2.0",
                "id": 6,
                "method": "tools/call",
                "params": {
                    "name": "graph_query",
                    "arguments": {
                        "graphSpace": "current",
                        "queryType": "GRAPH_OVERVIEW",
                        "search": "x" * 5000,
                        "maxTokens": 128,
                    },
                },
            }
        )
        structured = bounded["result"]["structuredContent"]  # type: ignore[index]
        self.assertTrue(structured["_mcp"]["truncated"])
        self.assertLessEqual(
            len(json.dumps(structured, ensure_ascii=False).encode("utf-8")),
            128 * 4,
        )
        self.assertLessEqual(
            len(
                json.dumps(
                    bounded["result"],  # type: ignore[index]
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
            ),
            128 * 4,
        )

    def test_cli_stdio_emits_only_mcp_messages(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "code_ontology_platform",
                    "--database",
                    str(Path(directory) / "platform.db"),
                    "--rules",
                    str(ROOT / "rules" / "requirement-change-planning-rules.yaml"),
                    "mcp",
                ],
                cwd=ROOT,
                input=(
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": 1,
                            "method": "initialize",
                            "params": {"protocolVersion": MCP_PROTOCOL_VERSION},
                        }
                    )
                    + "\n"
                ),
                text=True,
                capture_output=True,
                timeout=15,
                check=True,
            )
            lines = completed.stdout.splitlines()
            self.assertEqual(1, len(lines))
            response = json.loads(lines[0])
            self.assertEqual(MCP_PROTOCOL_VERSION, response["result"]["protocolVersion"])
            self.assertEqual("", completed.stderr)

    def test_streamable_http_rejects_cross_origin_requests(self) -> None:
        server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            handler_for(_McpService()),  # type: ignore[arg-type]
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            endpoint = f"http://127.0.0.1:{server.server_port}/mcp"
            valid = urllib.request.Request(
                endpoint,
                data=json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/list",
                        "params": {},
                    }
                ).encode(),
                headers={
                    "Content-Type": "application/json",
                    "MCP-Protocol-Version": MCP_PROTOCOL_VERSION,
                    "Origin": f"http://127.0.0.1:{server.server_port}",
                },
                method="POST",
            )
            with urllib.request.urlopen(valid, timeout=3) as response:
                payload = json.load(response)
            self.assertEqual("2.0", payload["jsonrpc"])
            self.assertTrue(payload["result"]["tools"])

            request = urllib.request.Request(
                endpoint,
                data=json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/list",
                        "params": {},
                    }
                ).encode(),
                headers={
                    "Content-Type": "application/json",
                    "Origin": "https://attacker.example",
                },
                method="POST",
            )
            with self.assertRaises(urllib.error.HTTPError) as raised:
                urllib.request.urlopen(request, timeout=3)
            self.assertEqual(403, raised.exception.code)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
