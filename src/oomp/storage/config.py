"""Local SQLite path selection; construction never creates files."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def database_path(explicit: str | os.PathLike[str] | None = None) -> Path:
    if explicit is not None:
        candidate = os.fspath(explicit)
        if not candidate.strip() or candidate == ":memory:":
            raise ValueError("database path must name a durable file")
        return Path(candidate).expanduser().resolve()

    override = os.environ.get("OOMP_DB_PATH")
    if override is not None and not override.strip():
        raise ValueError("OOMP_DB_PATH must not be blank")
    if override is not None:
        if override == ":memory:":
            raise ValueError("OOMP_DB_PATH must name a durable file")
        return Path(override).expanduser().resolve()

    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return (base / "OOMP" / "events.sqlite3").expanduser().resolve()
    if sys.platform == "darwin":
        return (Path.home() / "Library" / "Application Support" / "OOMP" / "events.sqlite3").resolve()
    xdg = os.environ.get("XDG_DATA_HOME", "")
    base = Path(xdg).expanduser() if xdg.strip() else Path.home() / ".local" / "share"
    return (base / "oomp" / "events.sqlite3").resolve()