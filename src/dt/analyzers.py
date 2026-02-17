"""Analyzers that produce actionable insights from ingested session data."""
from .db import get_connection


def _interval(days: int) -> str:
    """Build a DuckDB interval clause. days is always a validated int."""
    return f"INTERVAL '{days}' DAY"


def analyze_context(days: int = 7) -> dict:
    """Analyze context efficiency patterns."""
    conn = get_connection(read_only=True)
    iv = _interval(days)

    repeat_reads = conn.execute(f"""
        SELECT
            file_path,
            COUNT(DISTINCT session_id) as sessions,
            SUM(CASE WHEN is_repeat THEN 1 ELSE 0 END) as repeat_count,
            COUNT(*) as total_reads
        FROM file_access
        WHERE timestamp >= CURRENT_DATE - {iv}
          AND access_type = 'read'
        GROUP BY file_path
        HAVING repeat_count > 0
        ORDER BY repeat_count DESC
        LIMIT 20
    """).fetchall()

    heavy_sessions = conn.execute(f"""
        SELECT
            session_id, project_name, summary,
            message_count, tool_call_count,
            total_input_tokens + total_output_tokens as total_tokens,
            total_cache_read,
            duration_seconds / 60 as duration_minutes
        FROM sessions
        WHERE first_message_at >= CURRENT_DATE - {iv}
        ORDER BY message_count DESC
        LIMIT 10
    """).fetchall()

    cache_efficiency = conn.execute(f"""
        SELECT
            model,
            SUM(cache_read_tokens) as cache_reads,
            SUM(input_tokens) as direct_input,
            SUM(cache_create_tokens) as cache_creates,
            CASE WHEN SUM(cache_read_tokens) + SUM(input_tokens) > 0
                THEN ROUND(SUM(cache_read_tokens) * 100.0 /
                    (SUM(cache_read_tokens) + SUM(input_tokens)), 1)
                ELSE 0 END as cache_pct
        FROM messages
        WHERE timestamp >= CURRENT_DATE - {iv}
          AND model IS NOT NULL AND model != ''
        GROUP BY model
        ORDER BY cache_reads DESC
    """).fetchall()

    hotspot_files = conn.execute(f"""
        SELECT
            file_path,
            COUNT(*) as total_reads,
            COUNT(DISTINCT session_id) as sessions
        FROM file_access
        WHERE timestamp >= CURRENT_DATE - {iv}
          AND access_type = 'read'
        GROUP BY file_path
        ORDER BY total_reads DESC
        LIMIT 20
    """).fetchall()

    conn.close()
    return {
        "repeat_reads": repeat_reads,
        "heavy_sessions": heavy_sessions,
        "cache_efficiency": cache_efficiency,
        "hotspot_files": hotspot_files,
    }


def analyze_tools(days: int = 7) -> dict:
    """Analyze tool usage patterns."""
    conn = get_connection(read_only=True)
    iv = _interval(days)

    tool_freq = conn.execute(f"""
        SELECT
            tool_name,
            COUNT(*) as count,
            SUM(CASE WHEN result_error THEN 1 ELSE 0 END) as errors,
            ROUND(SUM(CASE WHEN result_error THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) as error_rate
        FROM tool_calls
        WHERE timestamp >= CURRENT_DATE - {iv}
        GROUP BY tool_name
        ORDER BY count DESC
    """).fetchall()

    failures = conn.execute(f"""
        SELECT
            tool_name,
            input_summary,
            session_id,
            timestamp
        FROM tool_calls
        WHERE timestamp >= CURRENT_DATE - {iv}
          AND result_error = TRUE
        ORDER BY timestamp DESC
        LIMIT 20
    """).fetchall()

    subagent_stats = conn.execute(f"""
        SELECT
            agent_type,
            model,
            COUNT(*) as launches,
            AVG(message_count) as avg_messages,
            AVG(duration_seconds) as avg_duration_sec,
            SUM(total_tokens) as total_tokens
        FROM subagents
        WHERE started_at >= CURRENT_DATE - {iv}
        GROUP BY agent_type, model
        ORDER BY launches DESC
    """).fetchall()

    conn.close()
    return {
        "tool_frequency": tool_freq,
        "failures": failures,
        "subagent_stats": subagent_stats,
    }


def analyze_prompts(days: int = 7) -> dict:
    """Analyze prompt patterns and effectiveness."""
    conn = get_connection(read_only=True)
    iv = _interval(days)

    patterns = conn.execute(f"""
        SELECT
            pattern,
            COUNT(*) as count,
            AVG(word_count) as avg_words
        FROM prompts
        WHERE timestamp >= CURRENT_DATE - {iv}
          AND pattern IS NOT NULL
        GROUP BY pattern
        ORDER BY count DESC
    """).fetchall()

    verbose = conn.execute(f"""
        SELECT
            text,
            word_count,
            project_path,
            timestamp
        FROM prompts
        WHERE timestamp >= CURRENT_DATE - {iv}
          AND word_count > 50
        ORDER BY word_count DESC
        LIMIT 10
    """).fetchall()

    by_project = conn.execute(f"""
        SELECT
            project_path,
            COUNT(*) as prompts,
            AVG(word_count) as avg_words
        FROM prompts
        WHERE timestamp >= CURRENT_DATE - {iv}
        GROUP BY project_path
        ORDER BY prompts DESC
        LIMIT 15
    """).fetchall()

    conn.close()
    return {
        "patterns": patterns,
        "verbose_prompts": verbose,
        "by_project": by_project,
    }


