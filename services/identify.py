"""Image → figure identification pipeline.

Lifted out of the old `api/main.py` /identify handler, but called directly
from the GUI (no HTTP envelope, no async). Heavy steps (rembg + DINOv2 +
optional Gemini rerank) take seconds — callers should run this off the UI
thread.
"""
from __future__ import annotations
import io
import tempfile
from pathlib import Path
from typing import Optional

from PIL import Image

from config import RERANK_TOP_K
from db.connection import connect
from embeddings.embedder import get_embedder
from crawler.fx_updater import latest_jpy_to_krw, latest_jpy_to_usd
from api.rerank import rerank as gemini_rerank
from .types import (
    FigureCandidate,
    IdentifyResult,
    PartnerPrice,
    PriceStats,
    RerankMeta,
)


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _vector_search(query_vec_bytes: bytes, k: int) -> list[dict]:
    conn = connect()
    try:
        rows = conn.execute(
            """
            SELECT fe.figure_image_id, fe.distance,
                   fi.figure_id, fi.image_path
            FROM figure_embeddings fe
            JOIN figure_images fi ON fi.id = fe.figure_image_id
            WHERE fe.embedding MATCH ?
              AND k = ?
            ORDER BY fe.distance
            """,
            (query_vec_bytes, k),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _dedupe_to_figures(image_hits: list[dict], max_figures: int) -> list[dict]:
    """Keep the closest image per figure; preserve ranking by distance."""
    out: dict[int, dict] = {}
    for h in image_hits:
        fid = h["figure_id"]
        if fid not in out or h["distance"] < out[fid]["distance"]:
            out[fid] = h
    return sorted(out.values(), key=lambda r: r["distance"])[:max_figures]


def load_candidate(figure_id: int, distance: float, jpy_to_krw: float, jpy_to_usd: float) -> FigureCandidate:
    conn = connect()
    try:
        fig = conn.execute("SELECT * FROM figures WHERE id = ?", (figure_id,)).fetchone()
        if fig is None:
            raise ValueError(f"figure {figure_id} missing")

        imgs = conn.execute(
            "SELECT image_path FROM figure_images WHERE figure_id = ? ORDER BY id",
            (figure_id,),
        ).fetchall()

        msrp_jpy = fig["msrp_jpy"]
        msrp_krw = int(round(msrp_jpy * jpy_to_krw)) if msrp_jpy is not None else None

        usd_to_krw = (jpy_to_krw / jpy_to_usd) if jpy_to_usd else 0.0
        def partner_to_krw(price: float, ccy: str) -> int:
            if ccy == "JPY":
                return int(round(price * jpy_to_krw))
            if ccy == "USD":
                return int(round(price * usd_to_krw))
            return 0

        partner_rows = conn.execute(
            """SELECT store, price, currency FROM partner_prices
               WHERE figure_id = ? ORDER BY currency, price""",
            (figure_id,),
        ).fetchall()
        partners = [
            PartnerPrice(
                store=p["store"],
                price=p["price"],
                currency=p["currency"],
                price_krw=partner_to_krw(p["price"], p["currency"]),
            )
            for p in partner_rows
        ]

        return FigureCandidate(
            figure_id=fig["id"],
            name_en=fig["name_en"],
            maker=fig["maker"],
            character_name=fig["character_name"],
            origin=fig["origin"],
            release_date=fig["release_date"],
            image_paths=[r["image_path"] for r in imgs],
            distance=float(distance),
            price=PriceStats(msrp_jpy=msrp_jpy, msrp_krw=msrp_krw, partners=partners),
        )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def identify(
    image_bytes: bytes,
    *,
    rerank: bool = False,
    k: int = RERANK_TOP_K,
    multi_crop: bool = True,
) -> IdentifyResult:
    """Run the full pipeline. Returns dataclasses ready for the GUI.

    Multi-crop fanout (default on) embeds 5 query variants and merges by
    min-distance per figure_id — same as the old web endpoint.
    """
    if not image_bytes:
        raise ValueError("empty image")

    embedder = get_embedder()
    if multi_crop:
        vecs = embedder.embed_bytes_multi(image_bytes, remove_bg=True)
    else:
        vecs = [embedder.embed_bytes(image_bytes, remove_bg=True)]

    all_hits: list[dict] = []
    for v in vecs:
        all_hits.extend(_vector_search(v.tobytes(), k=max(k * 3, 20)))
    figure_hits = _dedupe_to_figures(all_hits, max_figures=k)

    jpy_to_krw = latest_jpy_to_krw()
    jpy_to_usd = latest_jpy_to_usd()

    if not figure_hits:
        return IdentifyResult(best=None, alternates=[], fx_jpy_to_krw=jpy_to_krw)

    candidates = [
        load_candidate(h["figure_id"], h["distance"], jpy_to_krw, jpy_to_usd)
        for h in figure_hits
    ]

    rerank_meta: Optional[RerankMeta] = None
    best = candidates[0]
    alternates = candidates[1:]

    if rerank and candidates:
        # Look up disk paths for each candidate (gemini_rerank needs file paths,
        # not URLs). One image per figure is enough — we use the first.
        conn = connect()
        try:
            id_list = [c.figure_id for c in candidates]
            qmarks = ",".join("?" * len(id_list))
            rows = conn.execute(
                f"SELECT figure_id, image_path FROM figure_images WHERE figure_id IN ({qmarks})",
                id_list,
            ).fetchall()
            path_by_fid = {r["figure_id"]: r["image_path"] for r in rows}
            cand_paths = [path_by_fid[c.figure_id] for c in candidates if c.figure_id in path_by_fid]
        finally:
            conn.close()

        suffix = ".png"
        # Sniff format from bytes for the tempfile.
        try:
            with Image.open(io.BytesIO(image_bytes)) as im:
                if im.format:
                    suffix = "." + im.format.lower()
        except Exception:
            pass
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(image_bytes)
            query_path = f.name
        try:
            raw = gemini_rerank(query_path, cand_paths)
            idx = int(raw.get("best_index", -1))
            note = None
            if 0 <= idx < len(candidates):
                best = candidates[idx]
                alternates = [c for i, c in enumerate(candidates) if i != idx]
            elif idx == -1:
                note = "Gemini found no confident match."
            rerank_meta = RerankMeta(
                best_index=idx,
                confidence=str(raw.get("confidence", "low")),
                reason=str(raw.get("reason", ""))[:300],
                note=note,
            )
        finally:
            Path(query_path).unlink(missing_ok=True)

    return IdentifyResult(
        best=best,
        alternates=alternates,
        rerank=rerank_meta,
        fx_jpy_to_krw=jpy_to_krw,
    )
