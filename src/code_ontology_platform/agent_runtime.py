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
import time
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
        if candidate:
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


class ScriptedAgentAdapter:
    """Deterministic integration-test adapter; production uses OpenCodeAdapter."""

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
        "implementationTasks": plan["implementationTasks"],
        "verificationObligations": plan["verificationObligations"],
        "allowedFiles": implementation_context["allowedFiles"],
        "forbiddenFiles": implementation_context["forbiddenFiles"],
        "requiredTests": implementation_context["requiredTests"],
    }
    return (
        "Load the `implement-approved-change` skill, then implement only the "
        "approved tasks below. Do not commit, push, merge, rebase, tag, deploy, "
        "or access production. Return the changed files, proposal IDs, tests, "
        "results, unresolved issues, and deviations.\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )
