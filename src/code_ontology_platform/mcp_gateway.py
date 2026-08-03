from __future__ import annotations

import json
import re
import sys
from collections.abc import Callable, Mapping
from typing import Any, TextIO
from urllib.parse import quote, unquote

from .errors import PlatformError
from .service import PlatformService

MCP_PROTOCOL_VERSION = "2025-11-25"
_SUPPORTED_PROTOCOL_VERSIONS = frozenset(
    {"2025-11-25", "2025-06-18", "2025-03-26"}
)


def _object_schema(
    properties: Mapping[str, Any],
    *,
    required: list[str] | None = None,
) -> dict[str, Any]:
    normalized_properties = dict(properties)
    normalized_properties.setdefault(
        "maxTokens",
        {
            "type": "integer",
            "minimum": 128,
            "maximum": 50000,
            "description": "限制完整 MCP 工具响应的近似 Token 数。",
        },
    )
    return {
        "type": "object",
        "properties": normalized_properties,
        "required": required or [],
        "additionalProperties": False,
    }


_GRAPH_REF_PROPERTIES = {
    "repositoryId": {
        "type": "string",
        "minLength": 1,
        "description": "可选仓库作用域；Current Graph 多仓库场景建议提供。",
    },
    "graphSpace": {
        "type": "string",
        "enum": [
            "actual",
            "approved",
            "business",
            "current",
            "desired",
            "impact",
            "proposed",
        ],
        "default": "current",
    },
    "revision": {"type": "string"},
}


def _schema_errors(value: Any, schema: Mapping[str, Any], path: str = "$") -> list[str]:
    """Validate the JSON Schema subset used by the MCP tool declarations."""

    expected_type = schema.get("type")
    if expected_type == "object":
        if not isinstance(value, Mapping):
            return [f"{path} 必须是 object"]
        properties = schema.get("properties", {})
        errors = [
            f"{path}.{name} 为必填字段"
            for name in schema.get("required", [])
            if name not in value
        ]
        if schema.get("additionalProperties") is False:
            errors.extend(
                f"{path}.{name} 是未声明字段"
                for name in value
                if name not in properties
            )
        for name, item in value.items():
            item_schema = properties.get(name)
            if isinstance(item_schema, Mapping):
                errors.extend(_schema_errors(item, item_schema, f"{path}.{name}"))
        return errors
    if expected_type == "array":
        if not isinstance(value, list):
            return [f"{path} 必须是 array"]
        errors = []
        minimum = schema.get("minItems")
        maximum = schema.get("maxItems")
        if isinstance(minimum, int) and len(value) < minimum:
            errors.append(f"{path} 至少包含 {minimum} 项")
        if isinstance(maximum, int) and len(value) > maximum:
            errors.append(f"{path} 最多包含 {maximum} 项")
        item_schema = schema.get("items")
        if isinstance(item_schema, Mapping):
            for index, item in enumerate(value):
                errors.extend(_schema_errors(item, item_schema, f"{path}[{index}]"))
        return errors
    if expected_type == "string":
        if not isinstance(value, str):
            return [f"{path} 必须是 string"]
        if value not in schema.get("enum", [value]):
            return [f"{path} 必须是以下值之一: {schema['enum']}"]
        minimum = schema.get("minLength")
        maximum = schema.get("maxLength")
        if isinstance(minimum, int) and len(value) < minimum:
            return [f"{path} 长度不能小于 {minimum}"]
        if isinstance(maximum, int) and len(value) > maximum:
            return [f"{path} 长度不能大于 {maximum}"]
        return []
    if expected_type == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            return [f"{path} 必须是 integer"]
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if isinstance(minimum, int) and value < minimum:
            return [f"{path} 不能小于 {minimum}"]
        if isinstance(maximum, int) and value > maximum:
            return [f"{path} 不能大于 {maximum}"]
        return []
    if expected_type == "boolean" and not isinstance(value, bool):
        return [f"{path} 必须是 boolean"]
    return []


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def _tool_result_document(value: Any) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(value, ensure_ascii=False),
            }
        ],
        "structuredContent": value,
        "isError": False,
    }


