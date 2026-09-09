import asyncio
import json
import os
import re

from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from agent import answer_question, get_llm
from db.connection import fetch_table_schema, get_engine

load_dotenv()


def _parse_tool_result(raw_result) -> list[dict]:
    if getattr(raw_result, "is_error", False):
        content = getattr(raw_result, "content", [])
        text_parts = []
        for item in content:
            text = getattr(item, "text", None)
            if text:
                text_parts.append(str(text))
        if text_parts:
            raise ValueError("MCP tool error: " + " | ".join(text_parts))
        raise ValueError("MCP tool returned an error without details.")

    structured = getattr(raw_result, "structured_content", None)
    if isinstance(structured, list):
        return structured
    if isinstance(structured, dict):
        return [structured]

    content = getattr(raw_result, "content", [])
    if not content:
        return []

    first = content[0]
    text = getattr(first, "text", None)
    if not text:
        return []

    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            return [parsed]
    except (TypeError, ValueError):
        return []

    return []


def _is_valid_sql_for_schema(sql: str, table_name: str, schema: list[dict]) -> bool:
    if not sql or not sql.strip().lower().startswith("select"):
        return False

    if re.search(r"\bfrom\s+([a-zA-Z_][\w]*)\b", sql, re.IGNORECASE):
        match = re.search(r"\bfrom\s+([a-zA-Z_][\w]*)\b", sql, re.IGNORECASE)
        if match and match.group(1).lower() != table_name.lower():
            return False

    allowed_columns = {str(row["column_name"]).lower() for row in schema}
    selected_columns = re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\b", sql)
    for col in selected_columns:
        lower_col = col.lower()
        if lower_col in {"select", "from", "where", "and", "or", "as", "on", "join", "limit", "order", "by", "group", "having", "count", "sum", "avg", "min", "max", "distinct", "where", "like", "in", "between", "not", "null", "is", "desc", "asc"}:
            continue
        if lower_col not in allowed_columns and lower_col not in {"employee_salary"}:
            return False
    return True


def _build_fallback_sql(question: str, table_name: str, schema: list[dict]) -> str:
    q = question.strip().lower()
    name_match = re.search(r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)", question)
    person_name = name_match.group(1) if name_match else None

    if person_name:
        if "base salary" in q or ("salary" in q and "base" in q):
            return f"SELECT base_salary FROM {table_name} WHERE emp_name = '{person_name}' LIMIT 1"
        if "total salary" in q:
            return f"SELECT total_salary FROM {table_name} WHERE emp_name = '{person_name}' LIMIT 1"
        if "bonus" in q:
            return f"SELECT bonus FROM {table_name} WHERE emp_name = '{person_name}' LIMIT 1"

    if "base_salary" in {str(row["column_name"]).lower() for row in schema}:
        return f"SELECT base_salary FROM {table_name} LIMIT 5"
    return f"SELECT * FROM {table_name} LIMIT 5"


async def ask_employee_salary(question: str) -> str:
    table_name = os.getenv("TABLE_NAME", "employee_salary")
    schema = fetch_table_schema(get_engine(), table_name)

    llm = get_llm()
    sql_prompt = (
        "You are a MySQL SQL assistant. "
        "Use the exact table name and columns from the schema. "
        "Never invent tables or columns. "
        "Generate exactly one safe SELECT statement. "
        "Return only SQL, no markdown.\n\n"
        f"Schema: {schema}\n\nQuestion: {question}"
    )

    generated_sql = ""
    for _ in range(2):
        generated_sql = str(llm.invoke(sql_prompt).content).strip()
        if generated_sql.startswith("```"):
            generated_sql = generated_sql.replace("```sql", "").replace("```", "").strip()
        if _is_valid_sql_for_schema(generated_sql, table_name, schema):
            break
        sql_prompt = (
            sql_prompt
            + "\nImportant: Use the exact table name 'employee_salary' and only the schema columns listed above. "
            "Do not use names like 'employees' or unknown columns."
        )
    else:
        generated_sql = _build_fallback_sql(question, table_name, schema)

    server_params = StdioServerParameters(
        command="python",
        args=["mcp_server.py"],
        cwd=".",
    )

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tool_result = await session.call_tool("query_employee_salary", {"sql": generated_sql})
            rows = _parse_tool_result(tool_result)
            if not rows:
                raise ValueError(f"No result returned from MCP server for SQL: {generated_sql}")
            return answer_question(question, schema, rows)


def main() -> None:
    print("QueryBridge local AI demo")
    print("Example: What is the average salary by department?")
    question = input("Ask your question: ").strip()
    if not question:
        print("No question entered.")
        return

    print("\nAnswer:\n")
    print(asyncio.run(ask_employee_salary(question)))


if __name__ == "__main__":
    main()
