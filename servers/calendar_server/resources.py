import json

from mcp.server.fastmcp import FastMCP

from . import config


def register(mcp: FastMCP) -> None:
    @mcp.resource("calendar://working-hours", mime_type="application/json")
    def working_hours() -> str:
        """Working hours used by find_free_slots."""
        return json.dumps(
            {
                "timezone": str(config.TZ),
                "start": config.WORK_START.isoformat(timespec="minutes"),
                "end": config.WORK_END.isoformat(timespec="minutes"),
                "days": ["Mon", "Tue", "Wed", "Thu", "Fri"],
            },
            indent=2,
        )

    @mcp.resource("calendar://list", mime_type="application/json")
    def calendars() -> str:
        """The calendars this server can read and write."""
        return json.dumps(
            [{"id": "primary", "provider": config.PROVIDER, "timezone": str(config.TZ)}], indent=2
        )