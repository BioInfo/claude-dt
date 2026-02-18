"""Tests for ingestion pipeline (ingest.py)."""
import json
from datetime import datetime
from pathlib import Path

import pytest

from dt.ingest import (
    parse_project_name,
    extract_text_content,
    extract_tool_calls,
    extract_tool_results,
    classify_prompt,
    parse_timestamp,
    safe_json_parse,
    ingest_session_file,
    _summarize_tool_input,
    _extract_file_path,
)
from dt.db import get_connection


class TestParseProjectName:
    """Test project name extraction from encoded paths."""

    def test_encoded_path_with_username(self):
        """Extract project name from -Users-username-apps-project format."""
        assert parse_project_name("-Users-testuser-apps-myproject") == "myproject"

    def test_encoded_path_home(self):
        """Extract project name from -home-username-apps-project format."""
        assert parse_project_name("-home-testuser-apps-dt") == "dt"

    def test_simple_path(self):
        """Extract from simple path format."""
        assert parse_project_name("myproject") == "myproject"

    def test_path_with_multiple_components(self):
        """Extract last meaningful component from multi-part path."""
        path = "-Users-alice-code-backend-src-core"
        result = parse_project_name(path)
        assert result == "core"

    def test_empty_path(self):
        """Handle empty path gracefully."""
        assert parse_project_name("") == ""

    def test_path_with_dashes_only(self):
        """Handle path that's just dashes."""
        result = parse_project_name("---")
        assert isinstance(result, str)

    def test_very_short_path(self):
        """Handle very short paths."""
        assert parse_project_name("p") == "p"


class TestExtractTextContent:
    """Test text extraction from message content."""

    def test_string_content(self):
        """Extract text from simple string."""
        text = "This is a message"
        assert extract_text_content(text) == text

    def test_long_string_truncated(self):
        """Truncate long strings to 2000 chars."""
        text = "x" * 3000
        result = extract_text_content(text)
        assert len(result) == 2000

    def test_array_of_text_blocks(self):
        """Extract text from array of blocks."""
        content = [
            {"type": "text", "text": "First block"},
            {"type": "text", "text": "Second block"},
        ]
        result = extract_text_content(content)
        assert "First block" in result
        assert "Second block" in result

    def test_mixed_content_blocks(self):
        """Handle mixed text and tool blocks."""
        content = [
            {"type": "text", "text": "Hello"},
            {"type": "tool_use", "id": "t1", "name": "Read"},
            {"type": "text", "text": "World"},
        ]
        result = extract_text_content(content)
        assert "Hello" in result
        assert "World" in result

    def test_tool_result_content(self):
        """Extract content from tool_result blocks."""
        content = [
            {
                "type": "tool_result",
                "tool_use_id": "t1",
                "content": "File contents here",
            }
        ]
        result = extract_text_content(content)
        assert "File contents" in result

    def test_empty_content(self):
        """Handle empty content gracefully."""
        assert extract_text_content("") == ""
        assert extract_text_content([]) == ""

    def test_non_dict_items_in_list(self):
        """Handle non-dict items in content array."""
        content = ["string", {"type": "text", "text": "block"}, None]
        result = extract_text_content(content)
        assert "string" in result or "block" in result

    def test_missing_text_field(self):
        """Handle blocks missing text field."""
        content = [{"type": "text"}, {"type": "text", "text": "valid"}]
        result = extract_text_content(content)
        assert "valid" in result