def detect_antipatterns(days: int = 7) -> list[dict]:
    """Detect anti-patterns across recent sessions."""
    conn = get_connection(read_only=True)
    iv = _interval(days)
    findings = []

    repeats = conn.execute(f"""
        SELECT session_id, file_path, COUNT(*) as reads
        FROM file_access
        WHERE timestamp >= CURRENT_DATE - {iv}
          AND access_type = 'read'
        GROUP BY session_id, file_path
        HAVING reads >= 3
        ORDER BY reads DESC
        LIMIT 20
    """).fetchall()

    for row in repeats:
        findings.append({
            "type": "repeat_read",
            "severity": "warning",
            "session_id": row[0],
            "description": f"File {row[1]} read {row[2]} times in one session",
            "file_path": row[1],
            "suggestion": "Add key content to CLAUDE.md or use shorter sessions",
        })

    long_sessions = conn.execute(f"""
        SELECT session_id, project_name, user_message_count, summary
        FROM sessions
        WHERE first_message_at >= CURRENT_DATE - {iv}
          AND user_message_count > 30
        ORDER BY user_message_count DESC
        LIMIT 10
    """).fetchall()

    for row in long_sessions:
        findings.append({
            "type": "long_session",
            "severity": "info",
            "session_id": row[0],
            "description": f"Session in {row[1]} had {row[2]} user turns: {row[3]}",
            "suggestion": "Consider breaking into focused sessions with /clear",
        })

    sensitive = conn.execute(f"""
        SELECT session_id, file_path, COUNT(*) as accesses
        FROM file_access
        WHERE timestamp >= CURRENT_DATE - {iv}
          AND (file_path LIKE '%%.env' OR file_path LIKE '%%.env.%%'
               OR file_path LIKE '%%credentials%%'
               OR file_path LIKE '%%secret%%'
               OR file_path LIKE '%%apikey%%'
               OR file_path LIKE '%%.pem')
        GROUP BY session_id, file_path
    """).fetchall()

    for row in sensitive:
        findings.append({
            "type": "sensitive_access",
            "severity": "critical",
            "session_id": row[0],
            "description": f"Sensitive file accessed: {row[1]} ({row[2]}x)",
            "file_path": row[1],
            "suggestion": "Use .env.example or document variables in CLAUDE.md instead",
        })

    error_tools = conn.execute(f"""
        SELECT
            tool_name,
            COUNT(*) as total,
            SUM(CASE WHEN result_error THEN 1 ELSE 0 END) as errors
        FROM tool_calls
        WHERE timestamp >= CURRENT_DATE - {iv}
        GROUP BY tool_name
        HAVING errors > 3 AND errors * 1.0 / total > 0.2
    """).fetchall()

    for row in error_tools:
        findings.append({
            "type": "tool_failure_rate",
            "severity": "warning",
            "description": f"{row[0]}: {row[2]}/{row[1]} calls failed ({row[2]*100//row[1]}%)",
            "suggestion": f"Review common {row[0]} failures; may indicate prompt issues",
        })

    opus_waste = conn.execute(f"""
        SELECT
            agent_type, model, COUNT(*) as launches,
            AVG(message_count) as avg_msgs
        FROM subagents
        WHERE started_at >= CURRENT_DATE - {iv}
          AND model LIKE '%%opus%%'
          AND message_count < 5
        GROUP BY agent_type, model
        HAVING launches >= 2
    """).fetchall()

    for row in opus_waste:
        findings.append({
            "type": "model_waste",
            "severity": "info",
            "description": f"Opus used for {row[0]} ({row[2]} launches, avg {row[3]:.0f} msgs)",
            "suggestion": "Consider Haiku or Sonnet for this agent type",
        })

    conn.close()
    return findings


def generate_report(days: int = 7) -> dict:
    """Generate a comprehensive report combining all analyzers."""
    conn = get_connection(read_only=True)
    iv = _interval(days)

    overview = conn.execute(f"""
        SELECT
            COUNT(*) as sessions,
            SUM(message_count) as messages,
            SUM(tool_call_count) as tool_calls,
            SUM(tool_error_count) as tool_errors,
            SUM(total_input_tokens + total_output_tokens) as total_tokens,
            SUM(total_cache_read) as cache_reads,
            AVG(user_message_count) as avg_turns,
            COUNT(DISTINCT project_name) as projects
        FROM sessions
        WHERE first_message_at >= CURRENT_DATE - {iv}
    """).fetchone()

    model_usage = conn.execute(f"""
        SELECT
            model,
            COUNT(*) as messages,
            SUM(input_tokens + output_tokens) as tokens,
            SUM(cache_read_tokens) as cache_reads
        FROM messages
        WHERE timestamp >= CURRENT_DATE - {iv}
          AND model IS NOT NULL AND model != ''
        GROUP BY model
        ORDER BY tokens DESC
    """).fetchall()

    top_projects = conn.execute(f"""
        SELECT
            project_name,
            COUNT(*) as sessions,
            SUM(message_count) as messages,
            SUM(tool_call_count) as tool_calls
        FROM sessions
        WHERE first_message_at >= CURRENT_DATE - {iv}
        GROUP BY project_name
        ORDER BY messages DESC
        LIMIT 10
    """).fetchall()

    daily = conn.execute(f"""
        SELECT date, message_count, session_count, tool_call_count, total_tokens
        FROM daily_stats
        WHERE date >= CURRENT_DATE - {iv}
        ORDER BY date
    """).fetchall()

    conn.close()

    return {
        "period_days": days,
        "overview": overview,
        "model_usage": model_usage,
        "top_projects": top_projects,
        "daily_trend": daily,
        "context": analyze_context(days),
        "tools": analyze_tools(days),
        "prompts": analyze_prompts(days),
        "antipatterns": detect_antipatterns(days),
    }
