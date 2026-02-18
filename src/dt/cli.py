"""CLI for dt - Claude Code DevTools."""
import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
from rich.text import Text

console = Console()


@click.group()
@click.version_option(version="0.3.0")
def cli():
    """dt - Claude Code DevTools. Actionable intelligence from session data."""
    pass


@cli.command()
@click.option("--since", type=int, help="Only ingest sessions from last N days")
@click.option("--project", type=str, help="Filter to specific project name")
@click.option("--reset", is_flag=True, help="Reset database before ingesting")
def ingest(since, project, reset):
    """Ingest Claude Code session data into DuckDB."""
    from .ingest import run_ingest

    result = run_ingest(since_days=since, project_filter=project, reset=reset)
    if result:
        console.print()
        table = Table(title="Ingest Complete", show_header=False, border_style="green")
        table.add_column("Metric", style="bold")
        table.add_column("Value", justify="right")
        table.add_row("Sessions parsed", f"{result['sessions']:,}")
        table.add_row("Messages", f"{result['messages']:,}")
        table.add_row("Tool calls", f"{result['tool_calls']:,}")
        table.add_row("Files processed", f"{result['files_processed']:,}")
        if result['skipped']:
            table.add_row("Skipped (outside range)", f"{result['skipped']:,}")
        console.print(table)


@cli.command()
def status():
    """Show database status and stats."""
    from .db import get_connection, DB_PATH

    if not DB_PATH.exists():
        console.print("[red]No database found. Run 'dt ingest' first.[/red]")
        return

    conn = get_connection(read_only=True)

    table = Table(title="dt Database Status", show_header=False, border_style="blue")
    table.add_column("", style="bold")
    table.add_column("", justify="right")

    # Table counts
    for tbl in ["sessions", "messages", "tool_calls", "subagents", "file_access", "prompts", "daily_stats"]:
        count = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        table.add_row(tbl, f"{count:,}")

    # DB file size
    import os
    size_mb = os.path.getsize(DB_PATH) / (1024 * 1024)
    table.add_row("Database size", f"{size_mb:.1f} MB")

    # Last ingest
    last = conn.execute("SELECT value FROM meta WHERE key = 'last_ingest'").fetchone()
    if last:
        table.add_row("Last ingest", last[0][:19])

    conn.close()
    console.print(table)


