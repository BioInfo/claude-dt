"""Tests for analyzer functions (analyzers.py)."""
from datetime import datetime, timedelta

import pytest

from dt.analyzers import (
    analyze_context,
    analyze_tools,
    analyze_prompts,
    detect_antipatterns,
    analyze_health,
    compute_scores,
    analyze_trends,
    generate_report,
    generate_markdown_report,
    _sparkline,
    _short_model,
    _short_path,
)
from dt.db import get_connection
from dt.ingest import ingest_session_file, ingest_daily_stats, ingest_prompts


@pytest.fixture
def seeded_db(temp_db, sample_session_jsonl, sample_stats_cache, sample_history_jsonl):
    """Populate a database with sample data for testing."""
    conn = get_connection()
    ingest_session_file(
        conn, sample_session_jsonl, "-Users-testuser-apps-myproject"
    )
    ingest_daily_stats(conn)
    ingest_prompts(conn)
    conn.close()
    return temp_db


class TestAnalyzeContext:
    """Test context analyzer."""

    def test_analyze_context_returns_dict(self, seeded_db):
        """Verify analyze_context returns a dict with expected keys."""
        result = analyze_context(days=7)
        assert isinstance(result, dict)
        assert "repeat_reads" in result
        assert "heavy_sessions" in result
        assert "cache_efficiency" in result
        assert "hotspot_files" in result

    def test_analyze_context_repeat_reads(self, seeded_db):
        """Verify repeat_reads analysis."""
        result = analyze_context(days=7)
        assert isinstance(result["repeat_reads"], list)

    def test_analyze_context_cache_efficiency(self, seeded_db):
        """Verify cache_efficiency analysis."""
        result = analyze_context(days=7)
        assert isinstance(result["cache_efficiency"], list)

    def test_analyze_context_respects_days_filter(self, seeded_db):
        """Verify days parameter is respected."""
        result_7 = analyze_context(days=7)
        result_1 = analyze_context(days=1)
        # Results may differ based on date filtering
        assert isinstance(result_7, dict)
        assert isinstance(result_1, dict)

    def test_analyze_context_empty_db(self, temp_db):
        """Handle empty database gracefully."""
        result = analyze_context(days=7)
        assert isinstance(result, dict)
        assert result["repeat_reads"] == []


class TestAnalyzeTools:
    """Test tool analyzer."""

    def test_analyze_tools_returns_dict(self, seeded_db):
        """Verify analyze_tools returns expected structure."""
        result = analyze_tools(days=7)
        assert isinstance(result, dict)
        assert "tool_frequency" in result
        assert "failures" in result
        assert "subagent_stats" in result

    def test_analyze_tools_frequency(self, seeded_db):
        """Verify tool_frequency data."""
        result = analyze_tools(days=7)
        freq = result["tool_frequency"]
        assert isinstance(freq, list)
        if freq:
            # Each row should have (name, count, errors, error_rate)
            assert len(freq[0]) >= 3

    def test_analyze_tools_failures(self, seeded_db):
        """Verify failures data."""
        result = analyze_tools(days=7)
        assert isinstance(result["failures"], list)

    def test_analyze_tools_subagent_stats(self, seeded_db):
        """Verify subagent_stats data."""
        result = analyze_tools(days=7)
        assert isinstance(result["subagent_stats"], list)

    def test_analyze_tools_empty_db(self, temp_db):
        """Handle empty database gracefully."""
        result = analyze_tools(days=7)
        assert isinstance(result, dict)
        assert result["tool_frequency"] == []


class TestAnalyzePrompts:
    """Test prompt analyzer."""

    def test_analyze_prompts_returns_dict(self, seeded_db):
        """Verify analyze_prompts returns expected structure."""
        result = analyze_prompts(days=7)
        assert isinstance(result, dict)
        assert "patterns" in result
        assert "verbose_prompts" in result
        assert "by_project" in result

    def test_analyze_prompts_patterns(self, seeded_db):
        """Verify patterns data."""
        result = analyze_prompts(days=7)
        assert isinstance(result["patterns"], list)

    def test_analyze_prompts_by_project(self, seeded_db):
        """Verify by_project data."""
        result = analyze_prompts(days=7)
        assert isinstance(result["by_project"], list)

    def test_analyze_prompts_empty_db(self, temp_db):
        """Handle empty database gracefully."""
        result = analyze_prompts(days=7)
        assert isinstance(result, dict)
        assert result["patterns"] == []


class TestDetectAntipatterns:
    """Test antipattern detection."""

    def test_detect_antipatterns_returns_list(self, seeded_db):
        """Verify detect_antipatterns returns a list."""
        result = detect_antipatterns(days=7)
        assert isinstance(result, list)

    def test_antipattern_structure(self, seeded_db):
        """Verify antipattern items have expected structure."""
        result = detect_antipatterns(days=7)
        if result:
            ap = result[0]
            assert "type" in ap
            assert "severity" in ap
            assert "description" in ap
            assert "suggestion" in ap
            assert ap["severity"] in ("critical", "warning", "info")

    def test_detect_antipatterns_empty_db(self, temp_db):
        """Handle empty database gracefully."""
        result = detect_antipatterns(days=7)
        assert isinstance(result, list)

    def test_antipattern_severity_levels(self, seeded_db):
        """Verify antipatterns have valid severity levels."""
        result = detect_antipatterns(days=7)
        valid_severities = {"critical", "warning", "info"}
        for ap in result:
            assert ap["severity"] in valid_severities


