from __future__ import annotations

import argparse
import json
from pathlib import Path

from code_ontology_platform.evaluation.loader import EvaluationLoader
from code_ontology_platform.evaluation.platform_backends import PlatformWorkflowBackend
from code_ontology_platform.evaluation.reports import (
    compare_run_sets,
    load_run_set,
)
from code_ontology_platform.evaluation.runner import (
    BatchEvaluationRunner,
    FileArtifactBackend,
    write_run_set,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run Code Ontology change-workflow evaluations"
    )
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate", help="validate scenario YAML files")
    validate.add_argument("path", type=Path)

    run = commands.add_parser(
        "run",
        help="execute or judge change-workflow scenarios against goldens",
    )
    run.add_argument("path", type=Path)
    run.add_argument(
        "--backend",
        choices=("file", "platform"),
        default="file",
        help="file judges pre-produced artifacts; platform executes real workflows",
    )
    run.add_argument(
        "--rules",
        type=Path,
        help="planning rules path used by the platform backend",
    )
    run.add_argument(
        "--output",
        type=Path,
        default=Path("evaluation/reports/latest.json"),
    )
    run.add_argument(
        "--fail-on-false-ready",
        action=argparse.BooleanOptionalAction,
        default=True,
    )

    compare = commands.add_parser("compare", help="compare two evaluation run sets")
    compare.add_argument("baseline", type=Path)
    compare.add_argument("candidate", type=Path)
    compare.add_argument("--output", type=Path)

    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    loader = EvaluationLoader()

    if arguments.command == "validate":
        scenarios = loader.load_scenarios(arguments.path)
        print(
            json.dumps(
                {
                    "valid": True,
                    "count": len(scenarios),
                    "scenarioIds": [item.scenario_id for item in scenarios],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if arguments.command == "run":
        scenarios = loader.load_scenarios(arguments.path)
        backend = (
            FileArtifactBackend(loader)
            if arguments.backend == "file"
            else PlatformWorkflowBackend(rules_path=arguments.rules, loader=loader)
        )
        runner = BatchEvaluationRunner(backend, loader)
        document = runner.run_many(scenarios)
        output = write_run_set(document, arguments.output)
        document["output"] = str(output)
        print(json.dumps(document["summary"], ensure_ascii=False, indent=2))
        false_ready_rate = document["summary"]["metrics"].get(
            "falseReadyRate", 0.0
        )
        if arguments.fail_on_false_ready and false_ready_rate > 0:
            return 2
        if document["summary"]["errors"] > 0 or document["summary"]["failed"] > 0:
            return 1
        return 0

    if arguments.command == "compare":
        document = compare_run_sets(
            load_run_set(arguments.baseline),
            load_run_set(arguments.candidate),
        )
        if arguments.output is not None:
            arguments.output.parent.mkdir(parents=True, exist_ok=True)
            arguments.output.write_text(
                json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True)
                + "\n",
                encoding="utf-8",
            )
        print(json.dumps(document, ensure_ascii=False, indent=2))
        return 1 if document["regressionCount"] else 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