@cli.command()
@click.option("--period", type=int, default=7, help="Number of days to analyze (default: 7)")
@click.option("--project", type=str, help="Filter to specific project")
@click.option("--format", "fmt", type=click.Choice(["text", "json", "markdown"]), default="text")
def report(period, project, fmt):
    """Generate a comprehensive report."""
    from .analyzers import generate_report, generate_markdown_report
    import json

    if fmt == "markdown":
        md = generate_markdown_report(days=period)
        console.print(md)
        return

    data = generate_report(days=period)

    if fmt == "json":
        # Convert tuples to serializable format
        def serialize(obj):
            if isinstance(obj, tuple):
                return list(obj)
            if hasattr(obj, 'isoformat'):
                return obj.isoformat()
            return str(obj)
        console.print(json.dumps(data, default=serialize, indent=2))
        return

    # Scores panel
    scores = data.get("scores", {})
    if scores:
        score_text = Text()
        composite = scores.get("composite", 0)
        comp_style = "green bold" if composite >= 80 else ("yellow bold" if composite >= 60 else "red bold")
        score_text.append(f"  Overall: ", style="bold")
        score_text.append(f"{composite}/100\n", style=comp_style)
        for key, label in [("context", "Context"), ("tools", "Tools"), ("prompts", "Prompts"), ("health", "Health")]:
            s = scores.get(key, 0)
            style = "green" if s >= 80 else ("yellow" if s >= 60 else "red")
            score_text.append(f"  {label}: ")
            score_text.append(f"{s}/100", style=style)
            score_text.append("  ")
        console.print(Panel(score_text, title="Scores", border_style="magenta"))

    # Overview panel
    ov = data["overview"]
    if ov:
        overview_text = Text()
        overview_text.append(f"  Sessions: {ov[0] or 0:,}\n", style="bold")
        overview_text.append(f"  Messages: {ov[1] or 0:,}\n")
        overview_text.append(f"  Tool calls: {ov[2] or 0:,}")
        if ov[3]:
            overview_text.append(f" ({ov[3]:,} errors)\n", style="red")
        else:
            overview_text.append("\n")
        tokens = ov[4] or 0
        cache = ov[5] or 0
        overview_text.append(f"  Tokens: {tokens:,}")
        if cache > 0 and tokens > 0:
            eff = cache * 100 / (cache + tokens)
            overview_text.append(f" (cache efficiency: {eff:.0f}%)\n", style="green")
        else:
            overview_text.append("\n")
        overview_text.append(f"  Avg turns/session: {ov[6] or 0:.1f}\n")
        overview_text.append(f"  Projects: {ov[7] or 0}")
        console.print(Panel(overview_text, title=f"Last {period} Days", border_style="blue"))

    # Model usage
    if data["model_usage"]:
        mt = Table(title="Model Usage", border_style="dim")
        mt.add_column("Model")
        mt.add_column("Messages", justify="right")
        mt.add_column("Tokens", justify="right")
        mt.add_column("Cache Reads", justify="right")
        for row in data["model_usage"]:
            model_short = row[0].replace("claude-", "").replace("-20251001", "").replace("-20250929", "").replace("-20251101", "")
            mt.add_row(model_short, f"{row[1]:,}", f"{row[2] or 0:,}", f"{row[3] or 0:,}")
        console.print(mt)

    # Subagent model usage
    if data.get("subagent_model_usage"):
        smt = Table(title="Subagent Model Usage", border_style="cyan")
        smt.add_column("Model")
        smt.add_column("Launches", justify="right")
        smt.add_column("Messages", justify="right")
        smt.add_column("Tokens", justify="right")
        smt.add_column("Tools", justify="right")
        smt.add_column("Avg Msgs", justify="right")
        for row in data["subagent_model_usage"]:
            model_short = row[0].replace("claude-", "").replace("-20251001", "").replace("-20250929", "").replace("-20251101", "")
            smt.add_row(model_short, f"{row[1]:,}", f"{row[2] or 0:,}", f"{row[3] or 0:,}", f"{row[4] or 0:,}", f"{row[5] or 0:.0f}")
        console.print(smt)

    # Top projects
    if data["top_projects"]:
        pt = Table(title="Top Projects", border_style="dim")
        pt.add_column("Project")
        pt.add_column("Sessions", justify="right")
        pt.add_column("Messages", justify="right")
        pt.add_column("Tools", justify="right")
        for row in data["top_projects"]:
            pt.add_row(row[0], f"{row[1]:,}", f"{row[2]:,}", f"{row[3]:,}")
        console.print(pt)

    # Context hotspots
    ctx = data.get("context", {})
    if ctx.get("hotspot_files"):
        ht = Table(title="Context Hotspots (Most-Read Files)", border_style="yellow")
        ht.add_column("File")
        ht.add_column("Reads", justify="right")
        ht.add_column("Sessions", justify="right")
        for row in ctx["hotspot_files"][:10]:
            ht.add_row(str(row[0])[-60:], f"{row[1]:,}", f"{row[2]:,}")
        console.print(ht)

    # Cache efficiency
    if ctx.get("cache_efficiency"):
        ct = Table(title="Cache Efficiency by Model", border_style="green")
        ct.add_column("Model")
        ct.add_column("Cache Reads", justify="right")
        ct.add_column("Direct Input", justify="right")
        ct.add_column("Efficiency", justify="right")
        for row in ctx["cache_efficiency"]:
            model_short = row[0].replace("claude-", "").replace("-20251001", "").replace("-20250929", "").replace("-20251101", "")
            style = "green" if (row[4] or 0) > 90 else ("yellow" if (row[4] or 0) > 70 else "red")
            ct.add_row(model_short, f"{row[1] or 0:,}", f"{row[2] or 0:,}", f"[{style}]{row[4] or 0}%[/{style}]")
        console.print(ct)

    # Tool usage
    tools = data.get("tools", {})
    if tools.get("tool_frequency"):
        tt = Table(title="Tool Usage", border_style="dim")
        tt.add_column("Tool")
        tt.add_column("Calls", justify="right")
        tt.add_column("Errors", justify="right")
        tt.add_column("Error %", justify="right")
        for row in tools["tool_frequency"][:15]:
            err_style = "red" if (row[3] or 0) > 10 else "dim"
            tt.add_row(row[0], f"{row[1]:,}", f"{row[2]:,}", f"[{err_style}]{row[3] or 0}%[/{err_style}]")
        console.print(tt)

    # Subagent stats
    if tools.get("subagent_stats"):
        st = Table(title="Subagent Usage", border_style="dim")
        st.add_column("Agent Type")
        st.add_column("Model")
        st.add_column("Launches", justify="right")
        st.add_column("Avg Msgs", justify="right")
        st.add_column("Total Tokens", justify="right")
        for row in tools["subagent_stats"]:
            model_short = (row[1] or "?").replace("claude-", "").replace("-20251001", "").replace("-20250929", "").replace("-20251101", "")
            st.add_row(row[0] or "?", model_short, f"{row[2]:,}", f"{row[3] or 0:.0f}", f"{row[5] or 0:,}")
        console.print(st)

    # Prompt patterns
    prompts = data.get("prompts", {})
    if prompts.get("patterns"):
        pp = Table(title="Prompt Patterns", border_style="dim")
        pp.add_column("Pattern")
        pp.add_column("Count", justify="right")
        pp.add_column("Avg Words", justify="right")
        for row in prompts["patterns"]:
            pp.add_row(row[0], f"{row[1]:,}", f"{row[2] or 0:.0f}")
        console.print(pp)

    # Anti-patterns
    aps = data.get("antipatterns", [])
    if aps:
        console.print()
        console.print(Panel.fit("[bold red]Anti-Patterns Detected[/bold red]", border_style="red"))
        for ap in aps[:15]:
            severity_style = {"critical": "red bold", "warning": "yellow", "info": "dim"}.get(ap["severity"], "")
            console.print(f"  [{severity_style}]{ap['severity'].upper()}[/{severity_style}] [{severity_style}]{ap['type']}[/{severity_style}]")
            console.print(f"    {ap['description']}")
            console.print(f"    [dim]Suggestion: {ap['suggestion']}[/dim]")
            console.print()

    # Top recommendations
    recs = data.get("recommendations", [])
    if recs:
        console.print()
        _print_recommendations(recs[:5], title=f"Top Recommendations")


