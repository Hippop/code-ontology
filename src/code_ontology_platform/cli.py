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
