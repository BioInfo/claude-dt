"""Ingest Claude Code session JSONL files into DuckDB."""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

from .config import PROJECTS_DIR, STATS_CACHE, HISTORY_FILE
from .db import get_connection, init_db


def parse_project_name(project_path: str) -> str:
    """Extract human-readable project name from encoded path.

    Claude Code encodes project paths as: -Users-username-apps-myproject
    This extracts the last meaningful component as the project name.
    """
    parts = project_path.strip("-").split("-")
    # Skip platform prefix (Users/home) and username
    if len(parts) >= 2 and parts[0] in ("Users", "home"):
        remaining = parts[2:]  # Skip prefix + username
        if not remaining:
            return "~"
        return remaining[-1]
    return parts[-1] if parts else project_path


def extract_text_content(content) -> str:
    """Extract text from message content (string or array of blocks)."""
    if isinstance(content, str):
        return content[:2000]
    if isinstance(content, list):
        texts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    texts.append(block.get("text", "")[:500])
                elif block.get("type") == "tool_result":
                    c = block.get("content", "")
                    if isinstance(c, str):
                        texts.append(c[:200])
            elif isinstance(block, str):
                texts.append(block[:500])
        return "\n".join(texts)[:2000]
    return ""


def extract_tool_calls(content) -> list[dict]:
    """Extract tool_use blocks from message content."""
    if not isinstance(content, list):
        return []
    calls = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "tool_use":
            tool_input = block.get("input", {})
            summary = _summarize_tool_input(block.get("name", ""), tool_input)
            file_path = _extract_file_path(block.get("name", ""), tool_input)
            calls.append({
                "tool_use_id": block.get("id", ""),
                "tool_name": block.get("name", ""),
                "input_summary": summary[:500],
                "file_path": file_path,
            })
    return calls


def extract_tool_results(content) -> dict:
    """Extract tool_result blocks, returns {tool_use_id: {error, length}}."""
    if not isinstance(content, list):
        return {}
    results = {}
    for block in content:
        if isinstance(block, dict) and block.get("type") == "tool_result":
            tid = block.get("tool_use_id", "")
            c = block.get("content", "")
            results[tid] = {
                "result_error": block.get("is_error", False),
                "result_length": len(c) if isinstance(c, str) else 0,
            }
    return results


def _summarize_tool_input(tool_name: str, inp: dict) -> str:
    """Create a human-readable summary of tool input."""
    if tool_name in ("Read", "read"):
        return inp.get("file_path", "")
    if tool_name in ("Edit", "edit"):
        fp = inp.get("file_path", "")
        old = (inp.get("old_string", "") or "")[:50]
        return f"{fp} | {old}..."
    if tool_name in ("Write", "write"):
        return inp.get("file_path", "")
    if tool_name in ("Bash", "bash"):
        return (inp.get("command", "") or "")[:200]
    if tool_name in ("Grep", "grep"):
        return f"{inp.get('pattern', '')} in {inp.get('path', '.')}"
    if tool_name in ("Glob", "glob"):
        return inp.get("pattern", "")
    if tool_name in ("Task",):
        return f"{inp.get('subagent_type', '')}:{inp.get('description', '')}"[:200]
    if tool_name in ("WebSearch",):
        return inp.get("query", "")
    if tool_name in ("WebFetch",):
        return inp.get("url", "")[:200]
    try:
        return json.dumps(inp)[:200]
    except (TypeError, ValueError):
        return str(inp)[:200]


def _extract_file_path(tool_name: str, inp: dict) -> str | None:
    """Extract file path from tool input if applicable."""
    if tool_name in ("Read", "read", "Edit", "edit", "Write", "write"):
        return inp.get("file_path")
    if tool_name in ("Grep", "grep"):
        return inp.get("path")
    return None


def parse_timestamp(ts: str | None) -> datetime | None:
    """Parse ISO 8601 timestamp."""
    if not ts:
        return None
    try:
        ts = ts.rstrip("Z")
        if "+" in ts:
            ts = ts.split("+")[0]
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None