def _print_recommendations(recs: list[dict], title: str = "Recommendations"):
    """Print recommendations with Rich formatting."""
    if not recs:
        console.print("[green]No recommendations. Looking good.[/green]")
        return

    high = sum(1 for r in recs if r["priority"] == "high")
    med = sum(1 for r in recs if r["priority"] == "medium")
    low = sum(1 for r in recs if r["priority"] == "low")
    console.print(Panel.fit(
        f"[bold]{title}[/bold]: {len(recs)} total "
        f"([red]{high} high[/red], [yellow]{med} medium[/yellow], [blue]{low} low[/blue])",
        border_style="magenta"
    ))

    for rec in recs:
        priority_style = {"high": "red bold", "medium": "yellow", "low": "blue"}.get(rec["priority"], "")
        cat_style = "dim"

        console.print(
            f"  [{priority_style}]{rec['priority'].upper()}[/{priority_style}]  "
            f"{rec['title']}  [{cat_style}][{rec['category']}][/{cat_style}]"
        )
        console.print(f"    {rec['description']}")
        if rec.get("impact"):
            console.print(f"    [green]Impact: {rec['impact']}[/green]")
        console.print(f"    [dim]Prompt:[/dim]")
        console.print(f"    [dim italic]{rec['prompt']}[/dim italic]")
        console.print()


@cli.command()
@click.option("--days", type=int, default=7, help="Number of days to analyze")
@click.option("--format", "fmt", type=click.Choice(["text", "json", "markdown"]), default="text")
@click.option("--category", type=click.Choice(["all", "context", "session", "model", "prompt", "tools"]), default="all")
def recommend(days, fmt, category):
    """Generate prioritized recommendations with ready-to-paste prompts."""
    from .analyzers import recommend as run_recommend
    import json

    recs = run_recommend(days, category=category)

    if fmt == "json":
        console.print(json.dumps(recs, indent=2))
        return

    if fmt == "markdown":
        lines = [f"# dt Recommendations - Last {days} Days\n"]
        for rec in recs:
            priority_icon = {"high": "!!!", "medium": "!!", "low": "!"}.get(rec["priority"], "")
            lines.append(f"## {priority_icon} {rec['title']} [{rec['category']}]\n")
            lines.append(f"{rec['description']}\n")
            lines.append(f"**Action:** {rec['action']}\n")
            lines.append(f"**Prompt to fix:**\n```\n{rec['prompt']}\n```\n")
            if rec.get("impact"):
                lines.append(f"*Impact: {rec['impact']}*\n")
        console.print("\n".join(lines))
        return

    _print_recommendations(recs, title=f"Recommendations (last {days} days)")


