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

    # ✅ Check table name
    match = re.search(r"\bfrom\s+([a-zA-Z_][\w]*)\b", sql, re.IGNORECASE)
    if match and match.group(1).lower() != table_name.lower():
        return False

    # ✅ Allowed columns from schema
    allowed_columns = {row["column_name"].lower() for row in schema}

    # ✅ Extract columns only from SELECT clause
    select_match = re.search(r"select\s+(.*?)\s+from", sql, re.IGNORECASE | re.DOTALL)
    if select_match:
        selected = select_match.group(1)
        # split by commas, strip aliases
        selected_columns = [col.strip().split()[0].lower() for col in selected.split(",")]
        for col in selected_columns:
            if col != "*" and col not in allowed_columns:
                return False

    return True


def _as_float(value) -> float:
    if value in (None, "", "N/A"):
        return 0.0
    try:
        if isinstance(value, (int, float)):
            return float(value)
        cleaned = str(value).replace("$", "").replace(",", "").strip()
        return float(cleaned)
    except (TypeError, ValueError):
        return 0.0


def _sort_rows_for_question(question: str, rows: list[dict]) -> list[dict]:
    q = question.lower()
    if any(word in q for word in ["high to low", "highest to lowest", "descending", "top salary", "from high to low"]):
        return sorted(rows, key=lambda row: _as_float(row.get("total_salary", row.get("base_salary", 0))), reverse=True)
    if any(word in q for word in ["low to high", "lowest to highest", "ascending"]):
        return sorted(rows, key=lambda row: _as_float(row.get("total_salary", row.get("base_salary", 0))))
    return rows


def _needs_income_sort(question: str) -> bool:
    q = question.lower()
    salary_terms = ["salary", "total salary", "base salary"]
    order_terms = ["sort", "sorted", "order", "high to low", "low to high", "highest", "lowest", "descending", "ascending"]
    return any(term in q for term in salary_terms) and any(term in q for term in order_terms)


def _build_salary_order_sql(question: str, table_name: str) -> str:
    q = question.lower()
    if any(term in q for term in ["high to low", "highest", "descending", "sort", "sorted", "order"]) and "low to high" not in q:
        return f"SELECT emp_name, total_salary FROM {table_name} ORDER BY total_salary DESC"
    return f"SELECT emp_name, total_salary FROM {table_name} ORDER BY total_salary ASC"


def _build_fallback_sql(question: str, table_name: str, schema: list[dict]) -> str:
    q = question.strip().lower()
    name_match = re.search(r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)", question)
    person_name = name_match.group(1) if name_match else None

    if _needs_income_sort(question):
        return _build_salary_order_sql(question, table_name)

    if "total salary" in q and ("high to low" in q or "highest" in q or "descending" in q or "from high to low" in q or "sorted" in q or "sort" in q):
        return f"SELECT emp_name, total_salary FROM {table_name} ORDER BY total_salary DESC"
    if "total salary" in q and ("low to high" in q or "lowest" in q or "ascending" in q):
        return f"SELECT emp_name, total_salary FROM {table_name} ORDER BY total_salary ASC"
    if "high to low" in q or "highest" in q or "descending" in q or "from high to low" in q:
        return f"SELECT emp_name, total_salary FROM {table_name} ORDER BY total_salary DESC"
    if "low to high" in q or "lowest" in q or "ascending" in q:
        return f"SELECT emp_name, total_salary FROM {table_name} ORDER BY total_salary ASC"

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

    if _needs_income_sort(question):
        generated_sql = _build_salary_order_sql(question, table_name)
    else:
        llm = get_llm()
        sql_prompt = (
            "You are a MySQL SQL assistant. "
            "Always use the exact table name and columns from the schema. "
            "Never invent tables or columns. "
            "Generate exactly one safe SELECT statement. "
            "Return only SQL, no markdown.\n\n"
            "Important rules:\n"
            "- For Nth highest values, use ORDER BY column DESC LIMIT N-1,1.\n"
            "- Always use the table name 'employee_salary'.\n"
            "- Only use schema columns listed below.\n"
            "- Do not invent aliases or unknown columns.\n"
            "- Prefer simple SELECT queries without CTEs or subqueries unless required.\n\n"
            f"Schema: {schema}\n\nQuestion: {question}"
       )

        generated_sql = ""
        valid_sql_statement = False

        for _ in range(2):
            generated_sql = str(llm.invoke(sql_prompt).content).strip()
            if generated_sql.startswith("```"):
                generated_sql = generated_sql.replace("```sql", "").replace("```", "").strip()
            if _is_valid_sql_for_schema(generated_sql, table_name, schema):
                valid_sql_statement = True
                break
            sql_prompt += (
                "\nImportant: Use the exact table name 'employee_salary' and only the schema columns listed above. "
                "Do not use names like 'employees' or unknown columns."
            )

        if not valid_sql_statement:
            generated_sql = _build_fallback_sql(question, table_name, schema)

    q_lower = question.lower()
    if ("total salary" in q_lower or "salary" in q_lower) and ("sort" in q_lower or "sorted" in q_lower or "high to low" in q_lower or "low to high" in q_lower or "descending" in q_lower or "ascending" in q_lower):
        if "total_salary" not in generated_sql.lower():
            generated_sql = f"SELECT emp_name, total_salary FROM {table_name} ORDER BY total_salary DESC"

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
            rows = _sort_rows_for_question(question, rows)
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