class TestExtractToolCalls:
    """Test tool call extraction."""

    def test_single_tool_use(self):
        """Extract a single tool_use block."""
        content = [
            {
                "type": "tool_use",
                "id": "toolu_123",
                "name": "Read",
                "input": {"file_path": "/src/main.py"},
            }
        ]
        calls = extract_tool_calls(content)
        assert len(calls) == 1
        assert calls[0]["tool_use_id"] == "toolu_123"
        assert calls[0]["tool_name"] == "Read"

    def test_multiple_tool_uses(self):
        """Extract multiple tool_use blocks."""
        content = [
            {
                "type": "tool_use",
                "id": "t1",
                "name": "Read",
                "input": {"file_path": "/a.py"},
            },
            {
                "type": "tool_use",
                "id": "t2",
                "name": "Bash",
                "input": {"command": "ls"},
            },
        ]
        calls = extract_tool_calls(content)
        assert len(calls) == 2

    def test_mixed_content_with_tools(self):
        """Extract tools from mixed content."""
        content = [
            {"type": "text", "text": "Some text"},
            {
                "type": "tool_use",
                "id": "t1",
                "name": "Read",
                "input": {"file_path": "/file.py"},
            },
            {"type": "text", "text": "More text"},
        ]
        calls = extract_tool_calls(content)
        assert len(calls) == 1

    def test_non_list_content(self):
        """Handle non-list content."""
        calls = extract_tool_calls("string content")
        assert calls == []

    def test_empty_content(self):
        """Handle empty content."""
        assert extract_tool_calls([]) == []

    def test_tool_use_without_input(self):
        """Handle tool_use with missing input."""
        content = [{"type": "tool_use", "id": "t1", "name": "Read"}]
        calls = extract_tool_calls(content)
        assert len(calls) == 1


class TestExtractToolResults:
    """Test tool result extraction."""

    def test_single_tool_result(self):
        """Extract a single tool_result."""
        content = [
            {
                "type": "tool_result",
                "tool_use_id": "t1",
                "content": "Result data",
                "is_error": False,
            }
        ]
        results = extract_tool_results(content)
        assert "t1" in results
        assert results["t1"]["result_error"] is False

    def test_tool_result_with_error(self):
        """Extract tool_result marked as error."""
        content = [
            {
                "type": "tool_result",
                "tool_use_id": "t1",
                "content": "Error message",
                "is_error": True,
            }
        ]
        results = extract_tool_results(content)
        assert results["t1"]["result_error"] is True

    def test_result_length_calculation(self):
        """Calculate result content length."""
        content = [
            {
                "type": "tool_result",
                "tool_use_id": "t1",
                "content": "x" * 100,
                "is_error": False,
            }
        ]
        results = extract_tool_results(content)
        assert results["t1"]["result_length"] == 100

    def test_non_string_result_content(self):
        """Handle non-string result content."""
        content = [
            {
                "type": "tool_result",
                "tool_use_id": "t1",
                "content": None,
                "is_error": False,
            }
        ]
        results = extract_tool_results(content)
        assert results["t1"]["result_length"] == 0

    def test_non_list_content(self):
        """Handle non-list content."""
        assert extract_tool_results("string") == {}


class TestSummarizeToolInput:
    """Test tool input summarization."""

    def test_read_tool(self):
        """Summarize Read tool input."""
        result = _summarize_tool_input("Read", {"file_path": "/src/main.py"})
        assert result == "/src/main.py"

    def test_edit_tool(self):
        """Summarize Edit tool input."""
        result = _summarize_tool_input("Edit", {
            "file_path": "/src/main.py",
            "old_string": "x" * 100,
        })
        assert "/src/main.py" in result
        assert "|" in result

    def test_write_tool(self):
        """Summarize Write tool input."""
        result = _summarize_tool_input("Write", {"file_path": "/src/new.py"})
        assert result == "/src/new.py"

    def test_bash_tool(self):
        """Summarize Bash tool input."""
        result = _summarize_tool_input("Bash", {"command": "git status"})
        assert "git status" in result

    def test_grep_tool(self):
        """Summarize Grep tool input."""
        result = _summarize_tool_input("Grep", {
            "pattern": "def foo",
            "path": "/src",
        })
        assert "def foo" in result
        assert "/src" in result

    def test_task_tool(self):
        """Summarize Task tool input."""
        result = _summarize_tool_input("Task", {
            "subagent_type": "Explore",
            "description": "Find patterns",
        })
        assert "Explore" in result
        assert "Find patterns" in result

    def test_unknown_tool(self):
        """Handle unknown tool type."""
        inp = {"some_field": "value"}
        result = _summarize_tool_input("UnknownTool", inp)
        assert isinstance(result, str)
        assert len(result) <= 200


