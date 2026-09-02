from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from .engineering_semantics import EngineeringSemantics, local_name, node_type


GENERATION_CONTRACT_TYPES = frozenset(
    {
        "RequirementContract",
        "SpecificationContract",
        "BehaviorContract",
        "ConstraintContract",
        "StateContract",
        "InputOutputContract",
    }
)
_TYPE_EXPRESSION = re.compile(r"^[A-Za-z_][A-Za-z0-9_., |\[\]]*$")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _safe_target(value: Any) -> PurePosixPath:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("generation.targetPath must be a non-empty relative path")
    target = PurePosixPath(value)
    if target.is_absolute() or ".." in target.parts or target.suffix != ".py":
        raise ValueError("generation.targetPath must be a relative Python file without '..'")
    return target


def _type_expression(value: Any, name: str) -> str:
    text = str(value or "Any").strip()
    if not _TYPE_EXPRESSION.fullmatch(text):
        raise ValueError(f"{name} contains an unsupported Python type expression")
    return text


def _symbol(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text.isidentifier():
        raise ValueError(f"{name} must be a Python identifier")
    return text


class OntologyCodeGenerator:
    """Generate deterministic Python artifacts from governed requirement contracts."""

    def __init__(self, graph: Mapping[str, Any]) -> None:
        self.graph = dict(graph)
        self.semantics = EngineeringSemantics(graph)
        self.nodes = self.semantics.nodes
        self.edges = self.semantics.edges
        self.node_by_id = self.semantics.node_by_id
        self.incoming: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.outgoing: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for edge in self.edges:
            source = str(edge.get("source", ""))
            target = str(edge.get("target", ""))
            if source and target:
                self.outgoing[source].append(edge)
                self.incoming[target].append(edge)

    def generation_contracts(self) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        result: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for contract in sorted(self.nodes, key=lambda item: str(item.get("id", ""))):
            if node_type(contract) not in GENERATION_CONTRACT_TYPES:
                continue
            generation = contract.get("generation")
            if generation is None:
                continue
            if not isinstance(generation, Mapping):
                raise ValueError(f"{contract.get('id')}.generation must be an object")
            owners = [
                self.node_by_id.get(str(edge.get("source")))
                for edge in self.incoming.get(str(contract.get("id")), [])
                if local_name(edge.get("relation")) in {"definesContract", "define"}
            ]
            owners = [item for item in owners if node_type(item) == "EngineeringRequirement"]
            if len(owners) != 1:
                raise ValueError(
                    f"Generation contract {contract.get('id')} must have exactly one EngineeringRequirement owner"
                )
            result.append((contract, owners[0]))
        return result

    def _requirement_record(self, requirement: Mapping[str, Any]) -> dict[str, Any]:
        requirement_id = str(requirement["id"])

        def targets(relations: set[str], *, direction: str = "out") -> tuple[str, ...]:
            edges = self.outgoing[requirement_id] if direction == "out" else self.incoming[requirement_id]
            side = "target" if direction == "out" else "source"
            return tuple(
                sorted(
                    {
                        str(edge[side])
                        for edge in edges
                        if local_name(edge.get("relation")) in relations
                    }
                )
            )

        return {
            "requirement_id": requirement_id,
            "label": str(requirement.get("label", requirement_id)),
            "capability_ids": targets({"specifiesCapability", "specify"}),
            "contract_ids": targets({"definesContract", "define"}),
            "implementation_ids": targets({"implementsRequirement"}, direction="in"),
            "verification_ids": tuple(
                sorted(
                    set(targets({"verifiesRequirement"}, direction="in"))
                    | set(targets({"verifies"}, direction="in"))
                )
            ),
        }

    def _render_registry(self, contract: Mapping[str, Any]) -> str:
        requirements = [
            self._requirement_record(node)
            for node in sorted(self.nodes, key=lambda item: str(item.get("id", "")))
            if node_type(node) == "EngineeringRequirement"
        ]
        model_id = str(self.graph.get("graphId", "engineering-model"))
        model_revision = str(self.graph.get("revision", "unversioned"))
        lines = [
            '"""Generated from the governed engineering ontology model. Do not edit manually."""',
            "",
            "from __future__ import annotations",
            "",
            "from dataclasses import dataclass",
            "",
            f"MODEL_ID = {model_id!r}",
            f"MODEL_REVISION = {model_revision!r}",
            f"GENERATION_CONTRACT_ID = {str(contract['id'])!r}",
            "",
            "",
            "@dataclass(frozen=True)",
            "class EngineeringRequirementRecord:",
            "    requirement_id: str",
            "    label: str",
            "    capability_ids: tuple[str, ...]",
            "    contract_ids: tuple[str, ...]",
            "    implementation_ids: tuple[str, ...]",
            "    verification_ids: tuple[str, ...]",
            "",
            "",
            "ENGINEERING_REQUIREMENTS = (",
        ]
        for item in requirements:
            lines.extend(
                [
                    "    EngineeringRequirementRecord(",
                    f"        requirement_id={item['requirement_id']!r},",
                    f"        label={item['label']!r},",
                    f"        capability_ids={item['capability_ids']!r},",
                    f"        contract_ids={item['contract_ids']!r},",
                    f"        implementation_ids={item['implementation_ids']!r},",
                    f"        verification_ids={item['verification_ids']!r},",
                    "    ),",
                ]
            )
        lines.extend(
            [
                ")",
                "",
                "REQUIREMENT_BY_ID = {item.requirement_id: item for item in ENGINEERING_REQUIREMENTS}",
                "",
                "",
                "def get_requirement(requirement_id: str) -> EngineeringRequirementRecord:",
                "    return REQUIREMENT_BY_ID[requirement_id]",
                "",
            ]
        )
        return "\n".join(lines)

    @staticmethod
    def _render_dataclass(generation: Mapping[str, Any]) -> str:
        symbol = _symbol(generation.get("symbol"), "generation.symbol")
        fields = generation.get("fields", [])
        if not isinstance(fields, list) or not fields:
            raise ValueError("python-dataclass generation requires non-empty fields")
        lines = [
            '"""Generated from a governed RequirementContract. Do not edit manually."""',
            "",
            "from __future__ import annotations",
            "",
            "from dataclasses import dataclass",
            "from typing import Any",
            "",
            "",
            "@dataclass(frozen=True)",
            f"class {symbol}:",
        ]
        for index, value in enumerate(fields):
            if not isinstance(value, Mapping):
                raise ValueError(f"generation.fields[{index}] must be an object")
            name = _symbol(value.get("name"), f"generation.fields[{index}].name")
            annotation = _type_expression(value.get("type", "Any"), f"generation.fields[{index}].type")
            suffix = f" = {value['default']!r}" if "default" in value else ""
            lines.append(f"    {name}: {annotation}{suffix}")
        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _render_protocol(generation: Mapping[str, Any]) -> str:
        symbol = _symbol(generation.get("symbol"), "generation.symbol")
        methods = generation.get("methods", [])
        if not isinstance(methods, list) or not methods:
            raise ValueError("python-protocol generation requires non-empty methods")
        lines = [
            '"""Generated from a governed RequirementContract. Do not edit manually."""',
            "",
            "from __future__ import annotations",
            "",
            "from typing import Any, Protocol",
            "",
            "",
            f"class {symbol}(Protocol):",
        ]
        for index, value in enumerate(methods):
            if not isinstance(value, Mapping):
                raise ValueError(f"generation.methods[{index}] must be an object")
            name = _symbol(value.get("name"), f"generation.methods[{index}].name")
            parameters = value.get("parameters", [])
            if not isinstance(parameters, list):
                raise ValueError(f"generation.methods[{index}].parameters must be an array")
            rendered = ["self"]
            for p_index, parameter in enumerate(parameters):
                if not isinstance(parameter, Mapping):
                    raise ValueError("method parameter must be an object")
                p_name = _symbol(parameter.get("name"), f"parameter[{p_index}].name")
                p_type = _type_expression(parameter.get("type", "Any"), f"parameter[{p_index}].type")
                rendered.append(f"{p_name}: {p_type}")
            returns = _type_expression(value.get("returns", "None"), f"generation.methods[{index}].returns")
            lines.append(f"    def {name}({', '.join(rendered)}) -> {returns}: ...")
        lines.append("")
        return "\n".join(lines)

    def render(self, contract: Mapping[str, Any]) -> tuple[PurePosixPath, str]:
        generation = contract["generation"]
        target = _safe_target(generation.get("targetPath"))
        kind = str(generation.get("kind", ""))
        if kind == "python-engineering-registry":
            source = self._render_registry(contract)
        elif kind == "python-dataclass":
            source = self._render_dataclass(generation)
        elif kind == "python-protocol":
            source = self._render_protocol(generation)
        else:
            raise ValueError(f"Unsupported generation kind: {kind}")
        compile(source, str(target), "exec")
        return target, source

    def generate(
        self,
        output_root: str | Path,
        *,
        apply: bool = False,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        validation = self.semantics.validate()
        if not validation["conforms"]:
            raise ValueError(f"Engineering model does not conform: {validation['issues']}")
        root = Path(output_root).resolve()
        artifacts: list[dict[str, Any]] = []
        for contract, requirement in self.generation_contracts():
            target, source = self.render(contract)
            destination = (root / Path(*target.parts)).resolve()
            if root != destination and root not in destination.parents:
                raise ValueError("Generated target escapes output root")
            content_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
            status = "Planned"
            if destination.exists():
                current = destination.read_text(encoding="utf-8")
                if current == source:
                    status = "Unchanged"
                elif not overwrite:
                    raise FileExistsError(f"Refusing to overwrite generated artifact: {destination}")
                else:
                    status = "Updated"
            elif apply:
                status = "Created"
            if apply and status in {"Created", "Updated"}:
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(source, encoding="utf-8")
            artifacts.append(
                {
                    "contractId": contract["id"],
                    "requirementId": requirement["id"],
                    "targetPath": target.as_posix(),
                    "contentHash": content_hash,
                    "status": status,
                    "source": source if not apply else None,
                }
            )
        return {
            "modelId": self.graph.get("graphId"),
            "modelRevision": self.graph.get("revision"),
            "applied": apply,
            "artifactCount": len(artifacts),
            "artifacts": artifacts,
            "inputHash": hashlib.sha256(_canonical_json(self.graph).encode("utf-8")).hexdigest(),
        }


def load_model(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError("Engineering model must be a JSON object")
    return dict(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="code-ontology-generate")
    parser.add_argument("model", type=Path)
    parser.add_argument("--output", type=Path, default=Path.cwd())
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    arguments = parser.parse_args(argv)
    result = OntologyCodeGenerator(load_model(arguments.model)).generate(
        arguments.output,
        apply=arguments.apply,
        overwrite=arguments.overwrite,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
