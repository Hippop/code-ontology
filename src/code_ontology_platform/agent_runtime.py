from __future__ import annotations

import base64
import fnmatch
import json
import os
import re
import secrets
import shlex
import shutil
import socket
import subprocess
import tempfile
import time
from collections import Counter
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .errors import PlatformError, conflict, invalid
from .store import content_hash

OPENCODE_API_VERSION = "server-v1"
CODEX_API_VERSION = "exec-jsonl-v1"
FORBIDDEN_COMMAND_PATTERNS = (
    "git commit*",
    "git push*",
    "git merge*",
    "git rebase*",
    "git tag*",
    "kubectl *",
    "helm *",
    "terraform *",
)
READ_ONLY_GIT_PATTERNS = (
    "git status*",
    "git diff*",
    "git log*",
    "git show*",
    "git branch --show-current*",
    "git rev-parse*",
)
_TEST_EXECUTABLES = frozenset({"./mvnw", "mvn", "./gradlew", "gradle"})
_TEST_GOALS = frozenset({"test", "check", "verify"})
_UNTRACKED_BUILD_OUTPUTS = (
    ".gradle/**",
    "build/**",
    "out/**",
    "target/**",
)


def _message_summary(messages: list[dict[str, Any]]) -> dict[str, Any]:
    assistant_messages = [
        item
        for item in messages
        if isinstance(item, dict)
        and isinstance(item.get("info"), dict)
        and item["info"].get("role") == "assistant"
    ]
    if not assistant_messages:
        return {"assistantMessageCount": 0}
    latest = assistant_messages[-1]
    info = latest.get("info", {})
    parts = latest.get("parts", [])
    text_parts = [
        str(part.get("text"))
        for part in parts
        if isinstance(part, dict)
        and part.get("type") == "text"
        and part.get("text") is not None
    ]
    return {
        "assistantMessageCount": len(assistant_messages),
        "latestMessageId": info.get("id"),
        "finish": info.get("finish"),
        "error": info.get("error"),
        "partTypes": [part.get("type") for part in parts if isinstance(part, dict)][
            -20:
        ],
        "textTail": "\n".join(text_parts)[-2000:],
    }


