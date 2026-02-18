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
    """Generate a comprehensive report dict aggregating all analyzers."""
    conn = get_connection(read_only=True)
    iv = _interval(days)

    overview = conn.execute(f"""
        SELECT
            COUNT(DISTINCT session_id),
            SUM(message_count),
            SUM(tool_call_count),
            SUM(tool_error_count),
            SUM(total_input_tokens + total_output_tokens),
            SUM(total_cache_read),
            AVG(message_count),
            COUNT(DISTINCT project_name)
        FROM sessions WHERE first_message_at >= CURRENT_DATE - {iv}
    """).fetchone()

    top_projects = conn.execute(f"""
        SELECT project_name, COUNT(*) as sessions,
            SUM(message_count) as msgs, SUM(tool_call_count) as tools
        FROM sessions WHERE first_message_at >= CURRENT_DATE - {iv}
            AND project_name IS NOT NULL
        GROUP BY project_name ORDER BY sessions DESC LIMIT 10
    """).fetchall()

    subagent_model_usage = conn.execute(f"""
        SELECT model, COUNT(*) as launches,
            SUM(message_count) as msgs, SUM(total_tokens) as tokens,
            SUM(tool_call_count) as tools, AVG(message_count) as avg_msgs
        FROM subagents WHERE session_id IN (
            SELECT session_id FROM sessions
            WHERE first_message_at >= CURRENT_DATE - {iv}
        ) AND model IS NOT NULL
        GROUP BY model ORDER BY launches DESC
    """).fetchall()

    conn.close()

    tools_data = analyze_tools(days)
    model_usage = tools_data.get("model_usage", [])

    return {
        "period_days": days,
        "overview": overview,
        "model_usage": model_usage,
        "top_projects": top_projects,
        "subagent_model_usage": subagent_model_usage,
        "context": analyze_context(days),
        "tools": tools_data,
        "prompts": analyze_prompts(days),
        "antipatterns": detect_antipatterns(days),
        "scores": compute_scores(days),
        "health": analyze_health(days),
        "recommendations": recommend(days),
    }