def _tool_result_bytes(value: Any) -> int:
    return len(_json_bytes(_tool_result_document(value)))


def _bounded_tool_result(value: Any, max_tokens: int | None) -> Any:
    if max_tokens is None:
        return value
    byte_limit = max_tokens * 4
    serialized = _json_bytes(value)
    if _tool_result_bytes(value) <= byte_limit:
        return value

    identity_keys = (
        "repositoryId",
        "graphSpace",
        "revision",
        "query",
        "operation",
        "status",
        "count",
        "summary",
    )
    identity: dict[str, Any] = {}
    if isinstance(value, Mapping):
        for key in identity_keys:
            child = value.get(key)
            if isinstance(child, (str, int, float, bool)) or child is None:
                identity[key] = (
                    child[:256] + "…"
                    if isinstance(child, str) and len(child) > 256
                    else child
                )
            elif key == "summary" and isinstance(child, Mapping):
                identity[key] = {
                    str(summary_key): summary_value
                    for summary_key, summary_value in child.items()
                    if isinstance(summary_value, (str, int, float, bool))
                }

    def compact(item: Any, depth: int, list_limit: int, string_limit: int) -> Any:
        if isinstance(item, Mapping):
            if depth <= 0:
                return {"omittedFieldCount": len(item)}
            return {
                str(key): compact(child, depth - 1, list_limit, string_limit)
                for key, child in list(item.items())[:20]
            }
        if isinstance(item, list):
            if depth <= 0:
                return {"omittedItemCount": len(item)}
            result = [
                compact(child, depth - 1, list_limit, string_limit)
                for child in item[:list_limit]
            ]
            if len(item) > list_limit:
                result.append({"omittedItemCount": len(item) - list_limit})
            return result
        if isinstance(item, str) and len(item) > string_limit:
            return item[:string_limit] + "…"
        return item

    for depth, list_limit, string_limit in (
        (4, 8, 1024),
        (3, 4, 512),
        (2, 2, 256),
        (1, 1, 128),
    ):
        result = {
            **identity,
            "_mcp": {
                "truncated": True,
                "maxTokens": max_tokens,
                "originalBytes": len(serialized),
                "estimate": "4 UTF-8 bytes per token",
            },
            "preview": compact(value, depth, list_limit, string_limit),
        }
        if _tool_result_bytes(result) <= byte_limit:
            return result
    result = {
        **{key: child for key, child in identity.items() if key != "summary"},
        "_mcp": {
            "truncated": True,
            "maxTokens": max_tokens,
            "originalBytes": len(serialized),
            "estimate": "4 UTF-8 bytes per token",
        },
    }
    if _tool_result_bytes(result) <= byte_limit:
        return result
    return {
        "_mcp": {
            "truncated": True,
            "maxTokens": max_tokens,
            "originalBytes": len(serialized),
        }
    }