class TestExtractFilePath:
    """Test file path extraction from tool inputs."""

    def test_read_tool(self):
        """Extract file path from Read tool."""
        path = _extract_file_path("Read", {"file_path": "/src/main.py"})
        assert path == "/src/main.py"

    def test_edit_tool(self):
        """Extract file path from Edit tool."""
        path = _extract_file_path("Edit", {"file_path": "/src/main.py"})
        assert path == "/src/main.py"

    def test_grep_tool(self):
        """Extract path from Grep tool."""
        path = _extract_file_path("Grep", {"path": "/src"})
        assert path == "/src"

    def test_bash_tool_no_path(self):
        """Bash tool returns None."""
        path = _extract_file_path("Bash", {"command": "git status"})
        assert path is None

    def test_missing_path_field(self):
        """Handle missing path field."""
        path = _extract_file_path("Read", {})
        assert path is None


class TestParseTimestamp:
    """Test ISO 8601 timestamp parsing."""

    def test_iso_with_z(self):
        """Parse timestamp with Z suffix."""
        ts = parse_timestamp("2026-02-18T10:00:00Z")
        assert ts.year == 2026
        assert ts.month == 2
        assert ts.day == 18

    def test_iso_with_z_and_ms(self):
        """Parse timestamp with milliseconds and Z."""
        ts = parse_timestamp("2026-02-18T10:00:00.123Z")
        assert ts.year == 2026

    def test_iso_with_timezone_offset(self):
        """Parse timestamp with timezone offset."""
        ts = parse_timestamp("2026-02-18T10:00:00+00:00")
        assert ts.year == 2026

    def test_iso_without_suffix(self):
        """Parse timestamp without suffix."""
        ts = parse_timestamp("2026-02-18T10:00:00")
        assert ts.year == 2026

    def test_invalid_timestamp(self):
        """Return None for invalid timestamp."""
        assert parse_timestamp("not a timestamp") is None
        assert parse_timestamp("") is None

    def test_none_input(self):
        """Handle None input."""
        assert parse_timestamp(None) is None


class TestSafeJsonParse:
    """Test safe JSON parsing."""

    def test_valid_json(self):
        """Parse valid JSON."""
        line = '{"key": "value"}'
        result = safe_json_parse(line)
        assert result["key"] == "value"

    def test_invalid_json(self):
        """Return None for invalid JSON."""
        assert safe_json_parse("{invalid json}") is None
        assert safe_json_parse("") is None

    def test_json_with_special_chars(self):
        """Parse JSON with special characters."""
        line = '{"key": "value with \\"quotes\\""}'
        result = safe_json_parse(line)
        assert result is not None

    def test_json_with_arrays(self):
        """Parse JSON with arrays."""
        line = '{"items": [1, 2, 3]}'
        result = safe_json_parse(line)
        assert result["items"] == [1, 2, 3]