def generate_markdown_report(days: int = 7, title: str | None = None) -> str:
    """Generate a complete markdown report."""
    data = generate_report(days)
    lines = []

    period_label = f"Last {days} Days" if days <= 7 else f"Last {days} Days" if days <= 30 else "All Time"
    report_title = title or f"dt Report - {period_label}"
    lines.append(f"# {report_title}\n")

    from datetime import date
    from . import __version__
    lines.append(f"*Generated by dt v{__version__} on {date.today()}*\n")

    # Scores
    scores = data.get("scores", {})
    if scores:
        lines.append("## Scores\n")
        lines.append(f"| Dimension | Score |")
        lines.append(f"|-----------|-------|")
        lines.append(f"| **Overall** | **{scores.get('composite', 0)}/100** |")
        for key, label in [("context", "Context"), ("tools", "Tools"), ("prompts", "Prompts"), ("health", "Health")]:
            lines.append(f"| {label} | {scores.get(key, 0)}/100 |")
        lines.append("")

    # Overview
    ov = data.get("overview")
    if ov:
        lines.append("## Overview\n")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Sessions | {ov[0] or 0:,} |")
        lines.append(f"| Messages | {ov[1] or 0:,} |")
        tool_str = f"{ov[2] or 0:,}"
        if ov[3]:
            tool_str += f" ({ov[3]:,} errors, {ov[3]*100//(ov[2] or 1)}%)"
        lines.append(f"| Tool calls | {tool_str} |")
        lines.append(f"| Tokens | {ov[4] or 0:,} |")
        if ov[5] and ov[4]:
            eff = ov[5] * 100 / (ov[5] + ov[4])
            lines.append(f"| Cache efficiency | {eff:.0f}% |")
        lines.append(f"| Avg turns/session | {ov[6] or 0:.1f} |")
        lines.append(f"| Active projects | {ov[7] or 0} |")
        lines.append("")

    # Model usage
    if data.get("model_usage"):
        lines.append("## Model Usage\n")
        lines.append("### Main Conversation\n")
        lines.append("| Model | Messages | Tokens | Cache Reads |")
        lines.append("|-------|----------|--------|-------------|")
        for row in data["model_usage"]:
            model = _short_model(row[0])
            lines.append(f"| {model} | {row[1]:,} | {row[2] or 0:,} | {row[3] or 0:,} |")
        lines.append("")

    if data.get("subagent_model_usage"):
        lines.append("### Subagent Work\n")
        lines.append("| Model | Launches | Messages | Tokens | Tools | Avg Msgs |")
        lines.append("|-------|----------|----------|--------|-------|----------|")
        for row in data["subagent_model_usage"]:
            model = _short_model(row[0])
            lines.append(f"| {model} | {row[1]:,} | {row[2] or 0:,} | {row[3] or 0:,} | {row[4] or 0:,} | {row[5] or 0:.0f} |")
        lines.append("")

    # Top projects
    if data.get("top_projects"):
        lines.append("## Top Projects\n")
        lines.append("| Project | Sessions | Messages | Tools |")
        lines.append("|---------|----------|----------|-------|")
        for row in data["top_projects"]:
            lines.append(f"| {row[0]} | {row[1]:,} | {row[2]:,} | {row[3]:,} |")
        lines.append("")

    # Tool usage
    tools = data.get("tools", {})
    if tools.get("tool_frequency"):
        lines.append("## Tool Usage\n")
        lines.append("| Tool | Calls | Errors | Error % |")
        lines.append("|------|-------|--------|---------|")
        for row in tools["tool_frequency"][:15]:
            lines.append(f"| {row[0]} | {row[1]:,} | {row[2]:,} | {row[3] or 0}% |")
        lines.append("")

    # Subagent types
    if tools.get("subagent_stats"):
        lines.append("## Subagent Types\n")
        lines.append("| Agent Type | Model | Launches | Avg Msgs | Total Tokens |")
        lines.append("|------------|-------|----------|----------|--------------|")
        for row in tools["subagent_stats"]:
            model = _short_model(row[1] or "?")
            lines.append(f"| {row[0] or '?'} | {model} | {row[2]:,} | {row[3] or 0:.0f} | {row[5] or 0:,} |")
        lines.append("")

    # Context hotspots
    ctx = data.get("context", {})
    if ctx.get("hotspot_files"):
        lines.append("## Context Hotspots\n")
        lines.append("| File | Total Reads | Sessions | Reads/Session |")
        lines.append("|------|-------------|----------|---------------|")
        for row in ctx["hotspot_files"][:15]:
            fp = str(row[0])
            sessions = row[2] or 1
            rps = row[1] / sessions
            lines.append(f"| {_short_path(fp)} | {row[1]:,} | {row[2]:,} | {rps:.1f} |")
        lines.append("")

    # Prompt patterns
    prompts = data.get("prompts", {})
    if prompts.get("patterns"):
        lines.append("## Prompt Patterns\n")
        lines.append("| Pattern | Count | Avg Words |")
        lines.append("|---------|-------|-----------|")
        for row in prompts["patterns"]:
            lines.append(f"| {row[0]} | {row[1]:,} | {row[2] or 0:.0f} |")
        lines.append("")

    # Anti-patterns
    aps = data.get("antipatterns", [])
    if aps:
        lines.append("## Anti-Patterns\n")
        # Group by type
        by_type = {}
        for ap in aps:
            by_type.setdefault(ap["type"], []).append(ap)
        lines.append("| Pattern | Count | Worst Case |")
        lines.append("|---------|-------|------------|")
        for ptype, items in by_type.items():
            worst = items[0]["description"][:60]
            lines.append(f"| {ptype} | {len(items)} | {worst} |")
        lines.append("")

    # Health
    health = data.get("health", {})
    if health.get("claudemd_candidates"):
        lines.append("## CLAUDE.md Candidates\n")
        lines.append("Files frequently re-read that should be summarized in CLAUDE.md:\n")
        lines.append("| File | Sessions | Reads/Session |")
        lines.append("|------|----------|---------------|")
        for row in health["claudemd_candidates"][:10]:
            lines.append(f"| {_short_path(str(row[0]))} | {row[1]} | {row[3]} |")
        lines.append("")

    # Recommendations
    recs = data.get("recommendations", [])
    if recs:
        lines.append("## Recommendations\n")
        for rec in recs:
            priority_icon = {"high": "!!!", "medium": "!!", "low": "!"}.get(rec["priority"], "")
            lines.append(f"### {priority_icon} {rec['title']} [{rec['category']}]\n")
            lines.append(f"{rec['description']}\n")
            lines.append(f"**Action:** {rec['action']}\n")
            lines.append(f"**Prompt to fix:**\n```\n{rec['prompt']}\n```\n")
            if rec.get("impact"):
                lines.append(f"*Impact: {rec['impact']}*\n")

    return "\n".join(lines)


