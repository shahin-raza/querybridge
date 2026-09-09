import os
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

load_dotenv()


def get_db_url() -> str:
    host = os.getenv("DB_HOST", "127.0.0.1")
    db_name = os.getenv("DB_NAME", "mcp_db")
    user = os.getenv("DB_USER", "root")
    password = os.getenv("DB_PASSWORD", "")
    port = os.getenv("DB_PORT", "3306")

    return f"mysql+pymysql://{user}:{password}@{host}:{port}/{db_name}"


def get_engine() -> Engine:
    return create_engine(get_db_url(), pool_pre_ping=True)


def fetch_table_schema(engine: Engine, table_name: str) -> list[dict[str, Any]]:
    with engine.connect() as conn:
        result = conn.execute(
            text(
                """
                SELECT COLUMN_NAME AS column_name,
                       DATA_TYPE AS data_type,
                       IS_NULLABLE AS is_nullable
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME = :table_name
                ORDER BY ORDINAL_POSITION
                """
            ),
            {"table_name": table_name},
        )
        return [
            {
                "column_name": row[0],
                "data_type": row[1],
                "is_nullable": row[2],
            }
            for row in result.fetchall()
        ]


def run_query(engine: Engine, query: str) -> list[dict[str, Any]]:
    with engine.connect() as conn:
        result = conn.execute(text(query))
        rows = result.mappings().all()
        return [dict(row) for row in rows]