class TestClassifyPrompt:
    """Test prompt pattern classification."""

    def test_continue_prompts(self):
        """Classify continuation prompts."""
        assert classify_prompt("continue") == "continue"
        assert classify_prompt("yes") == "continue"
        assert classify_prompt("go") == "continue"

    def test_command_prompts(self):
        """Classify command prompts."""
        assert classify_prompt("/session") == "command"
        assert classify_prompt("/clear") == "command"

    def test_fix_prompts(self):
        """Classify fix/debug prompts."""
        assert classify_prompt("fix the error") == "fix"
        assert classify_prompt("debug the issue") == "fix"
        assert classify_prompt("why is this broken") == "fix"

    def test_create_prompts(self):
        """Classify create prompts."""
        assert classify_prompt("create a component") == "create"
        assert classify_prompt("build a new feature") == "create"
        assert classify_prompt("add a test") == "create"

    def test_question_prompts(self):
        """Classify question prompts."""
        assert classify_prompt("what is this doing?") == "question"
        assert classify_prompt("how does this work?") == "question"
        assert classify_prompt("can you explain?") == "question"

    def test_refactor_prompts(self):
        """Classify refactor prompts."""
        assert classify_prompt("refactor this") == "refactor"
        assert classify_prompt("clean up the code") == "refactor"
        assert classify_prompt("simplify the logic") == "refactor"

    def test_update_prompts(self):
        """Classify update prompts."""
        assert classify_prompt("update the config") == "update"
        assert classify_prompt("change the value") == "update"

    def test_other_prompts(self):
        """Classify unmatched prompts as other."""
        assert classify_prompt("") == "other"
        assert classify_prompt("something random") == "other"

    def test_case_insensitive(self):
        """Classify should be case insensitive."""
        assert classify_prompt("CONTINUE") == "continue"
        assert classify_prompt("FIX THE BUG") == "fix"


class TestIngestSessionFile:
    """Test full session file ingestion."""

    def test_ingest_valid_session(self, temp_db, sample_session_jsonl):
        """Ingest a valid session file."""
        conn = get_connection()
        result = ingest_session_file(
            conn, sample_session_jsonl, "-Users-testuser-apps-myproject"
        )
        conn.close()

        assert result is not None
        assert result["messages"] > 0
        assert result["tool_calls"] > 0

    def test_ingest_with_errors(self, temp_db, sample_session_with_errors):
        """Ingest session with tool errors."""
        conn = get_connection()
        result = ingest_session_file(
            conn, sample_session_with_errors, "-Users-testuser-apps-myproject"
        )
        conn.close()

        assert result is not None
        # Check that error was recorded
        conn = get_connection(read_only=True)
        errors = conn.execute(
            "SELECT COUNT(*) FROM tool_calls WHERE result_error = TRUE"
        ).fetchone()[0]
        conn.close()
        assert errors > 0

    def test_ingest_creates_session_record(self, temp_db, sample_session_jsonl):
        """Verify session record is created."""
        conn = get_connection()
        ingest_session_file(
            conn, sample_session_jsonl, "-Users-testuser-apps-myproject"
        )
        conn.close()

        conn = get_connection(read_only=True)
        sessions = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        conn.close()
        assert sessions == 1

    def test_ingest_creates_message_records(self, temp_db, sample_session_jsonl):
        """Verify message records are created."""
        conn = get_connection()
        ingest_session_file(
            conn, sample_session_jsonl, "-Users-testuser-apps-myproject"
        )
        conn.close()

        conn = get_connection(read_only=True)
        messages = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        conn.close()
        assert messages > 0

    def test_ingest_creates_tool_call_records(self, temp_db, sample_session_jsonl):
        """Verify tool call records are created."""
        conn = get_connection()
        ingest_session_file(
            conn, sample_session_jsonl, "-Users-testuser-apps-myproject"
        )
        conn.close()

        conn = get_connection(read_only=True)
        tools = conn.execute("SELECT COUNT(*) FROM tool_calls").fetchone()[0]
        conn.close()
        assert tools > 0

    def test_ingest_nonexistent_file(self, temp_db):
        """Handle nonexistent file gracefully."""
        conn = get_connection()
        result = ingest_session_file(
            conn, Path("/nonexistent/session.jsonl"), "project"
        )
        conn.close()
        assert result is None

    def test_session_name_from_file(self, temp_db, sample_session_jsonl):
        """Use filename as session ID."""
        conn = get_connection()
        ingest_session_file(
            conn, sample_session_jsonl, "-Users-testuser-apps-myproject"
        )
        conn.close()

        conn = get_connection(read_only=True)
        sessions = conn.execute(
            "SELECT session_id FROM sessions"
        ).fetchall()
        conn.close()

        assert len(sessions) > 0
        assert sessions[0][0] == sample_session_jsonl.stem
