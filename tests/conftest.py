"""Shared pytest fixtures for dt tests."""
import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import duckdb

from dt.config import DB_PATH, PROJECTS_DIR
from dt.db import init_db, SCHEMA_SQL


@pytest.fixture
def temp_db_path(tmp_path):
    """Provide a temporary database path."""
    db_path = tmp_path / "test.duckdb"
    yield db_path
    # Cleanup
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def temp_db(temp_db_path, monkeypatch):
    """Initialize a temporary DuckDB with schema."""
    monkeypatch.setattr("dt.db.DB_PATH", temp_db_path)
    monkeypatch.setattr("dt.config.DB_PATH", temp_db_path)

    conn = duckdb.connect(str(temp_db_path))
    for statement in SCHEMA_SQL.split(";"):
        statement = statement.strip()
        if statement:
            conn.execute(statement)
    conn.execute(
        "INSERT OR REPLACE INTO meta VALUES ('schema_version', '1')"
    )
    conn.close()

    yield temp_db_path
    conn.close()


@pytest.fixture
def temp_projects_dir(tmp_path, monkeypatch):
    """Provide a temporary projects directory with isolated stats/history."""
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    monkeypatch.setattr("dt.config.PROJECTS_DIR", projects_dir)
    monkeypatch.setattr("dt.ingest.PROJECTS_DIR", projects_dir)
    # Also isolate stats and history to avoid reading real user data
    fake_stats = tmp_path / "stats-cache.json"
    fake_history = tmp_path / "history.jsonl"
    monkeypatch.setattr("dt.ingest.STATS_CACHE", fake_stats)
    monkeypatch.setattr("dt.ingest.HISTORY_FILE", fake_history)
    return projects_dir


@pytest.fixture
def sample_session_jsonl(tmp_path):
    """Create a sample session JSONL file."""
    session_file = tmp_path / "abc123.jsonl"

    base_time = datetime(2026, 2, 18, 10, 0, 0)
    lines = [
        {
            "type": "summary",
            "sessionId": "abc123",
            "summary": "Fixed a login bug",
            "timestamp": base_time.isoformat() + "Z",
        },
        {
            "type": "user",
            "uuid": "user-1",
            "parentUuid": None,
            "message": {
                "role": "user",
                "content": "Fix the login bug in auth.py",
            },
            "sessionId": "abc123",
            "timestamp": (base_time + timedelta(seconds=1)).isoformat() + "Z",
        },
        {
            "type": "assistant",
            "uuid": "asst-1",
            "parentUuid": "user-1",
            "message": {
                "role": "assistant",
                "model": "claude-opus-4-6",
                "content": [
                    {
                        "type": "text",
                        "text": "I'll examine the login code first.",
                    },
                    {
                        "type": "tool_use",
                        "id": "toolu_001",
                        "name": "Read",
                        "input": {"file_path": "/src/auth.py"},
                    },
                ],
                "usage": {
                    "input_tokens": 1000,
                    "output_tokens": 200,
                    "cache_read_input_tokens": 500,
                    "cache_creation_input_tokens": 0,
                },
            },
            "sessionId": "abc123",
            "timestamp": (base_time + timedelta(seconds=2)).isoformat() + "Z",
        },
        {
            "type": "user",
            "uuid": "user-2",
            "parentUuid": "asst-1",
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_001",
                        "content": "def login():\n    # bug here\n    return token",
                        "is_error": False,
                    }
                ],
            },
            "sessionId": "abc123",
            "timestamp": (base_time + timedelta(seconds=3)).isoformat() + "Z",
        },
        {
            "type": "assistant",
            "uuid": "asst-2",
            "parentUuid": "user-2",
            "message": {
                "role": "assistant",
                "model": "claude-opus-4-6",
                "content": [
                    {
                        "type": "text",
                        "text": "Found the bug. Now I'll fix it.",
                    },
                    {
                        "type": "tool_use",
                        "id": "toolu_002",
                        "name": "Edit",
                        "input": {
                            "file_path": "/src/auth.py",
                            "old_string": "def login():\n    # bug here",
                            "new_string": "def login():\n    # fixed",
                        },
                    },
                ],
                "usage": {
                    "input_tokens": 800,
                    "output_tokens": 150,
                    "cache_read_input_tokens": 400,
                    "cache_creation_input_tokens": 100,
                },
            },
            "sessionId": "abc123",
            "timestamp": (base_time + timedelta(seconds=4)).isoformat() + "Z",
        },
        {
            "type": "user",
            "uuid": "user-3",
            "parentUuid": "asst-2",
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_002",
                        "content": "File updated successfully",
                        "is_error": False,
                    }
                ],
            },
            "sessionId": "abc123",
            "timestamp": (base_time + timedelta(seconds=5)).isoformat() + "Z",
        },
    ]

    with open(session_file, "w") as f:
        for line in lines:
            f.write(json.dumps(line) + "\n")

    return session_file


