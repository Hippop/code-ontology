from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import tree_sitter_java
import yaml
from tree_sitter import Language, Node, Parser

from .errors import invalid

EXTRACTOR_VERSION = "java-tree-sitter-0.2.0"
_IGNORED_PARTS = frozenset(
    {
        ".codegraph",
        ".git",
        ".gradle",
        ".idea",
        ".mvn",
        ".vscode",
        "build",
        "generated",
        "node_modules",
        "out",
        "target",
    }
)
_HTTP_ANNOTATIONS = {
    "GetMapping": "GET",
    "PostMapping": "POST",
    "PutMapping": "PUT",
    "PatchMapping": "PATCH",
    "DeleteMapping": "DELETE",
}
_TYPE_KINDS = {
    "class_declaration": "Class",
    "interface_declaration": "Interface",
    "enum_declaration": "Enum",
    "record_declaration": "Class",
    "annotation_type_declaration": "Interface",
}
_TYPE_ROLES = {
    "RestController": "SpringController",
    "Controller": "SpringController",
    "Service": "SpringService",
    "Repository": "SpringRepository",
    "Configuration": "SpringConfiguration",
    "Entity": "PersistenceEntity",
    "Component": "SpringComponent",
}
_SECRET_KEY = re.compile(
    r"(^|[._-])(password|passwd|secret|token|api[-_]?key|private[-_]?key)($|[._-])",
    re.IGNORECASE,
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _node_text(node: Node | None, source: bytes) -> str:
    if node is None:
        return ""
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _walk(node: Node):
    yield node
    for child in node.children:
        yield from _walk(child)


def _annotation_values(node: Node | None, source: bytes) -> dict[str, str]:
    if node is None:
        return {}
    result: dict[str, str] = {}
    for candidate in _walk(node):
        if candidate.type not in {"annotation", "marker_annotation"}:
            continue
        name = _node_text(candidate.child_by_field_name("name"), source).split(".")[-1]
        if name:
            result[name] = _node_text(candidate, source)
    return result


def _first_string(value: str) -> str | None:
    match = re.search(r'"([^"]*)"', value)
    return match.group(1) if match else None


def _mapping_path(value: str) -> str:
    return _first_string(value) or ""


def _join_api_path(base: str, child: str) -> str:
    parts = [part.strip("/") for part in (base, child) if part.strip("/")]
    return "/" + "/".join(parts) if parts else "/"


def _normalize_type(value: str) -> str:
    value = re.sub(r"@\w+(?:\([^)]*\))?\s*", "", value)
    value = re.sub(r"<.*>", "", value)
    value = value.replace("...", "").replace("[]", "")
    return value.strip().split()[-1] if value.strip() else ""


def _safe_git(repository: Path, *arguments: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repository), *arguments],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout.strip()


def _workspace_revision(repository: Path) -> str:
    digest = hashlib.sha256()
    for directory, child_directories, filenames in os.walk(repository):
        child_directories[:] = sorted(
            name for name in child_directories if name not in _IGNORED_PARTS
        )
        root = Path(directory)
        for filename in sorted(filenames):
            path = root / filename
            if not path.is_file():
                continue
            relative = path.relative_to(repository).as_posix()
            digest.update(relative.encode("utf-8"))
            try:
                digest.update(path.read_bytes())
            except OSError:
                continue
    return f"workspace:{digest.hexdigest()}"


def inspect_repository(
    repository_path: str | Path, repository_id: str | None = None
) -> dict[str, Any]:
    repository = Path(repository_path).resolve()
    if not repository.is_dir():
        raise invalid(f"仓库目录不存在: {repository}")
    remote = _safe_git(repository, "config", "--get", "remote.origin.url")
    commit = _safe_git(repository, "rev-parse", "HEAD")
    branch = _safe_git(repository, "branch", "--show-current")
    workspace_revision = _workspace_revision(repository)
    git_status = _safe_git(
        repository,
        "status",
        "--porcelain",
        "--untracked-files=all",
        "--",
        ".",
        ":(exclude).codegraph/**",
    )
    dirty = bool(git_status)
    revision = (
        f"{commit}+{workspace_revision}" if commit and dirty else commit
    ) or workspace_revision
    resolved_repository_id = repository_id or (
        "repo-" + hashlib.sha256(str(remote or repository).encode()).hexdigest()[:16]
    )
    return {
        "repositoryId": resolved_repository_id,
        "name": repository.name,
        "path": str(repository),
        "branch": branch,
        "commit": commit,
        "revision": revision,
        "remote": remote,
        "dirty": dirty,
    }


@dataclass
class MethodInfo:
    entity_id: str
    owner_id: str
    name: str
    arity: int
    invocations: list[tuple[str | None, str, int]] = field(default_factory=list)
    variables: dict[str, str] = field(default_factory=dict)


@dataclass
class TypeInfo:
    entity_id: str
    fqn: str
    package: str
    imports: dict[str, str]
    static_imports: dict[str, str]
    fields: dict[str, str] = field(default_factory=dict)
    methods: list[MethodInfo] = field(default_factory=list)
    extends: list[str] = field(default_factory=list)
    implements: list[str] = field(default_factory=list)


