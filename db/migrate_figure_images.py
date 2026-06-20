"""One-shot migration: drop UNIQUE constraint on figure_images.figure_id
and add the `source` column. SQLite has no DROP CONSTRAINT, so we
rebuild the table.

Idempotent: if the new schema is already in place, exits silently.
"""
from __future__ import annotations
from db.connection import connect


def needs_migration(conn) -> bool:
    # Check whether 'source' column exists — proxy for "already migrated".
    cols = [r[1] for r in conn.execute("PRAGMA table_info(figure_images)")]
    return "source" not in cols


def main() -> None:
    conn = connect()
    try:
        if not needs_migration(conn):
            print("[migrate] figure_images already on new schema; nothing to do.")
            return

        print("[migrate] rebuilding figure_images (drop UNIQUE, add source)...")
        conn.executescript("""
            BEGIN;
            CREATE TABLE figure_images_new (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                figure_id   INTEGER NOT NULL,
                image_path  TEXT NOT NULL,
                image_url   TEXT,
                source      TEXT DEFAULT 'mfc',
                FOREIGN KEY (figure_id) REFERENCES figures(id) ON DELETE CASCADE
            );
            INSERT INTO figure_images_new (id, figure_id, image_path, image_url, source)
                SELECT id, figure_id, image_path, image_url, 'mfc' FROM figure_images;
            DROP TABLE figure_images;
            ALTER TABLE figure_images_new RENAME TO figure_images;
            CREATE INDEX IF NOT EXISTS idx_figure_images_figure ON figure_images(figure_id);
            COMMIT;
        """)
        n = conn.execute("SELECT COUNT(*) FROM figure_images").fetchone()[0]
        print(f"[migrate] done. figure_images rows: {n}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
