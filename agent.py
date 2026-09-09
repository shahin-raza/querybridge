import os
from typing import Any

from dotenv import load_dotenv
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_core.prompts import ChatPromptTemplate


def _format_sorted_salary_answer(question: str, result: list[dict[str, Any]]) -> str:
    q = question.lower()
    if not any(term in q for term in ["sort", "sorted", "order", "high to low", "low to high", "highest", "lowest", "descending", "ascending"]):
        return ""

    items: list[str] = []
    for index, row in enumerate(result, start=1):
        name = row.get("emp_name") or row.get("employee_name") or row.get("name")
        if not name:
            continue
        salary = row.get("total_salary") or row.get("base_salary") or row.get("salary")
        items.append(f"{index}. **{name}** - Total Salary: {salary if salary not in (None, '', 'N/A') else 'Not specified'}")

    if not items:
        return ""

    direction = "from high to low" if any(term in q for term in ["high to low", "highest", "descending", "sort", "sorted"]) else "from low to high"
    return f"Based on the query results, here is the list of employee names sorted by total salary {direction}:\n\n" + "\n".join(items)

load_dotenv()


MODEL_NAME = os.getenv("LLM_MODEL", "llama3.1")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


def get_llm() -> ChatOllama:
    return ChatOllama(
        model=MODEL_NAME,
        base_url=BASE_URL,
        temperature=0,
    )


def get_embeddings() -> OllamaEmbeddings:
    return OllamaEmbeddings(model=EMBEDDING_MODEL, base_url=BASE_URL)


def build_sql_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a SQL assistant for a Mysql database. "
                "Use the provided schema and table data to answer the user's question. "
                "Only return valid SELECT SQL. Do not use UPDATE/INSERT/DELETE. "
                "If the question is ambiguous, prefer a simple query that is safe and explanatory.",
            ),
            (
                "user",
                "Schema:\n{schema}\n\nQuestion:\n{question}",
            ),
        ]
    )


def build_answer_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a helpful analyst. Answer the question using the database query results. "
                "Be concise, factual, and mention numbers clearly.",
            ),
            (
                "user",
                "Question:\n{question}\n\nQuery Result:\n{result}",
            ),
        ]
    )


def answer_question(question: str, schema: list[dict[str, Any]], result: list[dict[str, Any]]) -> str:
    direct_answer = _format_sorted_salary_answer(question, result)
    if direct_answer:
        return direct_answer

    llm = get_llm()
    answer_prompt = build_answer_prompt()
    response = llm.invoke(answer_prompt.format(question=question, result=result))
    return response.content
