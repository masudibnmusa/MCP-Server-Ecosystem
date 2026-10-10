import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]


def _path(env_name: str, default: str) -> Path:
    p = Path(os.getenv(env_name, default))
    return p if p.is_absolute() else ROOT / p


@dataclass(frozen=True)
class AgentConfig:
    root: Path
    registry_path: Path
    log_dir: Path
    model: str
    max_tokens: int = 4096
    connect_timeout_s: float = 20.0
    call_timeout_s: float = 30.0
    health_interval_s: float = 10.0
    ping_timeout_s: float = 5.0
    reconnect_wait_s: float = 6.0
    max_tool_rounds: int = 8
    max_replans: int = 2
    max_tools_in_context: int = 20
    max_result_chars: int = 20_000


def load_config() -> AgentConfig:
    return AgentConfig(
        root=ROOT,
        registry_path=_path("REGISTRY_PATH", "registry/servers.json"),
        log_dir=_path("LOG_DIR", "data/logs"),
        model=os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5"),
        call_timeout_s=float(os.getenv("TOOL_CALL_TIMEOUT_S", "30")),
    )