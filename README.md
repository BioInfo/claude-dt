# dt - Claude Code DevTools

> Actionable intelligence from your Claude Code sessions. Know what happened, learn what to improve.

Analyze your Claude Code session logs to uncover inefficiency patterns, optimize context usage, improve prompt effectiveness, and maintain healthy project configuration. All offline, all local, zero telemetry.

[![PyPI version](https://img.shields.io/pypi/v/claude-dt)](https://pypi.org/project/claude-dt/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](./LICENSE)
[![Status: Alpha](https://img.shields.io/badge/status-alpha-yellow)](#)

## Quick Start

Install from PyPI:

```bash
pip install claude-dt
```

Ingest your Claude Code session data into a local DuckDB:

```bash
dt ingest --since 7
```

Generate your first report:

```bash
dt report
```

That's it. Everything runs offline on your machine.

## Features

- **Session Ingestion** - Parse JSONL session logs from `~/.claude/projects/` into a fast DuckDB analytical database
- **5 Powerful Analyzers** - Context efficiency, tool usage, prompt quality, anti-pattern detection, project health
- **Composite Scoring** - Get a 0-100 score for each dimension plus an overall health metric
- **Trend Analysis** - Track metrics over time with period-over-period comparison and sparkline charts
- **Multiple Output Formats** - Rich terminal output (colored tables, panels), Markdown for docs, JSON for automation
- **Export Tools** - Export any table as CSV, JSON, or Parquet for external analysis
- **Smart Recommendations** - Prioritized, actionable suggestions with ready-to-paste prompts
- **Web Dashboard** - Interactive browser UI with scores, charts, filtering, and drill-down
- **Raw SQL Access** - Power users can query the DuckDB directly with `dt query`
- **Read-Only Analysis** - Never modifies Claude Code files or configuration
- **Zero Configuration** - Works out of the box with sensible defaults

## Sample Output

```
╭──────────────────────────── Scores ────────────────────────────╮
│  Overall: 70/100                                               │
│  Context: 59/100  Tools: 82/100  Prompts: 62/100  Health: 80/100 │
╰────────────────────────────────────────────────────────────────╯

╭──────────────────── Last 7 Days ──────────────╮
│  Sessions: 63                                  │
│  Messages: 13,391                              │
│  Tool calls: 4,731 (282 errors)                │
│  Tokens: 420,095 (cache efficiency: 100%)      │
│  Avg turns/session: 87.0                       │
│  Projects: 13                                  │
╰──────────────────────────────────────────────╯
```

## Installation

### From PyPI (recommended)

```bash
pip install claude-dt
dt ingest --since 7
dt report
```

### Development Installation

```bash
git clone https://github.com/BioInfo/claude-dt.git
cd claude-dt
python3 -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -e ".[dev]"
dt report
```

## Commands

### Core Commands

#### dt ingest

Parse Claude Code session JSONL files into DuckDB. Runs incrementally by default (skips already-ingested sessions).

```bash
dt ingest                    # Ingest all new sessions
dt ingest --since 7          # Ingest last 7 days only
dt ingest --since 30         # Ingest last 30 days
dt ingest --project myapp    # Filter to a specific project
dt ingest --reset            # Full reset: delete database and re-ingest everything
```

Options:
- `--since N` - Only ingest sessions from the last N days (faster for iteration)
- `--project NAME` - Filter to a specific project directory
- `--reset` - Delete the existing database and ingest from scratch

#### dt report

Generate a comprehensive insights report covering all dimensions. Default period is 7 days.

```bash
dt report                    # Last 7 days, terminal format
dt report --period 14        # Last 14 days
dt report --period 30        # Last 30 days
dt report --format json      # JSON output for scripting
dt report --format markdown  # Markdown for documentation
```

Options:
- `--period N` - Analyze the last N days (default: 7)
- `--format FORMAT` - Output format: `text` (default), `json`, or `markdown`

Output includes:
- Composite scores (context, tools, prompts, health, overall)
- Session overview and project statistics
- Model usage distribution
- Subagent routing patterns
- Context efficiency and cache hit rates
- Tool frequency and error rates
- Prompt patterns
- Anti-patterns detected

#### dt context

Analyze context usage patterns. Identifies duplicate file reads, hotspots, and inefficient access patterns.

```bash
dt context                   # Last 7 days
dt context --days 14         # Last 14 days
```

Shows:
- Files read multiple times within single sessions
- Most-accessed files (context hotspots)
- Duplicate read frequencies
- Sessions with high fragmentation

#### dt tools

Analyze tool usage distribution and error rates.

```bash
dt tools                     # Last 7 days
dt tools --days 30           # Last 30 days
```

Shows:
- Most and least used tools
- Tool error rates and failure types
- Subagent launches and model routing
- Tool chain patterns

#### dt prompts

Analyze prompt effectiveness and patterns.

```bash
dt prompts                   # Last 7 days
dt prompts --days 14         # Last 14 days
```

Shows:
- Prompt pattern distribution
- Average prompt length and word count
- Prompt effectiveness by project
- High-performing vs low-performing patterns

#### dt antipatterns

Detect known inefficiency anti-patterns.

```bash
dt antipatterns              # Last 7 days
dt antipatterns --days 30    # Last 30 days
```

Detects:
- Edit-retry cycles (failed edits that succeed after retry)
- High compaction rates (context overload)
- Duplicate file reads in single session (context forgot)
- Stale sessions without /clear
- Tool call immediately after identical tool call

#### dt trends

Show usage trends with period-over-period comparison.

```bash
dt trends                    # Compare last 7d vs previous 7d
dt trends --days 30          # Compare last 15d vs previous 15d
```

Shows:
- Metric trends (sessions, messages, tools, tokens, errors)
- Percentage change from previous period
- Daily sparkline charts
- Model shift analysis

#### dt health

Project configuration health check. Audits your CLAUDE.md and project setup.

```bash
dt health                    # Last 30 days
dt health --days 60          # Last 60 days
dt health --fix              # Generate CLAUDE.md suggestions
```

Shows:
- Files frequently re-read (CLAUDE.md candidates)
- Context fragmenters (large files causing repeated reads)
- Error-prone projects
- High-access projects

Use `--fix` to generate suggestions for improving your CLAUDE.md based on actual file access patterns.

#### dt recommend

Generate prioritized recommendations with ready-to-paste prompts.

```bash
dt recommend                         # Last 7 days, all categories
dt recommend --days 14               # Last 14 days
dt recommend --category context      # Only context-related recs
dt recommend --format json           # JSON output
dt recommend --format markdown       # Markdown output
```

Categories: `all`, `context`, `session`, `model`, `prompt`, `tools`

Each recommendation includes:
- Priority level (high, medium, low)
- Description of the issue
- Concrete action to take
- A prompt you can paste directly into Claude Code

#### dt serve

Start an interactive web dashboard in your browser.

```bash
dt serve                             # Start on http://localhost:8042
dt serve --port 9000                 # Custom port
dt serve --dev                       # API-only mode (for frontend development)
```

The dashboard provides:
- Score gauges for all four dimensions
- Interactive charts with zoom and filtering
- Sortable, paginated tables
- Recommendation cards with copy-to-clipboard prompts
- Session browser with detail drill-down
- Trend comparison with period switching

**Frontend development:** Run `dt serve --dev` for the API, then `cd web && npm run dev` for hot-reloading on port 5173.

#### dt session

View details of a single session or list recent sessions.

```bash
dt session list              # Show recent 20 sessions
dt session abc123            # Details for session starting with abc123 (partial match OK)
```

Shows:
- Session summary, duration, project
- Message count and turns
- Tool usage breakdown
- Model information
- Token consumption and cache efficiency
- Subagent count

#### dt status

Show database status: table counts, file size, last ingest time.

```bash
dt status
```

#### dt query

Run raw SQL queries against the DuckDB database. For power users.

```bash
dt query "SELECT * FROM sessions ORDER BY first_message_at DESC LIMIT 5"
dt query "SELECT tool_name, COUNT(*) FROM tool_calls GROUP BY tool_name"
```

Access to tables: `sessions`, `messages`, `tool_calls`, `subagents`, `file_access`, `prompts`, `daily_stats` and views: `session_efficiency`, `file_hotspots`.

#### dt export

Export a table as CSV, JSON, or Parquet.

```bash
dt export sessions                      # Export to dt-sessions.csv (default)
dt export sessions --format json        # Export as JSON
dt export sessions --format parquet     # Export as Parquet
dt export sessions -o output.csv        # Specify output file
dt export sessions --days 7             # Only last 7 days
```

## Analyzers

### 1. Context Efficiency

Detects wasteful context usage patterns and opportunities for optimization.

**Signals:**
- Duplicate file reads within a session (file read, context compacted, file read again)
- High compaction frequency indicating context window saturation
- Cache hit ratio (how effectively Claude Code leverages prompt caching)
- Large files read repeatedly (context hotspots)

**What it scores:**
- Repeat read frequency (lower is better)
- Cache efficiency ratio (higher is better)
- Compaction rate per hour (lower is better)
- File hotspot concentration

**Score 0-100:** Composite of all signals. 80+ is excellent, 60-80 is acceptable, below 60 needs improvement.

### 2. Tool Usage

Identifies tool usage patterns and failure modes.

**Signals:**
- Most and least used tools
- Tool error rates (timeout, not found, invalid input)
- Tool chains (what tools follow what tools)
- Subagent model selection effectiveness

**What it scores:**
- Error rate distribution (lower is better)
- Tool diversity (using the right tool for the job)
- Subagent routing efficiency
- Model selection for subagents

**Score 0-100:** Tools should have <5% error rate. Good subagent routing with appropriate model selection scores higher.

### 3. Prompt Quality

Measures how effectively your prompts convey intent and task specification.

**Signals:**
- Turns-to-completion (fewer turns = better prompt clarity)
- Clarification requests from Claude Code
- Prompt length vs outcome correlation
- Pattern effectiveness comparison

**What it scores:**
- Average turns per task (lower is better)
- Clarification frequency (lower is better)
- Prompt specificity signals (presence of file names, line numbers, etc.)
- Consistency of prompt structure

**Score 0-100:** Prompts that consistently complete in 1-2 turns score high. Prompts requiring 5+ turns for similar tasks score lower.

### 4. Anti-Pattern Detection

Flags known inefficiency patterns and behavioral anti-patterns.

**Patterns detected:**
- **Edit-retry cycle** - Edit fails multiple times on same file before succeeding (indicates wrong old_string)
- **Context overload** - 4+ compactions in a single session (context window saturation)
- **Duplicate reads** - Same file read multiple times in single session (context forgot)
- **Stale sessions** - Sessions running 2+ hours without /clear (context pollution)
- **Retry spam** - Identical tool call made twice in a row without change

**Impact:** Each pattern is scored by frequency and severity. Frequent patterns lower the health score.

### 5. Project Health

Audits your project configuration and CLAUDE.md effectiveness.

**Checks:**
- Directories with high access frequency but no CLAUDE.md (documentation gaps)
- CLAUDE.md files not updated recently (drift from current usage)
- Large files read repeatedly (should be in CLAUDE.md or split)
- Projects with high tool error rates (possible tool misconfiguration)
- Missing .claudeignore for generated directories

**Output:**
- CLAUDE.md candidates (files to document)
- Context fragmenters (files causing repeated reads)
- Error-prone projects (needs investigation)
- High-access projects (good automation candidates)

**Score 0-100:** Complete, up-to-date CLAUDE.md with all hotspots documented scores high. Missing documentation, stale config, and large fragmenters lower the score.

## Data Model

dt reads from Claude Code's session storage and creates a local DuckDB database for fast analysis.

### Source Data

Claude Code stores session data in `~/.claude/projects/<project-path>/`:

- `<session-id>.jsonl` - Session index with summary and message UUIDs
- `<session-id>/subagents/agent-<id>.jsonl` - Full subagent execution traces
- `<session-id>/tool-results/toolu_<id>.txt` - Large tool outputs stored separately

Additional sources:
- `~/.claude/stats-cache.json` - Aggregated daily statistics (model usage, session counts)
- `~/.claude/history.jsonl` - User prompt history with timestamps and project paths

### Database Location

dt creates and maintains a single DuckDB file:

```
~/.dt/dt.duckdb
```

All analysis runs locally against this file. Nothing is sent to the cloud.

### Core Tables

- `sessions` - Session metadata (project, duration, message counts, models)
- `messages` - All messages in all sessions (user, assistant, progress, summary)
- `tool_calls` - Tool invocations with inputs and error status
- `subagents` - Subagent launches with model selection and token usage
- `file_access` - File read/write/edit/glob operations with repeat detection
- `prompts` - User prompts with classification and word count
- `daily_stats` - Aggregated daily activity metrics

For full schema details, see the [PRD](./docs/PRD.md).

## Requirements

- **Python 3.10+** - dt requires modern Python
- **Claude Code** - Any version that generates session JSONL (v2.0+)
- **Disk space** - ~50MB per 1,000 sessions (DuckDB is highly compressed)

No API keys needed. No network access required. Fully offline.

## Design Principles

1. **Read-only by default** - dt never modifies Claude Code files, session logs, or configuration. It only reads and analyzes.
2. **Fast** - DuckDB provides sub-second analytical queries over thousands of sessions.
3. **Offline** - No API calls, no telemetry, no network access. Everything runs locally on your machine.
4. **Progressive** - Works with zero configuration. Power users can tune thresholds and run custom queries.
5. **Transparent** - Full SQL access via `dt query` means no black-box analysis.

## Troubleshooting

### DuckDB Lock Errors

DuckDB only allows one write connection at a time. If you see lock errors:

```bash
# Check for hanging processes
ps aux | grep python | grep dt

# Kill them
pkill -f "python.*dt"

# Remove lock files
rm -f ~/.dt/dt.duckdb.wal ~/.dt/dt.duckdb.lock
```

### No Data After Ingest

Make sure Claude Code is storing session data where dt expects it:

```bash
# Check if session files exist
ls -la ~/.claude/projects/ | head
```

If empty, you may not have any Claude Code sessions yet. Create a new Claude Code session to generate session data.

### Database Corruption

If the database becomes corrupted:

```bash
dt ingest --reset
```

This will delete the existing database and re-ingest all sessions from scratch (takes a few minutes for large histories).

## Contributing

dt is open-source. Contributions welcome:

- Report bugs and feature requests on GitHub
- Submit pull requests for bug fixes and new analyzers
- Suggest improvements to scoring algorithms
- Help with documentation and examples

See [CONTRIBUTING.md](./CONTRIBUTING.md) for development setup and guidelines.

## Performance Notes

### Ingest Time

- Full ingest of 1,400+ sessions from 3.9GB of JSONL takes ~10-15 minutes on M4 Mac
- Incremental ingest (last 7 days) typically completes in seconds
- Use `--since N` for fast iteration during development

### Query Speed

- All `dt` commands complete in <1 second (after initial database setup)
- DuckDB uses columnar compression, making analytical queries fast
- Database file size typically 50MB per 1,000 sessions

### Disk Usage

dt stores data efficiently:
- `~/.dt/dt.duckdb` - Compressed DuckDB file (50MB per 1,000 sessions)
- No temporary files or caching beyond the database
- Safe to delete and regenerate anytime

## Roadmap

### Phase 1: Foundation (v0.1) - COMPLETE
- JSONL session parser
- DuckDB schema and incremental ingestion
- `dt ingest`, `dt query`, `dt export` commands

### Phase 2: Core Analyzers (v0.2) - COMPLETE
- Context efficiency, tool usage, prompts, anti-patterns, health analyzers
- Composite scoring system
- `dt report` command

### Phase 3: Reports & Output (v0.3) - COMPLETE
- Rich terminal output (colors, tables, panels)
- Markdown and JSON output formats
- `dt session`, `dt trends`, `dt health` commands

### Phase 4: Tests & Documentation (v0.3) - COMPLETE
- 194 tests with full coverage
- Comprehensive README and contributing guide

### Phase 5: Recommendations (v0.3) - COMPLETE
- `dt recommend` with prioritized, actionable suggestions
- Ready-to-paste prompts for each recommendation
- Category filtering (context, session, model, prompt, tools)

### Phase 6: Web Dashboard (v0.4) - COMPLETE
- `dt serve` with FastAPI backend and React frontend
- Interactive charts (Recharts), sortable tables, pagination
- Score gauges, trend comparison, session browser
- Recommendation cards with copy-to-clipboard

### Phase 7: Community & Extensions (v0.5+)
- PyPI package distribution
- CI/CD and cross-platform testing
- Hook integration for live insights during sessions
- Custom analyzer plugin system

## Related Tools

dt complements other Claude Code analysis tools:

| Tool | Purpose | Relationship |
|------|---------|--------------|
| [ccusage](https://github.com/ryoppippi/ccusage) | Token and cost tracking | dt adds pattern detection and recommendations on top |
| [claude-devtools](https://github.com/matt1398/claude-devtools) | Real-time context visualization | Complements dt's historical analysis |
| [claude-code-otel](https://github.com/ColeMurray/claude-code-otel) | Prometheus/Grafana observability | dt provides similar insights without infrastructure |

## License

MIT - See [LICENSE](./LICENSE)

## Support

- **Documentation** - See [docs/PRD.md](./docs/PRD.md) for detailed design and architecture
- **Issues** - Report bugs and request features on GitHub
- **Questions** - Open a discussion on GitHub

---

Made with care for Claude Code users who want to understand and optimize their workflow.