@cli.command()
@click.option("--days", type=int, default=7, help="Number of days to analyze")
def context(days):
    """Analyze context usage patterns."""
    from .analyzers import analyze_context

    data = analyze_context(days)

    if data["repeat_reads"]:
        t = Table(title=f"Repeat File Reads (Last {days} Days)", border_style="yellow")
        t.add_column("File")
        t.add_column("Sessions", justify="right")
        t.add_column("Repeats", justify="right")
        t.add_column("Total", justify="right")
        for row in data["repeat_reads"]:
            t.add_row(str(row[0])[-60:], f"{row[1]}", f"{row[2]}", f"{row[3]}")
        console.print(t)

    if data["hotspot_files"]:
        t = Table(title="Context Hotspots", border_style="yellow")
        t.add_column("File")
        t.add_column("Reads", justify="right")
        t.add_column("Sessions", justify="right")
        for row in data["hotspot_files"]:
            t.add_row(str(row[0])[-60:], f"{row[1]}", f"{row[2]}")
        console.print(t)


@cli.command()
@click.option("--days", type=int, default=7, help="Number of days to analyze")
def tools(days):
    """Analyze tool usage patterns."""
    from .analyzers import analyze_tools

    data = analyze_tools(days)

    if data["tool_frequency"]:
        t = Table(title=f"Tool Frequency (Last {days} Days)", border_style="blue")
        t.add_column("Tool")
        t.add_column("Calls", justify="right")
        t.add_column("Errors", justify="right")
        t.add_column("Error %", justify="right")
        for row in data["tool_frequency"]:
            t.add_row(row[0], f"{row[1]:,}", f"{row[2]:,}", f"{row[3] or 0}%")
        console.print(t)


@cli.command()
@click.option("--days", type=int, default=7, help="Number of days to analyze")
def antipatterns(days):
    """Detect anti-patterns in recent sessions."""
    from .analyzers import detect_antipatterns

    findings = detect_antipatterns(days)

    if not findings:
        console.print("[green]No anti-patterns detected. Nice work.[/green]")
        return

    for ap in findings:
        severity_style = {"critical": "red bold", "warning": "yellow", "info": "dim"}.get(ap["severity"], "")
        console.print(f"[{severity_style}]{ap['severity'].upper()}[/{severity_style}] {ap['type']}")
        console.print(f"  {ap['description']}")
        console.print(f"  [dim]{ap['suggestion']}[/dim]")
        console.print()

    console.print(f"[bold]Total: {len(findings)} findings[/bold]")


@cli.command()
@click.option("--days", type=int, default=7, help="Number of days to analyze")
def prompts(days):
    """Analyze prompt patterns."""
    from .analyzers import analyze_prompts

    data = analyze_prompts(days)

    if data["patterns"]:
        t = Table(title=f"Prompt Patterns (Last {days} Days)", border_style="blue")
        t.add_column("Pattern")
        t.add_column("Count", justify="right")
        t.add_column("Avg Words", justify="right")
        for row in data["patterns"]:
            t.add_row(row[0], f"{row[1]:,}", f"{row[2] or 0:.0f}")
        console.print(t)

    if data["by_project"]:
        t = Table(title="Prompts by Project", border_style="dim")
        t.add_column("Project")
        t.add_column("Prompts", justify="right")
        t.add_column("Avg Words", justify="right")
        for row in data["by_project"]:
            name = str(row[0]).split("/")[-1] if row[0] else "?"
            t.add_row(name, f"{row[1]:,}", f"{row[2] or 0:.0f}")
        console.print(t)