class RepositoryScanner:
    """Deterministic Java/Spring and adjacent-schema repository extractor."""

    def __init__(self) -> None:
        self.parser = Parser(Language(tree_sitter_java.language()))
        self.nodes: dict[str, dict[str, Any]] = {}
        self.edges: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.types: dict[str, TypeInfo] = {}
        self.type_by_simple_name: dict[str, list[str]] = {}
        self.methods: list[MethodInfo] = []
        self.failures: list[dict[str, str]] = []
        self.unresolved_calls: list[dict[str, str]] = []
        self.external_calls: list[dict[str, str]] = []
        self.repository: Path
        self.repository_id: str
        self.revision: str
        self.modules: dict[Path, str]
        self.module_metadata: dict[Path, dict[str, Any]] = {}
        self.build_dependencies: list[tuple[Path, str, str | None]] = []

    def scan(
        self, repository_path: str | Path, repository_id: str | None = None
    ) -> dict[str, Any]:
        repository = Path(repository_path).resolve()
        identity = inspect_repository(repository, repository_id)
        self.repository = repository
        self.revision = identity["revision"]
        self.repository_id = identity["repositoryId"]
        self.modules = self._extract_build_model()

        repository_node = f"code:{self.repository_id}:repository"
        self._add_node(
            repository_node,
            "Repository",
            label=repository.name,
            path=str(repository),
            revision=self.revision,
            branch=identity["branch"],
            remote=identity["remote"],
            dirty=identity["dirty"],
        )
        for module_root, module_id in self.modules.items():
            metadata = self.module_metadata.get(module_root, {})
            self._add_node(
                module_id,
                "Module",
                label=module_root.name or repository.name,
                relativePath=module_root.relative_to(repository).as_posix() or ".",
                revision=self.revision,
                **metadata,
            )
            self._add_edge(repository_node, "code:contains", module_id)
        for module_root, coordinate, version in self.build_dependencies:
            artifact_id = f"artifact:maven:{coordinate}"
            self._add_node(
                artifact_id,
                "BuildArtifact",
                label=coordinate,
                coordinate=coordinate,
                version=version,
                external=True,
            )
            self._add_edge(
                self.modules[module_root], "code:dependsOnArtifact", artifact_id
            )

        java_files = self._files("*.java")
        parsed_files = 0
        for path in java_files:
            try:
                self._extract_java(path)
                parsed_files += 1
            except Exception as error:  # noqa: BLE001 - isolate per-file parser failures.
                self.failures.append(
                    {
                        "file": path.relative_to(repository).as_posix(),
                        "error": str(error),
                    }
                )
        self._resolve_type_relations()
        self._resolve_calls()
        self._extract_configuration()
        self._extract_sql()
        self._extract_openapi()

        relation_counts = Counter(edge["relation"] for edge in self.edges.values())
        coverage = {
            "extractorVersion": EXTRACTOR_VERSION,
            "scannedAt": _now(),
            "javaFiles": len(java_files),
            "parsedJavaFiles": parsed_files,
            "failedJavaFiles": len(self.failures),
            "parseSuccessRate": (parsed_files / len(java_files) if java_files else 1.0),
            "nodeCount": len(self.nodes),
            "edgeCount": len(self.edges),
            "unresolvedCallCount": len(self.unresolved_calls),
            "externalCallCount": len(self.external_calls),
            "relationCounts": dict(sorted(relation_counts.items())),
            "failures": self.failures,
            "unresolvedCalls": self.unresolved_calls[:200],
            "externalCalls": self.external_calls[:200],
        }
        return {
            "repository": identity,
            "graph": {
                "graphSpace": "current",
                "revision": self.revision,
                "repositoryId": self.repository_id,
                "graphId": f"urn:graph:current:{self.repository_id}:{self.revision}",
                "graphType": "Current",
                "baseRevision": self.revision,
                "createdAt": _now(),
                "createdBy": f"extractor:{EXTRACTOR_VERSION}",
                "sourceArtifact": str(repository),
                "status": "Extracted",
                "validationStatus": "NotValidated",
                "nodes": sorted(self.nodes.values(), key=lambda item: item["id"]),
                "edges": sorted(
                    self.edges.values(),
                    key=lambda item: (
                        item["source"],
                        item["relation"],
                        item["target"],
                    ),
                ),
            },
            "coverage": coverage,
            "buildModel": {
                "modules": [
                    {
                        "id": module_id,
                        "path": root.relative_to(repository).as_posix() or ".",
                    }
                    for root, module_id in sorted(
                        self.modules.items(), key=lambda item: str(item[0])
                    )
                ]
            },
        }

    def _files(self, pattern: str) -> list[Path]:
        return [
            path
            for path in sorted(self.repository.rglob(pattern))
            if path.is_file()
            and not any(
                part in _IGNORED_PARTS
                for part in path.relative_to(self.repository).parts
            )
        ]

    def _extract_build_model(self) -> dict[Path, str]:
        roots: set[Path] = {self.repository}
        roots.update(path.parent for path in self._files("pom.xml"))
        roots.update(path.parent for path in self._files("build.gradle"))
        roots.update(path.parent for path in self._files("build.gradle.kts"))
        result: dict[Path, str] = {}
        for root in sorted(roots):
            relative = root.relative_to(self.repository).as_posix() or "."
            module_id = f"code:{self.repository_id}:module:{relative}"
            result[root] = module_id
            pom = root / "pom.xml"
            gradle = root / "build.gradle"
            gradle_kts = root / "build.gradle.kts"
            if pom.is_file():
                self._parse_maven_model(root, pom)
            elif gradle.is_file() or gradle_kts.is_file():
                self._parse_gradle_model(
                    root, gradle if gradle.is_file() else gradle_kts
                )
        return result

    def _parse_maven_model(self, root: Path, pom: Path) -> None:
        try:
            document = ET.parse(pom).getroot()
        except (OSError, ET.ParseError) as error:
            self.failures.append(
                {
                    "file": pom.relative_to(self.repository).as_posix(),
                    "error": f"Maven model parse: {error}",
                }
            )
            return

        def children(element: ET.Element, name: str) -> list[ET.Element]:
            return [child for child in element if child.tag.rsplit("}", 1)[-1] == name]

        def text(element: ET.Element, name: str) -> str | None:
            matches = children(element, name)
            if not matches or matches[0].text is None:
                return None
            return matches[0].text.strip()

        parent = children(document, "parent")
        group_id = text(document, "groupId") or (
            text(parent[0], "groupId") if parent else None
        )
        artifact_id = text(document, "artifactId")
        version = text(document, "version") or (
            text(parent[0], "version") if parent else None
        )
        self.module_metadata[root] = {
            "buildSystem": "Maven",
            "groupId": group_id,
            "artifactId": artifact_id,
            "version": version,
            "packaging": text(document, "packaging") or "jar",
        }
        dependency_sets = children(document, "dependencies")
        for dependency_set in dependency_sets:
            for dependency in children(dependency_set, "dependency"):
                dependency_group = text(dependency, "groupId")
                dependency_artifact = text(dependency, "artifactId")
                if not dependency_group or not dependency_artifact:
                    continue
                coordinate = f"{dependency_group}:{dependency_artifact}"
                self.build_dependencies.append(
                    (root, coordinate, text(dependency, "version"))
                )

    def _parse_gradle_model(self, root: Path, build_file: Path) -> None:
        try:
            text = build_file.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            self.failures.append(
                {
                    "file": build_file.relative_to(self.repository).as_posix(),
                    "error": f"Gradle model read: {error}",
                }
            )
            return
        self.module_metadata[root] = {
            "buildSystem": "Gradle",
            "buildFile": build_file.name,
        }
        dependency_pattern = re.compile(
            r"""(?:implementation|api|compileOnly|runtimeOnly|testImplementation)
                \s*(?:\(\s*)?["']([^:"']+):([^:"']+)(?::([^"']+))?["']""",
            re.VERBOSE,
        )
        for match in dependency_pattern.finditer(text):
            self.build_dependencies.append(
                (
                    root,
                    f"{match.group(1)}:{match.group(2)}",
                    match.group(3),
                )
            )

    def _module_for(self, path: Path) -> str:
        candidates = [root for root in self.modules if path.is_relative_to(root)]
        return self.modules[max(candidates, key=lambda item: len(item.parts))]

    def _evidence(self, path: Path, node: Node | None = None) -> dict[str, Any]:
        raw = path.read_bytes()
        evidence: dict[str, Any] = {
            "source": path.relative_to(self.repository).as_posix(),
            "sourceHash": _sha256_bytes(raw),
            "revision": self.revision,
            "extractor": EXTRACTOR_VERSION,
        }
        if node is not None:
            evidence["startLine"] = node.start_point.row + 1
            evidence["endLine"] = node.end_point.row + 1
        return evidence

    def _add_node(self, entity_id: str, entity_type: str, **properties: Any) -> None:
        candidate = {
            "id": entity_id,
            "type": entity_type,
            "logicalId": entity_id,
            "revisionId": f"{entity_id}@{self.revision}",
            "revision": self.revision,
            **{key: value for key, value in properties.items() if value is not None},
        }
        existing = self.nodes.get(entity_id)
        if existing:
            roles = set(existing.get("roles", [])) | set(candidate.get("roles", []))
            existing.update(candidate)
            if roles:
                existing["roles"] = sorted(roles)
        else:
            self.nodes[entity_id] = candidate

    def _add_edge(
        self, source: str, relation: str, target: str, **properties: Any
    ) -> None:
        key = (source, relation, target)
        self.edges[key] = {
            "source": source,
            "relation": relation,
            "target": target,
            "revision": self.revision,
            **properties,
        }

    def _extract_java(self, path: Path) -> None:
        source = path.read_bytes()
        tree = self.parser.parse(source)
        if tree.root_node.has_error:
            self.failures.append(
                {
                    "file": path.relative_to(self.repository).as_posix(),
                    "error": "tree-sitter reported syntax errors",
                }
            )
        package = ""
        imports: dict[str, str] = {}
        static_imports: dict[str, str] = {}
        for child in tree.root_node.named_children:
            if child.type == "package_declaration":
                text = _node_text(child, source)
                package = text.removeprefix("package").rstrip(";").strip()
            elif child.type == "import_declaration":
                text = _node_text(child, source)
                declaration = text.removeprefix("import").rstrip(";").strip()
                is_static = declaration.startswith("static ")
                imported = declaration.removeprefix("static ").strip()
                key = imported.rsplit(".", 1)[-1]
                if is_static:
                    static_imports[key] = imported
                else:
                    imports[key] = imported

        relative = path.relative_to(self.repository).as_posix()
        file_id = f"code:{self.repository_id}:file:{relative}"
        self._add_node(
            file_id,
            "SourceFile",
            label=path.name,
            relativePath=relative,
            language="Java",
            evidence=self._evidence(path),
        )
        self._add_edge(self._module_for(path), "code:contains", file_id)
        for child in tree.root_node.named_children:
            if child.type in _TYPE_KINDS:
                self._extract_type(
                    child,
                    source,
                    path,
                    package,
                    imports,
                    static_imports,
                    file_id,
                    None,
                )

    def _extract_type(
        self,
        node: Node,
        source: bytes,
        path: Path,
        package: str,
        imports: dict[str, str],
        static_imports: dict[str, str],
        file_id: str,
        enclosing_fqn: str | None,
    ) -> None:
        name = _node_text(node.child_by_field_name("name"), source)
        fqn = (
            f"{enclosing_fqn}.{name}"
            if enclosing_fqn
            else f"{package}.{name}".strip(".")
        )
        entity_id = f"code:{self.repository_id}:java:{fqn}"
        modifiers = next(
            (child for child in node.children if child.type == "modifiers"), None
        )
        annotations = _annotation_values(modifiers, source)
        roles = sorted(
            {
                role
                for annotation, role in _TYPE_ROLES.items()
                if annotation in annotations
            }
        )
        self._add_node(
            entity_id,
            _TYPE_KINDS[node.type],
            label=name,
            qualifiedName=fqn,
            package=package,
            annotations=sorted(annotations),
            roles=roles,
            evidence=self._evidence(path, node),
        )
        self._add_edge(file_id, "code:declares", entity_id)
        self._add_edge(entity_id, "code:belongsToModule", self._module_for(path))
        info = TypeInfo(entity_id, fqn, package, imports, static_imports)
        self.types[entity_id] = info
        self.type_by_simple_name.setdefault(name, []).append(entity_id)

        superclass = node.child_by_field_name("superclass")
        if superclass is not None:
            info.extends.append(_node_text(superclass, source))
        interfaces = node.child_by_field_name("interfaces")
        if interfaces is None:
            interfaces = next(
                (
                    child
                    for child in node.children
                    if child.type in {"super_interfaces", "extends_interfaces"}
                ),
                None,
            )
        if interfaces is not None:
            type_list = next(
                (child for child in _walk(interfaces) if child.type == "type_list"),
                interfaces,
            )
            info.implements.extend(
                _node_text(child, source)
                for child in type_list.named_children
                if child.type not in {"type_arguments", "type_list"}
            )

        base_path = ""
        if "RequestMapping" in annotations:
            base_path = _mapping_path(annotations["RequestMapping"])
        body = node.child_by_field_name("body")
        if body is None:
            return
        if node.type == "record_declaration":
            self._extract_record_components(node, source, path, info)
        for member in body.named_children:
            if member.type == "field_declaration":
                self._extract_field(member, source, path, info)
            elif member.type in {"method_declaration", "constructor_declaration"}:
                self._extract_method(member, source, path, info, base_path, annotations)
            elif member.type in _TYPE_KINDS:
                self._extract_type(
                    member,
                    source,
                    path,
                    package,
                    imports,
                    static_imports,
                    file_id,
                    fqn,
                )

        if "Entity" in annotations:
            table = _first_string(annotations.get("Table", "")) or name
            table_id = f"db:{self.repository_id}:table:{table}"
            self._add_node(
                table_id,
                "Table",
                label=table,
                tableName=table,
                evidence=self._evidence(path, node),
            )
            self._add_edge(entity_id, "code:mappedToTable", table_id)

        prefix = _first_string(annotations.get("ConfigurationProperties", ""))
        if prefix:
            for field_name in info.fields:
                key = f"{prefix}.{re.sub(r'(?<!^)(?=[A-Z])', '-', field_name).lower()}"
                self._add_configuration_key(
                    key, entity_id, path, source_kind="ConfigurationProperties"
                )

    def _extract_record_components(
        self, node: Node, source: bytes, path: Path, owner: TypeInfo
    ) -> None:
        parameters = node.child_by_field_name("parameters")
        if parameters is None:
            return
        for component in parameters.named_children:
            if component.type != "formal_parameter":
                continue
            name = _node_text(component.child_by_field_name("name"), source)
            type_text = _node_text(component.child_by_field_name("type"), source)
            field_id = f"{owner.entity_id}#field:{name}"
            accessor_id = f"{owner.entity_id}#{name}()"
            owner.fields[name] = type_text
            self._add_node(
                field_id,
                "Field",
                label=name,
                fieldType=type_text,
                recordComponent=True,
                evidence=self._evidence(path, component),
            )
            self._add_node(
                accessor_id,
                "Method",
                label=f"{owner.fqn}.{name}",
                methodName=name,
                signature=f"{name}()",
                returnType=type_text,
                generated=True,
                evidence=self._evidence(path, component),
            )
            self._add_edge(owner.entity_id, "code:declares", field_id)
            self._add_edge(owner.entity_id, "code:declares", accessor_id)
            accessor = MethodInfo(accessor_id, owner.entity_id, name, 0)
            owner.methods.append(accessor)
            self.methods.append(accessor)

    def _extract_field(
        self, node: Node, source: bytes, path: Path, owner: TypeInfo
    ) -> None:
        type_text = _node_text(node.child_by_field_name("type"), source)
        modifiers = next(
            (child for child in node.children if child.type == "modifiers"), None
        )
        annotations = _annotation_values(modifiers, source)
        for child in node.named_children:
            if child.type != "variable_declarator":
                continue
            name = _node_text(child.child_by_field_name("name"), source)
            field_id = f"{owner.entity_id}#field:{name}"
            owner.fields[name] = type_text
            self._add_node(
                field_id,
                "Field",
                label=name,
                fieldType=type_text,
                annotations=sorted(annotations),
                evidence=self._evidence(path, node),
            )
            self._add_edge(owner.entity_id, "code:declares", field_id)
            value_annotation = annotations.get("Value")
            if value_annotation:
                match = re.search(r"\$\{([^}:]+)(?::[^}]*)?\}", value_annotation)
                if match:
                    self._add_configuration_key(
                        match.group(1), field_id, path, source_kind="@Value"
                    )

    def _extract_method(
        self,
        node: Node,
        source: bytes,
        path: Path,
        owner: TypeInfo,
        base_path: str,
        owner_annotations: dict[str, str],
    ) -> None:
        name_node = node.child_by_field_name("name")
        name = _node_text(name_node, source) or owner.fqn.rsplit(".", 1)[-1]
        parameters_node = node.child_by_field_name("parameters")
        parameter_types: list[str] = []
        parameters: list[tuple[str, str, Node]] = []
        if parameters_node is not None:
            for parameter in parameters_node.named_children:
                if parameter.type not in {
                    "formal_parameter",
                    "spread_parameter",
                    "receiver_parameter",
                }:
                    continue
                parameter_type = _node_text(
                    parameter.child_by_field_name("type"), source
                )
                parameter_name = _node_text(
                    parameter.child_by_field_name("name"), source
                )
                parameter_types.append(parameter_type)
                parameters.append((parameter_name, parameter_type, parameter))
        signature = ",".join(_normalize_type(item) for item in parameter_types)
        method_id = f"{owner.entity_id}#{name}({signature})"
        modifiers = next(
            (child for child in node.children if child.type == "modifiers"), None
        )
        annotations = _annotation_values(modifiers, source)
        is_test = "Test" in annotations or "ParameterizedTest" in annotations
        entity_type = (
            "UnitTest"
            if is_test
            else ("Constructor" if node.type == "constructor_declaration" else "Method")
        )
        return_type = _node_text(node.child_by_field_name("type"), source)
        self._add_node(
            method_id,
            entity_type,
            label=f"{owner.fqn}.{name}",
            methodName=name,
            signature=f"{name}({signature})",
            returnType=return_type,
            annotations=sorted(annotations),
            evidence=self._evidence(path, node),
        )
        self._add_edge(owner.entity_id, "code:declares", method_id)
        for index, (parameter_name, parameter_type, parameter_node) in enumerate(
            parameters
        ):
            parameter_id = f"{method_id}#parameter:{index}:{parameter_name}"
            self._add_node(
                parameter_id,
                "Parameter",
                label=parameter_name,
                parameterType=parameter_type,
                position=index,
                evidence=self._evidence(path, parameter_node),
            )
            self._add_edge(method_id, "code:declares", parameter_id)

        info = MethodInfo(
            method_id,
            owner.entity_id,
            name,
            len(parameter_types),
            variables={
                parameter_name: parameter_type
                for parameter_name, parameter_type, _ in parameters
            },
        )
        body = node.child_by_field_name("body")
        if body is not None:
            for candidate in _walk(body):
                if candidate.type != "local_variable_declaration":
                    continue
                local_type = _node_text(candidate.child_by_field_name("type"), source)
                for declarator in candidate.named_children:
                    if declarator.type == "variable_declarator":
                        local_name = _node_text(
                            declarator.child_by_field_name("name"), source
                        )
                        info.variables[local_name] = local_type
            for candidate in _walk(body):
                if candidate.type != "method_invocation":
                    continue
                invoked_name = _node_text(candidate.child_by_field_name("name"), source)
                object_node = candidate.child_by_field_name("object")
                invoked_object = (
                    _node_text(object_node, source) if object_node is not None else None
                )
                arguments = candidate.child_by_field_name("arguments")
                arity = len(arguments.named_children) if arguments is not None else 0
                info.invocations.append((invoked_object, invoked_name, arity))
        owner.methods.append(info)
        self.methods.append(info)

        mapping_annotation = next(
            (
                annotation
                for annotation in (
                    *_HTTP_ANNOTATIONS,
                    "RequestMapping",
                )
                if annotation in annotations
            ),
            None,
        )
        if mapping_annotation:
            if mapping_annotation == "RequestMapping":
                match = re.search(
                    r"RequestMethod\.(GET|POST|PUT|PATCH|DELETE)",
                    annotations[mapping_annotation],
                )
                http_method = match.group(1) if match else "ANY"
            else:
                http_method = _HTTP_ANNOTATIONS[mapping_annotation]
            operation_path = _join_api_path(
                base_path, _mapping_path(annotations[mapping_annotation])
            )
            operation_id = f"api:{self.repository_id}:{http_method}:{operation_path}"
            self._add_node(
                operation_id,
                "APIOperation",
                label=f"{http_method} {operation_path}",
                httpMethod=http_method,
                path=operation_path,
                evidence=self._evidence(path, node),
            )
            self._add_edge(method_id, "code:implementsOperation", operation_id)
            self._add_edge(owner.entity_id, "code:exposes", operation_id)

        listener_annotation = next(
            (
                annotation
                for annotation in ("KafkaListener", "RabbitListener", "JmsListener")
                if annotation in annotations
            ),
            None,
        )
        if listener_annotation:
            annotation_value = annotations[listener_annotation]
            channel = _first_string(annotation_value) or "unresolved-channel"
            technology = {
                "KafkaListener": "Kafka",
                "RabbitListener": "RabbitMQ",
                "JmsListener": "JMS",
            }[listener_annotation]
            event_type_id = (
                f"message:{self.repository_id}:{technology.lower()}:{channel}"
            )
            self._add_node(
                event_type_id,
                "EventType",
                label=channel,
                channel=channel,
                technology=technology,
                evidence=self._evidence(path, node),
            )
            self._add_edge(
                method_id,
                "code:consumesEvent",
                event_type_id,
                listenerAnnotation=listener_annotation,
            )
            if parameters:
                payload_type_id = self._resolve_type_id(parameters[0][1], owner)
                if payload_type_id:
                    self._add_edge(
                        event_type_id,
                        "code:usesPayloadType",
                        payload_type_id,
                    )

        if is_test:
            for invoked_object, invoked_name, arity in info.invocations:
                # Resolution later also records the direct call. This relation makes
                # the verification intent explicit for test-selection queries.
                if invoked_name.startswith(("assert", "verify")):
                    continue

    def _resolve_type_id(self, raw: str, owner: TypeInfo) -> str | None:
        normalized = _normalize_type(raw)
        if not normalized or normalized in {
            "boolean",
            "byte",
            "char",
            "double",
            "float",
            "int",
            "long",
            "short",
            "void",
            "String",
            "Object",
        }:
            return None
        simple = normalized.rsplit(".", 1)[-1]
        imported = owner.imports.get(simple)
        candidates = []
        if imported:
            candidates.extend(
                info.entity_id for info in self.types.values() if info.fqn == imported
            )
        package_name = f"{owner.package}.{simple}".strip(".")
        candidates.extend(
            info.entity_id for info in self.types.values() if info.fqn == package_name
        )
        candidates.extend(self.type_by_simple_name.get(simple, []))
        unique = list(dict.fromkeys(candidates))
        return unique[0] if len(unique) == 1 else None

    def _resolve_type_relations(self) -> None:
        for info in self.types.values():
            for raw in info.extends:
                target = self._resolve_type_id(raw, info)
                if target:
                    self._add_edge(info.entity_id, "code:extendsType", target)
            for raw in info.implements:
                target = self._resolve_type_id(raw, info)
                if target:
                    self._add_edge(info.entity_id, "code:implementsType", target)
            for field_name, raw_type in info.fields.items():
                target = self._resolve_type_id(raw_type, info)
                if target:
                    self._add_edge(
                        f"{info.entity_id}#field:{field_name}",
                        "code:hasFieldType",
                        target,
                    )
            if "SpringRepository" in self.nodes[info.entity_id].get("roles", []):
                for raw_interface in info.implements:
                    match = re.search(r"<\s*([^,>]+)", raw_interface)
                    if not match:
                        continue
                    entity_type = self._resolve_type_id(match.group(1), info)
                    if not entity_type:
                        continue
                    self._add_edge(info.entity_id, "code:dataDependsOn", entity_type)
                    for edge in list(self.edges.values()):
                        if (
                            edge["source"] == entity_type
                            and edge["relation"] == "code:mappedToTable"
                        ):
                            self._add_edge(
                                info.entity_id,
                                "code:readsTable",
                                edge["target"],
                            )
                            self._add_edge(
                                info.entity_id,
                                "code:writesTable",
                                edge["target"],
                            )

    def _is_external_call(
        self,
        owner: TypeInfo,
        method: MethodInfo,
        invoked_object: str | None,
        name: str,
    ) -> bool:
        def static_import_is_external(imported_name: str) -> bool:
            imported = (
                owner.static_imports.get(imported_name)
                or owner.static_imports.get("*")
            )
            if not imported:
                return False
            imported_owner = (
                imported.removesuffix(".*")
                if imported.endswith(".*")
                else imported.rsplit(".", 1)[0]
            )
            return not any(
                candidate.fqn == imported_owner for candidate in self.types.values()
            )

        if not invoked_object or invoked_object == "this":
            return static_import_is_external(name)

        root_object = invoked_object.split(".", 1)[0]
        raw_type = owner.fields.get(root_object) or method.variables.get(root_object)
        if raw_type:
            simple_type = _normalize_type(raw_type).rsplit(".", 1)[-1]
            imported_type = owner.imports.get(simple_type)
            if imported_type and self._resolve_type_id(raw_type, owner) is None:
                return True
        else:
            imported_type = owner.imports.get(root_object)
            if imported_type and self._resolve_type_id(imported_type, owner) is None:
                return True

        chained_static_call = re.match(r"([A-Za-z_$][\w$]*)\s*\(", invoked_object)
        return bool(
            chained_static_call
            and static_import_is_external(chained_static_call.group(1))
        )

    def _resolve_calls(self) -> None:
        method_index: dict[tuple[str, str, int], list[str]] = {}
        global_index: dict[tuple[str, int], list[str]] = {}
        for method in self.methods:
            method_index.setdefault(
                (method.owner_id, method.name, method.arity), []
            ).append(method.entity_id)
            global_index.setdefault((method.name, method.arity), []).append(
                method.entity_id
            )
        for method in self.methods:
            owner = self.types[method.owner_id]
            for invoked_object, name, arity in method.invocations:
                target_owner = owner.entity_id
                if invoked_object and invoked_object != "this":
                    root_object = invoked_object.split(".", 1)[0]
                    raw_type = owner.fields.get(root_object) or method.variables.get(
                        root_object
                    )
                    target_owner = (
                        self._resolve_type_id(raw_type, owner) if raw_type else None
                    )
                candidates = (
                    method_index.get((target_owner, name, arity), [])
                    if target_owner
                    else []
                )
                if not candidates:
                    candidates = global_index.get((name, arity), [])
                candidates = list(dict.fromkeys(candidates))
                if len(candidates) == 1:
                    relation = (
                        "code:verifies"
                        if self.nodes[method.entity_id]["type"]
                        in {"UnitTest", "IntegrationTest", "ContractTest"}
                        else "code:callsDirectly"
                    )
                    self._add_edge(
                        method.entity_id,
                        relation,
                        candidates[0],
                        confidence=1.0 if target_owner else 0.8,
                        evidenceType="StaticAST",
                    )
                else:
                    call = {
                        "caller": method.entity_id,
                        "object": invoked_object or "",
                        "method": name,
                        "arity": str(arity),
                        "candidateCount": str(len(candidates)),
                    }
                    if self._is_external_call(owner, method, invoked_object, name):
                        self.external_calls.append(call)
                    else:
                        self.unresolved_calls.append(call)

    def _add_configuration_key(
        self, key: str, reader_id: str, path: Path, *, source_kind: str
    ) -> None:
        entity_id = f"config:{self.repository_id}:{key}"
        self._add_node(
            entity_id,
            "ConfigurationKey",
            label=key,
            key=key,
            sourceKind=source_kind,
            sensitive=bool(_SECRET_KEY.search(key)),
            evidence=self._evidence(path),
        )
        self._add_edge(reader_id, "code:readsConfiguration", entity_id)

    def _extract_configuration(self) -> None:
        candidates = [
            *self._files("application*.yml"),
            *self._files("application*.yaml"),
            *self._files("application*.properties"),
        ]
        for path in sorted(set(candidates)):
            source_id = (
                f"config:{self.repository_id}:source:"
                f"{path.relative_to(self.repository).as_posix()}"
            )
            self._add_node(
                source_id,
                "ConfigurationSource",
                label=path.name,
                relativePath=path.relative_to(self.repository).as_posix(),
                evidence=self._evidence(path),
            )
            values: dict[str, Any] = {}
            try:
                if path.suffix == ".properties":
                    for line in path.read_text(encoding="utf-8").splitlines():
                        stripped = line.strip()
                        if not stripped or stripped.startswith(("#", "!")):
                            continue
                        key, separator, value = stripped.partition("=")
                        if separator:
                            values[key.strip()] = value.strip()
                else:
                    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

                    def flatten(
                        prefix: str, value: Any, output: dict[str, Any] = values
                    ) -> None:
                        if isinstance(value, dict):
                            for child_key, child_value in value.items():
                                flatten(f"{prefix}.{child_key}".strip("."), child_value)
                        else:
                            output[prefix] = value

                    flatten("", loaded)
            except (OSError, UnicodeError, yaml.YAMLError) as error:
                self.failures.append(
                    {
                        "file": path.relative_to(self.repository).as_posix(),
                        "error": f"configuration parse: {error}",
                    }
                )
                continue
            for key, value in values.items():
                key_id = f"config:{self.repository_id}:{key}"
                sensitive = bool(_SECRET_KEY.search(key))
                self._add_node(
                    key_id,
                    "ConfigurationKey",
                    label=key,
                    key=key,
                    sensitive=sensitive,
                    valueType=type(value).__name__,
                    value=None if sensitive else value,
                    redacted=sensitive,
                    evidence=self._evidence(path),
                )
                self._add_edge(source_id, "code:definesConfiguration", key_id)

    def _extract_sql(self) -> None:
        for path in self._files("*.sql"):
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as error:
                self.failures.append(
                    {
                        "file": path.relative_to(self.repository).as_posix(),
                        "error": f"SQL read: {error}",
                    }
                )
                continue
            for match in re.finditer(
                r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([`\"\w.]+)\s*\((.*?)\)\s*;",
                text,
                re.IGNORECASE | re.DOTALL,
            ):
                table = match.group(1).strip('`"')
                table_id = f"db:{self.repository_id}:table:{table}"
                self._add_node(
                    table_id,
                    "Table",
                    label=table,
                    tableName=table,
                    evidence=self._evidence(path),
                )
                for position, definition in enumerate(match.group(2).split(",")):
                    column_match = re.match(
                        r"\s*([`\"\w]+)\s+([A-Za-z][A-Za-z0-9_]*(?:\([^)]*\))?)",
                        definition,
                    )
                    if not column_match:
                        continue
                    column = column_match.group(1).strip('`"')
                    if column.upper() in {
                        "PRIMARY",
                        "FOREIGN",
                        "UNIQUE",
                        "CHECK",
                        "CONSTRAINT",
                    }:
                        continue
                    column_id = f"{table_id}#column:{column}"
                    self._add_node(
                        column_id,
                        "Column",
                        label=column,
                        columnName=column,
                        dataType=column_match.group(2),
                        position=position,
                        evidence=self._evidence(path),
                    )
                    self._add_edge(table_id, "code:contains", column_id)

    def _extract_openapi(self) -> None:
        candidates = [
            path
            for path in [
                *self._files("*.yaml"),
                *self._files("*.yml"),
                *self._files("*.json"),
            ]
            if "openapi" in path.name.lower() or "swagger" in path.name.lower()
        ]
        for path in sorted(set(candidates)):
            try:
                if path.suffix == ".json":
                    document = json.loads(path.read_text(encoding="utf-8"))
                else:
                    document = yaml.safe_load(path.read_text(encoding="utf-8"))
            except (
                OSError,
                UnicodeError,
                json.JSONDecodeError,
                yaml.YAMLError,
            ) as error:
                self.failures.append(
                    {
                        "file": path.relative_to(self.repository).as_posix(),
                        "error": f"OpenAPI parse: {error}",
                    }
                )
                continue
            if not isinstance(document, dict) or "openapi" not in document:
                continue
            for api_path, operations in document.get("paths", {}).items():
                if not isinstance(operations, dict):
                    continue
                for method, operation in operations.items():
                    if method.upper() not in {
                        "GET",
                        "POST",
                        "PUT",
                        "PATCH",
                        "DELETE",
                        "OPTIONS",
                        "HEAD",
                    }:
                        continue
                    operation_id = (
                        f"api:{self.repository_id}:{method.upper()}:{api_path}"
                    )
                    self._add_node(
                        operation_id,
                        "APIOperation",
                        label=f"{method.upper()} {api_path}",
                        httpMethod=method.upper(),
                        path=api_path,
                        operationId=(
                            operation.get("operationId")
                            if isinstance(operation, dict)
                            else None
                        ),
                        evidence=self._evidence(path),
                    )
            schemas = (
                document.get("components", {}).get("schemas", {})
                if isinstance(document.get("components"), dict)
                else {}
            )
            for schema_name, schema in schemas.items():
                schema_id = f"api:{self.repository_id}:schema:{schema_name}"
                self._add_node(
                    schema_id,
                    "Schema",
                    label=schema_name,
                    schemaName=schema_name,
                    evidence=self._evidence(path),
                )
                if not isinstance(schema, dict):
                    continue
                required = set(schema.get("required", []))
                for field_name, field_schema in schema.get("properties", {}).items():
                    field_id = f"{schema_id}#field:{field_name}"
                    self._add_node(
                        field_id,
                        "SchemaField",
                        label=field_name,
                        fieldName=field_name,
                        required=field_name in required,
                        fieldType=(
                            field_schema.get("type")
                            if isinstance(field_schema, dict)
                            else None
                        ),
                        evidence=self._evidence(path),
                    )
                    self._add_edge(schema_id, "code:hasSchemaField", field_id)