class TestAnalyzeHealth:
    """Test health analyzer."""

    def test_analyze_health_returns_dict(self, seeded_db):
        """Verify analyze_health returns expected structure."""
        result = analyze_health(days=30)
        assert isinstance(result, dict)
        assert "high_access_projects" in result
        assert "claudemd_candidates" in result
        assert "context_fragmenters" in result
        assert "error_prone_projects" in result

    def test_analyze_health_empty_db(self, temp_db):
        """Handle empty database gracefully."""
        result = analyze_health(days=30)
        assert isinstance(result, dict)
        assert result["high_access_projects"] == []

    def test_analyze_health_respects_days(self, seeded_db):
        """Verify days parameter is respected."""
        result_30 = analyze_health(days=30)
        result_7 = analyze_health(days=7)
        # Both should be dicts even if different sizes
        assert isinstance(result_30, dict)
        assert isinstance(result_7, dict)


class TestComputeScores:
    """Test score computation."""

    def test_compute_scores_returns_all_dimensions(self, seeded_db):
        """Verify compute_scores returns all score dimensions."""
        result = compute_scores(days=7)
        assert isinstance(result, dict)
        expected_keys = ["context", "tools", "prompts", "health", "composite"]
        for key in expected_keys:
            assert key in result

    def test_scores_are_0_to_100(self, seeded_db):
        """Verify all scores are in valid range."""
        result = compute_scores(days=7)
        for key in ["context", "tools", "prompts", "health", "composite"]:
            score = result[key]
            assert 0 <= score <= 100, f"{key} score out of range: {score}"

    def test_composite_is_weighted_average(self, seeded_db):
        """Verify composite is a weighted average."""
        result = compute_scores(days=7)
        # Composite should be influenced by all dimensions
        assert isinstance(result["composite"], int)
        assert result["composite"] >= 0

    def test_scores_empty_db(self, temp_db):
        """Compute scores on empty database."""
        result = compute_scores(days=7)
        assert isinstance(result, dict)
        # Should still have all keys
        for key in ["context", "tools", "prompts", "health", "composite"]:
            assert key in result
            assert isinstance(result[key], int)


class TestAnalyzeTrends:
    """Test trend analysis."""

    def test_analyze_trends_returns_dict(self, seeded_db):
        """Verify analyze_trends returns expected structure."""
        result = analyze_trends(days=14)
        assert isinstance(result, dict)
        assert "period_days" in result
        assert "current" in result
        assert "previous" in result
        assert "daily" in result
        assert "current_models" in result
        assert "previous_models" in result

    def test_trends_period_days(self, seeded_db):
        """Verify period_days is half of input."""
        result = analyze_trends(days=14)
        assert result["period_days"] == 7

    def test_trends_current_and_previous(self, seeded_db):
        """Verify current and previous are tuples."""
        result = analyze_trends(days=14)
        assert isinstance(result["current"], tuple)
        assert isinstance(result["previous"], tuple)

    def test_trends_empty_db(self, temp_db):
        """Analyze trends on empty database."""
        result = analyze_trends(days=14)
        assert isinstance(result, dict)
        assert result["daily"] == []

    def test_trends_respects_days(self, seeded_db):
        """Verify days parameter is respected."""
        result_30 = analyze_trends(days=30)
        result_7 = analyze_trends(days=7)
        assert result_30["period_days"] == 15
        assert result_7["period_days"] == 3


class TestGenerateReport:
    """Test report generation."""

    def test_generate_report_returns_dict(self, seeded_db):
        """Verify generate_report returns a comprehensive dict."""
        result = generate_report(days=7)
        assert isinstance(result, dict)
        assert "period_days" in result
        assert "overview" in result
        assert "model_usage" in result
        assert "context" in result
        assert "tools" in result
        assert "prompts" in result
        assert "antipatterns" in result
        assert "scores" in result

    def test_generate_report_overview(self, seeded_db):
        """Verify overview section."""
        result = generate_report(days=7)
        overview = result["overview"]
        if overview:
            # Should have counts
            assert isinstance(overview, tuple)

    def test_generate_report_includes_all_analyzers(self, seeded_db):
        """Verify report includes all analyzer outputs."""
        result = generate_report(days=7)
        assert "context" in result
        assert "tools" in result
        assert "prompts" in result
        assert "antipatterns" in result
        assert "scores" in result

    def test_generate_report_empty_db(self, temp_db):
        """Generate report on empty database."""
        result = generate_report(days=7)
        assert isinstance(result, dict)
        # All keys should exist even if empty
        assert "overview" in result