@pytest.fixture
def sample_session_with_errors(tmp_path):
    """Create a session JSONL file with tool errors."""
    session_file = tmp_path / "xyz789.jsonl"

    base_time = datetime(2026, 2, 17, 15, 0, 0)
    lines = [
        {
            "type": "summary",
            "sessionId": "xyz789",
            "summary": "Debugging test failures",
            "timestamp": base_time.isoformat() + "Z",
        },
        {
            "type": "user",
            "uuid": "u1",
            "parentUuid": None,
            "message": {
                "role": "user",
                "content": "Why are tests failing?",
            },
            "sessionId": "xyz789",
            "timestamp": (base_time + timedelta(seconds=1)).isoformat() + "Z",
        },
        {
            "type": "assistant",
            "uuid": "a1",
            "parentUuid": "u1",
            "message": {
                "role": "assistant",
                "model": "claude-sonnet-4-20250514",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_bad1",
                        "name": "Bash",
                        "input": {
                            "command": "cd /nonexistent && npm test"
                        },
                    },
                ],
                "usage": {
                    "input_tokens": 500,
                    "output_tokens": 100,
                    "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 0,
                },
            },
            "sessionId": "xyz789",
            "timestamp": (base_time + timedelta(seconds=2)).isoformat() + "Z",
        },
        {
            "type": "user",
            "uuid": "u2",
            "parentUuid": "a1",
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_bad1",
                        "content": "bash: cd: /nonexistent: No such file or directory",
                        "is_error": True,
                    }
                ],
            },
            "sessionId": "xyz789",
            "timestamp": (base_time + timedelta(seconds=3)).isoformat() + "Z",
        },
    ]

    with open(session_file, "w") as f:
        for line in lines:
            f.write(json.dumps(line) + "\n")

    return session_file


@pytest.fixture
def sample_subagent_jsonl(tmp_path):
    """Create a subagent session JSONL file."""
    agent_file = tmp_path / "agent-subagent123.jsonl"

    base_time = datetime(2026, 2, 18, 10, 5, 0)
    lines = [
        {
            "type": "user",
            "uuid": "sage1",
            "parentUuid": None,
            "message": {
                "role": "user",
                "content": "Explore the codebase for patterns",
            },
            "agentId": "subagent123",
            "timestamp": base_time.isoformat() + "Z",
        },
        {
            "type": "assistant",
            "uuid": "sage1a",
            "parentUuid": "sage1",
            "message": {
                "role": "assistant",
                "model": "claude-haiku-4-5-20251001",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_sub1",
                        "name": "Glob",
                        "input": {"pattern": "**/*.py"},
                    },
                ],
                "usage": {
                    "input_tokens": 200,
                    "output_tokens": 50,
                    "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 0,
                },
            },
            "agentId": "subagent123",
            "timestamp": (base_time + timedelta(seconds=1)).isoformat() + "Z",
        },
    ]

    with open(agent_file, "w") as f:
        for line in lines:
            f.write(json.dumps(line) + "\n")

    return agent_file


@pytest.fixture
def sample_stats_cache(tmp_path, monkeypatch):
    """Create a stats-cache.json file."""
    stats_file = tmp_path / "stats-cache.json"

    today = datetime.now().date()
    data = {
        "dailyActivity": [
            {
                "date": str(today - timedelta(days=2)),
                "messageCount": 45,
                "sessionCount": 3,
                "toolCallCount": 28,
            },
            {
                "date": str(today - timedelta(days=1)),
                "messageCount": 62,
                "sessionCount": 4,
                "toolCallCount": 35,
            },
            {
                "date": str(today),
                "messageCount": 38,
                "sessionCount": 2,
                "toolCallCount": 22,
            },
        ],
        "dailyModelTokens": [
            {
                "date": str(today - timedelta(days=2)),
                "tokensByModel": {
                    "claude-opus-4-6": 15000,
                    "claude-sonnet-4-20250514": 8000,
                },
            },
            {
                "date": str(today - timedelta(days=1)),
                "tokensByModel": {
                    "claude-opus-4-6": 18000,
                    "claude-sonnet-4-20250514": 9500,
                },
            },
            {
                "date": str(today),
                "tokensByModel": {
                    "claude-haiku-4-5-20251001": 5000,
                    "claude-sonnet-4-20250514": 6200,
                },
            },
        ],
    }

    with open(stats_file, "w") as f:
        json.dump(data, f)

    monkeypatch.setattr("dt.config.STATS_CACHE", stats_file)
    monkeypatch.setattr("dt.ingest.STATS_CACHE", stats_file)

    return stats_file


@pytest.fixture
def sample_history_jsonl(tmp_path, monkeypatch):
    """Create a history.jsonl file with user prompts."""
    history_file = tmp_path / "history.jsonl"

    now_ms = int(datetime.now().timestamp() * 1000)
    prompts = [
        {
            "display": "create a new React component",
            "timestamp": now_ms - 86400000,
            "project": "-Users-testuser-apps-myproject",
        },
        {
            "display": "fix the CSS layout issue",
            "timestamp": now_ms - 43200000,
            "project": "-Users-testuser-apps-myproject",
        },
        {
            "display": "What is the test coverage?",
            "timestamp": now_ms - 7200000,
            "project": "-Users-testuser-apps-myproject",
        },
        {
            "display": "continue",
            "timestamp": now_ms - 3600000,
            "project": "-Users-testuser-apps-myproject",
        },
    ]

    with open(history_file, "w") as f:
        for prompt in prompts:
            f.write(json.dumps(prompt) + "\n")

    monkeypatch.setattr("dt.config.HISTORY_FILE", history_file)
    monkeypatch.setattr("dt.ingest.HISTORY_FILE", history_file)

    return history_file