@cli.command("session")
@click.argument("session_id", default="list")
def session_cmd(session_id):
    """View session details. Use 'list' for recent sessions, or pass a session ID."""
    from .db import get_connection

    conn = get_connection(read_only=True)

    if session_id == "list":
        rows = conn.execute("""
            SELECT
                session_id, project_name, summary,
                user_message_count, tool_call_count,
                COALESCE(array_to_string(models_used, ', '), '') as models,
                first_message_at,
                ROUND(duration_seconds / 60, 1) as minutes
            FROM sessions
            ORDER BY first_message_at DESC
            LIMIT 20
        """).fetchall()

        t = Table(title="Recent Sessions", border_style="blue")
        t.add_column("ID", max_width=8)
        t.add_column("Project")
        t.add_column("Summary", max_width=40)
        t.add_column("Turns", justify="right")
        t.add_column("Tools", justify="right")
        t.add_column("When")
        t.add_column("Min", justify="right")

        for row in rows:
            sid = row[0][:8] if row[0] else "?"
            summary = (row[2] or "")[:40]
            when = str(row[6])[:16] if row[6] else "?"
            t.add_row(sid, row[1] or "?", summary, f"{row[3]}", f"{row[4]}", when, f"{row[7] or 0}")

        console.print(t)
    else:
        # Match partial session ID
        rows = conn.execute("""
            SELECT * FROM sessions WHERE session_id LIKE ?
        """, [f"{session_id}%"]).fetchall()

        if not rows:
            console.print(f"[red]No session found matching '{session_id}'[/red]")
            return

        row = rows[0]
        cols = [desc[0] for desc in conn.description]
        session = dict(zip(cols, row))

        console.print(Panel(f"[bold]{session.get('summary', 'No summary')}[/bold]", title=f"Session {session['session_id'][:8]}", border_style="blue"))
        console.print(f"  Project: {session['project_name']}")
        console.print(f"  Duration: {(session.get('duration_seconds') or 0) / 60:.1f} minutes")
        console.print(f"  Messages: {session.get('message_count', 0)} ({session.get('user_message_count', 0)} user, {session.get('assistant_msg_count', 0)} assistant)")
        console.print(f"  Tool calls: {session.get('tool_call_count', 0)} ({session.get('tool_error_count', 0)} errors)")
        console.print(f"  Models: {session.get('models_used', [])}")
        console.print(f"  Tokens: {(session.get('total_input_tokens', 0) or 0) + (session.get('total_output_tokens', 0) or 0):,}")
        console.print(f"  Cache reads: {session.get('total_cache_read', 0) or 0:,}")
        console.print(f"  Subagents: {session.get('subagent_count', 0)}")

        # Tool breakdown for this session
        tool_rows = conn.execute("""
            SELECT tool_name, COUNT(*) as cnt,
                   SUM(CASE WHEN result_error THEN 1 ELSE 0 END) as errors
            FROM tool_calls
            WHERE session_id = ?
            GROUP BY tool_name
            ORDER BY cnt DESC
        """, [session['session_id']]).fetchall()

        if tool_rows:
            console.print()
            tt = Table(title="Tools Used", border_style="dim")
            tt.add_column("Tool")
            tt.add_column("Calls", justify="right")
            tt.add_column("Errors", justify="right")
            for tr in tool_rows:
                tt.add_row(tr[0], f"{tr[1]}", f"{tr[2]}")
            console.print(tt)

    conn.close()


@cli.command()
@click.argument("sql")
def query(sql):
    """Run a raw SQL query against the database."""
    from .db import get_connection

    conn = get_connection(read_only=True)
    try:
        result = conn.execute(sql)
        rows = result.fetchall()
        if not rows:
            console.print("[dim]No results.[/dim]")
            return

        cols = [desc[0] for desc in result.description]
        t = Table(border_style="dim")
        for col in cols:
            t.add_column(col)
        for row in rows:
            t.add_row(*[str(v) for v in row])
        console.print(t)
    except Exception as e:
        console.print(f"[red]Query error: {e}[/red]")
    finally:
        conn.close()


def _generate_claudemd_suggestions(health_data: dict, project_filter: str | None = None):
    """Generate CLAUDE.md content suggestions based on usage patterns."""
    candidates = health_data.get("claudemd_candidates", [])
    fragmenters = health_data.get("context_fragmenters", [])

    if not candidates and not fragmenters:
        console.print("[green]No CLAUDE.md improvements detected.[/green]")
        return

    console.print("# Suggested CLAUDE.md additions\n")
    console.print("# Based on file access patterns from dt health analysis\n")

    if candidates:
        console.print("## Frequently Re-read Files\n")
        console.print("# These files are read repeatedly across sessions.")
        console.print("# Consider adding key content from these files to your CLAUDE.md:\n")
        for row in candidates[:10]:
            fp = str(row[0])
            console.print(f"# {fp}")
            console.print(f"#   {row[1]} sessions, {row[3]} reads/session")
            # Suggest based on file type
            if fp.endswith((".tsx", ".ts", ".jsx", ".js")):
                console.print(f"#   Suggestion: Document component API, key patterns, or imports")
            elif fp.endswith(".py"):
                console.print(f"#   Suggestion: Document module purpose, key functions, or config")
            elif fp.endswith(".md"):
                console.print(f"#   Suggestion: Inline key content or link in CLAUDE.md")
            console.print()

    if fragmenters:
        console.print("## Context Fragmenters\n")
        console.print("# These files cause repeated reads within single sessions.")
        console.print("# Consider splitting large files or adding summaries:\n")
        for row in fragmenters[:10]:
            fp = str(row[0])
            console.print(f"# {fp}")
            console.print(f"#   {row[1]} total reads, {row[2]} repeat reads across {row[3]} sessions")
            console.print()


