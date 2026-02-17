"""Configuration and paths for dt."""
from pathlib import Path

# Claude Code data locations
CLAUDE_DIR = Path.home() / ".claude"
PROJECTS_DIR = CLAUDE_DIR / "projects"
STATS_CACHE = CLAUDE_DIR / "stats-cache.json"
HISTORY_FILE = CLAUDE_DIR / "history.jsonl"
DEBUG_DIR = CLAUDE_DIR / "debug"

# dt storage
DT_DIR = Path.home() / ".dt"
DB_PATH = DT_DIR / "dt.duckdb"


def ensure_dt_dir() -> Path:
    """Create ~/.dt/ if it doesn't exist."""
    DT_DIR.mkdir(exist_ok=True)
    return DT_DIR
