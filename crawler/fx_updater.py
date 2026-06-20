"""Fetch JPY→KRW (and USD) once and cache in SQLite.

Run daily via cron or just before the API starts. Falls back to last
cached row if the network call fails.
"""
from __future__ import annotations
from datetime import date
import httpx

from config import FX_API_URL
from db.connection import connect


def update() -> None:
    today = date.today().isoformat()
    conn = connect()
    try:
        existing = conn.execute(
            "SELECT 1 FROM fx_rates WHERE date = ?", (today,)
        ).fetchone()
        if existing:
            print(f"[fx] already cached for {today}")
            return

        try:
            resp = httpx.get(FX_API_URL, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            rates = data.get("rates") or {}
            krw = float(rates.get("KRW"))
            usd = float(rates.get("USD")) if "USD" in rates else None
        except Exception as e:  # noqa: BLE001
            print(f"[fx] fetch failed: {e}")
            return

        conn.execute(
            """INSERT INTO fx_rates(date, jpy_to_krw, jpy_to_usd)
               VALUES (?, ?, ?)
               ON CONFLICT(date) DO UPDATE SET
                   jpy_to_krw = excluded.jpy_to_krw,
                   jpy_to_usd = excluded.jpy_to_usd""",
            (today, krw, usd),
        )
        conn.commit()
        print(f"[fx] {today}: 1 JPY = {krw} KRW, {usd} USD")
    finally:
        conn.close()


def latest_jpy_to_krw() -> float:
    """Return most recent cached rate; falls back to a sensible default."""
    conn = connect()
    try:
        row = conn.execute(
            "SELECT jpy_to_krw FROM fx_rates ORDER BY date DESC LIMIT 1"
        ).fetchone()
        return float(row[0]) if row else 9.5  # rough fallback
    finally:
        conn.close()


def latest_jpy_to_usd() -> float:
    """Most recent cached JPY→USD; fallback ~0.0063 (1 USD ≈ 158 JPY) if missing."""
    conn = connect()
    try:
        row = conn.execute(
            "SELECT jpy_to_usd FROM fx_rates WHERE jpy_to_usd IS NOT NULL ORDER BY date DESC LIMIT 1"
        ).fetchone()
        return float(row[0]) if row else 0.0063
    finally:
        conn.close()


if __name__ == "__main__":
    update()