@cli.command()
@click.option("--days", type=int, default=14, help="Total period to compare (split in half)")
def trends(days):
    """Show usage trends with period comparison."""
    from .analyzers import analyze_trends, _sparkline

    data = analyze_trends(days)
    half = data["period_days"]
    cur = data["current"]
    prev = data["previous"]

    def _delta(cur_val, prev_val):
        if not prev_val:
            return "[dim]new[/dim]"
        pct = (cur_val - prev_val) / prev_val * 100
        if pct > 0:
            return f"[green]+{pct:.0f}%[/green]"
        elif pct < 0:
            return f"[red]{pct:.0f}%[/red]"
        return "[dim]0%[/dim]"

    t = Table(title=f"Trends: Last {half}d vs Previous {half}d", border_style="blue")
    t.add_column("Metric")
    t.add_column(f"Current ({half}d)", justify="right")
    t.add_column(f"Previous ({half}d)", justify="right")
    t.add_column("Change", justify="right")

    metrics = [
        ("Sessions", 0), ("Messages", 1), ("Tool calls", 2),
        ("Tool errors", 3), ("Tokens", 4), ("Avg turns", 5),
        ("Projects", 6), ("Subagents", 7),
    ]
    for label, idx in metrics:
        c, p = cur[idx] or 0, prev[idx] or 0
        if label == "Avg turns":
            t.add_row(label, f"{c:.1f}", f"{p:.1f}", _delta(c, p))
        else:
            t.add_row(label, f"{c:,}", f"{p:,}", _delta(c, p))

    console.print(t)

    # Sparklines
    daily = data.get("daily", [])
    if daily:
        console.print()
        sessions_vals = [r[1] for r in daily]
        msgs_vals = [r[2] or 0 for r in daily]
        tools_vals = [r[3] or 0 for r in daily]

        spark_text = Text()
        spark_text.append("  Sessions: ", style="bold")
        spark_text.append(_sparkline(sessions_vals))
        spark_text.append(f"  ({min(sessions_vals)}-{max(sessions_vals)})\n")
        spark_text.append("  Messages: ", style="bold")
        spark_text.append(_sparkline(msgs_vals))
        spark_text.append(f"  ({min(msgs_vals):,}-{max(msgs_vals):,})\n")
        spark_text.append("  Tools:    ", style="bold")
        spark_text.append(_sparkline(tools_vals))
        spark_text.append(f"  ({min(tools_vals):,}-{max(tools_vals):,})")
        console.print(Panel(spark_text, title="Daily Activity", border_style="dim"))

    # Model shift
    cur_models = data.get("current_models", [])
    prev_models = data.get("previous_models", [])
    if cur_models or prev_models:
        from .analyzers import _short_model
        cur_dict = {_short_model(r[0]): r[1] for r in cur_models}
        prev_dict = {_short_model(r[0]): r[1] for r in prev_models}
        all_models = set(cur_dict) | set(prev_dict)

        mt = Table(title="Model Shift", border_style="dim")
        mt.add_column("Model")
        mt.add_column("Current", justify="right")
        mt.add_column("Previous", justify="right")
        mt.add_column("Change", justify="right")
        for m in sorted(all_models, key=lambda x: cur_dict.get(x, 0), reverse=True):
            c, p = cur_dict.get(m, 0), prev_dict.get(m, 0)
            mt.add_row(m, f"{c:,}", f"{p:,}", _delta(c, p))
        console.print(mt)


