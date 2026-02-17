# CLAUDE.md - dt (Claude Code DevTools)

## Project

Open-source CLI that analyzes Claude Code session logs and produces actionable insights.
GitHub target: `claude-dt` on PyPI.

## Stack

- Python 3.10+, Click CLI, DuckDB (analytical DB), Rich (terminal output)
- Source layout: `src/dt/` (flat modules, no subpackages)
- Venv: `.venv/` managed by `uv`
- DB location: `~/.dt/dt.duckdb`

## Key Files

- `src/dt/cli.py` -- CLI entry point (group = `cli`)
- `src/dt/db.py` -- DuckDB schema, `get_connection()`, `init_db()`, `reset_db()`
- `src/dt/ingest.py` -- JSONL session parser + ingestion pipeline
- `src/dt/analyzers.py` -- All analyzers: context, tools, prompts, antipatterns, generate_report
- `src/dt/config.py` -- Paths: PROJECTS_DIR, STATS_CACHE, HISTORY_FILE, DB_PATH
- `docs/PRD.md` -- Full product requirements and roadmap

## Data Sources

Claude Code stores session data in `~/.claude/projects/<project-path>/`:
- `<session-id>.jsonl` -- Summary lines (type: summary)
- `<session-id>/subagents/agent-<id>.jsonl` -- Subagent traces
- `<session-id>/tool-results/toolu_<id>.txt` -- Large tool outputs
- `~/.claude/stats-cache.json` -- Aggregated daily stats
- `~/.claude/history.jsonl` -- User prompt history

## Commands

```bash
source .venv/bin/activate
dt ingest --since 14        # Ingest last 14 days
dt ingest --reset           # Full reset + ingest
dt report --period 7        # Weekly report
dt report --format json     # JSON output
dt status                   # DB table counts
dt context --days 7         # Context efficiency analysis
dt tools --days 7           # Tool usage analysis
dt antipatterns --days 7    # Anti-pattern detection
dt prompts --days 7         # Prompt pattern analysis
dt session list             # Recent sessions
dt session <id>             # Session detail
dt query "SELECT ..."       # Raw SQL
```

## DuckDB Lock Issue

DuckDB only allows one write connection at a time. If `dt` commands fail with lock errors:
1. Check for zombie processes: `ps aux | grep python | grep dt`
2. Kill them: `kill <PID>`
3. The `ingest.py` uses try/finally to ensure conn.close()

## Schema (key tables)

- sessions: session_id, project_name, message_count, tool_call_count, models_used, tokens
- messages: uuid, session_id, role, model, tokens, content_text, turn_number
- tool_calls: tool_use_id, session_id, tool_name, input_summary, result_error, file_path
- subagents: agent_id, session_id, agent_type, model, message_count, total_tokens
- file_access: session_id, file_path, access_type, is_repeat, repeat_count
- prompts: text, word_count, project_path, pattern (classified)
- daily_stats: date, message_count, session_count, tool_call_count

## DuckDB Note

DuckDB does NOT support `?` placeholder in INTERVAL expressions.
Use f-strings: `CURRENT_DATE - INTERVAL '{days}' DAY` (safe when days is validated int from Click).
