from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ..errors import invalid


@dataclass(frozen=True)
class MutationDefinition:
    mutation_id: str
    kind: str
    operation: str
    target: dict[str, Any]
    selector: dict[str, Any]
    value: Any = None
    expected_failure: dict[str, Any] | None = None


@dataclass(frozen=True)
class MutationResult:
    mutation_id: str
    changed: bool
    details: dict[str, Any]


class MutationRegistry:
    def load(self, path: str | Path) -> MutationDefinition:
        source = Path(path)
        with source.open("r", encoding="utf-8") as stream:
            value = yaml.safe_load(stream)
        if not isinstance(value, dict):
            raise invalid("Mutation 文件必须是 object")
        if value.get("schemaVersion") != "evaluation-mutation/v1":
            raise invalid("Mutation schemaVersion 不受支持")
        return MutationDefinition(
            mutation_id=self._string(value.get("mutationId"), "mutationId"),
            kind=self._string(value.get("kind"), "kind"),
            operation=self._string(value.get("operation"), "operation"),
            target=dict(value.get("target") or {}),
            selector=dict(value.get("selector") or {}),
            value=value.get("value"),
            expected_failure=(
                dict(value["expectedFailure"])
                if isinstance(value.get("expectedFailure"), dict)
                else None
            ),
        )

    def apply_artifact(
        self, mutation: MutationDefinition, artifact: Any
    ) -> MutationResult:
        if mutation.kind != "artifact":
            raise invalid("当前 Mutation 不是 artifact mutation")
        changed = False
        target = copy.deepcopy(artifact)

        if mutation.operation == "RemoveArtifactItem":
            key = self._string(mutation.target.get("collection"), "target.collection")
            identity = mutation.selector.get("id")
            collection = target.get(key) if isinstance(target, dict) else None
            if not isinstance(collection, list):
                raise invalid(f"Artifact collection 不存在: {key}")
            before = len(collection)
            collection[:] = [
                item
                for item in collection
                if not (
                    isinstance(item, dict)
                    and identity
                    in {
                        item.get("id"),
                        item.get("changeId"),
                        item.get("impactId"),
                        item.get("requirementId"),
                        item.get("proposalId"),
                    }
                )
            ]
            changed = len(collection) != before

        elif mutation.operation == "ReplaceArtifactField":
            path = mutation.selector.get("path")
            if not isinstance(path, str) or not path:
                raise invalid("selector.path 不能为空")
            segments = path.split(".")
            cursor = target
            for segment in segments[:-1]:
                if not isinstance(cursor, dict) or segment not in cursor:
                    raise invalid(f"Artifact field 不存在: {path}")
                cursor = cursor[segment]
            if not isinstance(cursor, dict) or segments[-1] not in cursor:
                raise invalid(f"Artifact field 不存在: {path}")
            changed = cursor[segments[-1]] != mutation.value
            cursor[segments[-1]] = mutation.value
        else:
            raise invalid(
                "不支持的 Artifact Mutation",
                {"operation": mutation.operation},
            )

        return MutationResult(
            mutation_id=mutation.mutation_id,
            changed=changed,
            details={"artifact": target},
        )

    def apply_source(
        self, mutation: MutationDefinition, repository: str | Path
    ) -> MutationResult:
        if mutation.kind != "source":
            raise invalid("当前 Mutation 不是 source mutation")
        repository = Path(repository).resolve()
        file_value = self._string(mutation.target.get("file"), "target.file")
        path = (repository / file_value).resolve()
        if not path.is_relative_to(repository) or not path.is_file():
            raise invalid("Mutation target file 不存在或越界", {"path": str(path)})
        original = path.read_text(encoding="utf-8")
        updated = original

        if mutation.operation == "DropMarkedBlock":
            marker = self._string(mutation.selector.get("marker"), "selector.marker")
            begin = f"EVAL-BEGIN:{marker}"
            end = f"EVAL-END:{marker}"
            start = updated.find(begin)
            finish = updated.find(end)
            if start == -1 or finish == -1 or finish < start:
                raise invalid("未找到 Mutation marker", {"marker": marker})
            line_start = updated.rfind("\n", 0, start) + 1
            line_end = updated.find("\n", finish)
            if line_end == -1:
                line_end = len(updated)
            else:
                line_end += 1
            updated = updated[:line_start] + updated[line_end:]

        elif mutation.operation == "ReplaceMarkedValue":
            old = self._string(mutation.selector.get("old"), "selector.old")
            if old not in updated:
                raise invalid("未找到要替换的 Source 值")
            updated = updated.replace(old, str(mutation.value), 1)
        else:
            raise invalid(
                "不支持的 Source Mutation",
                {"operation": mutation.operation},
            )

        if updated != original:
            path.write_text(updated, encoding="utf-8")
        return MutationResult(
            mutation_id=mutation.mutation_id,
            changed=updated != original,
            details={"path": str(path)},
        )

    @staticmethod
    def _string(value: Any, name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise invalid(f"{name} 必须是非空字符串")
        return value.strip()