@cli.command()
@click.option("--days", type=int, default=30, help="Number of days to analyze")
@click.option("--fix", is_flag=True, help="Generate CLAUDE.md suggestions based on usage patterns")
@click.option("--project", type=str, help="Filter to specific project")
def health(days, fix, project):
    """Project configuration health check."""
    from .analyzers import analyze_health, compute_scores

    data = analyze_health(days)
    scores = compute_scores(days)

    if fix:
        _generate_claudemd_suggestions(data, project)
        return

    # Overall health score
    h = scores.get("health", 0)
    style = "green" if h >= 80 else ("yellow" if h >= 60 else "red")
    console.print(Panel(f"[{style} bold]Health Score: {h}/100[/{style} bold]", border_style=style))

    # CLAUDE.md candidates
    if data["claudemd_candidates"]:
        t = Table(title="CLAUDE.md Candidates (frequently re-read files)", border_style="yellow")
        t.add_column("File")
        t.add_column("Sessions", justify="right")
        t.add_column("Total Reads", justify="right")
        t.add_column("Reads/Session", justify="right")
        for row in data["claudemd_candidates"]:
            t.add_row(str(row[0])[-60:], f"{row[1]}", f"{row[2]}", f"{row[3]}")
        console.print(t)

    # Context fragmenters
    if data["context_fragmenters"]:
        t = Table(title="Context Fragmenters (high repeat reads)", border_style="red")
        t.add_column("File")
        t.add_column("Total Reads", justify="right")
        t.add_column("Repeat Reads", justify="right")
        t.add_column("Sessions", justify="right")
        for row in data["context_fragmenters"]:
            t.add_row(str(row[0])[-60:], f"{row[1]}", f"{row[2]}", f"{row[3]}")
        console.print(t)

    # Error-prone projects
    if data["error_prone_projects"]:
        t = Table(title="Error-Prone Projects", border_style="red")
        t.add_column("Project")
        t.add_column("Sessions", justify="right")
        t.add_column("Tool Calls", justify="right")
        t.add_column("Errors", justify="right")
        t.add_column("Error %", justify="right")
        for row in data["error_prone_projects"]:
            t.add_row(row[0], f"{row[1]}", f"{row[2]:,}", f"{row[3]:,}", f"{row[4]}%")
        console.print(t)

    # High access projects
    if data["high_access_projects"]:
        t = Table(title="Most-Accessed Projects", border_style="dim")
        t.add_column("Project")
        t.add_column("Sessions", justify="right")
        t.add_column("File Reads", justify="right")
        t.add_column("Unique Files", justify="right")
        for row in data["high_access_projects"]:
            t.add_row(row[0], f"{row[1]}", f"{row[2]:,}", f"{row[3]}")
        console.print(t)


@cli.command("export")
@click.argument("table_name", type=click.Choice(
    ["sessions", "messages", "tool_calls", "subagents", "file_access", "prompts", "daily_stats"]
))
@click.option("--format", "fmt", type=click.Choice(["csv", "json", "parquet"]), default="csv")
@click.option("--output", "-o", "output_path", type=str, help="Output file path")
@click.option("--days", type=int, help="Limit to last N days")
def export_cmd(table_name, fmt, output_path, days):
    """Export a table as CSV, JSON, or Parquet."""
    from .db import get_connection

    conn = get_connection(read_only=True)

    # Build query with optional date filter
    date_col = {
        "sessions": "first_message_at",
        "messages": "timestamp",
        "tool_calls": "timestamp",
        "subagents": "started_at",
        "file_access": "timestamp",
        "prompts": "timestamp",
        "daily_stats": "date",
    }.get(table_name, "timestamp")

    where = ""
    if days:
        iv = f"INTERVAL '{days}' DAY"
        where = f"WHERE {date_col} >= CURRENT_DATE - {iv}"

    query = f"SELECT * FROM {table_name} {where}"

    if not output_path:
        output_path = f"dt-{table_name}.{fmt}"

    try:
        if fmt == "csv":
            conn.execute(f"COPY ({query}) TO '{output_path}' (FORMAT CSV, HEADER)")
        elif fmt == "json":
            conn.execute(f"COPY ({query}) TO '{output_path}' (FORMAT JSON)")
        elif fmt == "parquet":
            conn.execute(f"COPY ({query}) TO '{output_path}' (FORMAT PARQUET)")

        import os
        size = os.path.getsize(output_path)
        console.print(f"[green]Exported {table_name} to {output_path} ({size:,} bytes)[/green]")
    except Exception as e:
        console.print(f"[red]Export error: {e}[/red]")
    finally:
        conn.close()


if __name__ == "__main__":
    cli()
