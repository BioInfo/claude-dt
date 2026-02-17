"""DuckDB database management for dt."""
import duckdb
from .config import DB_PATH, ensure_dt_dir

SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id          VARCHAR PRIMARY KEY,
    project_path        VARCHAR,
    project_name        VARCHAR,
    first_message_at    TIMESTAMP,
    last_message_at     TIMESTAMP,
    duration_seconds    DOUBLE,
    message_count       INTEGER DEFAULT 0,
    user_message_count  INTEGER DEFAULT 0,
    assistant_msg_count INTEGER DEFAULT 0,
    tool_call_count     INTEGER DEFAULT 0,
    tool_error_count    INTEGER DEFAULT 0,
    compaction_count    INTEGER DEFAULT 0,
    models_used         VARCHAR[],
    primary_model       VARCHAR,
    total_input_tokens  BIGINT DEFAULT 0,
    total_output_tokens BIGINT DEFAULT 0,
    total_cache_read    BIGINT DEFAULT 0,
    total_cache_create  BIGINT DEFAULT 0,
    subagent_count      INTEGER DEFAULT 0,
    summary             VARCHAR,
    file_path           VARCHAR
);

CREATE TABLE IF NOT EXISTS messages (
    uuid                VARCHAR PRIMARY KEY,
    session_id          VARCHAR,
    parent_uuid         VARCHAR,
    type                VARCHAR,
    role                VARCHAR,
    model               VARCHAR,
    agent_id            VARCHAR,
    is_sidechain        BOOLEAN DEFAULT FALSE,
    timestamp           TIMESTAMP,
    input_tokens        INTEGER DEFAULT 0,
    output_tokens       INTEGER DEFAULT 0,
    cache_read_tokens   BIGINT DEFAULT 0,
    cache_create_tokens BIGINT DEFAULT 0,
    content_text        VARCHAR,
    content_length      INTEGER DEFAULT 0,
    turn_number         INTEGER,
    cwd                 VARCHAR
);

CREATE TABLE IF NOT EXISTS tool_calls (
    tool_use_id         VARCHAR PRIMARY KEY,
    session_id          VARCHAR,
    message_uuid        VARCHAR,
    agent_id            VARCHAR,
    tool_name           VARCHAR,
    input_summary       VARCHAR,
    timestamp           TIMESTAMP,
    result_error        BOOLEAN DEFAULT FALSE,
    result_length       INTEGER DEFAULT 0,
    file_path           VARCHAR,
    duration_ms         INTEGER
);

CREATE TABLE IF NOT EXISTS subagents (
    agent_id            VARCHAR PRIMARY KEY,
    session_id          VARCHAR,
    agent_type          VARCHAR,
    model               VARCHAR,
    prompt_summary      VARCHAR,
    message_count       INTEGER DEFAULT 0,
    tool_call_count     INTEGER DEFAULT 0,
    total_tokens        BIGINT DEFAULT 0,
    started_at          TIMESTAMP,
    ended_at            TIMESTAMP,
    duration_seconds    DOUBLE
);

CREATE TABLE IF NOT EXISTS file_access (
    id                  INTEGER,
    session_id          VARCHAR,
    file_path           VARCHAR,
    access_type         VARCHAR,
    timestamp           TIMESTAMP,
    is_repeat           BOOLEAN DEFAULT FALSE,
    repeat_count        INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS anti_patterns (
    id                  INTEGER,
    session_id          VARCHAR,
    pattern_type        VARCHAR,
    severity            VARCHAR,
    description         VARCHAR,
    file_path           VARCHAR,
    timestamp           TIMESTAMP,
    token_cost          INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS prompts (
    uuid                VARCHAR PRIMARY KEY,
    session_id          VARCHAR,
    text                VARCHAR,
    word_count          INTEGER DEFAULT 0,
    timestamp           TIMESTAMP,
    project_path        VARCHAR,
    turns_to_complete   INTEGER,
    clarification_needed BOOLEAN DEFAULT FALSE,
    tool_calls_triggered INTEGER DEFAULT 0,
    pattern             VARCHAR
);

CREATE TABLE IF NOT EXISTS daily_stats (
    date                DATE PRIMARY KEY,
    message_count       INTEGER DEFAULT 0,
    session_count       INTEGER DEFAULT 0,
    tool_call_count     INTEGER DEFAULT 0,
    tokens_by_model     VARCHAR,
    total_tokens        BIGINT DEFAULT 0,
    cache_efficiency    DOUBLE,
    avg_turns_per_session DOUBLE,
    avg_tokens_per_turn DOUBLE
);

CREATE TABLE IF NOT EXISTS meta (
    key                 VARCHAR PRIMARY KEY,
    value               VARCHAR
);
"""


def get_connection(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Get a DuckDB connection, creating the database if needed."""
    ensure_dt_dir()
    return duckdb.connect(str(DB_PATH), read_only=read_only)


def init_db() -> duckdb.DuckDBPyConnection:
    """Initialize the database with schema."""
    conn = get_connection()
    for statement in SCHEMA_SQL.split(";"):
        statement = statement.strip()
        if statement:
            conn.execute(statement)
    conn.execute(
        "INSERT OR REPLACE INTO meta VALUES ('schema_version', ?)",
        [str(SCHEMA_VERSION)]
    )
    return conn


def reset_db() -> duckdb.DuckDBPyConnection:
    """Drop all tables and reinitialize."""
    conn = get_connection()
    tables = [
        "anti_patterns", "file_access", "prompts", "tool_calls",
        "subagents", "messages", "daily_stats", "sessions", "meta"
    ]
    for table in tables:
        conn.execute(f"DROP TABLE IF EXISTS {table}")
    conn.close()
    return init_db()
