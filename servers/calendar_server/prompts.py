from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    @mcp.prompt()
    def schedule_review_meeting(customer: str, duration_minutes: int = 30) -> str:
        """Template for booking a customer review meeting."""
        return (
            f"Schedule a {duration_minutes}-minute review meeting for customer '{customer}'.\n"
            "1. Call find_free_slots over the next 7 days.\n"
            "2. Pick the earliest slot.\n"
            f"3. Call create_event titled 'Account Review: {customer}' for that slot.\n"
            "4. Report the final date and time."
        )