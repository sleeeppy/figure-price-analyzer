"""Build the sqlite-vec index from all figure_images on disk.

Iterates figure_images rows, skipping any already-indexed ones, and inserts
DINOv2 embeddings into the figure_embeddings vec0 table. Idempotent.
"""
from __future__ import annotations
import argparse
import time

from db.connection import connect
from embeddings.embedder import get_embedder


def build(rebuild: bool = False, limit: int | None = None) -> None:
    embedder = get_embedder()
    conn = connect()
    try:
        if rebuild:
            print("[build_index] rebuild: wiping figure_embeddings")
            conn.execute("DELETE FROM figure_embeddings")
            conn.commit()

        already = {
            row[0] for row in conn.execute(
                "SELECT figure_image_id FROM figure_embeddings"
            )
        }
        rows = conn.execute(
            "SELECT id, image_path FROM figure_images ORDER BY id"
        ).fetchall()
        todo = [(rid, p) for rid, p in rows if rid not in already]
        if limit:
            todo = todo[:limit]
        print(f"[build_index] {len(todo)} images to embed (skipping {len(already)})")

        t0 = time.time()
        for i, (img_id, path) in enumerate(todo, 1):
            try:
                vec = embedder.embed_path(path, remove_bg=True)
            except Exception as e:  # noqa: BLE001
                print(f"  ! img {img_id} failed: {e}")
                continue
            conn.execute(
                "INSERT INTO figure_embeddings(figure_image_id, embedding) VALUES (?, ?)",
                (img_id, vec.tobytes()),
            )
            if i % 25 == 0:
                conn.commit()
                rate = i / max(1e-6, time.time() - t0)
                print(f"  [{i}/{len(todo)}] {rate:.2f} img/s")

        conn.commit()
        print(f"[build_index] done in {time.time() - t0:.1f}s")
    finally:
        conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild", action="store_true", help="Drop existing vectors first.")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    build(rebuild=args.rebuild, limit=args.limit)
