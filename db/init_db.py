"""Initialize the SQLite database.

Creates all normalized tables from schema.sql plus the sqlite-vec
virtual table for embeddings. Safe to run multiple times.
"""
from __future__ import annotations
from pathlib import Path
from db.connection import connect
from config import EMBED_DIM

SCHEMA_FILE = Path(__file__).parent / "schema.sql"


def init() -> None:
    conn = connect()
    try:
        # 1. Normalized tables
        with open(SCHEMA_FILE, "r", encoding="utf-8") as f:
            conn.executescript(f.read())

        # 2. Vector virtual table. We use the figure_image_id as the PK so
        #    we can JOIN directly to figure_images on rowid.
        conn.execute(
            f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS figure_embeddings USING vec0(
                figure_image_id INTEGER PRIMARY KEY,
                embedding       float[{EMBED_DIM}]
            )
            """
        )

        # 3. Sanity check
        (vec_version,) = conn.execute("SELECT vec_version()").fetchone()
        print(f"[init_db] sqlite-vec version: {vec_version}")
        print(f"[init_db] DB ready at: {conn.execute('PRAGMA database_list').fetchall()}")
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    init()
