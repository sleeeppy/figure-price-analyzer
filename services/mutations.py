"""Mutating service ops: append a user photo, add a manual figure,
crawl a single MFC item by URL, autocomplete suggestions.

All extracted from the old FastAPI endpoints — same behavior, just
callable as plain Python functions for the GUI.
"""
from __future__ import annotations
import hashlib
import io
import json
import re
import secrets
from pathlib import Path
from typing import Optional

import httpx
from PIL import Image

from config import IMAGE_DIR
from db.connection import connect
from crawler.fx_updater import latest_jpy_to_krw, latest_jpy_to_usd
from .identify import load_candidate
from .types import FigureCandidate


# User-added figures use ids above this so they never collide with MFC ids.
USER_FIGURE_ID_BASE = 9_000_000


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _next_user_figure_id() -> int:
    conn = connect()
    try:
        row = conn.execute(
            "SELECT COALESCE(MAX(id), ?) + 1 FROM figures WHERE id >= ?",
            (USER_FIGURE_ID_BASE - 1, USER_FIGURE_ID_BASE),
        ).fetchone()
        return int(row[0])
    finally:
        conn.close()


def _save_image_bytes(figure_id: int, raw: bytes, suffix: str = ".jpg") -> Path:
    dest_dir = IMAGE_DIR / str(figure_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{figure_id}-{secrets.token_hex(4)}{suffix}"
    dest = dest_dir / fname
    dest.write_bytes(raw)
    return dest


def _embed_and_index(image_id: int, image_abs_path: str) -> None:
    """Embed one image and insert into the vec0 index. Idempotent on image_id."""
    from embeddings.embedder import get_embedder
    emb = get_embedder()
    vec = emb.embed_path(image_abs_path, remove_bg=True)
    conn = connect()
    try:
        conn.execute("DELETE FROM figure_embeddings WHERE figure_image_id = ?", (image_id,))
        conn.execute(
            "INSERT INTO figure_embeddings(figure_image_id, embedding) VALUES (?, ?)",
            (image_id, vec.tobytes()),
        )
        conn.commit()
    finally:
        conn.close()


def _sniff_suffix(image_bytes: bytes, fallback: str = ".jpg") -> str:
    try:
        with Image.open(io.BytesIO(image_bytes)) as im:
            fmt = (im.format or "").lower()
        if fmt == "jpeg":
            return ".jpg"
        if fmt in ("png", "webp", "bmp", "gif"):
            return "." + fmt
    except Exception:
        pass
    return fallback


def _content_hash(image_bytes: bytes) -> str:
    return hashlib.sha256(image_bytes).hexdigest()


# ---------------------------------------------------------------------------
# /confirm_image — append a photo to an existing figure, then embed it.
# ---------------------------------------------------------------------------

def confirm_image(figure_id: int, image_bytes: bytes) -> tuple[FigureCandidate, int, bool]:
    """Returns (candidate, total_image_count_for_figure, inserted).
    `inserted=False` means the exact same bytes were already on disk for that
    figure (dedup by SHA-256) — common when user clicks "이 사진이 맞아요" twice.
    """
    if not image_bytes:
        raise ValueError("empty image")
    conn = connect()
    try:
        row = conn.execute("SELECT id FROM figures WHERE id = ?", (figure_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        raise LookupError(f"figure {figure_id} not found")

    # Dedup by exact byte hash against existing images on disk.
    digest = _content_hash(image_bytes)
    inserted = True
    conn = connect()
    try:
        existing = conn.execute(
            "SELECT image_path FROM figure_images WHERE figure_id = ?", (figure_id,)
        ).fetchall()
    finally:
        conn.close()
    for r in existing:
        p = Path(r["image_path"])
        if p.exists():
            try:
                if hashlib.sha256(p.read_bytes()).hexdigest() == digest:
                    inserted = False
                    break
            except OSError:
                continue

    if inserted:
        abs_path = _save_image_bytes(figure_id, image_bytes, _sniff_suffix(image_bytes))
        conn = connect()
        try:
            cur = conn.execute(
                "INSERT INTO figure_images (figure_id, image_path, source) "
                "VALUES (?, ?, 'user_confirm')",
                (figure_id, str(abs_path)),
            )
            image_id = cur.lastrowid
            conn.commit()
        finally:
            conn.close()
        _embed_and_index(image_id, str(abs_path))

    conn = connect()
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM figure_images WHERE figure_id = ?", (figure_id,)
        ).fetchone()[0]
    finally:
        conn.close()

    cand = load_candidate(
        figure_id,
        distance=0.0,
        jpy_to_krw=latest_jpy_to_krw(),
        jpy_to_usd=latest_jpy_to_usd(),
    )
    return cand, count, inserted


# ---------------------------------------------------------------------------
# /add_manual — create a new figure from a typed form + reference image
# ---------------------------------------------------------------------------

def add_manual(*, name_en: str, image_bytes: bytes,
               character_name: str = "", origin: str = "",
               maker: str = "", scale: str = "",
               release_date: str = "", msrp_jpy: str = "") -> tuple[FigureCandidate, int]:
    """Returns (candidate, new_figure_id)."""
    name_en = name_en.strip()
    if not name_en:
        raise ValueError("name_en is required")
    if not image_bytes:
        raise ValueError("image is required")
    msrp_int: Optional[int] = None
    if msrp_jpy.strip():
        try:
            msrp_int = int(float(msrp_jpy.replace(",", "")))
        except ValueError as e:
            raise ValueError(f"msrp_jpy not a number: {msrp_jpy!r}") from e

    new_id = _next_user_figure_id()
    abs_path = _save_image_bytes(new_id, image_bytes, _sniff_suffix(image_bytes))

    conn = connect()
    try:
        conn.execute(
            """INSERT INTO figures (id, name_en, maker, character_name, origin,
                                    release_date, msrp_jpy, raw_meta_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                new_id, name_en, maker.strip() or None,
                character_name.strip() or None, origin.strip() or None,
                release_date.strip() or None, msrp_int,
                json.dumps({"source": "user_manual", "scale": scale.strip() or None}),
            ),
        )
        cur = conn.execute(
            "INSERT INTO figure_images (figure_id, image_path, source) VALUES (?, ?, 'manual')",
            (new_id, str(abs_path)),
        )
        image_id = cur.lastrowid
        conn.commit()
    finally:
        conn.close()

    _embed_and_index(image_id, str(abs_path))

    cand = load_candidate(
        new_id, distance=0.0,
        jpy_to_krw=latest_jpy_to_krw(),
        jpy_to_usd=latest_jpy_to_usd(),
    )
    return cand, new_id


# ---------------------------------------------------------------------------
# /add_by_mfc — crawl a single MFC item by URL or bare id.
# ---------------------------------------------------------------------------

def add_by_mfc(url_or_id: str) -> tuple[FigureCandidate, bool]:
    """Returns (candidate, inserted). `inserted=False` if the figure was
    already in the DB; in that case we just return the existing row.
    """
    m = re.search(r"/item/(\d+)", url_or_id) or re.match(r"^\s*(\d+)\s*$", url_or_id)
    if not m:
        raise ValueError(f"unrecognized MFC URL or id: {url_or_id!r}")
    item_id = int(m.group(1))

    from crawler.mfc_crawler import (
        _client as mfc_client,
        _get as mfc_get,
        parse_detail,
        upsert_figure,
    )

    conn = connect()
    try:
        already = conn.execute("SELECT 1 FROM figures WHERE id = ?", (item_id,)).fetchone()
    finally:
        conn.close()

    inserted = False
    if already is None:
        with mfc_client() as client:
            try:
                html = mfc_get(client, f"https://myfigurecollection.net/item/{item_id}")
            except httpx.HTTPError as e:
                raise IOError(f"MFC fetch failed for item {item_id}: {e}") from e
            try:
                fig = parse_detail(html, item_id)
            except Exception as e:  # noqa: BLE001
                raise IOError(f"MFC parse failed for item {item_id}: {e}") from e
            upsert_figure(fig, client)
        # Re-embed any newly-inserted images.
        from embeddings.build_index import build as build_emb_index
        build_emb_index(limit=None)
        inserted = True

    cand = load_candidate(
        item_id, distance=0.0,
        jpy_to_krw=latest_jpy_to_krw(),
        jpy_to_usd=latest_jpy_to_usd(),
    )
    return cand, inserted


# ---------------------------------------------------------------------------
# /suggest — autocomplete distinct values from `figures`
# ---------------------------------------------------------------------------

_SUGGEST_FIELDS = {"character_name", "origin", "maker", "name_en"}


def suggest(field: str, q: str, limit: int = 8) -> list[tuple[str, int]]:
    if field not in _SUGGEST_FIELDS:
        raise ValueError(f"field must be one of {sorted(_SUGGEST_FIELDS)}")
    q = q.strip()
    conn = connect()
    try:
        if q:
            rows = conn.execute(
                f"""SELECT {field} AS v, COUNT(*) AS n FROM figures
                    WHERE {field} IS NOT NULL AND LOWER({field}) LIKE ?
                    GROUP BY {field} ORDER BY n DESC, {field} LIMIT ?""",
                (f"%{q.lower()}%", limit),
            ).fetchall()
        else:
            rows = conn.execute(
                f"""SELECT {field} AS v, COUNT(*) AS n FROM figures
                    WHERE {field} IS NOT NULL
                    GROUP BY {field} ORDER BY n DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [(r["v"], r["n"]) for r in rows]
    finally:
        conn.close()
