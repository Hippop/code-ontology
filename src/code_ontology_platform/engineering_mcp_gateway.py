from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

from .engineering_semantics import EngineeringSemantics
from .errors import invalid, not_found
from .mcp_gateway import ReadOnlyMcpGateway, _object_schema, serve_stdio
from .models import GRAPH_SPACES
from .service import PlatformService
from .store import SQLiteStore


def _default_rules_path() -> Path:
    configured = os.environ.get("CODE_ONTOLOGY_RULES")
    if configured:
        return Path(configured)
    candidates = [
        Path.cwd() / "rules" / "requirement-change-planning-rules.yaml",
        Path(__file__).resolve().parents[2] / "rules" / "requirement-change-planning-rules.yaml",
    ]
    return next((item for item in candidates if item.exists()), candidates[0])


_GRAPH_REF = {
    "repositoryId": {"type": "string", "minLength": 1},
    "graphSpace": {"type": "string", "enum": sorted(GRAPH_SPACES), "default": "current"},
    "revision": {"type": "string", "minLength": 1},
}


class EngineeringMcpGateway(ReadOnlyMcpGateway):
    """Read-only MCP gateway plus deterministic engineering-semantic tools."""

    def __init__(self, service: PlatformService) -> None:
        super().__init__(service)
        readonly = {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        }
        additions = [
            {
                "name": "engineering_validate",
                "description": "校验 EngineeringRequirement、Contract、Verification 与 Evidence 的闭环约束。",
                "inputSchema": _object_schema(dict(_GRAPH_REF)),
                "annotations": readonly,
            },
            {
                "name": "engineering_coverage",
                "description": "计算 leaf Requirement 的实现覆盖、验证覆盖和验证证据覆盖。",
                "inputSchema": _object_schema(dict(_GRAPH_REF)),
                "annotations": readonly,
            },
            {
                "name": "engineering_collect",
                "description": "沿白名单工程关系收集 Capability/Requirement/Contract/Code/Test 上下文。",
                "inputSchema": _object_schema(
                    {
                        **_GRAPH_REF,
                        "entityId": {"type": "string", "minLength": 1},
                        "depth": {"type": "integer", "minimum": 0, "maximum": 6, "default": 2},
                    },
                    required=["entityId"],
                ),
                "annotations": readonly,
            },
            {
                "name": "engineering_impact",
                "description": "仅按显式 ImpactRule 计算跨代码、需求、契约与验证的确定性影响路径。",
                "inputSchema": _object_schema(
                    {
                        **_GRAPH_REF,
                        "entityIds": {
                            "type": "array",
                            "minItems": 1,
                            "maxItems": 100,
                            "items": {"type": "string", "minLength": 1},
                        },
                        "depth": {"type": "integer", "minimum": 1, "maximum": 8, "default": 4},
                    },
                    required=["entityIds"],
                ),
                "annotations": readonly,
            },
        ]
        self.tools.extend(additions)
        self._dispatch.update(
            {
                "engineering_validate": self.engineering_validate,
                "engineering_coverage": self.engineering_coverage,
                "engineering_collect": self.engineering_collect,
                "engineering_impact": self.engineering_impact,
            }
        )
        self._tool_by_name = {tool["name"]: tool for tool in self.tools}

    def _analysis(self, args: dict[str, Any]) -> tuple[dict[str, Any], EngineeringSemantics]:
        graph_space, revision, nodes, edges = self.service._analysis_graph(args)
        metadata = {
            "repositoryId": args.get("repositoryId"),
            "graphSpace": graph_space,
            "revision": revision,
        }
        return metadata, EngineeringSemantics({"nodes": nodes, "edges": edges})

    def engineering_validate(self, args: dict[str, Any]) -> dict[str, Any]:
        metadata, analyzer = self._analysis(args)
        return {**metadata, **analyzer.validate()}

    def engineering_coverage(self, args: dict[str, Any]) -> dict[str, Any]:
        metadata, analyzer = self._analysis(args)
        return {**metadata, **analyzer.coverage()}

    def engineering_collect(self, args: dict[str, Any]) -> dict[str, Any]:
        metadata, analyzer = self._analysis(args)
        entity_id = str(args.get("entityId", ""))
        try:
            result = analyzer.collect(entity_id, depth=int(args.get("depth", 2)))
        except KeyError as error:
            raise not_found(f"工程语义实体不存在: {entity_id}") from error
        except ValueError as error:
            raise invalid(str(error)) from error
        return {**metadata, **result}

    def engineering_impact(self, args: dict[str, Any]) -> dict[str, Any]:
        metadata, analyzer = self._analysis(args)
        entity_ids = [str(item) for item in args.get("entityIds", [])]
        try:
            result = analyzer.impact(entity_ids, max_depth=int(args.get("depth", 4)))
        except KeyError as error:
            raise not_found(f"工程语义影响分析存在未知实体: {error.args[0]}") from error
        except ValueError as error:
            raise invalid(str(error)) from error
        return {**metadata, **result}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="code-ontology-engineering-mcp")
    parser.add_argument("--database", default=os.environ.get("CODE_ONTOLOGY_DB", "data/code-ontology.db"))
    parser.add_argument("--rules", default=str(_default_rules_path()))
    args = parser.parse_args(argv)
    roots_value = os.environ.get("CODE_ONTOLOGY_REPOSITORY_ROOTS")
    roots = [Path(item) for item in roots_value.split(os.pathsep) if item] if roots_value else None
    service = PlatformService(
        SQLiteStore(args.database),
        args.rules,
        repository_roots=roots,
        worktree_root=os.environ.get("CODE_ONTOLOGY_WORKTREE_ROOT"),
    )
    return serve_stdio(EngineeringMcpGateway(service))


if __name__ == "__main__":
    raise SystemExit(main())
