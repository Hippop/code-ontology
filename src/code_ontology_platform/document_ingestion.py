from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

import yaml

from .errors import invalid
from .store import content_hash

EXTRACTOR_VERSION = "markdown-requirement-ir-0.1.0"
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.+?)\s*$")
_EXPLICIT_ID = re.compile(r"^\[([A-Za-z0-9_.:-]+)]\s*(.*)$")
_CODE_TOKEN = re.compile(r"`([^`]+)`")
_HTTP_OPERATION = re.compile(
    r"\b(GET|POST|PUT|PATCH|DELETE)\s+(/[^\s`]+)", re.IGNORECASE
)


@dataclass(frozen=True)
class Section:
    section_id: str
    level: int
    title: str
    start_line: int
    end_line: int
    text: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "sectionId": self.section_id,
            "level": self.level,
            "title": self.title,
            "startLine": self.start_line,
            "endLine": self.end_line,
            "text": self.text,
        }


def parse_design_document(content: str) -> dict[str, Any]:
    if not isinstance(content, str) or not content.strip():
        raise invalid("设计文档内容不能为空")
    metadata: dict[str, Any] = {}
    body = content
    body_start = 1
    if content.startswith("---\n"):
        end = content.find("\n---\n", 4)
        if end >= 0:
            try:
                loaded = yaml.safe_load(content[4:end]) or {}
            except yaml.YAMLError as error:
                raise invalid(f"设计文档 Front Matter 非法: {error}") from error
            if not isinstance(loaded, dict):
                raise invalid("设计文档 Front Matter 必须是 object")
            metadata = loaded
            body_start = content[: end + 5].count("\n") + 1
            body = content[end + 5 :]

    lines = body.splitlines()
    headings: list[tuple[int, int, str]] = []
    for index, line in enumerate(lines):
        match = _HEADING.match(line)
        if match:
            headings.append((index, len(match.group(1)), match.group(2).strip()))
    sections: list[Section] = []
    if not headings:
        sections.append(
            Section(
                "root",
                1,
                str(metadata.get("title", "Document")),
                body_start,
                body_start + max(len(lines) - 1, 0),
                body.strip(),
            )
        )
    else:
        for position, (line_index, level, title) in enumerate(headings):
            end_index = (
                headings[position + 1][0] - 1
                if position + 1 < len(headings)
                else len(lines) - 1
            )
            section_lines = lines[line_index + 1 : end_index + 1]
            section_id = (
                f"section-{position + 1}-"
                + hashlib.sha256(title.encode("utf-8")).hexdigest()[:8]
            )
            sections.append(
                Section(
                    section_id,
                    level,
                    title,
                    body_start + line_index,
                    body_start + end_index,
                    "\n".join(section_lines).strip(),
                )
            )
    return {
        "metadata": metadata,
        "contentHash": content_hash(content),
        "sections": [section.as_dict() for section in sections],
        "lineCount": content.count("\n") + 1,
    }


def _section_kind(title: str) -> str:
    value = title.lower()
    rules = (
        (("goal", "目标", "背景", "business objective"), "goal"),
        (("scope", "范围", "非范围"), "scope"),
        (("process", "flow", "流程", "use case", "场景", "步骤"), "process"),
        (("rule", "规则", "约束"), "businessRule"),
        (("api", "接口", "contract", "契约"), "contract"),
        (("database", "数据库", "data", "数据", "migration", "迁移"), "data"),
        (("event", "message", "消息", "事件"), "event"),
        (("config", "配置", "feature flag"), "configuration"),
        (("accept", "验收", "test", "测试"), "acceptance"),
        (("deploy", "发布", "部署", "rollback", "回滚"), "deployment"),
        (("unresolved", "待定", "问题", "question"), "unresolved"),
        (("implementation", "实现建议", "技术方案"), "suggestion"),
    )
    for keywords, kind in rules:
        if any(keyword in value for keyword in keywords):
            return kind
    return "general"


def _items(section: dict[str, Any]) -> list[tuple[str | None, str]]:
    result: list[tuple[str | None, str]] = []
    for line in section["text"].splitlines():
        match = _LIST_ITEM.match(line)
        if not match:
            continue
        value = match.group(1).strip()
        explicit = _EXPLICIT_ID.match(value)
        if explicit:
            result.append((explicit.group(1), explicit.group(2).strip()))
        elif value:
            result.append((None, value))
    if not result and section["text"].strip():
        paragraphs = [
            value.strip()
            for value in re.split(r"\n\s*\n", section["text"])
            if value.strip()
        ]
        result.extend((None, value) for value in paragraphs)
    return result


