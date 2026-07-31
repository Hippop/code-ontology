from __future__ import annotations

import hmac
import json
import mimetypes
import os
import re
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from .errors import PlatformError, invalid
from .mcp_gateway import ReadOnlyMcpGateway
from .service import PlatformService

MAX_BODY_BYTES = 1_048_576


def handler_for(
    service: PlatformService,
    api_token: str | None = None,
    web_root: str | Path | None = None,
) -> type[BaseHTTPRequestHandler]:
    static_root = Path(web_root).resolve() if web_root is not None else None
    mcp_gateway = ReadOnlyMcpGateway(service)
    allowed_mcp_origins = {
        value.strip().rstrip("/")
        for value in os.environ.get("CODE_ONTOLOGY_ALLOWED_ORIGINS", "").split(",")
        if value.strip()
    }

    class AgentGatewayHandler(BaseHTTPRequestHandler):
        server_version = "CodeOntologyAgentGateway/0.3"

        def do_GET(self) -> None:
            self._dispatch("GET")

        def do_POST(self) -> None:
            self._dispatch("POST")

        def _dispatch(self, method: str) -> None:
            request_id = self.headers.get("X-Correlation-ID") or str(uuid.uuid4())
            try:
                parsed = urlsplit(self.path)
                path = parsed.path.rstrip("/") or "/"
                query = parse_qs(parsed.query)

                if method == "GET" and path == "/health":
                    self._json(
                        HTTPStatus.OK,
                        {
                            "status": "ok",
                            "ruleSet": service.planning_rules.rule_set,
                            "ruleSetVersion": service.planning_rules.version,
                        },
                        request_id,
                    )
                    return

                if (
                    method == "GET"
                    and static_root is not None
                    and (path == "/" or path.startswith("/assets/"))
                ):
                    self._static(path, static_root, request_id)
                    return

                if api_token is not None:
                    expected = f"Bearer {api_token}"
                    actual = self.headers.get("Authorization", "")
                    if not hmac.compare_digest(actual, expected):
                        raise PlatformError(
                            401,
                            "UNAUTHORIZED",
                            "缺少或使用了无效的 Bearer Token",
                        )

                if path == "/mcp":
                    self._validate_mcp_origin(allowed_mcp_origins)
                    if method == "GET":
                        raise PlatformError(
                            405,
                            "MCP_SSE_NOT_SUPPORTED",
                            "此无状态 MCP Gateway 不提供 GET/SSE",
                        )
                    mcp_gateway.validate_protocol_header(
                        self.headers.get("MCP-Protocol-Version")
                    )
                    result = mcp_gateway.handle(self._body())
                    if result is None:
                        self._empty(HTTPStatus.ACCEPTED, request_id)
                    else:
                        self._json(HTTPStatus.OK, result, request_id)
                    return

                if method == "GET" and path == "/api/graphs":
                    limit_value = self._optional_query(query, "limit")
                    try:
                        limit = int(limit_value) if limit_value else 500
                    except ValueError as error:
                        raise invalid("limit 必须是整数") from error
                    result = service.graph_catalog(
                        self._optional_query(query, "graphSpace"),
                        limit,
                    )
                    self._json(HTTPStatus.OK, result, request_id)
                    return

                if method == "POST" and path == "/api/graphs/compare":
                    result = service.graph_compare(self._body())
                    self._json(HTTPStatus.OK, result, request_id)
                    return

                if method == "POST" and path == "/api/graph-analysis/hybrid-search":
                    self._json(
                        HTTPStatus.OK,
                        service.hybrid_search(self._body()),
                        request_id,
                    )
                    return

                if method == "POST" and path == "/api/graph-analysis/communities":
                    self._json(
                        HTTPStatus.OK,
                        service.graph_communities(self._body()),
                        request_id,
                    )
                    return

                if method == "POST" and path == "/api/graph-analysis/processes":
                    self._json(
                        HTTPStatus.OK,
                        service.graph_processes(self._body()),
                        request_id,
                    )
                    return

                if method == "POST" and path == "/api/graph-analysis/contracts":
                    self._json(
                        HTTPStatus.OK,
                        service.contract_graph(self._body()),
                        request_id,
                    )
                    return

                if method == "GET" and path == "/api/requirement-workflows":
                    limit_value = self._optional_query(query, "limit")
                    try:
                        limit = int(limit_value) if limit_value else 100
                    except ValueError as error:
                        raise invalid("limit 必须是整数") from error
                    result = service.list_requirement_workflows(
                        requirement_id=self._optional_query(query, "requirementId"),
                        repository_id=self._optional_query(query, "repositoryId"),
                        limit=limit,
                    )
                    self._json(HTTPStatus.OK, result, request_id)
                    return

                workflow_resume_match = re.fullmatch(
                    r"/api/requirement-workflows/([^/]+)/resume", path
                )
                if method == "POST" and workflow_resume_match:
                    result = service.resume_requirement_workflow(
                        unquote(workflow_resume_match.group(1)),
                        self._body(),
                        request_id,
                    )
                    self._json(HTTPStatus.OK, result, request_id)
                    return

                workflow_retry_match = re.fullmatch(
                    r"/api/requirement-workflows/([^/]+)/retry", path
                )
                if method == "POST" and workflow_retry_match:
                    result = service.retry_requirement_workflow(
                        unquote(workflow_retry_match.group(1)),
                        self._body(),
                        request_id,
                    )
                    self._json(HTTPStatus.OK, result, request_id)
                    return

                workflow_match = re.fullmatch(
                    r"/api/requirement-workflows/([^/]+)", path
                )
                if method == "GET" and workflow_match:
                    result = service.get_requirement_workflow(
                        unquote(workflow_match.group(1))
                    )
                    self._json(HTTPStatus.OK, result, request_id)
                    return

                if method == "GET" and path == "/api/audit/events":
                    limit_value = self._optional_query(query, "limit")
                    try:
                        limit = int(limit_value) if limit_value else 1000
                    except ValueError as error:
                        raise invalid("limit 必须是整数") from error
                    result = service.audit_events(
                        requirement_id=self._optional_query(query, "requirementId"),
                        run_id=self._optional_query(query, "runId"),
                        correlation_id=self._optional_query(query, "correlationId"),
                        limit=limit,
                    )
                    self._json(HTTPStatus.OK, result, request_id)
                    return

                replay_match = re.fullmatch(
                    r"/api/audit/replay/requirements/([^/]+)", path
                )
                if method == "GET" and replay_match:
                    result = service.replay_requirement(unquote(replay_match.group(1)))
                    self._json(HTTPStatus.OK, result, request_id)
                    return

                context_match = re.fullmatch(
                    r"/api/agent-context/requirements/([^/]+)", path
                )
                if method == "GET" and context_match:
                    revision = self._single_query(query, "designRevisionId")
                    stage = self._single_query(query, "stage")
                    result = service.requirement_context(
                        unquote(context_match.group(1)), revision, stage
                    )
                    self._json(HTTPStatus.OK, result, request_id)
                    return

                reconciliation_match = re.fullmatch(
                    r"/api/reconciliation-runs/([^/]+)/agent-context", path
                )
                if method == "GET" and reconciliation_match:
                    result = service.reconciliation_context(
                        unquote(reconciliation_match.group(1))
                    )
                    self._json(HTTPStatus.OK, result, request_id)
                    return

                reconciliation_run_match = re.fullmatch(
                    r"/api/reconciliation-runs/([^/]+)", path
                )
                if method == "GET" and reconciliation_run_match:
                    result = service.get_reconciliation_run(
                        unquote(reconciliation_run_match.group(1))
                    )
                    self._json(HTTPStatus.OK, result, request_id)
                    return

                impact_run_match = re.fullmatch(
                    r"/api/(?:impact-runs|impact-analyses)/([^/]+)", path
                )
                if method == "GET" and impact_run_match:
                    result = service.get_impact_run(unquote(impact_run_match.group(1)))
                    self._json(HTTPStatus.OK, result, request_id)
                    return

                artifacts_match = re.fullmatch(
                    r"/api/agent-runs/([^/]+)/artifacts", path
                )
                if method == "GET" and artifacts_match:
                    result = service.list_artifacts(unquote(artifacts_match.group(1)))
                    self._json(HTTPStatus.OK, result, request_id)
                    return

                agent_run_diff_match = re.fullmatch(
                    r"/api/agent-runs/([^/]+)/diff", path
                )
                if method == "GET" and agent_run_diff_match:
                    result = service.agent_run_diff(
                        unquote(agent_run_diff_match.group(1))
                    )
                    self._json(HTTPStatus.OK, result, request_id)
                    return

                agent_run_match = re.fullmatch(r"/api/agent-runs/([^/]+)", path)
                if method == "GET" and agent_run_match:
                    result = service.get_agent_run(unquote(agent_run_match.group(1)))
                    self._json(HTTPStatus.OK, result, request_id)
                    return

                if method == "POST" and path == "/api/repositories":
                    result = service.register_repository(self._body(), request_id)
                    self._json(HTTPStatus.CREATED, result, request_id)
                    return

                if method == "POST" and path == "/api/requirement-workflows":
                    result = service.create_requirement_workflow(
                        self._body(), request_id
                    )
                    self._json(HTTPStatus.CREATED, result, request_id)
                    return

                repository_match = re.fullmatch(r"/api/repositories/([^/]+)", path)
                if method == "GET" and repository_match:
                    result = service.get_repository(unquote(repository_match.group(1)))
                    self._json(HTTPStatus.OK, result, request_id)
                    return

                if method == "POST" and path == "/api/design-documents":
                    result = service.create_design_document(self._body(), request_id)
                    self._json(HTTPStatus.CREATED, result, request_id)
                    return

                design_revision_match = re.fullmatch(
                    r"/api/design-documents/([^/]+)/revisions", path
                )
                if method == "POST" and design_revision_match:
                    result = service.create_design_revision(
                        unquote(design_revision_match.group(1)),
                        self._body(),
                        request_id,
                    )
                    self._json(HTTPStatus.CREATED, result, request_id)
                    return

                extract_design_match = re.fullmatch(
                    r"/api/design-revisions/([^/]+)/extract", path
                )
                if method == "POST" and extract_design_match:
                    result = service.extract_design_revision(
                        unquote(extract_design_match.group(1)),
                        self._body(),
                        request_id,
                    )
                    self._json(HTTPStatus.CREATED, result, request_id)
                    return

                requirement_ir_match = re.fullmatch(
                    r"/api/requirements/([^/]+)/ir", path
                )
                if method == "GET" and requirement_ir_match:
                    result = service.get_requirement_ir(
                        unquote(requirement_ir_match.group(1))
                    )
                    self._json(HTTPStatus.OK, result, request_id)
                    return

                runtime_evidence_match = re.fullmatch(
                    r"/api/requirements/([^/]+)/runtime-evidence", path
                )
                if method == "GET" and runtime_evidence_match:
                    result = service.runtime_evidence(
                        unquote(runtime_evidence_match.group(1))
                    )
                    self._json(HTTPStatus.OK, result, request_id)
                    return

                requirement_review_match = re.fullmatch(
                    r"/api/requirements/([^/]+)/review", path
                )
                if method == "POST" and requirement_review_match:
                    result = service.review_requirement(
                        unquote(requirement_review_match.group(1)),
                        self._body(),
                        request_id,
                    )
                    self._json(HTTPStatus.OK, result, request_id)
                    return

                snapshot_match = re.fullmatch(
                    r"/api/repositories/([^/]+)/snapshots", path
                )
                if method == "POST" and snapshot_match:
                    result = service.create_repository_snapshot(
                        unquote(snapshot_match.group(1)),
                        self._body(),
                        request_id,
                    )
                    self._json(HTTPStatus.CREATED, result, request_id)
                    return

                scan_match = re.fullmatch(r"/api/repositories/([^/]+)/scans", path)
                if method == "POST" and scan_match:
                    result = service.scan_repository(
                        unquote(scan_match.group(1)),
                        self._body(),
                        request_id,
                    )
                    self._json(HTTPStatus.CREATED, result, request_id)
                    return

                revisions_match = re.fullmatch(
                    r"/api/repositories/([^/]+)/graph-revisions", path
                )
                if method == "GET" and revisions_match:
                    result = service.repository_graph_revisions(
                        unquote(revisions_match.group(1))
                    )
                    self._json(HTTPStatus.OK, result, request_id)
                    return

                codegraph_match = re.fullmatch(
                    r"/api/repositories/([^/]+)/codegraph/"
                    r"(index|status|explore|impact|affected-tests|compare)",
                    path,
                )
                if codegraph_match:
                    repository_id = unquote(codegraph_match.group(1))
                    operation = codegraph_match.group(2)
                    if method == "GET" and operation == "status":
                        result = service.codegraph_index_status(repository_id)
                    elif method == "POST" and operation == "index":
                        result = service.codegraph_index(
                            repository_id, self._body(), request_id
                        )
                    elif method == "POST" and operation == "explore":
                        result = service.codegraph_explore(
                            repository_id, self._body()
                        )
                    elif method == "POST" and operation == "impact":
                        result = service.codegraph_impact(
                            repository_id, self._body()
                        )
                    elif method == "POST" and operation == "affected-tests":
                        result = service.codegraph_affected_tests(
                            repository_id, self._body()
                        )
                    elif method == "POST" and operation == "compare":
                        result = service.codegraph_compare(
                            repository_id, self._body()
                        )
                    else:
                        raise PlatformError(
                            405,
                            "METHOD_NOT_ALLOWED",
                            f"CodeGraph 操作不支持 {method}",
                        )
                    self._json(HTTPStatus.OK, result, request_id)
                    return

                if method == "POST" and path == "/api/agent-context/graph-query":
                    result = service.graph_query(self._body())
                    self._json(HTTPStatus.OK, result, request_id)
                    return

                if method == "POST" and path == "/api/change-plans/expand":
                    result = service.expand_change_plan(self._body())
                    self._json(HTTPStatus.OK, result, request_id)
                    return

                if method == "POST" and path == "/api/alignments/runs":
                    result = service.create_alignment_run(self._body(), request_id)
                    self._json(HTTPStatus.CREATED, result, request_id)
                    return

                alignment_run_match = re.fullmatch(
                    r"/api/alignments/runs/([^/]+)", path
                )
                if method == "GET" and alignment_run_match:
                    result = service.get_alignment_run(
                        unquote(alignment_run_match.group(1))
                    )
                    self._json(HTTPStatus.OK, result, request_id)
                    return

                alignment_review_match = re.fullmatch(
                    r"/api/alignments/([^/]+)/(confirm|reject)", path
                )
                if method == "POST" and alignment_review_match:
                    body = self._body()
                    if not isinstance(body, dict):
                        raise invalid("request 必须是 JSON object")
                    body["decision"] = (
                        "Confirm"
                        if alignment_review_match.group(2) == "confirm"
                        else "Reject"
                    )
                    result = service.review_alignment(
                        unquote(alignment_review_match.group(1)),
                        body,
                        request_id,
                    )
                    self._json(HTTPStatus.OK, result, request_id)
                    return

                if method == "POST" and path == "/api/change-plans":
                    result = service.create_change_plan(self._body(), request_id)
                    self._json(HTTPStatus.CREATED, result, request_id)
                    return

                if method == "POST" and path == "/api/agent-runs":
                    result = service.create_agent_run(self._body(), request_id)
                    self._json(HTTPStatus.CREATED, result, request_id)
                    return

                if method == "POST" and path == "/api/reconciliation-runs":
                    result = service.create_reconciliation_run(self._body(), request_id)
                    self._json(HTTPStatus.CREATED, result, request_id)
                    return

                if method == "POST" and path in {
                    "/api/impact-runs",
                    "/api/impact-analyses",
                }:
                    result = service.create_impact_run(self._body(), request_id)
                    self._json(HTTPStatus.CREATED, result, request_id)
                    return

                if method == "POST" and path == "/api/runtime-evidence":
                    result = service.record_runtime_evidence(self._body(), request_id)
                    self._json(HTTPStatus.CREATED, result, request_id)
                    return

                agent_permission_match = re.fullmatch(
                    r"/api/agent-runs/([^/]+)/permissions/([^/]+)", path
                )
                if method == "POST" and agent_permission_match:
                    result = service.respond_agent_permission(
                        unquote(agent_permission_match.group(1)),
                        unquote(agent_permission_match.group(2)),
                        self._body(),
                        request_id,
                    )
                    self._json(HTTPStatus.OK, result, request_id)
                    return

                change_plan_match = re.fullmatch(r"/api/change-plans/([^/]+)", path)
                if method == "GET" and change_plan_match:
                    result = service.get_change_plan(
                        unquote(change_plan_match.group(1))
                    )
                    self._json(HTTPStatus.OK, result, request_id)
                    return

                change_plan_review_match = re.fullmatch(
                    r"/api/change-plans/([^/]+)/review", path
                )
                if method == "POST" and change_plan_review_match:
                    result = service.review_change_plan(
                        unquote(change_plan_review_match.group(1)),
                        self._body(),
                        request_id,
                    )
                    self._json(HTTPStatus.OK, result, request_id)
                    return

                change_plan_approve_match = re.fullmatch(
                    r"/api/change-plans/([^/]+)/approve", path
                )
                if method == "POST" and change_plan_approve_match:
                    result = service.approve_change_plan(
                        unquote(change_plan_approve_match.group(1)),
                        self._body(),
                        request_id,
                    )
                    self._json(HTTPStatus.OK, result, request_id)
                    return

                if method == "POST" and path == "/api/alignments/agent-candidates":
                    result, replayed = service.record_alignment_candidates(
                        self._body(),
                        self.headers.get("Idempotency-Key", ""),
                        request_id,
                    )
                    self._json(
                        HTTPStatus.OK if replayed else HTTPStatus.CREATED,
                        result,
                        request_id,
                        replayed,
                    )
                    return

                if method == "POST" and path == "/api/change-plans/agent-drafts":
                    result, replayed = service.record_change_plan_draft(
                        self._body(),
                        self.headers.get("Idempotency-Key", ""),
                        request_id,
                    )
                    self._json(
                        HTTPStatus.OK if replayed else HTTPStatus.CREATED,
                        result,
                        request_id,
                        replayed,
                    )
                    return

                if method == "POST" and path == "/api/agent-artifacts":
                    result, replayed = service.record_agent_artifact(
                        self._body(),
                        self.headers.get("Idempotency-Key", ""),
                        request_id,
                    )
                    self._json(
                        HTTPStatus.OK if replayed else HTTPStatus.CREATED,
                        result,
                        request_id,
                        replayed,
                    )
                    return

                raise PlatformError(
                    404, "ROUTE_NOT_FOUND", f"未找到路由: {method} {path}"
                )
            except PlatformError as error:
                payload: dict[str, Any] = {
                    "error": {"code": error.code, "message": error.message}
                }
                if error.details is not None:
                    payload["error"]["details"] = error.details
                self._json(error.status, payload, request_id)
            except Exception:  # noqa: BLE001 - HTTP boundary must mask internal failures.
                self._json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {
                        "error": {
                            "code": "INTERNAL_ERROR",
                            "message": "服务处理请求时发生内部错误",
                        }
                    },
                    request_id,
                )

        def _body(self) -> Any:
            raw_length = self.headers.get("Content-Length")
            if raw_length is None:
                raise invalid("请求必须包含 Content-Length")
            try:
                length = int(raw_length)
            except ValueError as error:
                raise invalid("Content-Length 非法") from error
            if length < 0 or length > MAX_BODY_BYTES:
                raise PlatformError(
                    413,
                    "PAYLOAD_TOO_LARGE",
                    f"请求体不能超过 {MAX_BODY_BYTES} 字节",
                )
            raw = self.rfile.read(length)
            try:
                return json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise invalid(f"请求体必须是 UTF-8 JSON: {error}") from error

        @staticmethod
        def _single_query(query: dict[str, list[str]], name: str) -> str:
            values = query.get(name, [])
            if len(values) != 1:
                raise invalid(f"查询参数 {name} 必须且只能提供一次")
            return values[0]

        @staticmethod
        def _optional_query(query: dict[str, list[str]], name: str) -> str | None:
            values = query.get(name, [])
            if len(values) > 1:
                raise invalid(f"查询参数 {name} 最多提供一次")
            return values[0] if values else None

        def _json(
            self,
            status: int,
            payload: Any,
            request_id: str,
            replayed: bool = False,
        ) -> None:
            response = json.dumps(
                payload, ensure_ascii=False, separators=(",", ":")
            ).encode("utf-8")
            self.send_response(int(status))
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(response)))
            self.send_header("X-Correlation-ID", request_id)
            if replayed:
                self.send_header("X-Idempotent-Replay", "true")
            self.end_headers()
            self.wfile.write(response)

        def _empty(self, status: int, request_id: str) -> None:
            self.send_response(int(status))
            self.send_header("Content-Length", "0")
            self.send_header("X-Correlation-ID", request_id)
            self.end_headers()

        def _validate_mcp_origin(self, allowed_origins: set[str]) -> None:
            origin = self.headers.get("Origin")
            if origin is None:
                return
            normalized = origin.rstrip("/")
            if normalized in allowed_origins:
                return
            parsed = urlsplit(normalized)
            host = self.headers.get("Host", "").lower()
            if (
                parsed.scheme in {"http", "https"}
                and parsed.netloc
                and parsed.netloc.lower() == host
            ):
                return
            raise PlatformError(
                403,
                "MCP_ORIGIN_REJECTED",
                "MCP Origin 与服务 Host 不匹配",
                {"origin": origin, "host": host},
            )

        def _static(self, path: str, root: Path, request_id: str) -> None:
            relative = "index.html" if path == "/" else path.lstrip("/")
            target = (root / relative).resolve()
            if not target.is_relative_to(root) or not target.is_file():
                raise PlatformError(404, "ASSET_NOT_FOUND", f"未找到 Web Asset: {path}")
            content = target.read_bytes()
            content_type = (
                mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            )
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header(
                "Cache-Control",
                ("no-cache" if path == "/" else "public, max-age=31536000, immutable"),
            )
            self.send_header("X-Correlation-ID", request_id)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                (
                    "default-src 'self'; "
                    "style-src 'self' 'unsafe-inline' "
                    "https://fonts.googleapis.com; "
                    "font-src https://fonts.gstatic.com; "
                    "worker-src 'self' blob:; "
                    "img-src 'self' data:; connect-src 'self'"
                ),
            )
            self.end_headers()
            self.wfile.write(content)

        def log_message(self, format: str, *args: Any) -> None:
            # Keep the executable quiet by default; callers can log at the proxy layer.
            return

    return AgentGatewayHandler
