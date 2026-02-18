# dt - Claude Code DevTools

> Actionable feedback from your Claude Code sessions. Know what happened, learn what to improve.

## Problem

Claude Code generates rich session logs, but nobody looks at them. The data sits in `~/.claude/projects/` as raw JSONL, invisible to the developer. Meanwhile:

- **Context drift is a silent killer.** Your CLAUDE.md files go stale, skills stop matching your workflow, and you don't notice until sessions start taking 2x the turns they should.
- **Token waste is invisible.** Duplicate file reads, unnecessary compactions, subagent model mis-routing -- these cost real money on pay-per-token plans and burn rate limits on subscriptions.
- **No feedback loop exists.** You can bootstrap a CLAUDE.md in minutes. Maintaining it based on actual usage patterns? Nobody has tooling for that.

The v2.1.20 crisis (collapsed file details, developer revolt on GitHub/HN) proved that developers need visibility into what Claude Code is actually doing. But visibility alone isn't enough. You need actionable insights that close the loop.

## Solution

`dt` is an open-source CLI that reads Claude Code session logs and produces actionable insights about your usage patterns, prompt effectiveness, context efficiency, and project configuration health.

```
$ dt ingest          # Parse session JSONL into DuckDB
$ dt report          # Weekly insights report
$ dt session <id>    # Analyze a single session
$ dt health          # CLAUDE.md and project config audit
$ dt trends          # Usage trends over time
```

## Design Principles

1. **Read-only by default.** dt never modifies Claude Code files, session logs, or configuration. It only reads and analyzes.
2. **Fast.** DuckDB as the analytical engine. Sub-second queries over thousands of sessions.
3. **Offline.** No API calls, no telemetry, no network access. Everything runs locally on your machine.
4. **Progressive.** Works with zero configuration. Power users can tune analyzers and thresholds.
5. **Community-first.** Core features work for any Claude Code user. Advanced integrations are opt-in extensions.

## Prior Art & Inspiration

dt builds on and is inspired by these open-source tools:

| Tool | What It Does | How dt Relates |
|------|-------------|----------------|
| [ccusage](https://github.com/ryoppippi/ccusage) | Token/cost analytics from session JSONL | dt ingests similar data but adds pattern detection and actionable recommendations on top of raw metrics |
| [claude-devtools](https://github.com/matt1398/claude-devtools) | Context reconstruction, compaction visualization, tool trace | dt complements this -- claude-devtools shows what happened in real-time; dt analyzes patterns across sessions |
| [claude-code-otel](https://github.com/ColeMurray/claude-code-otel) | Prometheus/Grafana observability stack | dt provides similar insights without requiring Docker/Grafana infrastructure |
| [Context-Evaluator](https://packmind.com/evaluate-context-ai-coding-agent/) | CLAUDE.md drift and quality detection | dt includes a health checker inspired by this approach, extended with usage-based recommendations |
| [claude-code-tools](https://github.com/pchalasani/claude-code-tools) | Session search, cross-agent handoffs | dt's session analysis complements session-recall/search tools |
| [Claude-Code-Usage-Monitor](https://github.com/Maciek-roboblog/Claude-Code-Usage-Monitor) | Rich TUI dashboard with ML predictions | dt focuses on actionable insights rather than live monitoring |

## Data Model

### Source Data

Claude Code stores session data in `~/.claude/projects/<project-path>/`:

- `<session-id>.jsonl` -- Summary index with session titles and leaf UUIDs
- `<session-id>/` directory containing:
  - `subagents/agent-<id>.jsonl` -- Full subagent execution traces
  - `tool-results/toolu_<id>.txt` -- Large tool outputs stored separately

Each JSONL line is a message event with:
- `type`: `user`, `assistant`, `summary`, `progress`
- `message.role`: `user` or `assistant`
- `message.content[]`: Text blocks, tool_use blocks, tool_result blocks
- `message.usage`: Token counts (input, output, cache_read, cache_creation)
- `sessionId`, `timestamp`, `agentId`, `cwd`, `version`

Additional sources:
- `~/.claude/stats-cache.json` -- Aggregated daily activity, model usage, session counts
- `~/.claude/history.jsonl` -- User prompt history with timestamps and project paths

### DuckDB Schema

```sql
-- Core tables
CREATE TABLE sessions (
    session_id VARCHAR PRIMARY KEY,
    project VARCHAR NOT NULL,           -- e.g. "-Users-username-apps-myproject"
    started_at TIMESTAMP,
    ended_at TIMESTAMP,
    duration_ms BIGINT,
    total_turns INTEGER,                -- user message count
    total_messages INTEGER,             -- all messages
    compaction_count INTEGER DEFAULT 0,
    claude_version VARCHAR,
    primary_model VARCHAR               -- most-used model in session
);

CREATE TABLE messages (
    uuid VARCHAR PRIMARY KEY,
    session_id VARCHAR NOT NULL,
    parent_uuid VARCHAR,
    timestamp TIMESTAMP NOT NULL,
    type VARCHAR NOT NULL,              -- 'user', 'assistant', 'progress', 'summary'
    role VARCHAR,                       -- 'user', 'assistant'
    model VARCHAR,                      -- e.g. 'claude-opus-4-6'
    agent_id VARCHAR,                   -- null for main agent, 'a1f8246' for subagents
    is_subagent BOOLEAN DEFAULT FALSE,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cache_read_tokens INTEGER DEFAULT 0,
    cache_creation_tokens INTEGER DEFAULT 0,
    content_text TEXT,                  -- concatenated text content
    has_tool_use BOOLEAN DEFAULT FALSE,
    has_tool_result BOOLEAN DEFAULT FALSE
);

CREATE TABLE tool_calls (
    tool_use_id VARCHAR PRIMARY KEY,
    session_id VARCHAR NOT NULL,
    message_uuid VARCHAR NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    tool_name VARCHAR NOT NULL,         -- 'Read', 'Edit', 'Bash', 'Grep', etc.
    input_summary TEXT,                 -- condensed input (file path, command, pattern)
    is_error BOOLEAN DEFAULT FALSE,
    error_message TEXT,
    agent_id VARCHAR,                   -- which agent made the call
    -- Extracted fields for common tools
    file_path VARCHAR,                  -- for Read, Edit, Write, Glob
    bash_command VARCHAR,               -- for Bash
    grep_pattern VARCHAR,               -- for Grep
    subagent_type VARCHAR,              -- for Task tool
    subagent_model VARCHAR              -- for Task tool
);

CREATE TABLE file_access (
    id INTEGER PRIMARY KEY,
    session_id VARCHAR NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    file_path VARCHAR NOT NULL,
    operation VARCHAR NOT NULL,         -- 'read', 'edit', 'write', 'glob', 'grep'
    agent_id VARCHAR,
    is_repeat_in_session BOOLEAN DEFAULT FALSE,  -- read same file again
    access_number INTEGER DEFAULT 1     -- nth access of this file in session
);

CREATE TABLE daily_stats (
    date DATE PRIMARY KEY,
    message_count INTEGER,
    session_count INTEGER,
    tool_call_count INTEGER,
    tokens_by_model JSON                -- {"claude-opus-4-6": 12345, ...}
);

-- Views for common queries
CREATE VIEW session_efficiency AS
SELECT
    s.session_id,
    s.project,
    s.total_turns,
    s.compaction_count,
    s.duration_ms,
    COUNT(DISTINCT tc.tool_use_id) as tool_calls,
    COUNT(DISTINCT CASE WHEN tc.is_error THEN tc.tool_use_id END) as failed_tool_calls,
    COUNT(DISTINCT CASE WHEN fa.is_repeat_in_session THEN fa.id END) as duplicate_reads,
    SUM(m.input_tokens) as total_input_tokens,
    SUM(m.output_tokens) as total_output_tokens,
    SUM(m.cache_read_tokens) as total_cache_reads
FROM sessions s
LEFT JOIN messages m ON m.session_id = s.session_id
LEFT JOIN tool_calls tc ON tc.session_id = s.session_id
LEFT JOIN file_access fa ON fa.session_id = s.session_id
GROUP BY s.session_id, s.project, s.total_turns, s.compaction_count, s.duration_ms;

CREATE VIEW file_hotspots AS
SELECT
    file_path,
    COUNT(DISTINCT session_id) as sessions_accessed,
    COUNT(*) as total_accesses,
    COUNT(DISTINCT CASE WHEN operation = 'read' THEN id END) as reads,
    COUNT(DISTINCT CASE WHEN operation = 'edit' THEN id END) as edits,
    COUNT(DISTINCT CASE WHEN is_repeat_in_session THEN id END) as duplicate_reads
FROM file_access
GROUP BY file_path
ORDER BY total_accesses DESC;
```

## Analyzers

Each analyzer is a standalone module that queries DuckDB and produces structured findings.

### 1. Context Efficiency Analyzer

Detects wasteful context usage patterns.

**Signals:**
- Duplicate file reads within a session (file read, context compacted, file read again)
- High compaction frequency (>2 compactions per 30-minute window)
- Low cache hit ratio (cache_read_tokens / total_input_tokens < threshold)
- Large file reads that dominate context (>500 lines read repeatedly)

**Output:**
```
Context Efficiency: 72/100

Duplicate Reads (last 7 days):
  src/api/routes.ts: read 3x in session abc123 (compaction between reads)
  CLAUDE.md: read 5x across 3 sessions (already in system prompt)

Compaction Hotspots:
  Session abc123: 4 compactions in 28 min (avg: 1.5)
  Session def456: 3 compactions in 15 min (avg: 1.5)

Cache Efficiency: 89% (good, above 80% threshold)
  Trend: +3% vs last week
```

### 2. Prompt Quality Analyzer

Measures how effective your prompts are at conveying intent.

**Signals:**
- Turns-to-completion for tasks (fewer = better)
- Clarification requests (assistant asks a question before acting)
- Prompt length vs outcome correlation
- Patterns in high-performing vs low-performing prompts

**Output:**
```
Prompt Effectiveness: 78/100

High-Performing Patterns (1-2 turns to completion):
  "Fix [specific thing] in [file]" -- 92% success rate
  "Add [feature] to [component]"   -- 87% success rate

Improvement Opportunities:
  3 prompts required 5+ turns (avg for similar tasks: 2)
  Pattern: Prompts lacking file/component specificity

  Example: "Update the API" -> 3 clarification turns
  Suggested: "Add rate limiting to POST /api/users endpoint"
```

### 3. Tool Usage Analyzer

Identifies tool usage patterns and failures.

**Signals:**
- Most/least used tools
- Tool error rates (failed grep patterns, bad edit old_string matches)
- Tool chains (what tools follow what tools)
- Subagent usage: model selection, success rates, token cost

**Output:**
```
Tool Distribution (last 7 days):
  Read: 234 calls (31%)
  Bash: 189 calls (25%)
  Edit: 98 calls (13%)
  Grep: 87 calls (12%)
  ...

Tool Failures: 12 (1.6% error rate)
  Edit: 6 failures (old_string not found)
  Grep: 4 failures (timeout or no match)
  Bash: 2 failures (command not found)

Subagent Routing:
  haiku: 45 calls (exploration, search)
  sonnet: 23 calls (code writing)
  opus: 3 calls (architecture)
```

### 4. Anti-Pattern Detector

Flags known inefficiency patterns.

**Patterns detected:**
- Repeated file reads in single session (context forgot the file)
- High compaction rate (overloading context window)
- Edit-fail-retry cycles (wrong old_string, retry with different text)
- Overly long sessions without /clear (context pollution)
- Tool call immediately after identical tool call (retry without change)

**Output:**
```
Anti-Patterns (last 7 days): 8 detected

HIGH: Edit-Retry Cycle (3 occurrences)
  Session abc123: Edit failed 3x on same file before succeeding
  Impact: ~2K tokens wasted per cycle
  Fix: Read the file first; use unique old_string with more context

MEDIUM: Context Overload (2 occurrences)
  Sessions with 4+ compactions
  Fix: Break large tasks into smaller sessions; use /clear between subtasks

LOW: Stale Session (3 occurrences)
  Sessions running 2+ hours without /clear
  Fix: Start fresh sessions for new task domains
```

### 5. Project Health Checker

Audits your project configuration for Claude Code effectiveness.

**Checks:**
- Directories with high access frequency but no CLAUDE.md
- CLAUDE.md files that haven't been updated recently
- Skills that never activate (dead weight)
- Missing .claudeignore for large generated directories
- Large files that repeatedly fragment context

**Output:**
```
Project Health: src/api/

Missing Documentation:
  src/api/routes/ -- 23 file reads across 8 sessions, no CLAUDE.md
  Suggestion: Create CLAUDE.md documenting route patterns and conventions

Stale Configuration:
  CLAUDE.md last updated 45 days ago, 12 sessions since
  Suggestion: Review and update based on recent session patterns

Context Fragmenters:
  src/lib/config.ts: 2,400 lines, read 7 times
  Suggestion: Split into focused modules or add to CLAUDE.md summary
```

## CLI Interface

```
dt - Claude Code DevTools

USAGE:
    dt <command> [options]

COMMANDS:
    ingest              Parse session JSONL into DuckDB
    report              Generate insights report (default: last 7 days)
    session <id>        Analyze a single session
    health [path]       Project configuration health check
    trends              Usage trends over time
    query <sql>         Run raw SQL against the database
    export              Export data as CSV/JSON
    version             Show version info

INGEST OPTIONS:
    --full              Re-ingest all sessions (default: incremental)
    --project <path>    Only ingest sessions for a specific project
    --since <date>      Only ingest sessions after date

REPORT OPTIONS:
    --period <days>     Analysis period (default: 7)
    --format <fmt>      Output format: text, markdown, json (default: text)
    --analyzer <name>   Run specific analyzer only
    --project <path>    Filter to specific project

TRENDS OPTIONS:
    --period <days>     Trend period (default: 30)
    --metric <name>     Specific metric: tokens, sessions, tools, efficiency
    --format <fmt>      Output format: text, markdown, json, csv

HEALTH OPTIONS:
    --path <dir>        Check specific project directory
    --fix               Generate suggested CLAUDE.md content (to stdout)
```

## Architecture

```
dt/
├── src/
│   └── dt/
│       ├── __init__.py
│       ├── cli.py              # Click CLI entry point
│       ├── config.py           # Configuration and defaults
│       ├── db.py               # DuckDB connection and schema management
│       ├── ingest/
│       │   ├── __init__.py
│       │   ├── parser.py       # JSONL session parser
│       │   ├── stats.py        # stats-cache.json ingestion
│       │   └── history.py      # history.jsonl ingestion
│       ├── analyzers/
│       │   ├── __init__.py
│       │   ├── base.py         # Analyzer base class and scoring
│       │   ├── context.py      # Context efficiency analyzer
│       │   ├── prompts.py      # Prompt quality analyzer
│       │   ├── tools.py        # Tool usage analyzer
│       │   ├── antipatterns.py # Anti-pattern detector
│       │   └── health.py       # Project health checker
│       ├── reports/
│       │   ├── __init__.py
│       │   ├── weekly.py       # Weekly report generator
│       │   ├── session.py      # Single session analysis
│       │   └── trends.py       # Trend visualization (sparklines)
│       └── formatters/
│           ├── __init__.py
│           ├── text.py         # Terminal output (Rich)
│           ├── markdown.py     # Markdown output
│           └── json.py         # JSON output
├── tests/
│   ├── fixtures/               # Sample JSONL data for testing
│   ├── test_parser.py
│   ├── test_analyzers.py
│   └── test_reports.py
├── docs/
│   ├── PRD.md                  # This file
│   └── ROADMAP.md
├── pyproject.toml
├── CLAUDE.md
├── LICENSE                     # MIT
└── README.md
```

### Why DuckDB?

The analytical workload here is a perfect fit for DuckDB:

- **Native JSONL reading** -- Can query JSONL files directly during development, then persist to tables for production
- **Columnar storage** -- Aggregations across 1000+ sessions are sub-second
- **Zero infrastructure** -- Single file database, no server process
- **SQL interface** -- Power users can run raw queries with `dt query`
- **Parquet export** -- Easy to share anonymized datasets

Alternatives considered:
- SQLite: Great for transactional workloads, slower for analytical queries over wide tables
- Polars: Fast for DataFrames, but no persistent storage; every analysis starts from scratch
- ClickHouse: Overkill for local single-user analytics

## Roadmap

### Phase 1: Foundation (v0.1)

Core ingestion and basic analytics. Get data flowing into DuckDB.

- [ ] JSONL session parser (messages, tool calls, file access)
- [ ] stats-cache.json ingestion
- [ ] history.jsonl ingestion
- [ ] DuckDB schema creation and migration
- [ ] Incremental ingestion (track last-ingested timestamp)
- [ ] `dt ingest` command
- [ ] `dt query` command (raw SQL access)
- [ ] `dt export` command (CSV/JSON)
- [ ] Basic test suite with fixture data

### Phase 2: Core Analyzers (v0.2)

The five analyzers that produce actionable insights.

- [ ] Context efficiency analyzer (duplicate reads, compaction rate, cache ratio)
- [ ] Tool usage analyzer (frequency, errors, chains)
- [ ] Anti-pattern detector (edit-retry cycles, stale sessions, context overload)
- [ ] Project health checker (missing CLAUDE.md, large files, stale configs)
- [ ] Prompt quality analyzer (turns-to-completion, clarification detection)
- [ ] Scoring system (0-100 per analyzer, weighted composite)
- [ ] `dt report` command with all analyzers

### Phase 3: Reports & Output (v0.3)

Polished output formats and trend analysis.

- [ ] Rich terminal output (colors, tables, sparklines)
- [ ] Markdown output for documentation/wikis
- [ ] JSON output for programmatic consumption
- [ ] `dt session <id>` single-session deep dive
- [ ] `dt trends` with period comparison (this week vs last week)
- [ ] `dt health` with `--fix` to generate CLAUDE.md suggestions

### Phase 4: Community & Distribution (v0.4)

Package for public release.

- [ ] PyPI package (`pip install claude-dt`)
- [ ] Comprehensive README with screenshots/examples
- [ ] Sample output from anonymized sessions
- [ ] Contributing guide
- [ ] CI/CD (GitHub Actions)
- [ ] Cross-platform testing (macOS, Linux)
- [ ] Windows support for Claude Code on WSL

### Phase 5: Extensions (v0.5+)

Advanced features for power users. Opt-in, not required.

- [ ] Hook integration: `SessionStart` hook that injects top insight
- [ ] Hook integration: `PostToolUse` hook for live duplicate-read warnings
- [ ] Skill effectiveness scoring (activation frequency vs success rate)
- [ ] CLAUDE.md auto-generation from file access patterns
- [ ] Subagent model routing recommendations
- [ ] Custom analyzer plugin system
- [ ] Obsidian integration (weekly digest as vault note)
- [ ] Integration with ccusage for cost data enrichment
- [ ] Integration with claude-devtools for context reconstruction data
- [ ] Prompt pattern library (mine your most effective prompt structures)

### Future: Power-User Extensions

Features specific to advanced setups (multi-machine, large skill libraries, agent orchestration).

- [ ] Multi-project dashboard (compare efficiency across repos)
- [ ] Skill tuning signals (which skills need prompt rewriting)
- [ ] Cross-machine session correlation (SSH remote sessions)
- [ ] Agent orchestration analytics (subagent spawn patterns, model routing)
- [ ] Cost attribution per project/skill
- [ ] Improvement tracking over time (are your scores getting better?)
- [ ] Team/org rollup for shared repos
- [ ] MCP server health correlation (which MCP servers cause slowdowns)
- [ ] Session-to-git-commit attribution (which sessions produced commits)
- [ ] Blog-ready export (anonymized insights for sharing)

## Configuration

`dt` uses a simple TOML config file at `~/.config/dt/config.toml`:

```toml
[database]
path = "~/.config/dt/dt.duckdb"     # DuckDB file location

[sources]
claude_dir = "~/.claude"             # Claude Code data directory
# Supports multiple project paths
# projects = ["~/.claude/projects/-Users-me-app1", "~/.claude/projects/-Users-me-app2"]

[analyzers]
# Thresholds for analyzer scoring
compaction_warn = 2                  # compactions per 30 min
compaction_critical = 4
duplicate_read_warn = 2              # same file reads in session
cache_ratio_good = 0.80              # cache_read / total_input
session_stale_hours = 2              # hours before "stale session" warning

[report]
default_period_days = 7
format = "text"                      # text, markdown, json

[output]
color = true                         # terminal colors
sparklines = true                    # trend sparklines in text output
```

## Success Metrics

How we know dt is working:

1. **Time to first insight**: Under 60 seconds from install to seeing actionable data
2. **Accuracy**: Analyzers flag real issues, not noise (track false positive rate via community feedback)
3. **Adoption**: Users report changing behavior based on dt output
4. **Community**: Contributors add custom analyzers

## Non-Goals

- dt is NOT a real-time monitor (use claude-devtools or Claude-Code-Usage-Monitor)
- dt does NOT modify Claude Code configuration (it suggests; you decide)
- dt does NOT send data anywhere (fully offline)
- dt does NOT replace ccusage for cost tracking (it adds insight on top)
- dt does NOT require Claude Code to be running (analyzes historical data)

## Target Users

1. **Solo developers** using Claude Code daily who want to optimize their workflow
2. **Power users** with custom skills/agents/hooks who want tuning signals
3. **Team leads** evaluating Claude Code adoption and identifying training needs
4. **Open-source contributors** building Claude Code tooling