def analyze_trends(days: int = 14) -> dict:
    """Compare current period vs previous period of same length."""
    conn = get_connection(read_only=True)
    half = days // 2

    def _period_stats(offset_start: int, offset_end: int):
        iv_start = _interval(offset_start)
        iv_end = _interval(offset_end)
        return conn.execute(f"""
            SELECT
                COUNT(*) as sessions,
                COALESCE(SUM(message_count), 0) as messages,
                COALESCE(SUM(tool_call_count), 0) as tool_calls,
                COALESCE(SUM(tool_error_count), 0) as tool_errors,
                COALESCE(SUM(total_input_tokens + total_output_tokens), 0) as tokens,
                COALESCE(AVG(user_message_count), 0) as avg_turns,
                COUNT(DISTINCT project_name) as projects,
                COALESCE(SUM(subagent_count), 0) as subagents
            FROM sessions
            WHERE first_message_at >= CURRENT_DATE - {iv_start}
              AND first_message_at < CURRENT_DATE - {iv_end}
        """).fetchone()

    current = _period_stats(half, 0)
    previous = _period_stats(days, half)

    # Daily breakdown for sparklines
    iv = _interval(days)
    daily = conn.execute(f"""
        SELECT
            CAST(first_message_at AS DATE) as day,
            COUNT(*) as sessions,
            SUM(message_count) as messages,
            SUM(tool_call_count) as tools,
            SUM(total_input_tokens + total_output_tokens) as tokens
        FROM sessions
        WHERE first_message_at >= CURRENT_DATE - {iv}
        GROUP BY day
        ORDER BY day
    """).fetchall()

    # Model shift
    def _model_stats(offset_start: int, offset_end: int):
        iv_s = _interval(offset_start)
        iv_e = _interval(offset_end)
        return conn.execute(f"""
            SELECT model, COUNT(*) as msgs
            FROM messages
            WHERE timestamp >= CURRENT_DATE - {iv_s}
              AND timestamp < CURRENT_DATE - {iv_e}
              AND model IS NOT NULL AND model != ''
            GROUP BY model
            ORDER BY msgs DESC
        """).fetchall()

    current_models = _model_stats(half, 0)
    previous_models = _model_stats(days, half)

    conn.close()
    return {
        "period_days": half,
        "current": current,
        "previous": previous,
        "daily": daily,
        "current_models": current_models,
        "previous_models": previous_models,
    }


def _sparkline(values: list[int | float], width: int = 20) -> str:
    """Generate a Unicode sparkline from values."""
    if not values:
        return ""
    blocks = " \u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"
    mn, mx = min(values), max(values)
    rng = mx - mn if mx != mn else 1
    return "".join(blocks[min(8, int((v - mn) / rng * 8))] for v in values)


