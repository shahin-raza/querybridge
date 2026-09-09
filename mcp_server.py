import os
from typing import Any

from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer

from db.connection import fetch_table_schema, get_engine, run_query

load_dotenv()

mcp = MCPServer("salary-db-mcp")


@mcp.tool()
def get_employee_salary_schema() -> list[dict[str, Any]]:
    """Return the schema of the employee_salary table for AI/agent use."""
    table_name = os.getenv("TABLE_NAME", "employee_salary")
    return fetch_table_schema(get_engine(), table_name)


@mcp.tool()
def read_employee_salary(limit: int = 10) -> list[dict[str, Any]]:
    """Read the latest rows from employee_salary. Keep the result small for LLM use."""
    table_name = os.getenv("TABLE_NAME", "employee_salary")
    engine = get_engine()
    return run_query(engine, f"SELECT * FROM {table_name} LIMIT {max(1, min(limit, 50))}")


@mcp.tool()
def query_employee_salary(sql: str) -> list[dict[str, Any]]:
    """Run a read-only SQL query against the employee_salary table. Only SELECT statements are allowed."""
    sql = sql.strip()
    if not sql.lower().startswith("select"):
        raise ValueError("Only SELECT queries are allowed.")
    return run_query(get_engine(), sql)


if __name__ == "__main__":
    mcp.run(transport="stdio")