class ReadOnlyMcpGateway:
    """Transport-neutral MCP gateway exposing read-only graph operations."""

    def __init__(self, service: PlatformService) -> None:
        self.service = service
        readonly = {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        }
        self.tools: list[dict[str, Any]] = [
            {
                "name": "list_repositories",
                "description": "发现已注册仓库，作为多仓库查询的入口。",
                "inputSchema": _object_schema(
                    {
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 500,
                            "default": 100,
                        }
                    }
                ),
                "annotations": readonly,
            },
            {
                "name": "repository_context",
                "description": "读取仓库身份、Current Graph、索引新鲜度和可用能力。",
                "inputSchema": _object_schema(
                    {"repositoryId": {"type": "string", "minLength": 1}},
                    required=["repositoryId"],
                ),
                "annotations": readonly,
            },
            {
                "name": "symbol_context",
                "description": "搜索符号并返回首选实体的 360 度图邻域。",
                "inputSchema": _object_schema(
                    {
                        **_GRAPH_REF_PROPERTIES,
                        "query": {"type": "string", "minLength": 1},
                        "entityId": {"type": "string"},
                        "depth": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 6,
                            "default": 2,
                        },
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 200,
                            "default": 50,
                        },
                    },
                    required=["query"],
                ),
                "annotations": readonly,
            },
            {
                "name": "detect_changes",
                "description": "把 Git 工作区或基线差异映射为受影响实体、流程和测试。",
                "inputSchema": _object_schema(
                    {
                        "repositoryId": {"type": "string", "minLength": 1},
                        "baseRef": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 256,
                        },
                        "depth": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 6,
                            "default": 2,
                        },
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 500,
                            "default": 100,
                        },
                    },
                    required=["repositoryId"],
                ),
                "annotations": readonly,
            },
            {
                "name": "trace",
                "description": "查找两个代码实体之间的有向调用路径。",
                "inputSchema": _object_schema(
                    {
                        **_GRAPH_REF_PROPERTIES,
                        "sourceEntityId": {"type": "string", "minLength": 1},
                        "targetEntityId": {"type": "string", "minLength": 1},
                        "depth": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 6,
                            "default": 4,
                        },
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 200,
                            "default": 50,
                        },
                    },
                    required=["sourceEntityId", "targetEntityId"],
                ),
                "annotations": readonly,
            },
            {
                "name": "graph_query",
                "description": "读取一个图空间的概览、邻域、调用链或变更上下文。",
                "inputSchema": _object_schema(
                    {
                        **_GRAPH_REF_PROPERTIES,
                        "queryType": {
                            "type": "string",
                            "enum": [
                                "BUSINESS_TRACE",
                                "CALL_PATH",
                                "CHANGE_CONTEXT",
                                "CONTRACT_CONSUMERS",
                                "DATA_DEPENDENCIES",
                                "ENTITY_NEIGHBORHOOD",
                                "GRAPH_OVERVIEW",
                                "IMPLEMENTATION_SLICE",
                                "IMPACT_PATHS",
                            ],
                        },
                        "entityId": {"type": "string", "minLength": 1},
                        "targetEntityId": {"type": "string", "minLength": 1},
                        "depth": {"type": "integer", "minimum": 0, "maximum": 6},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 500},
                        "entityTypes": {
                            "type": "array",
                            "maxItems": 100,
                            "items": {"type": "string"},
                        },
                        "relations": {
                            "type": "array",
                            "maxItems": 200,
                            "items": {"type": "string"},
                        },
                        "search": {"type": "string", "maxLength": 10000},
                    },
                    required=["queryType"],
                ),
                "annotations": readonly,
            },
            {
                "name": "hybrid_search",
                "description": "使用 BM25、确定性语义向量和图中心度融合搜索实体。",
                "inputSchema": _object_schema(
                    {
                        **_GRAPH_REF_PROPERTIES,
                        "query": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 10000,
                        },
                        "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                        "entityTypes": {
                            "type": "array",
                            "maxItems": 100,
                            "items": {"type": "string"},
                        },
                    },
                    required=["query"],
                ),
                "annotations": readonly,
            },
            {
                "name": "codegraph_explore",
                "description": "通过只读 CodeGraph Sidecar 探索代码库。",
                "inputSchema": _object_schema(
                    {
                        "repositoryId": {"type": "string", "minLength": 1},
                        "query": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 10000,
                        },
                        "allowStale": {"type": "boolean", "default": False},
                    },
                    required=["repositoryId", "query"],
                ),
                "annotations": readonly,
            },
            {
                "name": "codegraph_impact",
                "description": "查询一个代码符号的只读影响范围。",
                "inputSchema": _object_schema(
                    {
                        "repositoryId": {"type": "string", "minLength": 1},
                        "symbol": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 1000,
                        },
                        "depth": {"type": "integer", "minimum": 1, "maximum": 8},
                        "allowStale": {"type": "boolean", "default": False},
                    },
                    required=["repositoryId", "symbol"],
                ),
                "annotations": readonly,
            },
            {
                "name": "affected_tests",
                "description": "根据变更文件查询受影响测试。",
                "inputSchema": _object_schema(
                    {
                        "repositoryId": {"type": "string", "minLength": 1},
                        "changedFiles": {
                            "type": "array",
                            "minItems": 1,
                            "maxItems": 500,
                            "items": {"type": "string", "minLength": 1},
                        },
                        "depth": {"type": "integer", "minimum": 1, "maximum": 8},
                        "allowStale": {"type": "boolean", "default": False},
                    },
                    required=["repositoryId", "changedFiles"],
                ),
                "annotations": readonly,
            },
            {
                "name": "index_status",
                "description": "读取 CodeGraph 索引新鲜度、版本与来源。",
                "inputSchema": _object_schema(
                    {"repositoryId": {"type": "string", "minLength": 1}},
                    required=["repositoryId"],
                ),
                "annotations": readonly,
            },
            {
                "name": "communities",
                "description": "读取确定性图社区划分。",
                "inputSchema": _object_schema(
                    {
                        **_GRAPH_REF_PROPERTIES,
                        "minimumSize": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 100,
                        },
                    }
                ),
                "annotations": readonly,
            },
            {
                "name": "processes",
                "description": "读取从 API、事件或测试入口推导的业务/代码流程。",
                "inputSchema": _object_schema(
                    {
                        **_GRAPH_REF_PROPERTIES,
                        "maxDepth": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 10,
                        },
                        "limit": {"type": "integer", "minimum": 1, "maximum": 500},
                    }
                ),
                "annotations": readonly,
            },
            {
                "name": "contract_graph",
                "description": "读取跨仓库 API、事件和 Schema 契约图。",
                "inputSchema": _object_schema(
                    {
                        "repositoryIds": {
                            "type": "array",
                            "maxItems": 500,
                            "items": {"type": "string", "minLength": 1},
                        }
                    }
                ),
                "annotations": readonly,
            },
        ]
        self._dispatch: dict[str, Callable[[dict[str, Any]], Any]] = {
            "list_repositories": self.service.list_repositories,
            "repository_context": lambda args: self.service.repository_context(
                str(args.get("repositoryId", ""))
            ),
            "symbol_context": self.service.symbol_context,
            "detect_changes": self.service.detect_changes,
            "trace": lambda args: self.service.graph_query(
                {
                    "repositoryId": args.get("repositoryId"),
                    "graphSpace": args.get("graphSpace", "current"),
                    "revision": args.get("revision"),
                    "queryType": "CALL_PATH",
                    "entityId": args.get("sourceEntityId"),
                    "targetEntityId": args.get("targetEntityId"),
                    "depth": args.get("depth", 4),
                    "limit": args.get("limit", 50),
                }
            ),
            "graph_query": self.service.graph_query,
            "hybrid_search": self.service.hybrid_search,
            "codegraph_explore": lambda args: self.service.codegraph_explore(
                str(args.get("repositoryId", "")), args
            ),
            "codegraph_impact": lambda args: self.service.codegraph_impact(
                str(args.get("repositoryId", "")), args
            ),
            "affected_tests": lambda args: self.service.codegraph_affected_tests(
                str(args.get("repositoryId", "")), args
            ),
            "index_status": lambda args: self.service.codegraph_index_status(
                str(args.get("repositoryId", ""))
            ),
            "communities": self.service.graph_communities,
            "processes": self.service.graph_processes,
            "contract_graph": self.service.contract_graph,
        }
        self._tool_by_name = {tool["name"]: tool for tool in self.tools}

    @staticmethod
    def validate_protocol_header(value: str | None) -> None:
        if value is not None and value not in _SUPPORTED_PROTOCOL_VERSIONS:
            raise PlatformError(
                400,
                "MCP_PROTOCOL_UNSUPPORTED",
                f"不支持 MCP-Protocol-Version: {value}",
            )

    def handle(self, message_value: Any) -> dict[str, Any] | None:
        if not isinstance(message_value, dict):
            return self._error(None, -32600, "Invalid Request")
        message = dict(message_value)
        request_id = message.get("id")
        if (
            message.get("jsonrpc") == "2.0"
            and "method" not in message
            and ("result" in message or "error" in message)
        ):
            return None
        if message.get("jsonrpc") != "2.0" or not isinstance(
            message.get("method"), str
        ):
            return self._error(request_id, -32600, "Invalid Request")
        method = str(message["method"])
        if "id" not in message:
            return None
        params = message.get("params", {})
        if not isinstance(params, dict):
            return self._error(request_id, -32602, "Invalid params")
        try:
            if method == "initialize":
                requested_protocol = params.get("protocolVersion")
                negotiated_protocol = (
                    requested_protocol
                    if requested_protocol in _SUPPORTED_PROTOCOL_VERSIONS
                    else MCP_PROTOCOL_VERSION
                )
                return self._result(
                    request_id,
                    {
                        "protocolVersion": negotiated_protocol,
                        "capabilities": {
                            "tools": {"listChanged": False},
                            "resources": {
                                "subscribe": False,
                                "listChanged": False,
                            },
                            "prompts": {"listChanged": False},
                        },
                        "serverInfo": {
                            "name": "code-ontology-readonly-gateway",
                            "version": "0.3.0",
                        },
                        "instructions": (
                            "此 Gateway 只提供图谱、代码影响和索引状态读取；"
                            "不提供索引、改码、提交或审批写操作。"
                        ),
                    },
                )
            if method == "ping":
                return self._result(request_id, {})
            if method == "tools/list":
                return self._result(request_id, {"tools": self.tools})
            if method == "tools/call":
                name = params.get("name")
                arguments = params.get("arguments", {})
                if not isinstance(name, str) or not isinstance(arguments, dict):
                    return self._error(request_id, -32602, "Invalid params")
                handler = self._dispatch.get(name)
                tool = self._tool_by_name.get(name)
                if handler is None or tool is None:
                    return self._tool_error(
                        request_id, f"未知或非只读工具: {name}", "MCP_TOOL_NOT_FOUND"
                    )
                schema_errors = _schema_errors(arguments, tool["inputSchema"])
                if schema_errors:
                    return self._tool_error(
                        request_id,
                        "工具参数不符合 inputSchema",
                        "MCP_INVALID_TOOL_ARGUMENTS",
                        {"errors": schema_errors},
                    )
                handler_arguments = dict(arguments)
                max_tokens = handler_arguments.pop("maxTokens", None)
                try:
                    value = handler(handler_arguments)
                except PlatformError as error:
                    return self._tool_error(
                        request_id,
                        error.message,
                        error.code,
                        error.details,
                    )
                value = _bounded_tool_result(value, max_tokens)
                return self._result(request_id, _tool_result_document(value))
            if method == "resources/list":
                repository_catalog = self.service.list_repositories({"limit": 500})
                repository_resources = [
                    {
                        "uri": (
                            "code-ontology://repositories/"
                            + quote(str(repository["repositoryId"]), safe="")
                            + "/context"
                        ),
                        "name": f"{repository['name']} repository context",
                        "description": "仓库身份、图版本和索引状态",
                        "mimeType": "application/json",
                    }
                    for repository in repository_catalog["repositories"]
                ]
                return self._result(
                    request_id,
                    {
                        "resources": [
                            {
                                "uri": "code-ontology://setup",
                                "name": "MCP setup guide",
                                "description": "工具选择、仓库作用域和索引准备说明",
                                "mimeType": "application/json",
                            },
                            {
                                "uri": "code-ontology://graphs",
                                "name": "Graph catalog",
                                "description": "所有图空间和版本的只读目录",
                                "mimeType": "application/json",
                            },
                            {
                                "uri": "code-ontology://repositories",
                                "name": "Repository catalog",
                                "description": "所有已注册代码仓库的只读目录",
                                "mimeType": "application/json",
                            },
                            {
                                "uri": "code-ontology://schema",
                                "name": "Graph MCP schema",
                                "description": "图空间、查询类型与只读工具目录",
                                "mimeType": "application/json",
                            },
                            *repository_resources,
                            *[
                                {
                                    "uri": (
                                        "code-ontology://repositories/"
                                        + quote(
                                            str(repository["repositoryId"]), safe=""
                                        )
                                        + f"/{resource_name}"
                                    ),
                                    "name": (
                                        f"{repository['name']} {resource_name}"
                                    ),
                                    "description": description,
                                    "mimeType": "application/json",
                                }
                                for repository in repository_catalog["repositories"]
                                for resource_name, description in (
                                    ("communities", "仓库的确定性功能社区"),
                                    ("processes", "仓库的 API、事件和测试流程"),
                                )
                            ],
                        ]
                    },
                )
            if method == "resources/templates/list":
                return self._result(
                    request_id,
                    {
                        "resourceTemplates": [
                            {
                                "uriTemplate": (
                                    "code-ontology://repositories/"
                                    "{repositoryId}/context"
                                ),
                                "name": "Repository context",
                                "description": "指定仓库的身份、图版本和索引状态",
                                "mimeType": "application/json",
                            },
                            {
                                "uriTemplate": (
                                    "code-ontology://repositories/"
                                    "{repositoryId}/communities"
                                ),
                                "name": "Repository communities",
                                "description": "指定仓库的确定性功能社区",
                                "mimeType": "application/json",
                            },
                            {
                                "uriTemplate": (
                                    "code-ontology://repositories/"
                                    "{repositoryId}/processes"
                                ),
                                "name": "Repository processes",
                                "description": "指定仓库的 API、事件和测试流程",
                                "mimeType": "application/json",
                            },
                        ]
                    },
                )
            if method == "resources/read":
                uri = params.get("uri")
                if not isinstance(uri, str):
                    return self._error(request_id, -32602, "Invalid params")
                if uri == "code-ontology://setup":
                    value = {
                        "server": "code-ontology-platform",
                        "protocolVersion": MCP_PROTOCOL_VERSION,
                        "transport": {
                            "stdio": "code-ontology-platform --database <db> mcp",
                            "streamableHttp": "POST http://127.0.0.1:8080/mcp",
                        },
                        "workflow": [
                            "先读取 code-ontology://repositories",
                            "用 repository_context 检查 Current Graph 与 CodeGraph 索引",
                            "探索符号优先使用 symbol_context",
                            "改码前使用 detect_changes、trace 和 codegraph_impact",
                            "大结果设置 maxTokens；多仓库查询提供 repositoryId",
                        ],
                        "indexing": (
                            "MCP 只读。平台 Current Graph 通过 scan 显式更新；"
                            "CodeGraph Sidecar 通过 codegraph index 显式更新。"
                        ),
                    }
                elif uri == "code-ontology://graphs":
                    value = self.service.graph_catalog()
                elif uri == "code-ontology://repositories":
                    value = self.service.list_repositories({"limit": 500})
                elif uri == "code-ontology://schema":
                    catalog = self.service.graph_catalog()
                    value = {
                        "protocolVersion": MCP_PROTOCOL_VERSION,
                        "graphSpaces": catalog.get("graphSpaces", []),
                        "tools": [
                            {
                                "name": tool["name"],
                                "description": tool["description"],
                                "inputSchema": tool["inputSchema"],
                            }
                            for tool in self.tools
                        ],
                    }
                else:
                    match = re.fullmatch(
                        r"code-ontology://repositories/([^/]+)/"
                        r"(context|communities|processes)",
                        uri,
                    )
                    if match:
                        repository_id = unquote(match.group(1))
                        resource_name = match.group(2)
                        if resource_name == "context":
                            value = self.service.repository_context(repository_id)
                        elif resource_name == "communities":
                            value = self.service.graph_communities(
                                {"repositoryId": repository_id}
                            )
                        else:
                            value = self.service.graph_processes(
                                {"repositoryId": repository_id}
                            )
                    else:
                        return self._error(
                            request_id, -32002, "Resource not found"
                        )
                return self._result(
                    request_id,
                    {
                        "contents": [
                            {
                                "uri": uri,
                                "mimeType": "application/json",
                                "text": json.dumps(value, ensure_ascii=False),
                            }
                        ]
                    },
                )
            if method == "prompts/list":
                return self._result(
                    request_id,
                    {
                        "prompts": [
                            {
                                "name": "detect_impact",
                                "description": "分析当前改动的图谱影响与测试范围",
                                "arguments": [
                                    {
                                        "name": "repositoryId",
                                        "description": "已注册仓库 ID",
                                        "required": True,
                                    },
                                    {
                                        "name": "baseRef",
                                        "description": "可选 Git 对比基线",
                                        "required": False,
                                    },
                                ],
                            },
                            {
                                "name": "generate_map",
                                "description": "基于社区、流程与契约生成架构地图",
                                "arguments": [
                                    {
                                        "name": "repositoryId",
                                        "description": "可选仓库 ID",
                                        "required": False,
                                    }
                                ],
                            },
                        ]
                    },
                )
            if method == "prompts/get":
                name = params.get("name")
                arguments = params.get("arguments", {})
                if not isinstance(name, str) or not isinstance(arguments, dict):
                    return self._error(request_id, -32602, "Invalid params")
                if name == "detect_impact":
                    repository_id = arguments.get("repositoryId")
                    if not isinstance(repository_id, str) or not repository_id:
                        return self._error(
                            request_id,
                            -32602,
                            "detect_impact 需要 repositoryId",
                        )
                    base_ref = arguments.get("baseRef")
                    suffix = (
                        f"，使用 Git 基线 {base_ref}"
                        if isinstance(base_ref, str) and base_ref
                        else ""
                    )
                    prompt = (
                        f"分析仓库 {repository_id} 的当前代码改动{suffix}。"
                        "先调用 detect_changes，再对高风险实体调用 symbol_context "
                        "或 graph_query；输出影响路径、受影响流程、建议测试和不确定项。"
                    )
                elif name == "generate_map":
                    repository_id = arguments.get("repositoryId")
                    scope = (
                        f"仓库 {repository_id}"
                        if isinstance(repository_id, str) and repository_id
                        else "已注册仓库"
                    )
                    prompt = (
                        f"为{scope}生成架构地图。先读取仓库资源和图目录，再调用 "
                        "communities、processes、contract_graph；用 Mermaid 表达主要"
                        "模块、入口流程和跨仓契约，并标注所用 Revision。"
                    )
                else:
                    return self._error(
                        request_id, -32602, f"未知 Prompt: {name}"
                    )
                return self._result(
                    request_id,
                    {
                        "description": (
                            "变更影响分析"
                            if name == "detect_impact"
                            else "架构地图生成"
                        ),
                        "messages": [
                            {
                                "role": "user",
                                "content": {"type": "text", "text": prompt},
                            }
                        ],
                    },
                )
            return self._error(request_id, -32601, "Method not found")
        except PlatformError as error:
            return self._error(
                request_id,
                -32000,
                error.message,
                {"code": error.code, "details": error.details},
            )

    @staticmethod
    def _result(request_id: Any, result: Any) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    @staticmethod
    def _error(
        request_id: Any,
        code: int,
        message: str,
        data: Any | None = None,
    ) -> dict[str, Any]:
        error = {"code": code, "message": message}
        if data is not None:
            error["data"] = data
        return {"jsonrpc": "2.0", "id": request_id, "error": error}

    @classmethod
    def _tool_error(
        cls,
        request_id: Any,
        message: str,
        code: str,
        details: Any | None = None,
    ) -> dict[str, Any]:
        value = {"error": {"code": code, "message": message}}
        if details is not None:
            value["error"]["details"] = details
        return cls._result(
            request_id,
            {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(value, ensure_ascii=False),
                    }
                ],
                "structuredContent": value,
                "isError": True,
            },
        )


def serve_stdio(
    gateway: ReadOnlyMcpGateway,
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
) -> int:
    """Serve newline-delimited MCP JSON-RPC over stdin/stdout."""

    source = input_stream or sys.stdin
    destination = output_stream or sys.stdout
    for raw_line in source:
        line = raw_line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            response = gateway._error(None, -32700, "Parse error")
        else:
            response = gateway.handle(message)
        if response is None:
            continue
        destination.write(
            json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n"
        )
        destination.flush()
    return 0
