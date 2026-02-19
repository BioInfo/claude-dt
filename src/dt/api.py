"""FastAPI backend for dt web dashboard."""
import json
from datetime import date, datetime
from typing import Any

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path


def _serialize(obj: Any) -> Any:
    """Custom serializer for DuckDB result types."""
    if isinstance(obj, tuple):
        return [_serialize(v) for v in obj]
    if isinstance(obj, list):
        return [_serialize(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if hasattr(obj, '__float__') and not isinstance(obj, (int, float, bool)):
        return float(obj)
    return obj


class DTJSONResponse(JSONResponse):
    def render(self, content: Any) -> bytes:
        return json.dumps(
            _serialize(content),
            default=str,
        ).encode("utf-8")


app = FastAPI(
    title="dt - Claude Code DevTools",
    default_response_class=DTJSONResponse,
)

# CORS for dev mode (Vite on 5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/api/report")
def api_report(days: int = Query(default=7, ge=1, le=365)):
    from .analyzers import generate_report
    return generate_report(days)


@app.get("/api/recommend")
def api_recommend(
    days: int = Query(default=7, ge=1, le=365),
    category: str = Query(default="all"),
):
    from .analyzers import recommend
    return recommend(days, category=category)


@app.get("/api/scores")
def api_scores(days: int = Query(default=7, ge=1, le=365)):
    from .analyzers import compute_scores
    return compute_scores(days)


@app.get("/api/trends")
def api_trends(days: int = Query(default=14, ge=2, le=365)):
    from .analyzers import analyze_trends
    return analyze_trends(days)


@app.get("/api/sessions")
def api_sessions(limit: int = Query(default=50, ge=1, le=500)):
    from .db import get_connection
    conn = get_connection(read_only=True)
    try:
        rows = conn.execute("""
            SELECT
                session_id, project_name, summary,
                user_message_count, tool_call_count,
                COALESCE(array_to_string(models_used, ', '), '') as models,
                first_message_at,
                ROUND(duration_seconds / 60, 1) as minutes,
                message_count, tool_error_count,
                total_input_tokens + total_output_tokens as total_tokens,
                subagent_count
            FROM sessions
            ORDER BY first_message_at DESC
            LIMIT ?
        """, [limit]).fetchall()
        cols = ["session_id", "project_name", "summary", "user_message_count",
                "tool_call_count", "models", "first_message_at", "minutes",
                "message_count", "tool_error_count", "total_tokens", "subagent_count"]
        return [dict(zip(cols, row)) for row in rows]
    finally:
        conn.close()


@app.get("/api/sessions/{session_id}")
def api_session_detail(session_id: str):
    from .db import get_connection
    conn = get_connection(read_only=True)
    try:
        rows = conn.execute(
            "SELECT * FROM sessions WHERE session_id LIKE ?",
            [f"{session_id}%"],
        ).fetchall()
        if not rows:
            return DTJSONResponse({"error": "Session not found"}, status_code=404)
        cols = [desc[0] for desc in conn.description]
        session = dict(zip(cols, rows[0]))

        # Tool breakdown
        tools = conn.execute("""
            SELECT tool_name, COUNT(*) as cnt,
                   SUM(CASE WHEN result_error THEN 1 ELSE 0 END) as errors
            FROM tool_calls WHERE session_id = ?
            GROUP BY tool_name ORDER BY cnt DESC
        """, [session["session_id"]]).fetchall()
        session["tool_breakdown"] = [
            {"tool": t[0], "count": t[1], "errors": t[2]} for t in tools
        ]
        return session
    finally:
        conn.close()


@app.get("/api/health")
def api_health(days: int = Query(default=30, ge=1, le=365)):
    from .analyzers import analyze_health
    return analyze_health(days)


@app.get("/api/status")
def api_status():
    from .db import get_connection, DB_PATH
    import os
    if not DB_PATH.exists():
        return {"error": "No database found. Run 'dt ingest' first."}
    conn = get_connection(read_only=True)
    try:
        tables = {}
        for tbl in ["sessions", "messages", "tool_calls", "subagents",
                     "file_access", "prompts", "daily_stats"]:
            tables[tbl] = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        size_mb = os.path.getsize(DB_PATH) / (1024 * 1024)
        last = conn.execute(
            "SELECT value FROM meta WHERE key = 'last_ingest'"
        ).fetchone()
        return {
            "tables": tables,
            "db_size_mb": round(size_mb, 1),
            "last_ingest": last[0][:19] if last else None,
        }
    finally:
        conn.close()


# Mount static files for built React app (production mode)
STATIC_DIR = Path(__file__).parent / "static"


def mount_static():
    """Mount static files if the build directory exists."""
    if STATIC_DIR.exists():
        app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


mount_static()