def _short_model(model: str) -> str:
    """Shorten model name for display."""
    return model.replace("claude-", "").replace("-20251001", "").replace("-20250929", "").replace("-20251101", "")


def _short_path(path: str) -> str:
    """Shorten file path for display."""
    if len(path) > 70:
        parts = path.split("/")
        if len(parts) > 3:
            return "/".join(parts[-3:])
    return path


def recommend(days: int = 7, category: str = "all") -> list[dict]:
    """Generate prioritized, actionable recommendations with ready-to-paste prompts.

    Synthesizes findings from all analyzers into concrete actions.
    Each recommendation includes a prompt that can be fed directly into Claude Code.
    """
    conn = get_connection(read_only=True)
    iv = _interval(days)
    recs = []

    if category in ("all", "context"):
        recs.extend(_rec_claudemd_candidates(conn, iv))
        recs.extend(_rec_context_fragmenters(conn, iv))

    if category in ("all", "session"):
        recs.extend(_rec_session_hygiene(conn, iv))
        recs.extend(_rec_edit_retry_cycles(conn, iv))

    if category in ("all", "model"):
        recs.extend(_rec_model_routing(conn, iv))

    if category in ("all", "prompt"):
        recs.extend(_rec_prompt_quality(conn, iv))

    if category in ("all", "tools"):
        recs.extend(_rec_tool_errors(conn, iv))

    conn.close()

    # Sort by priority: high first, then medium, then low
    priority_order = {"high": 0, "medium": 1, "low": 2}
    recs.sort(key=lambda r: priority_order.get(r["priority"], 3))
    return recs


def _rec_claudemd_candidates(conn, iv: str) -> list[dict]:
    """Recommend adding frequently re-read files to CLAUDE.md."""
    rows = conn.execute(f"""
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
        HAVING sessions >= 3 AND reads_per_session > 2
        ORDER BY reads_per_session DESC
        LIMIT 10
    """).fetchall()

    recs = []
    for row in rows:
        fp = str(row[0])
        short = _short_path(fp)
        recs.append({
            "category": "context",
            "priority": "high" if row[3] >= 4 else "medium",
            "title": f"Add {short} summary to CLAUDE.md",
            "description": f"Read {row[2]} times across {row[1]} sessions ({row[3]} reads/session). "
                          f"Claude keeps re-reading this file because key info isn't in context.",
            "action": f"Summarize key patterns from {short} in your project's CLAUDE.md.",
            "prompt": f"Read {fp} and add a concise summary of its key functions, patterns, and "
                      f"important details to CLAUDE.md under a ## Key Files section. Focus on what "
                      f"you need to know to work with this file without re-reading it every time.",
            "impact": f"~{row[2] * 500:,} tokens saved by avoiding {row[2]} re-reads",
            "data": {"file_path": fp, "sessions": row[1], "reads": row[2],
                     "reads_per_session": float(row[3])},
        })
    return recs


def _rec_context_fragmenters(conn, iv: str) -> list[dict]:
    """Recommend splitting or summarizing files that fragment context within sessions."""
    rows = conn.execute(f"""
        SELECT
            file_path,
            session_id,
            COUNT(*) as reads_in_session
        FROM file_access
        WHERE timestamp >= CURRENT_DATE - {iv}
          AND access_type = 'read'
        GROUP BY file_path, session_id
        HAVING reads_in_session >= 5
        ORDER BY reads_in_session DESC
        LIMIT 10
    """).fetchall()

    recs = []
    for row in rows:
        fp = str(row[0])
        short = _short_path(fp)
        recs.append({
            "category": "context",
            "priority": "high" if row[2] >= 8 else "medium",
            "title": f"Reduce re-reads of {short}",
            "description": f"Read {row[2]} times in a single session. The file is likely too large "
                          f"or complex for Claude to retain across compactions.",
            "action": f"Split {short} into smaller focused modules, or add the critical "
                      f"sections to CLAUDE.md.",
            "prompt": f"Read {fp} and identify the sections that are most frequently needed. "
                      f"Add a summary of those key sections to CLAUDE.md. If the file is over "
                      f"300 lines, suggest how to split it into smaller, focused modules.",
            "impact": f"~{(row[2] - 1) * 800:,} tokens saved per session from avoided re-reads",
            "data": {"file_path": fp, "session_id": row[1][:8],
                     "reads_in_session": row[2]},
        })
    return recs