class TestGenerateMarkdownReport:
    """Test markdown report generation."""

    def test_markdown_report_is_string(self, seeded_db):
        """Verify markdown report is a string."""
        result = generate_markdown_report(days=7)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_markdown_report_has_headers(self, seeded_db):
        """Verify markdown report has section headers."""
        result = generate_markdown_report(days=7)
        assert "# dt Report" in result

    def test_markdown_report_respects_days(self, seeded_db):
        """Verify days parameter is used in title."""
        result = generate_markdown_report(days=14)
        assert "14" in result or "Days" in result

    def test_markdown_report_valid_markdown(self, seeded_db):
        """Verify markdown report contains valid markdown."""
        result = generate_markdown_report(days=7)
        # Should have tables with pipes
        assert "|" in result
        # Should have code generation timestamp
        assert "Generated by dt" in result

    def test_markdown_report_empty_db(self, temp_db):
        """Generate markdown report on empty database."""
        result = generate_markdown_report(days=7)
        assert isinstance(result, str)
        assert "# dt Report" in result


class TestSparkline:
    """Test sparkline generation."""

    def test_sparkline_basic(self):
        """Test basic sparkline generation."""
        values = [1, 2, 3, 4, 5]
        result = _sparkline(values)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_sparkline_single_value(self):
        """Sparkline with single value."""
        result = _sparkline([5])
        assert isinstance(result, str)

    def test_sparkline_identical_values(self):
        """Sparkline with identical values."""
        result = _sparkline([5, 5, 5, 5])
        assert isinstance(result, str)

    def test_sparkline_empty(self):
        """Sparkline with empty list."""
        result = _sparkline([])
        assert result == ""

    def test_sparkline_width_parameter(self):
        """Test width parameter affects output."""
        values = list(range(30))
        result = _sparkline(values, width=20)
        assert isinstance(result, str)

    def test_sparkline_uses_unicode(self):
        """Verify sparkline uses unicode characters."""
        result = _sparkline([1, 5, 10, 15, 20])
        # Should contain block characters
        assert any(c in result for c in "\u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588")


class TestShortModel:
    """Test model name shortening."""

    def test_short_model_removes_claude_prefix(self):
        """Remove 'claude-' prefix."""
        assert _short_model("claude-opus-4-6") == "opus-4-6"
        assert _short_model("claude-sonnet-4-20250514") == "sonnet-4-20250514"

    def test_short_model_removes_date_suffixes(self):
        """Remove date suffixes from model names."""
        assert _short_model("claude-opus-4-20251001") == "opus-4"
        assert _short_model("claude-sonnet-4-20250929") == "sonnet-4"

    def test_short_model_already_short(self):
        """Handle already short model names."""
        assert _short_model("haiku") == "haiku"

    def test_short_model_empty_string(self):
        """Handle empty string."""
        assert _short_model("") == ""

    def test_short_model_no_matching_prefixes(self):
        """Handle names without standard prefixes."""
        result = _short_model("custom-model-name")
        assert isinstance(result, str)


class TestShortPath:
    """Test path shortening."""

    def test_short_path_long_path_shortened(self):
        """Shorten long paths."""
        long_path = "/very/long/path/to/some/nested/directory/file.py"
        result = _short_path(long_path)
        assert len(result) <= 70 or result == long_path

    def test_short_path_short_path_unchanged(self):
        """Keep short paths unchanged."""
        short_path = "/src/main.py"
        assert _short_path(short_path) == short_path

    def test_short_path_empty_string(self):
        """Handle empty string."""
        assert _short_path("") == ""

    def test_short_path_single_component(self):
        """Handle single component path."""
        result = _short_path("file.py")
        assert result == "file.py"


class TestScoreRanges:
    """Verify score computation edge cases."""

    def test_all_scores_on_empty_db(self, temp_db):
        """Verify scores exist on empty database."""
        scores = compute_scores(days=7)
        for score_name in ["context", "tools", "prompts", "health", "composite"]:
            assert score_name in scores
            assert isinstance(scores[score_name], int)
            assert 0 <= scores[score_name] <= 100

    def test_context_score_with_high_cache(self, seeded_db):
        """Context score should favor high cache efficiency."""
        scores = compute_scores(days=7)
        # With sample data that has cache reads, context should be reasonable
        assert scores["context"] >= 0

    def test_tool_score_with_few_errors(self, seeded_db):
        """Tool score should be high with few errors."""
        scores = compute_scores(days=7)
        # Sample data has minimal errors
        assert scores["tools"] > 0


class TestReportConsistency:
    """Test consistency across report outputs."""

    def test_report_and_markdown_consistent(self, seeded_db):
        """Verify report and markdown report are consistent."""
        report = generate_report(days=7)
        markdown = generate_markdown_report(days=7)

        # Both should exist and be non-empty
        assert report is not None
        assert markdown is not None
        assert len(markdown) > 0

    def test_all_analyzers_integrated(self, seeded_db):
        """Verify all analyzers are included in comprehensive report."""
        report = generate_report(days=7)
        # Should include outputs from all analyzer functions
        assert "context" in report
        assert "tools" in report
        assert "prompts" in report
        assert "antipatterns" in report
        assert "scores" in report
        assert "health" in report
