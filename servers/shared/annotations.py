"""Servers DECLARE what a tool does; the agent's approval_gate ENFORCES the policy.

Anything without readOnlyHint=True is treated as needing human approval by the agent.
"""
from mcp.types import ToolAnnotations

READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

# Adds data but does not overwrite or delete anything (create_event, create_ticket, ...)
WRITE_ADDITIVE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=False,
)

# May modify or remove existing data (insert_record is declared here to be conservative)
WRITE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=True,
    idempotentHint=False,
    openWorldHint=False,
)