def _rec_session_hygiene(conn, iv: str) -> list[dict]:
    """Recommend shorter, focused sessions."""
    rows = conn.execute(f"""
        SELECT session_id, project_name, user_message_count,
               duration_seconds / 3600.0 as hours, summary
        FROM sessions
        WHERE first_message_at >= CURRENT_DATE - {iv}
          AND (user_message_count > 40 OR duration_seconds > 10800)
        ORDER BY user_message_count DESC
        LIMIT 10
    """).fetchall()

    recs = []
    for row in rows:
        turns = row[2]
        hours = row[3] or 0
        project = row[1] or "unknown"
        priority = "high" if turns > 100 or hours > 10 else "medium"
        recs.append({
            "category": "session",
            "priority": priority,
            "title": f"Break up long {project} sessions",
            "description": f"Session ran {turns} turns over {hours:.1f}h. Long sessions cause "
                          f"context drift, compaction loops, and repeat file reads.",
            "action": "Use /clear between subtasks. Start new sessions for different task domains.",
            "prompt": f"Review my CLAUDE.md and add a session management rule: "
                      f"'For {project} work, break sessions into focused tasks of 15-20 turns. "
                      f"Use /clear between subtasks. Start a fresh session for each new feature or bug fix.'",
            "impact": "Better context retention, fewer compactions, fewer repeat reads",
            "data": {"session_id": row[0][:8], "project": project,
                     "turns": turns, "hours": round(hours, 1)},
        })
    return recs


