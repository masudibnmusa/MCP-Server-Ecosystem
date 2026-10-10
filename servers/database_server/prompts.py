from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    @mcp.prompt()
    def analyze_table(table: str) -> str:
        """Template for a structured analysis of one table."""
        return (
            f"Analyze the table `{table}`.\n"
            f"1. Call describe_table for `{table}` to learn its columns.\n"
            "2. Use run_query to profile it: row count, nulls, distinct values, min/max of "
            "numeric and date columns.\n"
            "3. Look for outliers, duplicates, or data-quality problems.\n"
            "4. Finish with a short summary and three follow-up questions worth investigating."
        )