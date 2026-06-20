"""SQLite connection with sqlite-vec extension loaded.

macOS's bundled sqlite often supports load_extension when Python is from
python.org or Homebrew. If your environment disables it, install
`pysqlite3-binary` and this module will use it transparently.
"""
from __future__ import annotations
import sqlite3 as _stdlib_sqlite

try:
    import pysqlite3 as sqlite3  # type: ignore
except ImportError:                                  # pragma: no cover
    sqlite3 = _stdlib_sqlite                         # type: ignore

import sqlite_vec
from config import DB_PATH


def connect() -> "sqlite3.Connection":
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    # Load sqlite-vec
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn
