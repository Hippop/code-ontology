from __future__ import annotations

import argparse
import os
from pathlib import Path
from .mcp_gateway import ReadOnlyMcpGateway, serve_stdio
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


class EngineeringMcpGateway(ReadOnlyMcpGateway):
    """Backward-compatible name for the unified read-only MCP gateway."""


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