def _rec_edit_retry_cycles(conn, iv: str) -> list[dict]:
    """Recommend reading files before editing to avoid retry cycles."""
    rows = conn.execute(f"""
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

    recs = []
    for row in rows:
        fp = str(row[1])
        short = _short_path(fp)
        recs.append({
            "category": "session",
            "priority": "medium",
            "title": f"Read {short} before editing",
            "description": f"Edit failed {row[2]}x on this file ({row[3]} total attempts). "
                          f"Each failed edit wastes ~2K tokens on the retry cycle.",
            "action": "Always Read a file before using Edit to get accurate old_string context.",
            "prompt": f"Add a rule to CLAUDE.md: 'Always Read {short} before editing it. "
                      f"Use enough surrounding context in old_string to make the match unique. "
                      f"If an Edit fails, re-Read the file before retrying.'",
            "impact": f"~{row[2] * 2000:,} tokens saved from avoided edit retries",
            "data": {"file_path": fp, "session_id": row[0][:8],
                     "errors": row[2], "attempts": row[3]},
        })
    return recs


def _rec_model_routing(conn, iv: str) -> list[dict]:
    """Recommend model changes for subagents."""
    recs = []

    # Opus used for short tasks (wasteful)
    opus_waste = conn.execute(f"""
        SELECT
            agent_type, model, COUNT(*) as launches,
            AVG(message_count) as avg_msgs,
            SUM(total_tokens) as total_tokens
        FROM subagents
        WHERE started_at >= CURRENT_DATE - {iv}
          AND model LIKE '%%opus%%'
          AND message_count < 10
        GROUP BY agent_type, model
        HAVING launches >= 2
    """).fetchall()

    for row in opus_waste:
        agent_type = row[0] or "unknown"
        recs.append({
            "category": "model",
            "priority": "high",
            "title": f"Switch {agent_type} subagents from Opus to Haiku",
            "description": f"Opus used for {agent_type} ({row[2]} launches, avg {row[3]:.0f} msgs, "
                          f"{row[4] or 0:,} tokens). Short tasks don't need Opus-level reasoning.",
            "action": f"Route {agent_type} to Haiku in your subagent model selection rules.",
            "prompt": f"Update CLAUDE.md subagent model rules: add '{agent_type}' to the Haiku "
                      f"tier for mechanical/lookup tasks. It currently runs on Opus but averages "
                      f"only {row[3]:.0f} messages per launch, which doesn't justify the cost.",
            "impact": f"~{(row[4] or 0) * 3 // 4:,} tokens saved (75% cost reduction Opus->Haiku)",
            "data": {"agent_type": agent_type, "launches": row[2],
                     "avg_msgs": round(float(row[3] or 0), 1),
                     "total_tokens": row[4] or 0},
        })

    # High-token Haiku agents that might benefit from Sonnet
    heavy_haiku = conn.execute(f"""
        SELECT
            agent_type, model, COUNT(*) as launches,
            AVG(message_count) as avg_msgs,
            SUM(total_tokens) as total_tokens,
            AVG(total_tokens) as avg_tokens
        FROM subagents
        WHERE started_at >= CURRENT_DATE - {iv}
          AND model LIKE '%%haiku%%'
          AND message_count > 30
        GROUP BY agent_type, model
        HAVING launches >= 3 AND avg_tokens > 5000
    """).fetchall()

    for row in heavy_haiku:
        agent_type = row[0] or "unknown"
        recs.append({
            "category": "model",
            "priority": "low",
            "title": f"Consider Sonnet for {agent_type} subagents",
            "description": f"Haiku used for {agent_type} ({row[2]} launches, avg {row[3]:.0f} msgs, "
                          f"avg {row[5] or 0:,.0f} tokens/launch). Complex tasks may benefit from "
                          f"Sonnet's stronger reasoning.",
            "action": f"Evaluate if {agent_type} quality would improve with Sonnet.",
            "prompt": f"Review recent {agent_type} subagent outputs for quality. If they required "
                      f"multiple retries or produced incomplete results, consider upgrading to "
                      f"model=sonnet in your CLAUDE.md subagent rules.",
            "impact": "Potentially fewer retries and better first-attempt quality",
            "data": {"agent_type": agent_type, "launches": row[2],
                     "avg_msgs": round(float(row[3] or 0), 1),
                     "avg_tokens_per_launch": round(float(row[5] or 0))},
        })

    return recs


def _rec_prompt_quality(conn, iv: str) -> list[dict]:
    """Recommend prompt improvements based on classification patterns."""
    recs = []

    row = conn.execute(f"""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN pattern = 'other' THEN 1 ELSE 0 END) as other_count,
            AVG(word_count) as avg_words,
            SUM(CASE WHEN word_count < 5 AND pattern != 'continue' THEN 1 ELSE 0 END) as very_short
        FROM prompts
        WHERE timestamp >= CURRENT_DATE - {iv}
          AND pattern IS NOT NULL
    """).fetchone()

    total = row[0] or 1
    other_pct = (row[1] or 0) * 100 / total
    avg_words = row[2] or 0
    very_short = row[3] or 0

    if other_pct > 60:
        recs.append({
            "category": "prompt",
            "priority": "high" if other_pct > 75 else "medium",
            "title": "Use action verbs to start prompts",
            "description": f"{other_pct:.0f}% of prompts couldn't be classified into action "
                          f"patterns. Structured prompts help Claude act faster with fewer "
                          f"clarification turns.",
            "action": "Start prompts with verbs: fix, create, update, refactor, test, review, find.",
            "prompt": "Review my recent prompt history and suggest how I can make my prompts "
                      "more actionable. Show me examples of transforming vague prompts into "
                      "specific ones using the pattern: [verb] [what] in [where]. "
                      "For example: 'fix the login bug' -> 'fix the authentication timeout "
                      "in src/auth/login.py by increasing the session TTL'.",
            "impact": "Fewer clarification turns, faster task completion",
            "data": {"other_pct": round(other_pct, 1), "total_prompts": total,
                     "avg_words": round(float(avg_words), 1)},
        })

    if very_short > 10:
        recs.append({
            "category": "prompt",
            "priority": "medium",
            "title": "Add specificity to short prompts",
            "description": f"{very_short} prompts were under 5 words (excluding 'continue'/'yes'). "
                          f"Very short prompts often need follow-up clarification.",
            "action": "Include the target file, component, or expected outcome in prompts.",
            "prompt": "Review my CLAUDE.md and add a prompt best practices section: "
                      "'When requesting changes, specify: (1) the action verb, (2) the target "
                      "file or component, (3) the expected behavior. Example: instead of "
                      "'fix the bug', say 'fix the null pointer in src/api/handler.py "
                      "when user.email is missing'.'",
            "impact": "Fewer follow-up turns per task",
            "data": {"very_short_count": very_short, "total_prompts": total},
        })

    return recs


def _rec_tool_errors(conn, iv: str) -> list[dict]:
    """Recommend fixes for high-error-rate tools."""
    rows = conn.execute(f"""
        SELECT
            tool_name,
            COUNT(*) as total,
            SUM(CASE WHEN result_error THEN 1 ELSE 0 END) as errors,
            ROUND(SUM(CASE WHEN result_error THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) as err_pct
        FROM tool_calls
        WHERE timestamp >= CURRENT_DATE - {iv}
        GROUP BY tool_name
        HAVING errors > 5 AND err_pct > 8
        ORDER BY errors DESC
    """).fetchall()

    # Tool-specific advice
    tool_advice = {
        "Bash": ("Review common Bash failures (command not found, permission denied). "
                 "Add frequently used commands to CLAUDE.md.",
                 "Review my recent Bash tool errors and add a ## Common Commands section "
                 "to CLAUDE.md with correct syntax for commands that frequently fail. "
                 "Include environment setup steps if commands need specific PATH or venv."),
        "Edit": ("Edit failures usually mean old_string didn't match. "
                 "Always Read the target file first.",
                 "Add to CLAUDE.md: 'Before using the Edit tool, always Read the target file "
                 "first. Use at least 3 lines of surrounding context in old_string to ensure "
                 "a unique match. Never guess at file contents.'"),
        "Write": ("Write failures often mean the directory doesn't exist or permissions issues.",
                  "Add to CLAUDE.md: 'Before using Write, verify the parent directory exists "
                  "with ls. Never overwrite files without reading them first.'"),
        "Read": ("Read failures mean files don't exist at the expected path.",
                 "Add to CLAUDE.md: 'Use Glob to verify file paths before Reading. "
                 "Common project paths: [list your key directories here].'"),
        "Glob": ("Glob failures often mean wrong patterns or wrong directory.",
                 "Add to CLAUDE.md: 'Key file patterns for this project: "
                 "[list common glob patterns, e.g., src/**/*.py, tests/**/*.py].'"),
    }

    recs = []
    for row in rows:
        tool = row[0]
        advice = tool_advice.get(tool, (
            f"Review {tool} error patterns and add usage guidelines to CLAUDE.md.",
            f"Review my recent {tool} tool errors and add corrective rules to CLAUDE.md."))

        recs.append({
            "category": "tools",
            "priority": "medium" if row[3] < 15 else "high",
            "title": f"Reduce {tool} error rate ({row[3]}%)",
            "description": f"{tool}: {row[2]} errors out of {row[1]} calls ({row[3]}%). "
                          f"{advice[0]}",
            "action": f"Add {tool} usage guidelines to CLAUDE.md.",
            "prompt": advice[1],
            "impact": f"~{row[2] * 1500:,} tokens saved from avoided error/retry cycles",
            "data": {"tool": tool, "errors": row[2], "total": row[1],
                     "error_pct": float(row[3])},
        })

    return recs
