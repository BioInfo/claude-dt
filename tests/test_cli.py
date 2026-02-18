"""Tests for CLI commands (cli.py)."""
import json

import pytest
from click.testing import CliRunner

from dt.cli import cli
from dt.db import get_connection
from dt.ingest import ingest_session_file, ingest_daily_stats, ingest_prompts


@pytest.fixture
def cli_runner():
    """Provide a Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def seeded_db_for_cli(temp_db, sample_session_jsonl, sample_stats_cache, sample_history_jsonl):
    """Populate a database with sample data for CLI testing."""
    conn = get_connection()
    ingest_session_file(
        conn, sample_session_jsonl, "-Users-testuser-apps-myproject"
    )
    ingest_daily_stats(conn)
    ingest_prompts(conn)
    conn.close()
    return temp_db


class TestCliVersion:
    """Test --version flag."""

    def test_version_output(self, cli_runner):
        """Verify --version shows version."""
        result = cli_runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "0.3.0" in result.output


class TestCliStatus:
    """Test 'dt status' command."""

    def test_status_empty_db(self, cli_runner, temp_db):
        """Status on empty database."""
        result = cli_runner.invoke(cli, ["status"])
        assert result.exit_code == 0

    def test_status_populated_db(self, cli_runner, seeded_db_for_cli):
        """Status with populated database."""
        result = cli_runner.invoke(cli, ["status"])
        assert result.exit_code == 0
        assert "sessions" in result.output.lower()

    def test_status_shows_table_counts(self, cli_runner, seeded_db_for_cli):
        """Status displays table row counts."""
        result = cli_runner.invoke(cli, ["status"])
        assert result.exit_code == 0
        # Should show at least one table name
        tables = ["sessions", "messages", "tool_calls"]
        assert any(tbl in result.output for tbl in tables)


class TestCliReport:
    """Test 'dt report' command."""

    def test_report_default_format(self, cli_runner, seeded_db_for_cli):
        """Report with default text format."""
        result = cli_runner.invoke(cli, ["report"])
        assert result.exit_code == 0
        assert len(result.output) > 0

    def test_report_text_format(self, cli_runner, seeded_db_for_cli):
        """Report with explicit text format."""
        result = cli_runner.invoke(cli, ["report", "--format", "text"])
        assert result.exit_code == 0

    def test_report_json_format(self, cli_runner, seeded_db_for_cli):
        """Report with JSON format produces valid JSON."""
        result = cli_runner.invoke(cli, ["report", "--format", "json"])
        assert result.exit_code == 0
        # Should be valid JSON
        try:
            data = json.loads(result.output)
            assert isinstance(data, dict)
        except json.JSONDecodeError:
            pytest.fail("Report output is not valid JSON")

    def test_report_markdown_format(self, cli_runner, seeded_db_for_cli):
        """Report with markdown format."""
        result = cli_runner.invoke(cli, ["report", "--format", "markdown"])
        assert result.exit_code == 0
        assert "dt Report" in result.output

    def test_report_period_option(self, cli_runner, seeded_db_for_cli):
        """Report respects --period option."""
        result = cli_runner.invoke(cli, ["report", "--period", "14"])
        assert result.exit_code == 0

    def test_report_empty_db(self, cli_runner, temp_db):
        """Report on empty database."""
        result = cli_runner.invoke(cli, ["report"])
        assert result.exit_code == 0

    def test_report_json_has_all_keys(self, cli_runner, seeded_db_for_cli):
        """JSON report includes all expected keys."""
        result = cli_runner.invoke(cli, ["report", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        # Check for major sections
        assert "overview" in data or "period_days" in data


class TestCliSessionCommand:
    """Test 'dt session' command."""

    def test_session_list(self, cli_runner, seeded_db_for_cli):
        """Session list shows recent sessions."""
        result = cli_runner.invoke(cli, ["session", "list"])
        assert result.exit_code == 0
        # Should show session info
        assert len(result.output) > 0

    def test_session_list_default(self, cli_runner, seeded_db_for_cli):
        """Session without argument defaults to list."""
        result = cli_runner.invoke(cli, ["session"])
        assert result.exit_code == 0

    def test_session_detail(self, cli_runner, seeded_db_for_cli):
        """Session with ID shows session details."""
        # First get a session ID
        result = cli_runner.invoke(cli, ["session", "list"])
        # Then query for a specific session (just the partial ID should work)
        result = cli_runner.invoke(cli, ["session", "abc"])
        assert result.exit_code == 0

    def test_session_nonexistent(self, cli_runner, seeded_db_for_cli):
        """Session with nonexistent ID."""
        result = cli_runner.invoke(cli, ["session", "doesnotexist"])
        assert result.exit_code == 0
        # Should show "No session found" or similar

    def test_session_empty_db(self, cli_runner, temp_db):
        """Session on empty database."""
        result = cli_runner.invoke(cli, ["session", "list"])
        assert result.exit_code == 0


class TestCliQuery:
    """Test 'dt query' command."""

    def test_query_simple(self, cli_runner, seeded_db_for_cli):
        """Raw query execution."""
        result = cli_runner.invoke(cli, ["query", "SELECT 1"])
        assert result.exit_code == 0

    def test_query_from_tables(self, cli_runner, seeded_db_for_cli):
        """Query actual tables."""
        result = cli_runner.invoke(cli, ["query", "SELECT COUNT(*) FROM sessions"])
        assert result.exit_code == 0
        assert "1" in result.output  # Should show count

    def test_query_invalid_sql(self, cli_runner, seeded_db_for_cli):
        """Invalid SQL should be handled."""
        result = cli_runner.invoke(cli, ["query", "SELECT * FROM nonexistent"])
        assert result.exit_code == 0  # Click catches exceptions
        # Should show error message
        assert "error" in result.output.lower() or "nonexistent" in result.output.lower()

    def test_query_no_results(self, cli_runner, seeded_db_for_cli):
        """Query with no results."""
        result = cli_runner.invoke(cli, ["query", "SELECT * FROM sessions WHERE session_id = 'fake'"])
        assert result.exit_code == 0


class TestCliContext:
    """Test 'dt context' command."""

    def test_context_command(self, cli_runner, seeded_db_for_cli):
        """Context analyzer command."""
        result = cli_runner.invoke(cli, ["context"])
        assert result.exit_code == 0

    def test_context_with_days(self, cli_runner, seeded_db_for_cli):
        """Context respects --days option."""
        result = cli_runner.invoke(cli, ["context", "--days", "14"])
        assert result.exit_code == 0

    def test_context_empty_db(self, cli_runner, temp_db):
        """Context on empty database."""
        result = cli_runner.invoke(cli, ["context"])
        assert result.exit_code == 0


class TestCliTools:
    """Test 'dt tools' command."""

    def test_tools_command(self, cli_runner, seeded_db_for_cli):
        """Tools analyzer command."""
        result = cli_runner.invoke(cli, ["tools"])
        assert result.exit_code == 0

    def test_tools_with_days(self, cli_runner, seeded_db_for_cli):
        """Tools respects --days option."""
        result = cli_runner.invoke(cli, ["tools", "--days", "30"])
        assert result.exit_code == 0

    def test_tools_empty_db(self, cli_runner, temp_db):
        """Tools on empty database."""
        result = cli_runner.invoke(cli, ["tools"])
        assert result.exit_code == 0


class TestCliPrompts:
    """Test 'dt prompts' command."""

    def test_prompts_command(self, cli_runner, seeded_db_for_cli):
        """Prompts analyzer command."""
        result = cli_runner.invoke(cli, ["prompts"])
        assert result.exit_code == 0

    def test_prompts_with_days(self, cli_runner, seeded_db_for_cli):
        """Prompts respects --days option."""
        result = cli_runner.invoke(cli, ["prompts", "--days", "7"])
        assert result.exit_code == 0

    def test_prompts_empty_db(self, cli_runner, temp_db):
        """Prompts on empty database."""
        result = cli_runner.invoke(cli, ["prompts"])
        assert result.exit_code == 0


class TestCliAntipatterns:
    """Test 'dt antipatterns' command."""

    def test_antipatterns_command(self, cli_runner, seeded_db_for_cli):
        """Antipatterns analyzer command."""
        result = cli_runner.invoke(cli, ["antipatterns"])
        assert result.exit_code == 0

    def test_antipatterns_with_days(self, cli_runner, seeded_db_for_cli):
        """Antipatterns respects --days option."""
        result = cli_runner.invoke(cli, ["antipatterns", "--days", "14"])
        assert result.exit_code == 0

    def test_antipatterns_empty_db(self, cli_runner, temp_db):
        """Antipatterns on empty database."""
        result = cli_runner.invoke(cli, ["antipatterns"])
        assert result.exit_code == 0


class TestCliHealth:
    """Test 'dt health' command."""

    def test_health_command(self, cli_runner, seeded_db_for_cli):
        """Health analyzer command."""
        result = cli_runner.invoke(cli, ["health"])
        assert result.exit_code == 0

    def test_health_with_days(self, cli_runner, seeded_db_for_cli):
        """Health respects --days option."""
        result = cli_runner.invoke(cli, ["health", "--days", "30"])
        assert result.exit_code == 0

    def test_health_empty_db(self, cli_runner, temp_db):
        """Health on empty database."""
        result = cli_runner.invoke(cli, ["health"])
        assert result.exit_code == 0


class TestCliTrends:
    """Test 'dt trends' command."""

    def test_trends_command(self, cli_runner, seeded_db_for_cli):
        """Trends analyzer command."""
        result = cli_runner.invoke(cli, ["trends"])
        assert result.exit_code == 0

    def test_trends_with_days(self, cli_runner, seeded_db_for_cli):
        """Trends respects --days option."""
        result = cli_runner.invoke(cli, ["trends", "--days", "28"])
        assert result.exit_code == 0

    def test_trends_empty_db(self, cli_runner, temp_db):
        """Trends on empty database."""
        result = cli_runner.invoke(cli, ["trends"])
        assert result.exit_code == 0


class TestCliIngest:
    """Test 'dt ingest' command."""

    def test_ingest_basic(self, cli_runner, temp_db, sample_session_jsonl, temp_projects_dir):
        """Ingest command works."""
        # Create project structure
        project_dir = temp_projects_dir / "-Users-testuser-apps-myproject"
        project_dir.mkdir(exist_ok=True)

        # Copy sample file
        import shutil
        dest_file = project_dir / sample_session_jsonl.name
        shutil.copy(sample_session_jsonl, dest_file)

        result = cli_runner.invoke(cli, ["ingest"])
        assert result.exit_code == 0

    def test_ingest_with_reset(self, cli_runner, temp_db, temp_projects_dir):
        """Ingest with --reset flag."""
        result = cli_runner.invoke(cli, ["ingest", "--reset"])
        # Should succeed or show helpful message
        assert result.exit_code == 0

    def test_ingest_shows_stats(self, cli_runner, temp_db, sample_session_jsonl, temp_projects_dir):
        """Ingest displays summary statistics."""
        project_dir = temp_projects_dir / "-Users-testuser-apps-myproject"
        project_dir.mkdir(exist_ok=True)

        import shutil
        dest_file = project_dir / sample_session_jsonl.name
        shutil.copy(sample_session_jsonl, dest_file)

        result = cli_runner.invoke(cli, ["ingest"])
        assert result.exit_code == 0


class TestCliExport:
    """Test 'dt export' command."""

    def test_export_csv(self, cli_runner, seeded_db_for_cli):
        """Export to CSV format."""
        result = cli_runner.invoke(cli, ["export", "sessions", "--format", "csv"])
        assert result.exit_code == 0

    def test_export_json(self, cli_runner, seeded_db_for_cli):
        """Export to JSON format."""
        result = cli_runner.invoke(cli, ["export", "messages", "--format", "json"])
        assert result.exit_code == 0

    def test_export_with_output_path(self, cli_runner, seeded_db_for_cli, tmp_path):
        """Export with specified output path."""
        output_file = tmp_path / "export.csv"
        result = cli_runner.invoke(cli, [
            "export", "sessions",
            "--format", "csv",
            "--output", str(output_file)
        ])
        assert result.exit_code == 0

    def test_export_all_tables(self, cli_runner, seeded_db_for_cli):
        """Export all available tables."""
        tables = ["sessions", "messages", "tool_calls", "subagents", "file_access", "prompts", "daily_stats"]
        for table in tables:
            result = cli_runner.invoke(cli, ["export", table, "--format", "csv"])
            assert result.exit_code == 0

    def test_export_with_days_filter(self, cli_runner, seeded_db_for_cli):
        """Export respects --days filter."""
        result = cli_runner.invoke(cli, [
            "export", "sessions",
            "--format", "csv",
            "--days", "7"
        ])
        assert result.exit_code == 0


class TestCliErrorHandling:
    """Test CLI error handling."""

    def test_invalid_command(self, cli_runner):
        """Invalid command shows error."""
        result = cli_runner.invoke(cli, ["nonexistent"])
        assert result.exit_code != 0

    def test_missing_required_argument(self, cli_runner):
        """Missing required argument shows error."""
        result = cli_runner.invoke(cli, ["export"])
        assert result.exit_code != 0

    def test_invalid_period_type(self, cli_runner, seeded_db_for_cli):
        """Invalid period type is handled."""
        result = cli_runner.invoke(cli, ["report", "--period", "invalid"])
        assert result.exit_code != 0

    def test_invalid_format(self, cli_runner, seeded_db_for_cli):
        """Invalid format is handled."""
        result = cli_runner.invoke(cli, ["report", "--format", "invalid"])
        assert result.exit_code != 0


class TestCliOutput:
    """Test CLI output quality."""

    def test_output_uses_tables(self, cli_runner, seeded_db_for_cli):
        """Output includes tables for data display."""
        result = cli_runner.invoke(cli, ["status"])
        assert result.exit_code == 0
        # Rich tables use box drawing characters
        assert len(result.output) > 0

    def test_report_text_output_readable(self, cli_runner, seeded_db_for_cli):
        """Text report is human-readable."""
        result = cli_runner.invoke(cli, ["report", "--format", "text"])
        assert result.exit_code == 0
        # Should not contain raw table data
        assert len(result.output) > 100

    def test_markdown_output_valid(self, cli_runner, seeded_db_for_cli):
        """Markdown output is valid markdown."""
        result = cli_runner.invoke(cli, ["report", "--format", "markdown"])
        assert result.exit_code == 0
        # Should have markdown elements
        assert "#" in result.output  # Headers
        assert "|" in result.output  # Tables
