#!/usr/bin/env python3
"""Export a CodeGraph index and its comparison with the platform baseline."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from code_ontology_platform.code_intelligence import (  # noqa: E402
    CodeGraphSidecar,
    compare_codegraph_to_baseline,
)
from code_ontology_platform.store import SQLiteStore  # noqa: E402


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("repository", type=Path)
    parser.add_argument("expected", type=Path)
    parser.add_argument("snapshot_output", type=Path)
    parser.add_argument("comparison_output", type=Path)
    parser.add_argument("--repository-id", default="repo-sdn-sample")
    arguments = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="codegraph-baseline-") as directory:
        store = SQLiteStore(Path(directory) / "platform.db")
        sidecar = CodeGraphSidecar(store)
        snapshot = sidecar.graph_snapshot(
            arguments.repository_id,
            arguments.repository.resolve(),
        )
    baseline = json.loads(arguments.expected.read_text(encoding="utf-8"))
    comparison = compare_codegraph_to_baseline(snapshot, baseline)
    write_json(arguments.snapshot_output, snapshot)
    write_json(arguments.comparison_output, comparison)
    print(
        json.dumps(
            {
                "snapshot": str(arguments.snapshot_output),
                "comparison": str(arguments.comparison_output),
                "actual": snapshot["summary"],
                "expected": baseline["summary"],
                "semanticCoverage": comparison["semanticCoverage"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