def safe_json_parse(line: str) -> dict | None:
    """Parse a JSONL line, handling very large lines by extracting key fields only."""
    try:
        return json.loads(line)
    except (json.JSONDecodeError, MemoryError):
        return None


def ingest_session_file(conn, jsonl_path: Path, project_path: str):
    """Parse a single session JSONL file and insert into DuckDB."""
    session_id = jsonl_path.stem
    project_name = parse_project_name(project_path)

    # For very large files (>20MB), use lightweight stats-only parser
    try:
        file_size = jsonl_path.stat().st_size
    except OSError:
        return None
    if file_size > 20_000_000:
        return _ingest_large_session(conn, jsonl_path, session_id, project_path, project_name)

    messages_batch = []
    tool_calls_batch = []
    tool_results_map = {}
    summaries = []
    models_seen = set()
    model_counts = {}
    timestamps = []
    user_count = 0
    assistant_count = 0
    tool_count = 0
    tool_errors = 0
    total_input = 0
    total_output = 0
    total_cache_read = 0
    total_cache_create = 0
    subagent_ids = set()
    turn_number = 0

    try:
        with open(jsonl_path, "r", errors="replace") as f:
            for line_num, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue

                # Lines over 1MB are tool results with large file contents.
                # Extract just metadata without full parse to save memory.
                if len(line) > 1_000_000:
                    # Quick extraction of key fields from the line prefix
                    try:
                        # Just get type and timestamp from the start of the JSON
                        if '"type":"summary"' in line[:200]:
                            summaries.append("(large message)")
                        ts_match = line.find('"timestamp":"')
                        if ts_match > 0:
                            ts_str = line[ts_match+13:ts_match+40].split('"')[0]
                            ts = parse_timestamp(ts_str)
                            if ts:
                                timestamps.append(ts)
                    except Exception:
                        pass
                    continue

                record = safe_json_parse(line)
                if record is None:
                    continue

                rec_type = record.get("type", "")
                timestamp = parse_timestamp(record.get("timestamp"))
                if timestamp:
                    timestamps.append(timestamp)

                if rec_type == "summary":
                    summaries.append(record.get("summary", ""))
                    continue

                if rec_type == "progress":
                    continue

                agent_id = record.get("agentId") or record.get("agent_id")
                if agent_id:
                    subagent_ids.add(agent_id)

                msg = record.get("message", {})
                if not isinstance(msg, dict):
                    continue

                role = msg.get("role", "")
                content = msg.get("content", "")
                usage = msg.get("usage", {}) or {}
                model = msg.get("model", "")

                if model:
                    models_seen.add(model)
                    model_counts[model] = model_counts.get(model, 0) + 1

                inp_tok = usage.get("input_tokens", 0) or 0
                out_tok = usage.get("output_tokens", 0) or 0
                cr_tok = usage.get("cache_read_input_tokens", 0) or 0
                cc_tok = usage.get("cache_creation_input_tokens", 0) or 0
                total_input += inp_tok
                total_output += out_tok
                total_cache_read += cr_tok
                total_cache_create += cc_tok

                uuid = record.get("uuid", f"{session_id}-{line_num}")
                is_sidechain = record.get("isSidechain", False)

                if role == "user":
                    user_count += 1
                    if not is_sidechain:
                        turn_number += 1
                    results = extract_tool_results(content)
                    tool_results_map.update(results)
                elif role == "assistant":
                    assistant_count += 1

                text_content = extract_text_content(content)

                messages_batch.append((
                    uuid, session_id, record.get("parentUuid"),
                    rec_type or role, role, model, agent_id,
                    is_sidechain, timestamp,
                    inp_tok, out_tok, cr_tok, cc_tok,
                    text_content[:2000] if text_content else None,
                    len(text_content) if text_content else 0,
                    turn_number,
                    record.get("cwd")
                ))

                if role == "assistant":
                    calls = extract_tool_calls(content)
                    for call in calls:
                        tool_count += 1
                        tool_calls_batch.append((
                            call["tool_use_id"], session_id, uuid,
                            agent_id, call["tool_name"],
                            call["input_summary"], timestamp,
                            call["file_path"]
                        ))

                # Batch insert every 5000 messages to avoid memory pressure
                if len(messages_batch) >= 5000:
                    _flush_batch(conn, messages_batch, tool_calls_batch, tool_results_map)
                    messages_batch.clear()
                    tool_calls_batch.clear()

    except (OSError, PermissionError):
        return None

    if not timestamps:
        return None

    # Flush remaining
    _flush_batch(conn, messages_batch, tool_calls_batch, tool_results_map)

    # Count errors from tool results
    for r in tool_results_map.values():
        if r.get("result_error"):
            tool_errors += 1

    primary_model = max(model_counts, key=model_counts.get) if model_counts else None
    first_ts = min(timestamps)
    last_ts = max(timestamps)
    duration = (last_ts - first_ts).total_seconds()
    last_summary = summaries[-1] if summaries else None

    conn.execute("""
        INSERT OR REPLACE INTO sessions VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
    """, [
        session_id, project_path, project_name,
        first_ts, last_ts, duration,
        user_count + assistant_count, user_count, assistant_count,
        tool_count, tool_errors, 0,
        list(models_seen), primary_model,
        total_input, total_output, total_cache_read, total_cache_create,
        len(subagent_ids), last_summary, str(jsonl_path)
    ])

    return {
        "session_id": session_id,
        "messages": user_count + assistant_count,
        "tool_calls": tool_count,
    }


