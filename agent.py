import os
from typing import Any

from dotenv import load_dotenv
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_core.prompts import ChatPromptTemplate

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
    llm = get_llm()
    answer_prompt = build_answer_prompt()
    response = llm.invoke(answer_prompt.format(question=question, result=result))
    return response.content
