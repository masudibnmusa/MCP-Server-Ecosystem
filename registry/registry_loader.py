"""Load and validate registry/servers.json. Add or remove servers without touching code."""
import json
from dataclasses import dataclass
from pathlib import Path

from jsonschema import Draft7Validator

from agent.mcp_client.namespace import NamespaceError, validate_server_name

SCHEMA_PATH = Path(__file__).with_name("servers.schema.json")


class RegistryError(Exception):
    pass


@dataclass(frozen=True)
class ServerSpec:
    name: str
    transport: str  # "stdio" | "http"
    command: str | None = None
    args: tuple[str, ...] = ()
    env_vars: tuple[str, ...] = ()
    url: str | None = None
    auth_env: str | None = None  # env var holding the bearer token
    trusted: bool = False
    enabled: bool = True
    call_timeout_s: float | None = None
    allow: tuple[str, ...] = ()
    deny: tuple[str, ...] = ()


def load_registry(path: Path | str) -> list[ServerSpec]:
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise RegistryError(f"Registry file not found: {path}")
    except json.JSONDecodeError as e:
        raise RegistryError(f"{path} is not valid JSON: {e}")

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = sorted(Draft7Validator(schema).iter_errors(data), key=lambda e: list(map(str, e.path)))
    if errors:
        lines = [f"  {'/'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in errors]
        raise RegistryError(f"{path} failed validation:\n" + "\n".join(lines))

    specs: list[ServerSpec] = []
    seen: set[str] = set()
    for item in data["servers"]:
        name = item["name"]
        try:
            validate_server_name(name)
        except NamespaceError as e:
            raise RegistryError(str(e))
        if name in seen:
            raise RegistryError(f"Duplicate server name: {name!r}")
        seen.add(name)

        perms = item.get("permissions", {})
        auth = item.get("auth") or {}
        specs.append(
            ServerSpec(
                name=name,
                transport=item["transport"],
                command=item.get("command"),
                args=tuple(item.get("args", ())),
                env_vars=tuple(item.get("env", ())),
                url=item.get("url"),
                auth_env=auth.get("env"),
                trusted=item.get("trusted", False),
                enabled=item.get("enabled", True),
                call_timeout_s=item.get("call_timeout_s"),
                allow=tuple(perms.get("allow", ())),
                deny=tuple(perms.get("deny", ())),
            )
        )
    return [s for s in specs if s.enabled]