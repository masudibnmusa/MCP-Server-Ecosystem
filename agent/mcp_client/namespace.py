"""calendar + create_event  <->  calendar__create_event

Rules that keep this unambiguous:
- Server names use single '-' or '_' separators only, so they never contain '__'.
- Therefore the FIRST '__' always marks the server/tool boundary. Tool names may contain
  underscores freely, even a leading one ("srv___private" -> ("srv", "_private")).
- Result must satisfy LLM tool-name rules: letters, digits, '_' and '-', max 64 chars.
"""
import re

SEPARATOR = "__"
_SERVER_RE = re.compile(r"^[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)*$")
_LLM_TOOL_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class NamespaceError(ValueError):
    pass


def validate_server_name(server: str) -> str:
    if not server or not _SERVER_RE.match(server):
        raise NamespaceError(
            f"Invalid server name {server!r}: use letters/digits separated by single '-' or '_' "
            "(no leading, trailing, or double underscores)."
        )
    return server


def make_name(server: str, tool: str) -> str:
    validate_server_name(server)
    if not tool:
        raise NamespaceError("Tool name is empty.")
    name = f"{server}{SEPARATOR}{tool}"
    if not _LLM_TOOL_RE.match(name):
        raise NamespaceError(
            f"{name!r} is not a valid LLM tool name (letters, digits, '_' and '-' only, max 64 chars)."
        )
    return name


def split_name(namespaced: str) -> tuple[str, str]:
    server, sep, tool = namespaced.partition(SEPARATOR)  # FIRST separator only
    if not sep or not tool:
        raise NamespaceError(f"{namespaced!r} is not a namespaced tool name (expected server__tool).")
    validate_server_name(server)
    return server, tool