def _desired_type(kind: str, text: str, explicit_id: str | None = None) -> str | None:
    if kind == "process":
        marker = (explicit_id or "") + " " + text
        if explicit_id and explicit_id.upper().startswith(("STEP", "BPS")):
            return "BusinessProcessStep"
        if "步骤" in marker.lower() or marker.lower().startswith("step"):
            return "BusinessProcessStep"
        return "BusinessProcess"
    if kind == "businessRule":
        return "BusinessRule"
    if kind == "contract":
        if "field" in text.lower() or "字段" in text:
            return "DesiredSchemaField"
        return "DesiredAPIOperation"
    if kind == "data":
        return "DesiredDatabaseObject"
    if kind == "event":
        return "DesiredEventType"
    if kind == "configuration":
        return "DesiredConfigurationKey"
    if kind == "acceptance":
        return "DesiredTestObligation"
    if kind == "deployment":
        return "DesiredDeploymentAction"
    if kind == "goal":
        return "DesiredBusinessEntity"
    return None


def extract_requirement_ir(
    *,
    requirement_id: str,
    design_revision_id: str,
    parsed_document: dict[str, Any],
) -> dict[str, Any]:
    evidence: list[dict[str, Any]] = []
    desired_entities: list[dict[str, Any]] = []
    suggestions: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    scope: list[str] = []
    active_process_id: str | None = None
    process_step_sequence = 0

    for section in parsed_document["sections"]:
        kind = _section_kind(section["title"])
        for index, (explicit_id, text) in enumerate(_items(section)):
            evidence_id = (
                f"evidence:{design_revision_id}:{section['sectionId']}:{index + 1}"
            )
            evidence.append(
                {
                    "evidenceId": evidence_id,
                    "sectionId": section["sectionId"],
                    "sectionTitle": section["title"],
                    "sourceText": text,
                    "startLine": section["startLine"],
                    "endLine": section["endLine"],
                    "confidence": 1.0,
                    "sourceCategory": "Explicit",
                }
            )
            if kind == "scope":
                scope.append(text)
                continue
            if kind == "suggestion":
                suggestions.append(
                    {
                        "suggestionId": explicit_id
                        or "suggestion-"
                        + hashlib.sha256(text.encode()).hexdigest()[:12],
                        "text": text,
                        "evidenceRefs": [evidence_id],
                        "sourceCategory": "Suggested",
                    }
                )
                continue
            if (
                kind == "unresolved"
                or "待定" in text
                or "TODO" in text.upper()
                or text.rstrip().endswith(("?", "？"))
            ):
                unresolved.append(
                    {
                        "questionId": explicit_id
                        or "question-" + hashlib.sha256(text.encode()).hexdigest()[:12],
                        "question": text,
                        "evidenceRefs": [evidence_id],
                    }
                )
                continue
            desired_type = _desired_type(kind, text, explicit_id)
            if desired_type is None:
                continue
            semantic_key = explicit_id or (
                _CODE_TOKEN.search(text).group(1) if _CODE_TOKEN.search(text) else text
            )
            desired_id = (
                f"desired:{requirement_id}:{desired_type}:"
                + hashlib.sha256(semantic_key.encode()).hexdigest()[:16]
            )
            entity: dict[str, Any] = {
                "entityId": desired_id,
                "entityType": desired_type,
                "canonicalId": explicit_id,
                "label": text,
                "sourceCategory": "Explicit",
                "confidence": 1.0,
                "evidenceRefs": [evidence_id],
                "derivedFromRevision": design_revision_id,
            }
            if desired_type == "BusinessProcess":
                active_process_id = desired_id
                process_step_sequence = 0
            elif desired_type == "BusinessProcessStep":
                process_step_sequence += 1
                entity["processEntityId"] = active_process_id
                entity["sequence"] = process_step_sequence
            if desired_type == "DesiredAPIOperation":
                operation = _HTTP_OPERATION.search(text)
                if operation:
                    entity["httpMethod"] = operation.group(1).upper()
                    entity["path"] = operation.group(2)
            code_tokens = _CODE_TOKEN.findall(text)
            if code_tokens:
                entity["designTokens"] = code_tokens
            desired_entities.append(entity)

    if not desired_entities:
        unresolved.append(
            {
                "questionId": "question-no-desired-entity",
                "question": "文档没有可确定抽取的目标业务或技术实体。",
                "evidenceRefs": [],
            }
        )
    return {
        "requirementId": requirement_id,
        "designRevisionId": design_revision_id,
        "extractorVersion": EXTRACTOR_VERSION,
        "documentHash": parsed_document["contentHash"],
        "status": "Draft",
        "scope": scope,
        "desiredEntities": desired_entities,
        "documentEvidence": evidence,
        "implementationSuggestions": suggestions,
        "unresolvedQuestions": unresolved,
        "sourceClassification": {
            "explicit": len(desired_entities),
            "inferred": 0,
            "suggested": len(suggestions),
            "unresolved": len(unresolved),
        },
    }