def _ingest_large_session(conn, jsonl_path: Path, session_id: str,
                          project_path: str, project_name: str):
    """Lightweight parser for large files. Extracts session-level stats only."""
    summaries = []
    models_seen = set()
    model_counts = {}
    first_ts = None
    last_ts = None
    user_count = 0
    assistant_count = 0
    tool_count = 0
    total_input = 0
    total_output = 0
    total_cache_read = 0
    total_cache_create = 0

    try:
        with open(jsonl_path, "r", errors="replace") as f:
            for line in f:
                # Skip very long lines entirely
                if len(line) > 500_000:
                    continue

                line = line.strip()
                if not line:
                    continue

                record = safe_json_parse(line)
                if record is None:
                    continue

                rec_type = record.get("type", "")

                if rec_type == "summary":
                    summaries.append(record.get("summary", ""))
                    continue

                if rec_type == "progress":
                    continue

                ts = parse_timestamp(record.get("timestamp"))
                if ts:
                    if first_ts is None or ts < first_ts:
                        first_ts = ts
                    if last_ts is None or ts > last_ts:
                        last_ts = ts

                msg = record.get("message", {})
                if not isinstance(msg, dict):
                    continue

                role = msg.get("role", "")
                usage = msg.get("usage", {}) or {}
                model = msg.get("model", "")

                if model:
                    models_seen.add(model)
                    model_counts[model] = model_counts.get(model, 0) + 1

                if role == "user":
                    user_count += 1
                elif role == "assistant":
                    assistant_count += 1

                total_input += usage.get("input_tokens", 0) or 0
                total_output += usage.get("output_tokens", 0) or 0
                total_cache_read += usage.get("cache_read_input_tokens", 0) or 0
                total_cache_create += usage.get("cache_creation_input_tokens", 0) or 0

                # Count tool calls
                content = msg.get("content", [])
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_use":
                            tool_count += 1

    except (OSError, PermissionError):
        return None

    if first_ts is None:
        return None

    primary_model = max(model_counts, key=model_counts.get) if model_counts else None
    duration = (last_ts - first_ts).total_seconds() if last_ts and first_ts else 0
    last_summary = summaries[-1] if summaries else None

    conn.execute("""
        INSERT OR REPLACE INTO sessions VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
    """, [
        session_id, project_path, project_name,
        first_ts, last_ts, duration,
        user_count + assistant_count, user_count, assistant_count,
        tool_count, 0, 0,
        list(models_seen), primary_model,
        total_input, total_output, total_cache_read, total_cache_create,
        0, last_summary, str(jsonl_path)
    ])

    return {
        "session_id": session_id,
        "messages": user_count + assistant_count,
        "tool_calls": tool_count,
    }


