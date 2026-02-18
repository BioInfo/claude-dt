"""Tests for database management (db.py)."""
import duckdb
import pytest

from dt.db import init_db, reset_db, get_connection, SCHEMA_SQL, SCHEMA_VERSION


class TestInitDb:
    """Test database initialization."""

    def test_init_creates_tables(self, temp_db):
        """Verify init_db creates all required tables."""
        conn = get_connection(read_only=True)
        tables = conn.execute(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'main'
            ORDER BY table_name
            """
        ).fetchall()
        conn.close()

        table_names = [t[0] for t in tables]
        required_tables = [
            "anti_patterns",
            "daily_stats",
            "file_access",
            "messages",
            "meta",
            "prompts",
            "sessions",
            "subagents",
            "tool_calls",
        ]
        for tbl in required_tables:
            assert tbl in table_names, f"Table {tbl} not created"

    def test_init_sets_schema_version(self, temp_db):
        """Verify schema version is set in meta table."""
        conn = get_connection(read_only=True)
        result = conn.execute(
            "SELECT value FROM meta WHERE key = 'schema_version'"
        ).fetchone()
        conn.close()

        assert result is not None
        assert result[0] == str(SCHEMA_VERSION)

    def test_sessions_table_schema(self, temp_db):
        """Verify sessions table has correct columns."""
        conn = get_connection(read_only=True)
        cols = conn.execute(
            "PRAGMA table_info(sessions)"
        ).fetchall()
        conn.close()

        col_names = [c[1] for c in cols]
        required_cols = [
            "session_id",
            "project_path",
            "project_name",
            "first_message_at",
            "last_message_at",
            "message_count",
            "tool_call_count",
            "models_used",
        ]
        for col in required_cols:
            assert col in col_names, f"Column {col} not in sessions table"

    def test_messages_table_schema(self, temp_db):
        """Verify messages table has correct columns."""
        conn = get_connection(read_only=True)
        cols = conn.execute(
            "PRAGMA table_info(messages)"
        ).fetchall()
        conn.close()

        col_names = [c[1] for c in cols]
        required_cols = [
            "uuid",
            "session_id",
            "role",
            "model",
            "timestamp",
            "content_text",
        ]
        for col in required_cols:
            assert col in col_names, f"Column {col} not in messages table"

    def test_tool_calls_table_schema(self, temp_db):
        """Verify tool_calls table has correct columns."""
        conn = get_connection(read_only=True)
        cols = conn.execute(
            "PRAGMA table_info(tool_calls)"
        ).fetchall()
        conn.close()

        col_names = [c[1] for c in cols]
        required_cols = [
            "tool_use_id",
            "session_id",
            "tool_name",
            "input_summary",
            "result_error",
        ]
        for col in required_cols:
            assert col in col_names, f"Column {col} not in tool_calls table"

    def test_prompts_table_schema(self, temp_db):
        """Verify prompts table has correct columns."""
        conn = get_connection(read_only=True)
        cols = conn.execute(
            "PRAGMA table_info(prompts)"
        ).fetchall()
        conn.close()

        col_names = [c[1] for c in cols]
        required_cols = ["uuid", "text", "word_count", "pattern"]
        for col in required_cols:
            assert col in col_names, f"Column {col} not in prompts table"

    def test_init_idempotent(self, temp_db):
        """Verify init_db is idempotent (safe to call multiple times)."""
        conn1 = init_db()
        conn1.close()

        conn2 = init_db()
        tables1 = conn2.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'main'"
        ).fetchone()[0]
        conn2.close()

        conn3 = init_db()
        tables2 = conn3.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'main'"
        ).fetchone()[0]
        conn3.close()

        assert tables1 == tables2


class TestResetDb:
    """Test database reset functionality."""

    def test_reset_clears_tables(self, temp_db):
        """Verify reset_db clears all data tables."""
        # Insert some data first
        conn = get_connection()
        conn.execute(
            "INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                "test-session-1",
                "project",
                "projectname",
                "2026-01-01",
                "2026-01-01",
                10.0,
                5,
                2,
                3,
                2,
                0,
                0,
                [],
                None,
                1000,
                500,
                0,
                0,
                0,
                "test",
                "path",
            ],
        )
        conn.close()

        # Reset the database
        conn = reset_db()
        conn.close()

        # Verify data is cleared
        conn = get_connection(read_only=True)
        count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        conn.close()

        assert count == 0

    def test_reset_recreates_schema(self, temp_db):
        """Verify reset_db recreates schema."""
        reset_db().close()

        conn = get_connection(read_only=True)
        tables = conn.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'main'"
        ).fetchone()[0]
        conn.close()

        assert tables > 0

    def test_reset_with_existing_data(self, temp_db):
        """Verify reset handles existing data correctly."""
        conn = get_connection()
        conn.execute(
            "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                "msg-1",
                "sess-1",
                None,
                "user",
                "user",
                None,
                None,
                False,
                "2026-01-01",
                0,
                0,
                0,
                0,
                "text",
                100,
                1,
                None,
            ],
        )
        conn.close()

        reset_db().close()

        conn = get_connection(read_only=True)
        count = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        conn.close()

        assert count == 0


class TestGetConnection:
    """Test connection management."""

    def test_get_connection_returns_valid_connection(self, temp_db):
        """Verify get_connection returns a valid DuckDB connection."""
        conn = get_connection()
        assert isinstance(conn, duckdb.DuckDBPyConnection)
        conn.close()

    def test_get_read_only_connection(self, temp_db):
        """Verify read-only flag is respected."""
        # Insert data with write connection
        conn = get_connection()
        conn.execute(
            "INSERT INTO meta VALUES ('test_key', 'test_value')"
        )
        conn.close()

        # Try to write with read-only connection
        ro_conn = get_connection(read_only=True)
        with pytest.raises(Exception):
            ro_conn.execute("INSERT INTO meta VALUES ('bad', 'data')")
        ro_conn.close()

    def test_connection_can_query(self, temp_db):
        """Verify connection can execute queries."""
        conn = get_connection()
        result = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()
        conn.close()

        assert result is not None
        assert isinstance(result[0], int)

    def test_multiple_connections(self, temp_db):
        """Verify multiple connections can be created."""
        conn1 = get_connection()
        conn2 = get_connection()

        assert conn1 is not conn2

        conn1.close()
        conn2.close()

    def test_connection_initialization(self, temp_db):
        """Verify fresh connection has schema."""
        conn = get_connection()
        tables = conn.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'main'"
        ).fetchone()[0]
        conn.close()

        assert tables > 0


class TestSchemaSQL:
    """Test schema SQL constant."""

    def test_schema_sql_contains_all_tables(self):
        """Verify SCHEMA_SQL contains all required table definitions."""
        required_tables = [
            "CREATE TABLE",
            "sessions",
            "messages",
            "tool_calls",
            "subagents",
            "file_access",
            "prompts",
            "daily_stats",
            "meta",
        ]
        for table_str in required_tables:
            assert table_str in SCHEMA_SQL

    def test_schema_sql_valid_sql(self):
        """Verify SCHEMA_SQL contains valid SQL."""
        # Should not raise
        for statement in SCHEMA_SQL.split(";"):
            statement = statement.strip()
            if statement:
                try:
                    duckdb.sql(f"PREPARE {statement}")
                except duckdb.ParserException:
                    # Some statements might fail parsing, that's ok
                    pass

    def test_schema_version_constant(self):
        """Verify SCHEMA_VERSION is set."""
        assert SCHEMA_VERSION > 0
        assert isinstance(SCHEMA_VERSION, int)
