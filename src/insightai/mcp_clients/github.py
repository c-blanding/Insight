"""Read-only GitHub MCP access for source diagnosis."""

from __future__ import annotations

import json
import ipaddress
import os
from typing import Any
from urllib.parse import urlsplit

from fastmcp import Client
from langchain.mcp import MCPAdapter
from langchain_core.tools import BaseTool, StructuredTool


_ALLOWED_TOOLS = frozenset(
    {"get_repository", "get_file_contents", "search_code", "get_commit"}
)
_MAX_TOOL_RESULT_CHARS = 20_000


class GitHubMCPError(RuntimeError):
    """GitHub MCP is unavailable or does not expose the required read tools."""


def _bounded_text(value: Any) -> str:
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, default=str, ensure_ascii=False)
    if len(text) > _MAX_TOOL_RESULT_CHARS:
        return text[:_MAX_TOOL_RESULT_CHARS] + "\n[Result truncated]"
    return text


def _file_text(value: Any) -> str | None:
    """Extract text from common MCP result wrappers for citation validation."""
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return value
        if decoded != value:
            extracted = _file_text(decoded)
            if extracted is not None:
                return extracted
        return value
    if isinstance(value, dict):
        for key in ("text", "content", "contents", "file_content", "fileContent", "data"):
            if key in value:
                extracted = _file_text(value[key])
                if extracted is not None:
                    return extracted
        return None
    if isinstance(value, list):
        chunks = [part for item in value if (part := _file_text(item)) is not None]
        return "\n".join(chunks) if chunks else None
    content = getattr(value, "content", None)
    return _file_text(content) if content is not None else None


def _bounded_tool(
    tool: BaseTool,
    repo: str,
    commit_sha: str,
    verified_line_counts: dict[str, int],
) -> StructuredTool:
    owner, repository = repo.split("/", maxsplit=1)
    fields = getattr(tool.args_schema, "model_fields", None)
    if fields is None:
        schema = tool.args_schema.schema() if tool.args_schema else {}
        fields = schema.get("properties", {})

    async def invoke(**arguments: Any) -> str:
        if "owner" in fields:
            arguments["owner"] = owner
        if "repo" in fields:
            arguments["repo"] = repository
        if tool.name == "get_file_contents":
            revision_field = "ref" if "ref" in fields else "sha"
            arguments[revision_field] = commit_sha
        elif tool.name == "get_commit":
            revision_field = "sha" if "sha" in fields else "ref"
            arguments[revision_field] = commit_sha
        elif tool.name == "search_code":
            query = str(arguments.get("query") or "").strip()
            if f"repo:{repo}" not in query:
                arguments["query"] = f"repo:{repo} {query}".strip()
        result = await tool.ainvoke(arguments)
        if tool.name == "get_file_contents":
            path = str(arguments.get("path") or "").replace("\\", "/")
            content = _file_text(result)
            if path and not path.startswith("/") and ".." not in path.split("/"):
                if content is not None:
                    verified_line_counts[path] = len(content.splitlines())
        return _bounded_text(result)

    return StructuredTool.from_function(
        coroutine=invoke,
        name=tool.name,
        description=tool.description or "Read-only GitHub repository lookup.",
        args_schema=tool.args_schema,
    )


def _tool_fields(tool: BaseTool) -> set[str]:
    fields = getattr(tool.args_schema, "model_fields", None)
    if fields is not None:
        return set(fields)
    schema = tool.args_schema.schema() if tool.args_schema else {}
    return set((schema.get("properties") or {}).keys())


class GitHubMCP:
    """Expose a small allowlist of read-only GitHub tools to the diagnosis agent.

    Configure ``GITHUB_MCP_URL`` with an HTTP(S) MCP endpoint. A bearer token may
    be supplied through ``GITHUB_MCP_TOKEN``; it is used only by the MCP client
    and is never included in graph state or model-visible tool arguments.
    """

    def __init__(
        self,
        repo: str,
        commit_sha: str,
        url: str | None = None,
        token: str | None = None,
    ) -> None:
        self.repo = repo
        self.commit_sha = commit_sha
        self.url = (url or os.environ.get("GITHUB_MCP_URL", "")).strip()
        self.token = token if token is not None else os.environ.get("GITHUB_MCP_TOKEN")
        try:
            parsed_url = urlsplit(self.url)
            hostname = parsed_url.hostname or ""
            parsed_url.port  # Force validation of malformed ports.
            is_loopback = hostname.lower() == "localhost"
            if hostname:
                try:
                    is_loopback = ipaddress.ip_address(hostname).is_loopback
                except ValueError:
                    pass
            if (
                parsed_url.scheme not in {"http", "https"}
                or not hostname
                or parsed_url.username is not None
                or parsed_url.password is not None
                or (parsed_url.scheme == "http" and not is_loopback)
            ):
                raise ValueError("endpoint must use HTTPS, except on loopback")
        except ValueError as exc:
            raise GitHubMCPError(
                "GITHUB_MCP_URL must be HTTPS (HTTP is allowed only on loopback)"
            ) from exc
        target = Client(self.url, auth=self.token) if self.token else self.url
        self.adapter = MCPAdapter(target)
        self._entered = False
        self.verified_line_counts: dict[str, int] = {}

    async def __aenter__(self) -> "GitHubMCP":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        await self.stop()

    async def start(self) -> list[StructuredTool]:
        try:
            await self.adapter.__aenter__()
            self._entered = True
            discovered = await self.adapter.list_tools()
        except Exception as exc:
            await self.stop()
            raise GitHubMCPError("Could not connect to the configured GitHub MCP") from exc

        selected = []
        selected_names: set[str] = set()
        for tool in discovered:
            if tool.name not in _ALLOWED_TOOLS:
                continue
            fields = _tool_fields(tool)
            if not {"owner", "repo"}.issubset(fields):
                continue
            if tool.name == "get_file_contents" and (
                "path" not in fields or not ({"ref", "sha"} & fields)
            ):
                continue
            if tool.name == "get_commit" and not ({"sha", "ref"} & fields):
                continue
            if tool.name == "search_code" and "query" not in fields:
                continue
            selected.append(
                _bounded_tool(
                    tool, self.repo, self.commit_sha, self.verified_line_counts
                )
            )
            selected_names.add(tool.name)
        required = {
            "get_repository",
            "search_code",
            "get_commit",
            "get_file_contents",
        }
        if not required.issubset(selected_names):
            await self.stop()
            missing = ", ".join(sorted(required - selected_names))
            raise GitHubMCPError(
                f"GitHub MCP must expose revision-pinned tools: {missing}"
            )
        if not selected:
            await self.stop()
            raise GitHubMCPError(
                "GitHub MCP did not expose any allowed read-only repository tools"
            )
        return selected

    async def stop(self) -> None:
        if not self._entered:
            return
        self._entered = False
        await self.adapter.__aexit__(None, None, None)