def _flush_batch(conn, messages_batch, tool_calls_batch, tool_results_map=None):
    """Insert batched data into DuckDB."""
    if messages_batch:
        conn.executemany("""
            INSERT OR IGNORE INTO messages VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
        """, messages_batch)
    if tool_calls_batch:
        # Apply error info from tool_results_map before inserting
        resolved = []
        for tc in tool_calls_batch:
            tid = tc[0]  # tool_use_id
            r = (tool_results_map or {}).get(tid, {})
            resolved.append(tc + (r.get("result_error", False), r.get("result_length", 0)))
        conn.executemany("""
            INSERT OR IGNORE INTO tool_calls (
                tool_use_id, session_id, message_uuid, agent_id,
                tool_name, input_summary, timestamp, file_path,
                result_error, result_length
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, resolved)


def ingest_subagent_files(conn, session_dir: Path, session_id: str):
    """Parse subagent JSONL files within a session directory."""
    subagents_dir = session_dir / "subagents"
    if not subagents_dir.exists():
        return

    for jsonl_file in subagents_dir.glob("*.jsonl"):
        agent_id = jsonl_file.stem.replace("agent-", "")
        messages = 0
        tools = 0
        total_tokens = 0
        agent_type = None
        model = None
        prompt_summary = None
        timestamps = []

        try:
            with open(jsonl_file, "r", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    record = safe_json_parse(line)
                    if record is None:
                        continue

                    ts = parse_timestamp(record.get("timestamp"))
                    if ts:
                        timestamps.append(ts)

                    msg = record.get("message", {})
                    if not isinstance(msg, dict):
                        continue
                    role = msg.get("role", "")
                    usage = msg.get("usage", {}) or {}

                    if role in ("user", "assistant"):
                        messages += 1

                    if not model and msg.get("model"):
                        model = msg["model"]

                    if role == "user" and prompt_summary is None:
                        text = extract_text_content(msg.get("content", ""))
                        prompt_summary = text[:500] if text else None

                    total_tokens += (usage.get("input_tokens", 0) or 0)
                    total_tokens += (usage.get("output_tokens", 0) or 0)

                    content = msg.get("content", [])
                    if isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "tool_use":
                                tools += 1
        except (OSError, PermissionError):
            continue

        if not timestamps:
            continue

        first_ts = min(timestamps)
        last_ts = max(timestamps)

        conn.execute("""
            INSERT OR REPLACE INTO subagents VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
        """, [
            agent_id, session_id, agent_type, model,
            prompt_summary, messages, tools, total_tokens,
            first_ts, last_ts, (last_ts - first_ts).total_seconds()
        ])


def ingest_daily_stats(conn):
    """Import daily stats from stats-cache.json."""
    if not STATS_CACHE.exists():
        return

    with open(STATS_CACHE) as f:
        data = json.load(f)

    daily = data.get("dailyActivity", [])
    daily_tokens = {d["date"]: d["tokensByModel"] for d in data.get("dailyModelTokens", [])}

    for day in daily:
        date = day["date"]
        tokens_model = daily_tokens.get(date, {})
        total_tokens = sum(tokens_model.values())

        conn.execute("""
            INSERT OR REPLACE INTO daily_stats (
                date, message_count, session_count, tool_call_count,
                tokens_by_model, total_tokens
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, [
            date, day.get("messageCount", 0),
            day.get("sessionCount", 0), day.get("toolCallCount", 0),
            json.dumps(tokens_model), total_tokens
        ])


def ingest_prompts(conn):
    """Import user prompt history."""
    if not HISTORY_FILE.exists():
        return

    batch = []
    with open(HISTORY_FILE, "r", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            text = record.get("display", "")
            ts_ms = record.get("timestamp")
            ts = datetime.fromtimestamp(ts_ms / 1000) if ts_ms else None
            project = record.get("project", "")
            words = len(text.split()) if text else 0
            pattern = classify_prompt(text) if text else None

            batch.append((
                f"prompt-{ts_ms}", None, text[:2000], words,
                ts, project, None, False, 0, pattern
            ))

    if batch:
        conn.executemany("""
            INSERT OR IGNORE INTO prompts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, batch)


def classify_prompt(text: str) -> str:
    """Classify prompt into a pattern category."""
    t = text.lower().strip()
    if t in ("continue", "yes", "y", "ok", "go ahead", "proceed"):
        return "continue"
    if t.startswith("/"):
        return "command"
    if any(t.startswith(w) for w in ("fix ", "debug ", "why is", "why does", "what's wrong")):
        return "fix"
    if any(t.startswith(w) for w in ("create ", "build ", "make ", "add ", "implement ", "write ")):
        return "create"
    if any(t.startswith(w) for w in ("refactor", "clean up", "simplify", "optimize")):
        return "refactor"
    if any(t.startswith(w) for w in ("what ", "how ", "why ", "where ", "explain", "show me")):
        return "question"
    if any(t.startswith(w) for w in ("update ", "change ", "modify ", "edit ")):
        return "update"
    if any(t.startswith(w) for w in ("test ", "run ", "check ")):
        return "execute"
    if any(t.startswith(w) for w in ("read ", "look at", "review ")):
        return "review"
    if "[pasted" in t.lower():
        return "paste"
    return "other"


def run_ingest(since_days: int | None = None, project_filter: str | None = None,
               reset: bool = False):
    """Main ingest entry point. Returns stats dict."""
    import time

    if reset:
        from .db import reset_db
        conn = reset_db()
        print("Database reset.")
    else:
        conn = init_db()

    try:
        if not PROJECTS_DIR.exists():
            print("No projects directory found at ~/.claude/projects/")
            return

        cutoff = None
        if since_days:
            cutoff = datetime.now() - timedelta(days=since_days)

        project_dirs = sorted(PROJECTS_DIR.iterdir())
        if project_filter:
            project_dirs = [d for d in project_dirs if project_filter in d.name]

        total_sessions = 0
        total_messages = 0
        total_tools = 0
        skipped = 0

        all_files = []
        for project_dir in project_dirs:
            if not project_dir.is_dir():
                continue
            for jsonl_file in project_dir.glob("*.jsonl"):
                if cutoff:
                    try:
                        mtime = datetime.fromtimestamp(jsonl_file.stat().st_mtime)
                        if mtime < cutoff:
                            skipped += 1
                            continue
                    except OSError:
                        continue
                all_files.append((jsonl_file, project_dir.name))

        print(f"Processing {len(all_files)} session files ({skipped} skipped)...", flush=True)
        start = time.time()

        for i, (jsonl_file, project_path) in enumerate(all_files):
            result = ingest_session_file(conn, jsonl_file, project_path)
            if result:
                total_sessions += 1
                total_messages += result["messages"]
                total_tools += result["tool_calls"]

            session_dir = jsonl_file.parent / jsonl_file.stem
            if session_dir.is_dir():
                ingest_subagent_files(conn, session_dir, jsonl_file.stem)

            if (i + 1) % 100 == 0:
                elapsed = time.time() - start
                rate = (i + 1) / elapsed
                eta = (len(all_files) - i - 1) / rate if rate > 0 else 0
                print(f"  {i+1}/{len(all_files)} ({elapsed:.0f}s, ETA {eta:.0f}s) "
                      f"sessions={total_sessions} msgs={total_messages:,}", flush=True)

        elapsed = time.time() - start
        print(f"Sessions: {total_sessions:,} parsed in {elapsed:.1f}s")

        print("Importing daily stats...", flush=True)
        ingest_daily_stats(conn)

        print("Importing prompt history...", flush=True)
        ingest_prompts(conn)

        print("Backfilling subagent types...", flush=True)
        backfill_subagent_types(conn)

        print("Computing file access patterns...", flush=True)
        compute_file_access(conn)

        conn.execute(
            "INSERT OR REPLACE INTO meta VALUES ('last_ingest', ?)",
            [datetime.now().isoformat()]
        )

        total_elapsed = time.time() - start
        print(f"Done in {total_elapsed:.1f}s")

        return {
            "sessions": total_sessions,
            "messages": total_messages,
            "tool_calls": total_tools,
            "skipped": skipped,
            "files_processed": len(all_files),
        }
    finally:
        conn.close()


def backfill_subagent_types(conn):
    """Backfill agent_type from Task tool call input_summaries.

    Task tool calls have input_summary like 'Explore:Find files in codebase'.
    We match subagents to Task calls by session_id and closest timestamp.
    """
    # Get all Task tool calls with their subagent_type
    task_calls = conn.execute("""
        SELECT session_id, timestamp, input_summary
        FROM tool_calls
        WHERE tool_name = 'Task' AND input_summary IS NOT NULL
        ORDER BY session_id, timestamp
    """).fetchall()

    if not task_calls:
        return

    # Build lookup: session_id -> [(timestamp, agent_type)]
    session_tasks = {}
    for session_id, ts, summary in task_calls:
        agent_type = summary.split(":")[0] if ":" in summary else None
        if agent_type and ts:
            session_tasks.setdefault(session_id, []).append((ts, agent_type))

    # Get all subagents without agent_type
    subagents = conn.execute("""
        SELECT agent_id, session_id, started_at
        FROM subagents
        WHERE agent_type IS NULL AND started_at IS NOT NULL
    """).fetchall()

    updated = 0
    for agent_id, session_id, started_at in subagents:
        tasks = session_tasks.get(session_id, [])
        if not tasks:
            continue
        # Find closest Task call by timestamp (within 5 seconds)
        best_type = None
        best_diff = 5.0  # max 5 second window
        for ts, atype in tasks:
            diff = abs((started_at - ts).total_seconds())
            if diff < best_diff:
                best_diff = diff
                best_type = atype
        if best_type:
            conn.execute(
                "UPDATE subagents SET agent_type = ? WHERE agent_id = ?",
                [best_type, agent_id]
            )
            updated += 1

    print(f"  Updated {updated}/{len(subagents)} subagent types", flush=True)


def compute_file_access(conn):
    """Derive file access patterns from tool_calls."""
    conn.execute("DELETE FROM file_access")
    conn.execute("""
        INSERT INTO file_access (id, session_id, file_path, access_type, timestamp, is_repeat, repeat_count)
        SELECT
            row_number() OVER () as id,
            session_id,
            file_path,
            CASE
                WHEN tool_name IN ('Read', 'read') THEN 'read'
                WHEN tool_name IN ('Edit', 'edit') THEN 'edit'
                WHEN tool_name IN ('Write', 'write') THEN 'write'
                WHEN tool_name IN ('Grep', 'grep') THEN 'grep'
                WHEN tool_name IN ('Glob', 'glob') THEN 'glob'
                ELSE 'other'
            END as access_type,
            timestamp,
            CASE WHEN row_number() OVER (PARTITION BY session_id, file_path ORDER BY timestamp) > 1
                 THEN TRUE ELSE FALSE END as is_repeat,
            row_number() OVER (PARTITION BY session_id, file_path ORDER BY timestamp) as repeat_count
        FROM tool_calls
        WHERE file_path IS NOT NULL
        ORDER BY timestamp
    """)
