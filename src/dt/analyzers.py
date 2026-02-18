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

    # Edit-retry cycles: same file edited multiple times with errors between
    edit_retries = conn.execute(f"""
        SELECT
            session_id, file_path,
            SUM(CASE WHEN result_error THEN 1 ELSE 0 END) as edit_errors,
            COUNT(*) as edit_attempts
        FROM tool_calls
        WHERE timestamp >= CURRENT_DATE - {iv}
          AND tool_name IN ('Edit', 'edit')
          AND file_path IS NOT NULL
        GROUP BY session_id, file_path
        HAVING edit_errors >= 2
        ORDER BY edit_errors DESC
        LIMIT 10
    """).fetchall()

    for row in edit_retries:
        findings.append({
            "type": "edit_retry_cycle",
            "severity": "warning",
            "session_id": row[0],
            "description": f"Edit failed {row[2]}x on {row[1]} ({row[3]} total attempts)",
            "file_path": row[1],
            "suggestion": "Read the file first to get accurate old_string context",
        })

    # Stale sessions: running 2+ hours
    stale_sessions = conn.execute(f"""
        SELECT session_id, project_name, duration_seconds / 3600.0 as hours,
               user_message_count
        FROM sessions
        WHERE first_message_at >= CURRENT_DATE - {iv}
          AND duration_seconds > 7200
        ORDER BY duration_seconds DESC
        LIMIT 10
    """).fetchall()

    for row in stale_sessions:
        findings.append({
            "type": "stale_session",
            "severity": "info",
            "session_id": row[0],
            "description": f"Session in {row[1]} ran {row[2]:.1f}h with {row[3]} turns",
            "suggestion": "Use /clear between subtasks to avoid context drift",
        })

    # Tool retry without change: same tool+input called consecutively
    consecutive_dupes = conn.execute(f"""
        WITH ordered AS (
            SELECT session_id, tool_name, input_summary, timestamp,
                   LAG(tool_name) OVER (PARTITION BY session_id ORDER BY timestamp) as prev_tool,
                   LAG(input_summary) OVER (PARTITION BY session_id ORDER BY timestamp) as prev_summary
            FROM tool_calls
            WHERE timestamp >= CURRENT_DATE - {iv}
        )
        SELECT session_id, tool_name, COUNT(*) as repeats
        FROM ordered
        WHERE tool_name = prev_tool
          AND input_summary = prev_summary
          AND tool_name NOT IN ('Read', 'read')
        GROUP BY session_id, tool_name
        HAVING repeats >= 2
        ORDER BY repeats DESC
        LIMIT 10
    """).fetchall()

    for row in consecutive_dupes:
        findings.append({
            "type": "tool_retry_no_change",
            "severity": "warning",
            "session_id": row[0],
            "description": f"{row[1]} called {row[2]}x with identical input in one session",
            "suggestion": "Change approach if a tool call fails repeatedly",
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


def analyze_health(days: int = 30) -> dict:
    """Analyze project configuration health."""
    conn = get_connection(read_only=True)
    iv = _interval(days)

    # Projects with high file access but potentially missing CLAUDE.md
    high_access_projects = conn.execute(f"""
        SELECT
            s.project_name,
            COUNT(DISTINCT fa.session_id) as sessions,
            COUNT(*) as total_reads,
            COUNT(DISTINCT fa.file_path) as unique_files
        FROM file_access fa
        JOIN sessions s ON fa.session_id = s.session_id
        WHERE fa.timestamp >= CURRENT_DATE - {iv}
          AND fa.access_type = 'read'
        GROUP BY s.project_name
        HAVING total_reads >= 10
        ORDER BY total_reads DESC
        LIMIT 15
    """).fetchall()

    # Files read many times across sessions (CLAUDE.md candidates)
    claudemd_candidates = conn.execute(f"""
        SELECT
            file_path,
            COUNT(DISTINCT session_id) as sessions,
            COUNT(*) as total_reads,
            ROUND(COUNT(*) * 1.0 / COUNT(DISTINCT session_id), 1) as reads_per_session
        FROM file_access
        WHERE timestamp >= CURRENT_DATE - {iv}
          AND access_type = 'read'
          AND file_path NOT LIKE '%%CLAUDE.md'
          AND file_path NOT LIKE '%%.claude/%%'
        GROUP BY file_path
        HAVING sessions >= 3 AND reads_per_session > 3
        ORDER BY reads_per_session DESC
        LIMIT 15
    """).fetchall()

    # Large files that may fragment context (read many times, high repeat count)
    context_fragmenters = conn.execute(f"""
        SELECT
            file_path,
            COUNT(*) as total_reads,
            SUM(CASE WHEN is_repeat THEN 1 ELSE 0 END) as repeat_reads,
            COUNT(DISTINCT session_id) as sessions
        FROM file_access
        WHERE timestamp >= CURRENT_DATE - {iv}
          AND access_type = 'read'
        GROUP BY file_path
        HAVING repeat_reads >= 3
        ORDER BY repeat_reads DESC
        LIMIT 15
    """).fetchall()

    # Sessions with high tool error rates (may indicate config issues)
    error_prone_projects = conn.execute(f"""
        SELECT
            project_name,
            COUNT(*) as sessions,
            SUM(tool_call_count) as total_tools,
            SUM(tool_error_count) as total_errors,
            ROUND(SUM(tool_error_count) * 100.0 / NULLIF(SUM(tool_call_count), 0), 1) as error_rate
        FROM sessions
        WHERE first_message_at >= CURRENT_DATE - {iv}
          AND tool_call_count > 0
        GROUP BY project_name
        HAVING total_errors > 5
        ORDER BY error_rate DESC
        LIMIT 10
    """).fetchall()

    conn.close()
    return {
        "high_access_projects": high_access_projects,
        "claudemd_candidates": claudemd_candidates,
        "context_fragmenters": context_fragmenters,
        "error_prone_projects": error_prone_projects,
    }


def compute_scores(days: int = 7) -> dict:
    """Compute 0-100 scores for each analyzer dimension."""
    conn = get_connection(read_only=True)
    iv = _interval(days)

    # Context score: based on cache efficiency and repeat read ratio
    cache_row = conn.execute(f"""
        SELECT
            COALESCE(SUM(cache_read_tokens), 0) as cache_reads,
            COALESCE(SUM(input_tokens), 0) as direct_input
        FROM messages
        WHERE timestamp >= CURRENT_DATE - {iv}
    """).fetchone()
    cache_total = (cache_row[0] or 0) + (cache_row[1] or 0)
    cache_pct = (cache_row[0] / cache_total * 100) if cache_total > 0 else 100

    repeat_row = conn.execute(f"""
        SELECT
            COUNT(*) as total_reads,
            SUM(CASE WHEN is_repeat THEN 1 ELSE 0 END) as repeats
        FROM file_access
        WHERE timestamp >= CURRENT_DATE - {iv}
          AND access_type = 'read'
    """).fetchone()
    total_reads = repeat_row[0] or 1
    repeat_pct = (repeat_row[1] or 0) / total_reads * 100

    # Context score: cache efficiency (60% weight) + low repeat rate (40% weight)
    context_score = min(100, int(cache_pct * 0.6 + max(0, 100 - repeat_pct * 5) * 0.4))

    # Tool score: based on error rate
    tool_row = conn.execute(f"""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN result_error THEN 1 ELSE 0 END) as errors
        FROM tool_calls
        WHERE timestamp >= CURRENT_DATE - {iv}
    """).fetchone()
    total_tools = tool_row[0] or 1
    tool_error_pct = (tool_row[1] or 0) / total_tools * 100
    tool_score = max(0, min(100, int(100 - tool_error_pct * 3)))

    # Prompt score: based on "other" classification rate and avg word count
    prompt_row = conn.execute(f"""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN pattern = 'other' THEN 1 ELSE 0 END) as other_count,
            AVG(word_count) as avg_words
        FROM prompts
        WHERE timestamp >= CURRENT_DATE - {iv}
    """).fetchone()
    total_prompts = prompt_row[0] or 1
    other_pct = (prompt_row[1] or 0) / total_prompts * 100
    avg_words = prompt_row[2] or 0
    # Penalize high "other" rate and very short prompts
    prompt_score = max(0, min(100, int(100 - other_pct * 0.5 - max(0, 10 - avg_words) * 3)))

    # Health score: based on anti-pattern count
    ap_row = conn.execute(f"""
        SELECT COUNT(*) FROM (
            SELECT session_id, file_path
            FROM file_access
            WHERE timestamp >= CURRENT_DATE - {iv}
              AND access_type = 'read'
            GROUP BY session_id, file_path
            HAVING COUNT(*) >= 5
        )
    """).fetchone()
    severe_repeats = ap_row[0] or 0
    # Scale: 0 repeats = 100, 10 = 80, 20 = 60, 50+ = ~30
    health_score = max(20, min(100, int(100 - severe_repeats * 1.5)))

    conn.close()

    # Composite: weighted average
    composite = int(
        context_score * 0.30 +
        tool_score * 0.25 +
        prompt_score * 0.20 +
        health_score * 0.25
    )

    return {
        "context": context_score,
        "tools": tool_score,
        "prompts": prompt_score,
        "health": health_score,
        "composite": composite,
    }


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

    # Subagent model usage (separate from main conversation)
    subagent_model_usage = conn.execute(f"""
        SELECT
            model,
            COUNT(*) as launches,
            SUM(message_count) as total_messages,
            SUM(total_tokens) as total_tokens,
            SUM(tool_call_count) as total_tools,
            AVG(message_count) as avg_msgs,
            AVG(duration_seconds) as avg_duration
        FROM subagents
        WHERE started_at >= CURRENT_DATE - {iv}
          AND model IS NOT NULL AND model != ''
        GROUP BY model
        ORDER BY total_tokens DESC
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
        "subagent_model_usage": subagent_model_usage,
        "top_projects": top_projects,
        "daily_trend": daily,
        "context": analyze_context(days),
        "tools": analyze_tools(days),
        "prompts": analyze_prompts(days),
        "antipatterns": detect_antipatterns(days),
        "scores": compute_scores(days),
        "health": analyze_health(days),
    }
