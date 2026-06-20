"""Gemini Google-Search-grounded lookup. Wraps api.rerank.web_lookup so the
GUI doesn't depend on the (now-defunct) FastAPI layer.
"""
from __future__ import annotations
import io
import tempfile
from pathlib import Path

from PIL import Image

from crawler.fx_updater import latest_jpy_to_krw, latest_jpy_to_usd
from api.rerank import web_lookup as gemini_web_lookup
from .types import LookupCandidate, LookupObservation, LookupResult


def lookup(image_bytes: bytes, hint: str = "") -> LookupResult:
    if not image_bytes:
        return LookupResult(error="empty image")

    # Save to a tempfile because gemini_web_lookup wants a path.
    suffix = ".jpg"
    try:
        with Image.open(io.BytesIO(image_bytes)) as im:
            fmt = (im.format or "").lower()
            if fmt and fmt != "jpeg":
                suffix = "." + fmt
    except Exception:
        pass

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(image_bytes)
        query_path = f.name
    try:
        raw = gemini_web_lookup(query_path, hint=hint)
    finally:
        Path(query_path).unlink(missing_ok=True)

    if raw is None:
        return LookupResult(error="Gemini not configured (GEMINI_API_KEY missing).")
    if raw.get("error"):
        return LookupResult(error=raw["error"], citations=raw.get("citations", []))

    jpy_to_krw = latest_jpy_to_krw()
    jpy_to_usd = latest_jpy_to_usd()
    usd_to_krw = (jpy_to_krw / jpy_to_usd) if jpy_to_usd else 0.0

    def to_krw(price: float, ccy: str) -> int | None:
        if ccy == "JPY":
            return int(round(price * jpy_to_krw))
        if ccy == "USD":
            return int(round(price * usd_to_krw))
        return None

    cands_raw = raw.get("candidates") or []
    candidates: list[LookupCandidate] = []
    for c in cands_raw[:3]:
        msrp_jpy = c.get("msrp_jpy")
        msrp_krw = int(round(float(msrp_jpy) * jpy_to_krw)) if isinstance(msrp_jpy, (int, float)) and msrp_jpy > 0 else None
        obs = []
        for o in (c.get("observations") or []):
            try:
                price = float(o.get("price"))
            except (TypeError, ValueError):
                continue
            ccy = (o.get("currency") or "").upper()
            obs.append(LookupObservation(
                store=str(o.get("store", "")),
                price=price,
                currency=ccy,
                price_krw=to_krw(price, ccy),
                url=o.get("url"),
            ))
        # Drop product-page URLs accidentally placed in image_url
        iu = (c.get("image_url") or "").strip().lower().split("?", 1)[0]
        image_url = c.get("image_url") if iu.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif")) else None
        candidates.append(LookupCandidate(
            name_en=c.get("name_en"),
            character_name=c.get("character_name"),
            origin=c.get("origin"),
            maker=c.get("maker"),
            scale=c.get("scale"),
            msrp_jpy=msrp_jpy if isinstance(msrp_jpy, int) else None,
            msrp_krw=msrp_krw,
            release_date=c.get("release_date"),
            source_url=c.get("source_url"),
            image_url=image_url,
            observations=obs,
            confidence=c.get("confidence"),
            why_this_match=c.get("why_this_match"),
        ))

    return LookupResult(
        candidates=candidates,
        notes=raw.get("notes"),
        citations=raw.get("citations", []),
    )
