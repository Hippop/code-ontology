from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from ..errors import invalid
from .models import (
    EvaluationScenario,
    ExpectedArtifactRef,
    MutationRef,
    RepositoryFixtureRef,
)


class EvaluationLoader:
    def discover(self, path: str | Path) -> list[Path]:
        source = Path(path)
        if source.is_file():
            return [source]
        if not source.is_dir():
            raise invalid(f"Scenario 路径不存在: {source}")
        return sorted(
            item
            for item in source.rglob("*")
            if item.is_file() and item.suffix.lower() in {".yaml", ".yml"}
        )

    def load_scenarios(self, path: str | Path) -> list[EvaluationScenario]:
        scenarios = [self.load_scenario(item) for item in self.discover(path)]
        ids: set[str] = set()
        duplicates: list[str] = []
        for scenario in scenarios:
            if scenario.scenario_id in ids:
                duplicates.append(scenario.scenario_id)
            ids.add(scenario.scenario_id)
        if duplicates:
            raise invalid("Scenario ID 重复", {"scenarioIds": sorted(set(duplicates))})
        return scenarios

    def load_scenario(self, path: str | Path) -> EvaluationScenario:
        source = Path(path)
        document = self._load_mapping(source)
        schema_version = document.get("schemaVersion", "evaluation-scenario/v1")
        scenario_id = self._string(document.get("scenarioId"), "scenarioId")
        workflow = self._string(document.get("workflow"), "workflow")

        fixture_value = self._mapping(document.get("fixture"), "fixture")
        fixture_path = self._resolve(source.parent, fixture_value.get("path"))
        graph_baseline = fixture_value.get("graphBaseline")
        if graph_baseline is not None:
            graph_baseline = str(self._resolve(source.parent, graph_baseline))
        fixture = RepositoryFixtureRef(
            fixture_id=self._string(fixture_value.get("id"), "fixture.id"),
            source_path=str(fixture_path),
            revision=self._string(fixture_value.get("revision"), "fixture.revision"),
            graph_baseline=graph_baseline,
            fixture_level=self._string(fixture_value.get("level", "micro"), "fixture.level"),
        )
        if not fixture_path.exists():
            raise invalid(
                "Fixture 路径不存在",
                {"scenarioId": scenario_id, "path": str(fixture_path)},
            )

        expected_value = self._mapping(document.get("expected"), "expected")
        expected: dict[str, ExpectedArtifactRef] = {}
        for artifact_type, ref_value in expected_value.items():
            ref = self._mapping(ref_value, f"expected.{artifact_type}")
            artifact_path = self._resolve(source.parent, ref.get("path"))
            if not artifact_path.is_file():
                raise invalid(
                    "Expected Artifact 不存在",
                    {
                        "scenarioId": scenario_id,
                        "artifactType": artifact_type,
                        "path": str(artifact_path),
                    },
                )
            expected[artifact_type] = ExpectedArtifactRef(
                artifact_type=str(artifact_type),
                path=str(artifact_path),
                oracle_type=self._string(
                    ref.get("oracle", "deterministic"),
                    f"expected.{artifact_type}.oracle",
                ),
                compare_mode=self._string(
                    ref.get("compare", "exact"),
                    f"expected.{artifact_type}.compare",
                ),
            )

        mutation = None
        if document.get("mutation") is not None:
            mutation_value = self._mapping(document["mutation"], "mutation")
            mutation_path = mutation_value.get("path")
            mutation = MutationRef(
                mutation_id=self._string(mutation_value.get("id"), "mutation.id"),
                path=(
                    str(self._resolve(source.parent, mutation_path))
                    if mutation_path is not None
                    else None
                ),
            )

        return EvaluationScenario(
            schema_version=self._string(schema_version, "schemaVersion"),
            scenario_id=scenario_id,
            workflow=workflow,
            fixture=fixture,
            input=self._mapping(document.get("input", {}), "input"),
            planned_artifacts=(
                self._mapping(document["plannedArtifacts"], "plannedArtifacts")
                if document.get("plannedArtifacts") is not None
                else None
            ),
            expected=expected,
            expected_decision=self._string(
                document.get("expectedDecision"),
                "expectedDecision",
            ),
            mutation=mutation,
            tags=tuple(self._string(item, "tag") for item in document.get("tags", [])),
            oracle=self._mapping(document.get("oracle", {}), "oracle"),
            source_path=str(source.resolve()),
        )

    def load_artifact(self, path: str | Path) -> Any:
        source = Path(path)
        if source.suffix.lower() in {".yaml", ".yml"}:
            with source.open("r", encoding="utf-8") as stream:
                return yaml.safe_load(stream)
        with source.open("r", encoding="utf-8") as stream:
            return json.load(stream)

    def _load_mapping(self, path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as stream:
            value = yaml.safe_load(stream)
        return self._mapping(value, str(path))

    @staticmethod
    def _mapping(value: Any, name: str) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise invalid(f"{name} 必须是 object")
        return dict(value)

    @staticmethod
    def _string(value: Any, name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise invalid(f"{name} 必须是非空字符串")
        return value.strip()

    @staticmethod
    def _resolve(base: Path, value: Any) -> Path:
        if not isinstance(value, str) or not value.strip():
            raise invalid("路径必须是非空字符串")
        path = Path(value)
        if not path.is_absolute():
            path = base / path
        return path.resolve()
