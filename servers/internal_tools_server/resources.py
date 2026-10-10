import json

from mcp.server.fastmcp import FastMCP

_TEMPLATES = {
    "bug": {"title": "[Bug] <summary>", "description": "Steps to reproduce:\nExpected:\nActual:", "priority": "high"},
    "feature": {"title": "[Feature] <summary>", "description": "Problem:\nProposed solution:", "priority": "medium"},
    "customer_follow_up": {
        "title": "Follow up: <customer> account review",
        "description": "Meeting date:\nAction items:\nOwner:",
        "priority": "medium",
    },
}

_TEAM = [
    {"name": "Priya Nair", "role": "Account Manager", "handle": "@priya"},
    {"name": "Tom Becker", "role": "Support Lead", "handle": "@tom"},
    {"name": "Aiko Tanaka", "role": "Engineering Manager", "handle": "@aiko"},
]


def register(mcp: FastMCP) -> None:
    @mcp.resource("tickets://templates", mime_type="application/json")
    def ticket_templates() -> str:
        """Ticket templates (bug, feature, customer_follow_up)."""
        return json.dumps(_TEMPLATES, indent=2)

    @mcp.resource("team://members", mime_type="application/json")
    def team_members() -> str:
        """Team members who can be assigned tickets."""
        return json.dumps(_TEAM, indent=2)