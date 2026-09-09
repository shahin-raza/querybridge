# QueryBridge

QueryBridge is a local AI application that connects a MySQL database to an Ollama-powered language model through an MCP (Model Context Protocol) tool server. It lets you ask natural-language questions about your data while keeping database access structured, safe, and local.

## What this project does

- Exposes MySQL read operations through an MCP server
- Uses a local Ollama LLM to generate a safe SQL query
- Validates the SQL against the real table schema
- Executes the query through the MCP tool layer
- Passes the result back to the LLM for a human-readable answer

This app is intended for local development and experimentation with:
- MySQL running in XAMPP
- Ollama models running on the same machine
- Python 3.12 + uv for project management

## Architecture

- `main.py` – client entry point, asks a question and orchestrates the flow
- `mcp_server.py` – MCP server that exposes safe database tools
- `db/connection.py` – MySQL connection and SQL execution helpers
- `agent.py` – Ollama LLM and prompt logic
- `.env` – local environment variables for DB and model configuration

## Prerequisites

Before running the application, make sure you have:

- Python 3.12+
- uv installed
- Ollama installed and running locally
- XAMPP or another local MySQL service running
- A MySQL database named `mcp_db`
- A table named `employee_salary` in that database

## Install uv

If you do not have uv installed yet:

```bash
pip install uv
```

Or follow the official uv installation instructions for your OS.

## Ollama setup

Make sure Ollama is installed and the service is running.

Pull the required models:

```bash
ollama pull llama3.1
ollama pull nomic-embed-text
```

Start Ollama:

```bash
ollama serve
```

If Ollama is already running in the background, you can skip this step.

The app uses these default values:

```env
OLLAMA_BASE_URL=http://localhost:11434
LLM_MODEL=llama3.1
EMBEDDING_MODEL=nomic-embed-text
```

## MySQL / XAMPP setup

This project is configured to work with a local MySQL instance, typically running under XAMPP.

### Recommended DB values

Use the following values in your `.env` file:

```env
DB_HOST=127.0.0.1
DB_NAME=mcp_db
DB_USER=root
DB_PASSWORD=root
DB_PORT=3306
```

Important notes:
- Use `127.0.0.1` instead of `localhost` when running MySQL via XAMPP for better reliability on Windows
- Ensure XAMPP MySQL is running before starting the app
- The app expects the database `mcp_db` to exist

### Example table

The application is designed around a table like:

```sql
CREATE TABLE employee_salary (
    emp_id INT PRIMARY KEY,
    emp_name VARCHAR(100),
    department VARCHAR(50),
    designation VARCHAR(50),
    base_salary DECIMAL(10,2),
    bonus DECIMAL(10,2),
    total_salary DECIMAL(10,2),
    joining_date DATE
);
```

Sample rows may look like:

```sql
INSERT INTO employee_salary (emp_id, emp_name, department, designation, base_salary, bonus, total_salary, joining_date)
VALUES
(1, 'Alice Johnson', 'Engineering', 'Software Developer', 75000.00, 5000.00, 80000.00, '2021-03-15'),
(2, 'Bob Smith', 'Engineering', 'DevOps Engineer', 72000.00, 4500.00, 76500.00, '2020-07-10');
```

## Environment configuration

Create a `.env` file in the project root if it does not already exist.

Example:

```env
DB_HOST=127.0.0.1
DB_NAME=mcp_db
DB_USER=root
DB_PASSWORD=root
DB_PORT=3306
OLLAMA_BASE_URL=http://localhost:11434
LLM_MODEL=llama3.1
EMBEDDING_MODEL=nomic-embed-text
TABLE_NAME=employee_salary
```

You can copy the values from `.env.example` if present in the project.

## Running the project with uv

From the project folder:

```bash
cd C:\Users\srb3365\Documents\Projects\Python\querybridge
```

Install dependencies:

```bash
uv sync
```

Run the app:

```bash
uv run python main.py
```

When prompted, ask a question such as:

```text
what is base salary of Bob Smith
```

The app will:
1. read the schema from MySQL
2. ask Ollama to generate a safe SELECT query
3. call the MCP database tool
4. return a natural-language answer based on the results

## Quick validation commands

Check that MySQL is reachable:

```bash
uv run python -c "from db.connection import get_engine; from sqlalchemy import text; e=get_engine(); c=e.connect(); print(c.execute(text('SELECT 1 AS ok')).scalar_one()); c.close()"
```

Check the table exists:

```bash
uv run python -c "from db.connection import get_engine; from sqlalchemy import text; e=get_engine(); c=e.connect(); print(c.execute(text('SHOW TABLES')).fetchall()); c.close()"
```

## Troubleshooting

### MySQL connection refused

- Confirm XAMPP MySQL service is running
- Check that port `3306` is enabled
- Use `127.0.0.1` instead of `localhost`
- Validate the database credentials in `.env`

### Ollama connection failed

- Start Ollama with `ollama serve`
- Pull the models: `ollama pull llama3.1` and `ollama pull nomic-embed-text`
- Confirm `OLLAMA_BASE_URL` points to the correct host and port

### SQL generated is wrong

This app validates SQL against the current schema and rejects invalid table names or columns. If the model hallucinates a wrong table, the app will use a safe fallback for common employee salary questions.

## Notes

This is a local-first project designed to demonstrate:
- local model inference with Ollama
- structured database access through MCP
- MySQL read-only query execution
- AI + tools pattern for business data questions

## License

This project is provided for local learning and experimentation.