def _run_git(
    repository: Path,
    *arguments: str,
    timeout: int = 30,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", "-C", str(repository), *arguments],
            check=check,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as error:
        raise PlatformError(503, "GIT_UNAVAILABLE", "运行环境未安装 Git") from error
    except subprocess.TimeoutExpired as error:
        raise PlatformError(504, "GIT_TIMEOUT", "Git 操作超时") from error
    except subprocess.CalledProcessError as error:
        message = (error.stderr or error.stdout or "Git command failed").strip()
        raise conflict(f"Git 操作失败: {message[:500]}") from error


def _matches(path: str, pattern: str) -> bool:
    normalized_path = path.replace("\\", "/").lstrip("./")
    normalized_pattern = pattern.replace("\\", "/").lstrip("./")
    if normalized_pattern.endswith("/**"):
        prefix = normalized_pattern[:-3].rstrip("/")
        return normalized_path == prefix or normalized_path.startswith(prefix + "/")
    return fnmatch.fnmatchcase(normalized_path, normalized_pattern)


def validate_changed_paths(
    changed_files: list[str],
    allowed_files: list[str],
    forbidden_files: list[str],
) -> dict[str, Any]:
    normalized = sorted(
        {item.replace("\\", "/").lstrip("./") for item in changed_files if item.strip()}
    )
    forbidden = [
        path
        for path in normalized
        if any(_matches(path, pattern) for pattern in forbidden_files)
    ]
    outside_allowlist = [
        path
        for path in normalized
        if not any(_matches(path, pattern) for pattern in allowed_files)
    ]
    return {
        "status": ("Passed" if not forbidden and not outside_allowlist else "Rejected"),
        "changedFiles": normalized,
        "forbiddenFilesChanged": forbidden,
        "outsideAllowlist": outside_allowlist,
        "allowedPatterns": allowed_files,
        "forbiddenPatterns": forbidden_files,
    }


def validate_test_command(command: str) -> list[str]:
    try:
        arguments = shlex.split(command)
    except ValueError as error:
        raise invalid(f"测试命令无法解析: {command}") from error
    if not arguments or arguments[0] not in _TEST_EXECUTABLES:
        raise invalid(
            "requiredTests 只允许 Maven/Gradle 测试命令",
            {"command": command},
        )
    goals = {
        token.lstrip(":").split(":")[-1]
        for token in arguments[1:]
        if not token.startswith("-")
    }
    if not goals.intersection(_TEST_GOALS):
        raise invalid(
            "requiredTests 必须包含 test、check 或 verify 目标",
            {"command": command},
        )
    return arguments


def run_required_tests(
    worktree: str | Path,
    commands: list[str],
    *,
    timeout_per_command: int = 900,
) -> dict[str, Any]:
    path = Path(worktree).resolve()
    executions = []
    for command in commands:
        arguments = validate_test_command(command)
        started = time.monotonic()
        try:
            completed = subprocess.run(
                arguments,
                cwd=path,
                capture_output=True,
                text=True,
                timeout=timeout_per_command,
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
                check=False,
            )
            execution = {
                "command": command,
                "exitCode": completed.returncode,
                "durationMs": round((time.monotonic() - started) * 1000),
                "stdout": completed.stdout[-8000:],
                "stderr": completed.stderr[-8000:],
                "status": "Passed" if completed.returncode == 0 else "Failed",
            }
        except FileNotFoundError:
            execution = {
                "command": command,
                "exitCode": None,
                "durationMs": round((time.monotonic() - started) * 1000),
                "stdout": "",
                "stderr": f"测试执行器不存在: {arguments[0]}",
                "status": "Failed",
            }
        except subprocess.TimeoutExpired as error:
            execution = {
                "command": command,
                "exitCode": None,
                "durationMs": round((time.monotonic() - started) * 1000),
                "stdout": (error.stdout or "")[-8000:],
                "stderr": (error.stderr or "")[-8000:],
                "status": "TimedOut",
            }
        executions.append(execution)
        if execution["status"] != "Passed":
            break
    return {
        "status": (
            "Passed"
            if len(executions) == len(commands)
            and all(item["status"] == "Passed" for item in executions)
            else "Failed"
        ),
        "executions": executions,
    }


def collect_worktree_diff(worktree: str | Path, base_commit: str) -> dict[str, Any]:
    path = Path(worktree).resolve()
    head = _run_git(path, "rev-parse", "HEAD").stdout.strip()
    status = _run_git(
        path, "status", "--porcelain=v1", "--untracked-files=all"
    ).stdout.splitlines()
    changed_files = []
    for line in status:
        candidate = line[3:] if len(line) > 3 else ""
        if " -> " in candidate:
            candidate = candidate.split(" -> ", 1)[1]
        is_untracked_build_output = line[:2] == "??" and any(
            _matches(candidate, pattern) for pattern in _UNTRACKED_BUILD_OUTPUTS
        )
        if candidate and not is_untracked_build_output:
            changed_files.append(candidate)
    patch = _run_git(
        path,
        "diff",
        "--binary",
        "--no-ext-diff",
        base_commit,
        "--",
        timeout=60,
    ).stdout
    for file_path in changed_files:
        absolute = path / file_path
        if absolute.is_file() and file_path not in patch:
            untracked_diff = _run_git(
                path,
                "diff",
                "--binary",
                "--no-index",
                "--",
                "/dev/null",
                file_path,
                check=False,
            ).stdout
            patch += untracked_diff
    return {
        "baseCommit": base_commit,
        "headCommit": head,
        "headUnchanged": head == base_commit,
        "changedFiles": sorted(set(changed_files)),
        "patch": patch,
        "patchHash": content_hash({"patch": patch}),
    }


@dataclass(frozen=True)
class Worktree:
    path: Path
    repository_path: Path
    base_commit: str


class GitWorktreeManager:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def create(
        self,
        repository_path: str | Path,
        run_id: str,
        base_commit: str,
    ) -> Worktree:
        repository = Path(repository_path).resolve()
        if not re.fullmatch(r"[A-Za-z0-9._-]{3,128}", run_id):
            raise invalid("agentRunId 含有不安全字符")
        root = Path(
            _run_git(repository, "rev-parse", "--show-toplevel").stdout.strip()
        ).resolve()
        resolved_commit = _run_git(
            repository, "rev-parse", f"{base_commit}^{{commit}}"
        ).stdout.strip()
        target = (self.root / run_id).resolve()
        if not target.is_relative_to(self.root):
            raise invalid("Worktree 目标路径越界")
        if target.exists():
            raise conflict(f"Agent Worktree 已存在: {run_id}")
        _run_git(root, "worktree", "add", "--detach", str(target), resolved_commit)
        actual = _run_git(target, "rev-parse", "HEAD").stdout.strip()
        if actual != resolved_commit:
            self.remove(Worktree(target, root, resolved_commit))
            raise conflict("Worktree Base Commit 校验失败")
        return Worktree(target, root, resolved_commit)

    def remove(self, worktree: Worktree) -> None:
        if not worktree.path.is_relative_to(self.root):
            raise invalid("拒绝移除不属于 Agent Worktree Root 的路径")
        _run_git(
            worktree.repository_path,
            "worktree",
            "remove",
            "--force",
            str(worktree.path),
            check=False,
        )


class AgentAdapter(Protocol):
    def execute(
        self,
        *,
        worktree: Path,
        run_id: str,
        prompt: str,
        agent_name: str,
        allowed_files: list[str],
        forbidden_files: list[str],
        required_tests: list[str],
        skill_name: str = "implement-approved-change",
        read_only: bool = False,
    ) -> dict[str, Any]: ...

    def respond_permission(
        self,
        session_id: str,
        permission_id: str,
        response: str,
    ) -> bool: ...


class OpenCodeHttpClient:
    def __init__(
        self,
        base_url: str,
        *,
        username: str | None = None,
        password: str | None = None,
        timeout: int = 900,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.authorization = None
        if password is not None:
            credentials = f"{username or 'opencode'}:{password}".encode()
            self.authorization = "Basic " + base64.b64encode(credentials).decode()

    def request(
        self, method: str, path: str, body: Mapping[str, Any] | None = None
    ) -> Any:
        headers = {"Accept": "application/json"}
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body, ensure_ascii=False).encode()
        if self.authorization:
            headers["Authorization"] = self.authorization
        request = Request(
            self.base_url + path, data=data, headers=headers, method=method
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except HTTPError as error:
            detail = error.read().decode(errors="replace")[:1000]
            raise PlatformError(
                502,
                "OPENCODE_HTTP_ERROR",
                f"OpenCode Server 返回 HTTP {error.code}",
                {"body": detail},
            ) from error
        except (URLError, TimeoutError) as error:
            raise PlatformError(
                503,
                "OPENCODE_UNAVAILABLE",
                f"无法连接 OpenCode Server: {error}",
            ) from error
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError as error:
            raise PlatformError(
                502,
                "OPENCODE_INVALID_RESPONSE",
                "OpenCode Server 返回了非 JSON 响应",
            ) from error

    def health(self) -> dict[str, Any]:
        result = self.request("GET", "/global/health")
        if not isinstance(result, dict) or result.get("healthy") is not True:
            raise PlatformError(503, "OPENCODE_UNHEALTHY", "OpenCode Server 不健康")
        return result

    def providers(self) -> dict[str, Any]:
        result = self.request("GET", "/provider")
        return result if isinstance(result, dict) else {}

    def agents(self) -> list[dict[str, Any]]:
        result = self.request("GET", "/agent")
        return result if isinstance(result, list) else []

    def create_session(self, title: str) -> dict[str, Any]:
        result = self.request("POST", "/session", {"title": title})
        if not isinstance(result, dict) or not result.get("id"):
            raise PlatformError(
                502, "OPENCODE_INVALID_RESPONSE", "OpenCode 未返回 Session ID"
            )
        return result

    def message(self, session_id: str, prompt: str, agent_name: str) -> dict[str, Any]:
        result = self.request(
            "POST",
            f"/session/{quote(session_id, safe='')}/message",
            {
                "agent": agent_name,
                "parts": [{"type": "text", "text": prompt}],
            },
        )
        if not isinstance(result, dict):
            raise PlatformError(
                502, "OPENCODE_INVALID_RESPONSE", "OpenCode Message 响应非法"
            )
        return result

    def prompt_async(self, session_id: str, prompt: str, agent_name: str) -> None:
        self.request(
            "POST",
            f"/session/{quote(session_id, safe='')}/prompt_async",
            {
                "agent": agent_name,
                "parts": [{"type": "text", "text": prompt}],
            },
        )

    def session_status(self) -> dict[str, Any]:
        result = self.request("GET", "/session/status")
        return result if isinstance(result, dict) else {}

    def messages(self, session_id: str) -> list[dict[str, Any]]:
        result = self.request("GET", f"/session/{quote(session_id, safe='')}/message")
        return result if isinstance(result, list) else []

    def abort(self, session_id: str) -> bool:
        result = self.request(
            "POST", f"/session/{quote(session_id, safe='')}/abort", {}
        )
        return result is True

    def session_diff(self, session_id: str) -> list[dict[str, Any]]:
        result = self.request("GET", f"/session/{quote(session_id, safe='')}/diff")
        return result if isinstance(result, list) else []

    def respond_permission(
        self, session_id: str, permission_id: str, response: str
    ) -> bool:
        result = self.request(
            "POST",
            (
                f"/session/{quote(session_id, safe='')}/permissions/"
                f"{quote(permission_id, safe='')}"
            ),
            {"response": response, "remember": False},
        )
        return result is True


def _permission_config(
    required_tests: list[str],
    *,
    agent_name: str,
    skill_name: str,
    read_only: bool,
) -> dict[str, Any]:
    bash: dict[str, str] = {"*": "deny"}
    for pattern in READ_ONLY_GIT_PATTERNS:
        bash[pattern] = "allow"
    if not read_only:
        for command in required_tests:
            bash[command] = "allow"
            bash[command + " *"] = "allow"
    for pattern in FORBIDDEN_COMMAND_PATTERNS:
        bash[pattern] = "deny"
    edit_permission = "deny" if read_only else "allow"
    return {
        "$schema": "https://opencode.ai/config.json",
        "share": "disabled",
        "permission": {
            "*": "deny",
            "read": {
                "*": "allow",
                "*.env": "deny",
                "*.env.*": "deny",
                "**/secrets/**": "deny",
                "**/*.pem": "deny",
                "**/*.key": "deny",
            },
            "glob": "allow",
            "grep": "allow",
            "list": "allow",
            "edit": edit_permission,
            "skill": {
                "*": "deny",
                skill_name: "allow",
            },
            "bash": bash,
            "task": "deny",
            "external_directory": "deny",
            "webfetch": "deny",
            "websearch": "deny",
        },
        "agent": {
            agent_name: {
                "mode": "primary",
                "description": (
                    "Read-only governed analysis role."
                    if read_only
                    else "Implement only an approved change in a controlled worktree."
                ),
                "permission": {
                    "edit": edit_permission,
                    "bash": bash,
                    "skill": {
                        "*": "deny",
                        skill_name: "allow",
                    },
                    "task": "deny",
                    "external_directory": "deny",
                    "webfetch": "deny",
                    "websearch": "deny",
                },
            }
        },
    }


def _available_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        return int(server.getsockname()[1])


@contextmanager
def _local_server(
    *,
    binary: Path,
    worktree: Path,
    config_dir: Path,
    required_tests: list[str],
    agent_name: str,
    skill_name: str,
    read_only: bool,
):
    port = _available_port()
    password = secrets.token_urlsafe(24)
    environment = dict(os.environ)
    environment.update(
        {
            "OPENCODE_SERVER_USERNAME": "gateway",
            "OPENCODE_SERVER_PASSWORD": password,
            "OPENCODE_CONFIG_DIR": str(config_dir),
            "OPENCODE_CONFIG_CONTENT": json.dumps(
                _permission_config(
                    required_tests,
                    agent_name=agent_name,
                    skill_name=skill_name,
                    read_only=read_only,
                ),
                ensure_ascii=False,
            ),
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_SSH_COMMAND": "false",
        }
    )
    process = subprocess.Popen(
        [
            str(binary),
            "serve",
            "--hostname",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=worktree,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    client = OpenCodeHttpClient(
        f"http://127.0.0.1:{port}",
        username="gateway",
        password=password,
        timeout=2,
    )
    try:
        deadline = time.monotonic() + 20
        while True:
            if process.poll() is not None:
                raise PlatformError(
                    503,
                    "OPENCODE_START_FAILED",
                    f"OpenCode Server 启动失败，退出码 {process.returncode}",
                )
            try:
                client.health()
                break
            except PlatformError:
                if time.monotonic() >= deadline:
                    raise PlatformError(
                        504, "OPENCODE_START_TIMEOUT", "OpenCode Server 启动超时"
                    )
                time.sleep(0.1)
        client.timeout = 900
        yield client
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


class OpenCodeAdapter:
    """Real OpenCode Server adapter with a per-worktree isolated server."""

    def __init__(
        self,
        config_dir: str | Path,
        binary: str | Path | None = None,
        client_factory: Callable[[Path, list[str]], Any] | None = None,
        run_timeout_seconds: int = 300,
    ) -> None:
        self.config_dir = Path(config_dir).resolve()
        discovered = str(binary) if binary else shutil.which("opencode")
        self.binary = Path(discovered).resolve() if discovered else None
        self.client_factory = client_factory
        self.run_timeout_seconds = run_timeout_seconds
        self._sessions: dict[str, OpenCodeHttpClient] = {}

    def execute(
        self,
        *,
        worktree: Path,
        run_id: str,
        prompt: str,
        agent_name: str,
        allowed_files: list[str],
        forbidden_files: list[str],
        required_tests: list[str],
        skill_name: str = "implement-approved-change",
        read_only: bool = False,
    ) -> dict[str, Any]:
        if self.client_factory is not None:
            with self.client_factory(worktree, required_tests) as client:
                return self._execute(client, run_id, prompt, agent_name, skill_name)
        if self.binary is None or not self.binary.is_file():
            raise PlatformError(
                503,
                "OPENCODE_UNAVAILABLE",
                "未找到 OpenCode 可执行文件；请安装 opencode-ai 或配置 OPENCODE_BINARY",
            )
        with _local_server(
            binary=self.binary,
            worktree=worktree,
            config_dir=self.config_dir,
            required_tests=required_tests,
            agent_name=agent_name,
            skill_name=skill_name,
            read_only=read_only,
        ) as client:
            return self._execute(client, run_id, prompt, agent_name, skill_name)

    def describe(self) -> dict[str, Any]:
        return {
            "runtime": "OpenCode",
            "available": self.binary is not None and self.binary.is_file(),
            "binary": str(self.binary) if self.binary is not None else None,
            "apiVersion": OPENCODE_API_VERSION,
        }

    def _execute(
        self,
        client: OpenCodeHttpClient,
        run_id: str,
        prompt: str,
        agent_name: str,
        skill_name: str,
    ) -> dict[str, Any]:
        health = client.health()
        providers = client.providers()
        connected = providers.get("connected", [])
        if not connected:
            raise PlatformError(
                503,
                "OPENCODE_CREDENTIALS_MISSING",
                "OpenCode Server 未连接任何模型 Provider",
            )
        agents = client.agents()
        agent_names = {
            item.get("name") for item in agents if isinstance(item, dict)
        } | {item.get("id") for item in agents if isinstance(item, dict)}
        if agent_name not in agent_names:
            raise PlatformError(
                503,
                "OPENCODE_AGENT_MISSING",
                f"OpenCode 未加载受控 Agent: {agent_name}",
            )
        session = client.create_session(f"approved-change:{run_id}")
        session_id = str(session["id"])
        self._sessions[session_id] = client
        client.prompt_async(session_id, prompt, agent_name)
        deadline = time.monotonic() + self.run_timeout_seconds
        status_history: list[str] = []
        latest_messages: list[dict[str, Any]] = []
        while True:
            statuses = client.session_status()
            status = statuses.get(session_id, {"type": "idle"})
            status_type = status.get("type") if isinstance(status, dict) else "unknown"
            if not status_history or status_history[-1] != status_type:
                status_history.append(status_type)
            if status_type == "idle":
                messages = client.messages(session_id)
                assistant_messages = [
                    item
                    for item in messages
                    if isinstance(item, dict)
                    and isinstance(item.get("info"), dict)
                    and item["info"].get("role") == "assistant"
                ]
                if assistant_messages:
                    message = assistant_messages[-1]
                    break
            if time.monotonic() >= deadline:
                try:
                    latest_messages = client.messages(session_id)
                except PlatformError:
                    latest_messages = []
                try:
                    timeout_diff = client.session_diff(session_id)
                except PlatformError:
                    timeout_diff = []
                client.abort(session_id)
                raise PlatformError(
                    504,
                    "OPENCODE_RUN_TIMEOUT",
                    "OpenCode Agent Run 超过平台 Deadline，已中止",
                    {
                        "sessionId": session_id,
                        "timeoutSeconds": self.run_timeout_seconds,
                        "statusHistory": status_history,
                        "messageSummary": _message_summary(latest_messages),
                        "serverDiff": timeout_diff,
                    },
                )
            time.sleep(0.25)
        message_info = message.get("info")
        if isinstance(message_info, dict) and message_info.get("error") is not None:
            raise PlatformError(
                502,
                "OPENCODE_AGENT_FAILED",
                "OpenCode Agent 返回失败消息",
                {
                    "sessionId": session_id,
                    "error": message_info["error"],
                    "statusHistory": status_history,
                },
            )
        server_diff = client.session_diff(session_id)
        return {
            "runtime": "OpenCode",
            "runtimeVersion": health.get("version"),
            "apiVersion": OPENCODE_API_VERSION,
            "sessionId": session_id,
            "message": message,
            "serverDiff": server_diff,
            "connectedProviders": connected,
            "agentName": agent_name,
            "skillName": skill_name,
            "statusHistory": status_history,
        }

    def respond_permission(
        self, session_id: str, permission_id: str, response: str
    ) -> bool:
        client = self._sessions.get(session_id)
        if client is None:
            raise conflict("OpenCode Session 已结束或不属于当前运行时")
        return client.respond_permission(session_id, permission_id, response)


def _codex_event_summary(raw_output: str) -> dict[str, Any]:
    event_counts: Counter[str] = Counter()
    thread_id: str | None = None
    messages: list[str] = []
    commands: list[dict[str, Any]] = []
    file_changes: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    usage: dict[str, Any] | None = None
    invalid_lines = 0
    turn_completed = False

    for line in raw_output.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            invalid_lines += 1
            continue
        if not isinstance(event, dict):
            invalid_lines += 1
            continue
        event_type = str(event.get("type") or "unknown")
        event_counts[event_type] += 1
        if event_type == "thread.started":
            value = event.get("thread_id")
            thread_id = str(value) if value is not None else thread_id
        elif event_type == "turn.completed":
            turn_completed = True
            value = event.get("usage")
            usage = dict(value) if isinstance(value, Mapping) else None
        elif event_type in {"turn.failed", "error"}:
            errors.append(
                {
                    "type": event_type,
                    "message": str(
                        event.get("message")
                        or event.get("error")
                        or event.get("detail")
                        or "Codex execution failed"
                    )[:2000],
                }
            )
        if not event_type.startswith("item."):
            continue
        item = event.get("item")
        if not isinstance(item, Mapping):
            continue
        item_type = str(item.get("type") or "")
        if event_type == "item.completed" and item_type == "agent_message":
            value = item.get("text")
            if value is not None:
                messages.append(str(value))
        elif item_type == "command_execution" and len(commands) < 50:
            commands.append(
                {
                    "id": item.get("id"),
                    "command": str(item.get("command") or "")[:2000],
                    "status": item.get("status"),
                    "exitCode": item.get("exit_code"),
                    "outputTail": str(item.get("aggregated_output") or "")[-2000:],
                }
            )
        elif item_type == "file_change" and len(file_changes) < 100:
            file_changes.append(
                {
                    "id": item.get("id"),
                    "status": item.get("status"),
                    "changes": item.get("changes"),
                }
            )

    return {
        "threadId": thread_id,
        "turnCompleted": turn_completed,
        "eventCounts": dict(sorted(event_counts.items())),
        "invalidJsonLines": invalid_lines,
        "messages": messages[-20:],
        "finalMessage": messages[-1] if messages else None,
        "commands": commands,
        "fileChanges": file_changes,
        "errors": errors,
        "usage": usage,
    }


@contextmanager
def _isolated_codex_read_worktree(repository: Path, run_id: str):
    repository = repository.resolve()
    root = Path(
        _run_git(repository, "rev-parse", "--show-toplevel").stdout.strip()
    ).resolve()
    commit = _run_git(repository, "rev-parse", "HEAD").stdout.strip()
    safe_run_id = re.sub(r"[^A-Za-z0-9._-]", "-", run_id)[:48] or "run"
    temporary_root = Path(
        tempfile.mkdtemp(prefix=f"code-ontology-{safe_run_id}-")
    ).resolve()
    isolated = temporary_root / "repository"
    try:
        _run_git(root, "worktree", "add", "--detach", str(isolated), commit)
        yield isolated, commit
    finally:
        _run_git(
            root,
            "worktree",
            "remove",
            "--force",
            str(isolated),
            check=False,
        )
        shutil.rmtree(temporary_root, ignore_errors=True)


class CodexAdapter:
    """Non-interactive local Codex CLI adapter with JSONL event capture."""

    def __init__(
        self,
        binary: str | Path | None = None,
        *,
        model: str | None = None,
        sandbox_mode: str | None = None,
        run_timeout_seconds: int = 900,
        ignore_user_config: bool = True,
        runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    ) -> None:
        discovered = str(binary) if binary else shutil.which("codex")
        self.binary = Path(discovered).resolve() if discovered else None
        self.model = model or os.environ.get("CODE_ONTOLOGY_CODEX_MODEL")
        self.sandbox_mode = (
            sandbox_mode
            or os.environ.get("CODE_ONTOLOGY_CODEX_SANDBOX")
            or "workspace-write"
        )
        if self.sandbox_mode not in {
            "read-only",
            "workspace-write",
            "danger-full-access",
        }:
            raise invalid(
                "CODE_ONTOLOGY_CODEX_SANDBOX 必须是 read-only、"
                "workspace-write 或 danger-full-access"
            )
        self.run_timeout_seconds = run_timeout_seconds
        self.ignore_user_config = ignore_user_config
        self.runner = runner or subprocess.run
        self._sessions: set[str] = set()

    def describe(self) -> dict[str, Any]:
        version = None
        if self.binary is not None and self.binary.is_file():
            try:
                result = subprocess.run(
                    [str(self.binary), "--version"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
                if result.returncode == 0:
                    version = result.stdout.strip() or result.stderr.strip()
            except (OSError, subprocess.SubprocessError):
                version = None
        return {
            "runtime": "Codex",
            "available": self.binary is not None and self.binary.is_file(),
            "binary": str(self.binary) if self.binary is not None else None,
            "version": version,
            "apiVersion": CODEX_API_VERSION,
            "sandboxMode": self.sandbox_mode,
            "ignoreUserConfig": self.ignore_user_config,
        }

    def execute(
        self,
        *,
        worktree: Path,
        run_id: str,
        prompt: str,
        agent_name: str,
        allowed_files: list[str],
        forbidden_files: list[str],
        required_tests: list[str],
        skill_name: str = "implement-approved-change",
        read_only: bool = False,
    ) -> dict[str, Any]:
        if self.binary is None or not self.binary.is_file():
            raise PlatformError(
                503,
                "CODEX_UNAVAILABLE",
                "未找到 Codex CLI；请安装 Codex 或配置 CODEX_BINARY",
            )
        if read_only:
            with _isolated_codex_read_worktree(
                worktree, run_id
            ) as (isolated, base_commit):
                result = self._execute(
                    worktree=isolated,
                    run_id=run_id,
                    prompt=prompt,
                    agent_name=agent_name,
                    skill_name=skill_name,
                    read_only=True,
                )
                diff = collect_worktree_diff(isolated, base_commit)
                if diff["changedFiles"] or not diff["headUnchanged"]:
                    raise PlatformError(
                        409,
                        "CODEX_READ_ONLY_VIOLATION",
                        "Codex 只读角色修改了隔离工作树，结果已拒绝并清理",
                        {
                            "sessionId": result.get("sessionId"),
                            "changedFiles": diff["changedFiles"],
                            "headUnchanged": diff["headUnchanged"],
                        },
                    )
                result["readOnlyIsolation"] = {
                    "status": "Passed",
                    "headUnchanged": True,
                    "changedFiles": [],
                }
                return result
        return self._execute(
            worktree=worktree,
            run_id=run_id,
            prompt=prompt,
            agent_name=agent_name,
            skill_name=skill_name,
            read_only=False,
        )

    def _execute(
        self,
        *,
        worktree: Path,
        run_id: str,
        prompt: str,
        agent_name: str,
        skill_name: str,
        read_only: bool,
    ) -> dict[str, Any]:
        command = [str(self.binary), "exec"]
        if self.ignore_user_config:
            command.append("--ignore-user-config")
        command.extend(
            [
                "--ephemeral",
                "--sandbox",
                self.sandbox_mode,
                "-c",
                'approval_policy="never"',
                "--json",
            ]
        )
        if self.model:
            command.extend(["--model", self.model])
        command.append("-")
        governed_prompt = (
            "You are executing a governed platform stage. The skill name below "
            "is a workflow label; do not search for or install a SKILL.md. Use "
            "only the supplied local repository and context. Do not use web "
            "search, connectors, subagents, or external services. Never commit, "
            "push, merge, rebase, tag, or deploy. "
            + (
                "This role is read-only; do not modify any file. "
                if read_only
                else "Modify only the approved files and leave changes uncommitted. "
            )
            + f"Role: {agent_name}. Skill label: {skill_name}. Run: {run_id}.\n\n"
            + prompt
        )
        environment = {
            **os.environ,
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_SSH_COMMAND": "false",
        }
        try:
            completed = self.runner(
                command,
                cwd=worktree,
                input=governed_prompt,
                capture_output=True,
                text=True,
                timeout=self.run_timeout_seconds,
                env=environment,
                check=False,
            )
        except FileNotFoundError as error:
            raise PlatformError(
                503, "CODEX_UNAVAILABLE", "Codex CLI 可执行文件不存在"
            ) from error
        except subprocess.TimeoutExpired as error:
            partial = (
                error.stdout.decode(errors="replace")
                if isinstance(error.stdout, bytes)
                else (error.stdout or "")
            )
            summary = _codex_event_summary(partial)
            raise PlatformError(
                504,
                "CODEX_RUN_TIMEOUT",
                "Codex Agent Run 超过平台 Deadline，进程已中止",
                {
                    "sessionId": summary["threadId"],
                    "timeoutSeconds": self.run_timeout_seconds,
                    "eventCounts": summary["eventCounts"],
                },
            ) from error
        summary = _codex_event_summary(completed.stdout)
        if completed.returncode != 0:
            raise PlatformError(
                502,
                "CODEX_EXEC_FAILED",
                f"Codex CLI 退出码为 {completed.returncode}",
                {
                    "sessionId": summary["threadId"],
                    "stderrTail": completed.stderr[-4000:],
                    "eventCounts": summary["eventCounts"],
                    "errors": summary["errors"],
                },
            )
        if (
            not summary["turnCompleted"]
            or summary["errors"]
            or summary["finalMessage"] is None
        ):
            raise PlatformError(
                502,
                "CODEX_INVALID_RESPONSE",
                "Codex CLI 未返回完整的最终 Agent 消息",
                {
                    "sessionId": summary["threadId"],
                    "turnCompleted": summary["turnCompleted"],
                    "eventCounts": summary["eventCounts"],
                    "errors": summary["errors"],
                    "stderrTail": completed.stderr[-4000:],
                },
            )
        session_id = str(summary["threadId"] or f"codex-{run_id}")
        self._sessions.add(session_id)
        return {
            "runtime": "Codex",
            "runtimeVersion": self.describe().get("version"),
            "apiVersion": CODEX_API_VERSION,
            "sessionId": session_id,
            "message": {
                "role": "assistant",
                "text": summary["finalMessage"],
                "messages": summary["messages"],
            },
            "events": {
                "counts": summary["eventCounts"],
                "commands": summary["commands"],
                "fileChanges": summary["fileChanges"],
                "invalidJsonLines": summary["invalidJsonLines"],
            },
            "usage": summary["usage"],
            "stderrTail": completed.stderr[-4000:],
            "connectedProviders": ["codex-auth"],
            "agentName": agent_name,
            "skillName": skill_name,
            "readOnly": read_only,
            "sandboxMode": self.sandbox_mode,
            "statusHistory": [
                value
                for value in ("turn.started", "turn.completed")
                if summary["eventCounts"].get(value)
            ],
        }

    def respond_permission(
        self, session_id: str, permission_id: str, response: str
    ) -> bool:
        if session_id not in self._sessions:
            raise conflict("Codex Session 已结束或不属于当前运行时")
        raise conflict("Codex 非交互运行固定使用 approval_policy=never，无待决权限请求")


def default_agent_adapter(project_root: str | Path) -> AgentAdapter:
    runtime = os.environ.get("CODE_ONTOLOGY_AGENT_RUNTIME", "auto").strip().lower()
    if runtime not in {"auto", "codex", "opencode"}:
        raise invalid(
            "CODE_ONTOLOGY_AGENT_RUNTIME 必须是 auto、codex 或 opencode"
        )
    codex_binary = os.environ.get("CODEX_BINARY") or shutil.which("codex")
    opencode_binary = os.environ.get("OPENCODE_BINARY") or shutil.which("opencode")
    if runtime == "codex" or (runtime == "auto" and codex_binary):
        return CodexAdapter(codex_binary)
    if runtime == "opencode" or (runtime == "auto" and opencode_binary):
        return OpenCodeAdapter(Path(project_root) / ".opencode", opencode_binary)
    return CodexAdapter(codex_binary)


class ScriptedAgentAdapter:
    """Deterministic test adapter; production selects Codex or OpenCode."""

    def __init__(
        self,
        action: Callable[[Path, str], Mapping[str, Any]],
    ) -> None:
        self.action = action

    def execute(
        self,
        *,
        worktree: Path,
        run_id: str,
        prompt: str,
        agent_name: str,
        allowed_files: list[str],
        forbidden_files: list[str],
        required_tests: list[str],
        skill_name: str = "implement-approved-change",
        read_only: bool = False,
    ) -> dict[str, Any]:
        result = dict(self.action(worktree, prompt))
        return {
            "runtime": "ScriptedTestAdapter",
            "runtimeVersion": "1",
            "apiVersion": "test",
            "sessionId": f"scripted-{run_id}",
            "message": result,
            "serverDiff": [],
            "connectedProviders": ["scripted"],
            "agentName": agent_name,
            "skillName": skill_name,
            "readOnly": read_only,
        }

    def respond_permission(
        self, session_id: str, permission_id: str, response: str
    ) -> bool:
        return response in {"once", "always", "reject"}


def build_agent_prompt(
    plan: Mapping[str, Any],
    implementation_context: Mapping[str, Any],
) -> str:
    payload = {
        "changePlanId": plan["planId"],
        "requirementId": plan["changeSet"]["requirementId"],
        "baseRevision": plan["changeSet"]["currentRevision"],
        "requirementContext": plan.get("requirementContext", {}),
        "approvedProposals": plan["proposals"],
        "implementationTasks": plan["implementationTasks"],
        "verificationObligations": plan["verificationObligations"],
        "allowedFiles": implementation_context["allowedFiles"],
        "forbiddenFiles": implementation_context["forbiddenFiles"],
        "requiredTests": implementation_context["requiredTests"],
    }
    return (
        "Load the `implement-approved-change` skill, then evaluate every "
        "approved proposal and implement every applicable approved task below. "
        "The desiredEntity label is the authoritative requirement text for its "
        "proposal. Do not commit, push, merge, rebase, tag, deploy, or access "
        "production. For every proposalId, return exactly one status from "
        "Implemented, AlreadySatisfied, Blocked, or NotApplicable, together "
        "with concrete file/graph evidence. Never claim a proposal was "
        "implemented solely because the overall requirement or tests passed. "
        "Also return changed files, tests and results, unresolved issues, and "
        "deviations.\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )
