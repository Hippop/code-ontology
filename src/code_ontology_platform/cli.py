from __future__ import annotations

import argparse
import json
import os
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .graph_baseline import (
    build_graph_baseline,
    compare_graph_baseline,
    load_graph_baseline,
    write_graph_baseline,
)
from .http_api import handler_for
from .mcp_gateway import MCP_PROTOCOL_VERSION, ReadOnlyMcpGateway, serve_stdio
from .models import list_value, object_value
from .repository_scan import RepositoryScanner
from .semantic_validation import validate_semantic_assets
from .service import PlatformService
from .store import SQLiteStore


def _default_rules_path() -> Path:
    configured = os.environ.get("CODE_ONTOLOGY_RULES")
    if configured:
        return Path(configured)
    candidates = [
        Path.cwd() / "rules" / "requirement-change-planning-rules.yaml",
        Path(__file__).resolve().parents[2]
        / "rules"
        / "requirement-change-planning-rules.yaml",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _service(arguments: argparse.Namespace) -> PlatformService:
    roots_value = os.environ.get("CODE_ONTOLOGY_REPOSITORY_ROOTS")
    roots = (
        [Path(item) for item in roots_value.split(os.pathsep) if item]
        if roots_value
        else None
    )
    return PlatformService(
        SQLiteStore(arguments.database),
        arguments.rules,
        repository_roots=roots,
        worktree_root=os.environ.get("CODE_ONTOLOGY_WORKTREE_ROOT"),
    )


def _seed(service: PlatformService, document_value: Any) -> dict[str, int]:
    document = object_value(document_value, "seed document")
    counts = {
        "requirementContexts": 0,
        "graphs": 0,
        "reconciliationContexts": 0,
    }
    for item_value in document.get("requirementContexts", []):
        item = object_value(item_value, "requirementContexts item")
        service.put_requirement_context(
            item["requirementId"],
            item["designRevisionId"],
            item["stage"],
            object_value(item.get("payload", {}), "requirement context payload"),
        )
        counts["requirementContexts"] += 1
    for item_value in document.get("graphs", []):
        item = object_value(item_value, "graphs item")
        service.replace_graph(
            item["graphSpace"],
            item["revision"],
            list_value(item.get("nodes"), "graph nodes", nonempty=True),
            list_value(item.get("edges", []), "graph edges"),
        )
        counts["graphs"] += 1
    for item_value in document.get("reconciliationContexts", []):
        item = object_value(item_value, "reconciliationContexts item")
        service.put_reconciliation_context(
            item["reconciliationRunId"],
            object_value(item.get("payload", {}), "reconciliation context payload"),
        )
        counts["reconciliationContexts"] += 1
    return counts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="code-ontology-platform",
        description="Code Ontology 受控 Agent Gateway 与规划规则执行器",
    )
    parser.add_argument(
        "--database",
        default=os.environ.get("CODE_ONTOLOGY_DB", "data/code-ontology.db"),
        help="SQLite database path",
    )
    parser.add_argument(
        "--rules",
        default=str(_default_rules_path()),
        help="planning rules YAML path",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="初始化数据库并校验规则")

    serve = commands.add_parser("serve", help="启动 HTTP API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8080)
    serve.add_argument(
        "--web-root",
        type=Path,
        default=Path(os.environ.get("CODE_ONTOLOGY_WEB_ROOT", "web/dist")),
    )
    commands.add_parser("mcp", help="通过 stdin/stdout 启动只读 MCP Server")
    commands.add_parser("doctor", help="检查数据库、仓库、CodeGraph 和 MCP 能力")

    seed = commands.add_parser("seed", help="装载受控上下文和图快照")
    seed.add_argument("file", type=Path)

    plan = commands.add_parser("plan", help="展开一个 Semantic Graph Difference")
    plan.add_argument("file", type=Path)

    semantic = commands.add_parser("validate", help="解析本体并执行 SHACL 校验")
    semantic.add_argument("--ontology-dir", type=Path, default=Path("ontology"))
    semantic.add_argument("--shapes-dir", type=Path, default=Path("shapes"))
    semantic.add_argument("--data-dir", type=Path, default=Path("examples"))

    scan = commands.add_parser("scan", help="扫描 Java/Spring 仓库并发布 Current Graph")
    scan.add_argument("path", type=Path)
    scan.add_argument("--repository-id")
    scan.add_argument("--include-graph", action="store_true")
    scan.add_argument(
        "--expected-graph",
        type=Path,
        help="扫描后与指定预期图谱基线比较；发现漂移时退出码为 1",
    )

    baseline = commands.add_parser(
        "baseline",
        help="生成或比较可移植的代码图谱预期基线",
    )
    baseline_commands = baseline.add_subparsers(
        dest="baseline_command",
        required=True,
    )
    baseline_generate = baseline_commands.add_parser(
        "generate",
        help="扫描仓库并生成预期图谱基线",
    )
    baseline_generate.add_argument("path", type=Path)
    baseline_generate.add_argument("output", type=Path)
    baseline_generate.add_argument("--repository-id")
    baseline_compare = baseline_commands.add_parser(
        "compare",
        help="扫描仓库并与预期图谱基线比较",
    )
    baseline_compare.add_argument("path", type=Path)
    baseline_compare.add_argument("expected", type=Path)
    baseline_compare.add_argument("--repository-id")
    baseline_compare.add_argument("--limit", type=int, default=200)

    codegraph = commands.add_parser(
        "codegraph", help="管理 CodeGraph Sidecar 索引并执行只读查询"
    )
    codegraph_commands = codegraph.add_subparsers(
        dest="codegraph_command", required=True
    )
    for name in ("index", "status", "explore", "impact", "affected", "compare"):
        command = codegraph_commands.add_parser(name)
        command.add_argument("path", type=Path)
        command.add_argument("--repository-id")
        if name == "explore":
            command.add_argument("query")
        elif name == "impact":
            command.add_argument("symbol")
            command.add_argument("--depth", type=int, default=3)
        elif name == "affected":
            command.add_argument("files", nargs="+")
            command.add_argument("--depth", type=int, default=3)
        elif name == "compare":
            command.add_argument("expected", type=Path)
            command.add_argument("--difference-limit", type=int, default=200)

    analysis = commands.add_parser(
        "analyze", help="执行混合检索、社区、流程和跨仓契约分析"
    )
    analysis_commands = analysis.add_subparsers(
        dest="analysis_command", required=True
    )
    analysis_search = analysis_commands.add_parser("search")
    analysis_search.add_argument("query")
    analysis_search.add_argument("--graph-space", default="current")
    analysis_search.add_argument("--revision")
    analysis_search.add_argument("--limit", type=int, default=20)
    for name in ("communities", "processes"):
        command = analysis_commands.add_parser(name)
        command.add_argument("--graph-space", default="current")
        command.add_argument("--revision")
    analysis_contracts = analysis_commands.add_parser("contracts")
    analysis_contracts.add_argument("--repository-id", action="append", default=[])
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)

    if arguments.command == "validate":
        result = validate_semantic_assets(
            ontology_files=sorted(arguments.ontology_dir.glob("*.ttl")),
            shape_files=sorted(arguments.shapes_dir.glob("*.ttl")),
            data_files=sorted(arguments.data_dir.glob("*.ttl")),
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["conforms"] else 1

    if arguments.command == "baseline":
        path = arguments.path.resolve()
        if arguments.baseline_command == "generate":
            repository_id = arguments.repository_id or f"repo-{path.name}"
            scan_result = RepositoryScanner().scan(path, repository_id)
            baseline = build_graph_baseline(
                scan_result["graph"],
                repository_id=repository_id,
            )
            output = write_graph_baseline(arguments.output, baseline)
            print(
                json.dumps(
                    {
                        "status": "Generated",
                        "path": str(output),
                        "repositoryId": repository_id,
                        "contentHash": baseline["contentHash"],
                        "summary": baseline["summary"],
                        "coverage": scan_result["coverage"],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        expected = load_graph_baseline(arguments.expected)
        repository_id = arguments.repository_id or str(expected["repositoryId"])
        scan_result = RepositoryScanner().scan(path, repository_id)
        comparison = compare_graph_baseline(
            expected,
            scan_result["graph"],
            limit=arguments.limit,
        )
        comparison["coverage"] = scan_result["coverage"]
        print(json.dumps(comparison, ensure_ascii=False, indent=2))
        return 0 if comparison["status"] == "Matched" else 1

    service = _service(arguments)

    if arguments.command == "init":
        print(
            json.dumps(
                {
                    "status": "initialized",
                    "database": arguments.database,
                    "graphTextRoot": (
                        str(service.store.graph_text_root)
                        if service.store.graph_text_root is not None
                        else None
                    ),
                    "ruleSet": service.planning_rules.rule_set,
                    "ruleSetVersion": service.planning_rules.version,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if arguments.command == "doctor":
        gateway = ReadOnlyMcpGateway(service)
        repositories = service.list_repositories({"limit": 500})
        describe_runtime = getattr(service.agent_adapter, "describe", None)
        agent_runtime = (
            describe_runtime()
            if callable(describe_runtime)
            else {
                "runtime": type(service.agent_adapter).__name__,
                "available": True,
            }
        )
        print(
            json.dumps(
                {
                    "status": "ok",
                    "database": str(Path(arguments.database).resolve()),
                    "rules": str(Path(arguments.rules).resolve()),
                    "repositoryCount": repositories["count"],
                    "repositories": [
                        {
                            "repositoryId": repository["repositoryId"],
                            "name": repository["name"],
                            "path": repository["path"],
                        }
                        for repository in repositories["repositories"]
                    ],
                    "codegraph": {
                        "available": service.codegraph_sidecar.available(),
                        "version": service.codegraph_sidecar.version(),
                        "command": service.codegraph_sidecar.command,
                    },
                    "agentRuntime": agent_runtime,
                    "mcp": {
                        "protocolVersion": MCP_PROTOCOL_VERSION,
                        "transports": ["stdio", "streamable-http"],
                        "toolCount": len(gateway.tools),
                        "tools": [tool["name"] for tool in gateway.tools],
                        "readOnly": True,
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if arguments.command == "seed":
        document = json.loads(arguments.file.read_text(encoding="utf-8"))
        print(json.dumps(_seed(service, document), ensure_ascii=False, indent=2))
        return 0

    if arguments.command == "plan":
        document = json.loads(arguments.file.read_text(encoding="utf-8"))
        print(
            json.dumps(
                service.expand_change_plan(document),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if arguments.command == "scan":
        path = arguments.path.resolve()
        service.repository_roots = [path]
        repository = service.register_repository(
            {
                "path": str(path),
                "repositoryId": arguments.repository_id,
            }
        )
        result = service.scan_repository(
            repository["repositoryId"],
            {
                "includeGraph": (
                    arguments.include_graph or arguments.expected_graph is not None
                )
            },
        )
        if arguments.expected_graph is not None:
            comparison = compare_graph_baseline(
                load_graph_baseline(arguments.expected_graph),
                result["graph"],
            )
            result["baselineComparison"] = comparison
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return (
            1
            if arguments.expected_graph is not None
            and result["baselineComparison"]["status"] != "Matched"
            else 0
        )

    if arguments.command == "codegraph":
        path = arguments.path.resolve()
        repository_id = arguments.repository_id or f"repo-{path.name}"
        service.repository_roots = [path]
        service.register_repository(
            {"path": str(path), "repositoryId": repository_id}
        )
        operation = arguments.codegraph_command
        if operation == "index":
            result = service.codegraph_index(repository_id)
        elif operation == "status":
            result = service.codegraph_index_status(repository_id)
        elif operation == "explore":
            result = service.codegraph_explore(
                repository_id, {"query": arguments.query}
            )
        elif operation == "impact":
            result = service.codegraph_impact(
                repository_id,
                {"symbol": arguments.symbol, "depth": arguments.depth},
            )
        elif operation == "affected":
            result = service.codegraph_affected_tests(
                repository_id,
                {"changedFiles": arguments.files, "depth": arguments.depth},
            )
        else:
            expected = load_graph_baseline(arguments.expected)
            result = service.codegraph_compare(
                repository_id,
                {
                    "expectedGraph": expected,
                    "differenceLimit": arguments.difference_limit,
                },
            )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if arguments.command == "analyze":
        body = {}
        if arguments.analysis_command in {"search", "communities", "processes"}:
            body = {
                "graphSpace": arguments.graph_space,
                "revision": arguments.revision,
            }
        if arguments.analysis_command == "search":
            body.update({"query": arguments.query, "limit": arguments.limit})
            result = service.hybrid_search(body)
        elif arguments.analysis_command == "communities":
            result = service.graph_communities(body)
        elif arguments.analysis_command == "processes":
            result = service.graph_processes(body)
        else:
            result = service.contract_graph(
                {"repositoryIds": arguments.repository_id}
            )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if arguments.command == "mcp":
        return serve_stdio(ReadOnlyMcpGateway(service))

    server = ThreadingHTTPServer(
        (arguments.host, arguments.port),
        handler_for(
            service,
            os.environ.get("CODE_ONTOLOGY_API_TOKEN"),
            arguments.web_root if arguments.web_root.is_dir() else None,
        ),
    )
    print(
        f"Code Ontology Agent Gateway listening on "
        f"http://{arguments.host}:{arguments.port}"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
