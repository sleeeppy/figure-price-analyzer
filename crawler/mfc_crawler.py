"""MyFigureCollection crawler.

Strategy:
  1. Iterate seed browse URLs (paginated listings).
  2. Extract item IDs from each listing page.
  3. Fetch /item/{id} detail pages.
  4. Parse meta, MSRP, Loose/MIB price, image URLs.
  5. Filter: scale must be 1/7 or 1/8, classification 'Prepainted'.
  6. Download images locally, upsert into DB.

Important notes on MFC HTML:
  MFC's HTML structure is stable but uses generic class names. The selectors
  below are placeholders based on common patterns. **VERIFY in browser
  devtools and adjust if a field comes back None for known-good items**.

Politeness:
  - 2.5s delay between requests (configurable in config.py)
  - Sets a descriptive User-Agent
  - Respects robots.txt manually (you should re-check before scaling up)
"""
from __future__ import annotations
import argparse
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse

import httpx
from bs4 import BeautifulSoup

from config import (
    MFC_BASE,
    MFC_SEED_URLS,
    MFC_REQUEST_DELAY_SEC,
    MFC_IMAGE_DELAY_SEC,
    MFC_USER_AGENT,
    IMAGE_DIR,
)
from db.connection import connect

# Scale filter dropped — accept any scale. Classification still gates to Prepainted.
ALLOWED_CLASSIFICATIONS = {"Prepainted", "Pre-painted"}


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def _client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": MFC_USER_AGENT},
        follow_redirects=True,
        timeout=30,
    )


def _get(client: httpx.Client, url: str) -> str:
    resp = client.get(url)
    resp.raise_for_status()
    time.sleep(MFC_REQUEST_DELAY_SEC)
    return resp.text


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

ITEM_LINK_RE = re.compile(r"/item/(\d+)")


@dataclass
class ParsedFigure:
    id: int
    name_en: Optional[str]
    maker: Optional[str]
    character_name: Optional[str]
    origin: Optional[str]
    release_date: Optional[str]
    msrp_jpy: Optional[int]
    image_url: Optional[str]
    # scale/classification kept transiently for filter; not persisted.
    scale: Optional[str]
    classification: Optional[str]
    raw_fields: dict
    partner_prices: list[tuple[str, float, str]] = field(default_factory=list)


def extract_item_ids(listing_html: str) -> list[int]:
    """Pull MFC item IDs from a listing/browse page."""
    soup = BeautifulSoup(listing_html, "lxml")
    ids: set[int] = set()
    for a in soup.find_all("a", href=True):
        m = ITEM_LINK_RE.search(a["href"])
        if m:
            ids.add(int(m.group(1)))
    return sorted(ids)


def next_page_url(listing_url: str, current_html: str) -> Optional[str]:
    """Find the 'next page' link on a browse listing, if any."""
    soup = BeautifulSoup(current_html, "lxml")
    # MFC paginator uses rel='next' on the link sometimes
    nxt = soup.find("a", rel="next")
    if nxt and nxt.get("href"):
        return urljoin(MFC_BASE, nxt["href"])
    # Fallback: bump &page= manually
    parsed = urlparse(listing_url)
    qs = parse_qs(parsed.query)
    page = int(qs.get("page", ["1"])[0])
    qs["page"] = [str(page + 1)]
    new = parsed._replace(query=urlencode({k: v[0] for k, v in qs.items()}))
    # Hard safety cap. MFC's 1/7 catalog is ~11k items × 100/page = ~110 pages,
    # but Garage-Kits/non-prepainted skips dilute that. 500 leaves headroom.
    return urlunparse(new) if page < 500 else None


# ---- detail page parsers --------------------------------------------------
# Each helper is tolerant of structural changes: returns None on miss.

def _data_field(soup: BeautifulSoup, label: str) -> Optional[str]:
    """MFC detail pages render fields as
        <div class="data-field">
          <div class="data-label">Label</div>
          <div class="data-value">Value</div>
        </div>
    Verified against /item/* in 2026-05. Label match is exact (case-insensitive).
    """
    for lab in soup.select("div.data-field > div.data-label"):
        if lab.get_text(strip=True).lower() == label.lower():
            val = lab.find_next_sibling("div", class_="data-value")
            if val:
                txt = val.get_text(" ", strip=True)
                if txt:
                    return txt
    return None


def _parse_scale(soup: BeautifulSoup) -> Optional[str]:
    """Scale lives inside the 'Dimensions' value, e.g. '1/ 7 H= 240 mm'."""
    dims = _data_field(soup, "Dimensions")
    if not dims:
        return None
    m = re.search(r"1\s*/\s*(\d+)", dims)
    return f"1/{m.group(1)}" if m else None


def _parse_msrp_jpy(soup: BeautifulSoup) -> Optional[int]:
    """MSRP is embedded in the 'Releases' value, e.g. '04/2026 ... 10,000 JPY ( USD )'."""
    raw = _data_field(soup, "Releases") or _data_field(soup, "Release")
    if not raw:
        return None
    m = re.search(r"([\d,]+)\s*JPY", raw)
    if m:
        return int(m.group(1).replace(",", ""))
    m2 = re.search(r"[¥￥]\s*([\d,]+)", raw)
    return int(m2.group(1).replace(",", "")) if m2 else None


def _parse_release_date(soup: BeautifulSoup) -> Optional[str]:
    """MFC Releases values come in two forms:
      - 'MM/DD/YYYY as ...' when the exact day is known
      - 'MM/YYYY as ...'     when only the month is known
    Normalize to ISO 'YYYY-MM-DD' or 'YYYY-MM'. Check MM/DD/YYYY first so the
    bare '(\\d{2}/\\d{4})' fallback doesn't swallow 'DD/YYYY' of a full date.
    """
    raw = _data_field(soup, "Releases") or _data_field(soup, "Release")
    if not raw:
        return None
    m = re.match(r"\s*(\d{2})/(\d{2})/(\d{4})", raw)
    if m:
        mm, dd, yyyy = m.groups()
        return f"{yyyy}-{mm}-{dd}"
    m2 = re.match(r"\s*(\d{2})/(\d{4})", raw)
    if m2:
        mm, yyyy = m2.groups()
        return f"{yyyy}-{mm}"
    return None


def _parse_name(soup: BeautifulSoup) -> tuple[Optional[str], Optional[str]]:
    """MFC has no separate Name fields. The <h1> holds the canonical English title,
    e.g. 'Blue Archive - Hayase Yuuka - 1/7 - Taisou-fuku (Iousen)'. JP name is
    not consistently exposed on the detail page — leave None.
    """
    h1 = soup.find("h1")
    name_en = h1.get_text(" ", strip=True) if h1 else None
    return name_en, None


# Matches "9,580 JPY", "141.62 USD", "(87.99 USD)" — store name handled separately.
_PRICE_CCY_RE = re.compile(r"([\d]{1,3}(?:,\d{3})*(?:\.\d+)?|\d+\.\d+)\s*(JPY|USD|EUR|GBP|HKD|KRW|CNY|TWD|AUD|CAD)\b")
_BBCODE_PARTNER_RE = re.compile(
    r"""<a[^>]+partnerId=[^>]+>([^<]+)</a>\s*\(\s*([\d,.]+)\s*([A-Z]{3})\s*\)""",
    re.I,
)
_MFC_PARTNER_TAG_RE = re.compile(r"\s*\((?:MFC\s+Partner|MFC)\)\s*$", re.I)


def _clean_store(name: str) -> str:
    """Drop the trailing '(MFC Partner)' tag — partnership status isn't useful
    for price comparison; treat all stores uniformly.
    """
    return _MFC_PARTNER_TAG_RE.sub("", name).strip()


def _parse_partner_prices(soup: BeautifulSoup) -> list[tuple[str, float, str]]:
    """MFC item pages list partner-store asking prices in two places:
      1) Structured "stamp" cards: <div class="stamp"> with <img alt="STORE">
         and a separate price element (e.g. "9,580 JPY").
      2) Free-text bbcode descriptions: "In stock @ <a>STORE</a> (PRICE CCY)".
    Collect both, dedupe by (store, price, currency).
    """
    out: list[tuple[str, float, str]] = []

    # 1) Stamp cards. Store name comes from the logo's alt attribute (most reliable);
    #    price/currency is anywhere in the card's text. Cards without a price token
    #    (e.g. "Available" but unpriced) are skipped.
    for stamp in soup.select("div.stamp"):
        logo = stamp.find("img", class_="stamp-icon")
        store = (logo.get("alt") or "").strip() if logo else ""
        if not store:
            anchor = stamp.find("a", class_="stamp-anchor") or stamp.find("a")
            store = anchor.get_text(strip=True) if anchor else ""
        if not store:
            continue
        text = stamp.get_text(" ", strip=True)
        m = _PRICE_CCY_RE.search(text)
        if not m:
            continue
        try:
            price = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        out.append((_clean_store(store), price, m.group(2).upper()))

    # 2) bbcode free-text descriptions. Regex on raw HTML so we can tie the
    #    partnerId anchor to the price token that follows it.
    for m in _BBCODE_PARTNER_RE.finditer(str(soup)):
        store = m.group(1).strip()
        try:
            price = float(m.group(2).replace(",", ""))
        except ValueError:
            continue
        out.append((_clean_store(store), price, m.group(3).upper()))

    # Dedupe by (store, price, currency) — bbcode often duplicates a stamp entry.
    seen: set[tuple[str, float, str]] = set()
    deduped: list[tuple[str, float, str]] = []
    for row in out:
        if row in seen:
            continue
        seen.add(row)
        deduped.append(row)
    return deduped


def _parse_image(soup: BeautifulSoup) -> Optional[str]:
    """One main photo per figure. MFC serves the same item picture at two sizes:
    /upload/items/0/<id>-<hash>.jpg (thumbnail) and /upload/items/1/<id>-<hash>.jpg (big).
    Prefer the /1/ variant; fall back to /0/ if /1/ isn't on the page.
    """
    big = small = None
    for img in soup.select("img"):
        src = img.get("data-src") or img.get("src") or ""
        if "/upload/items/1/" in src and big is None:
            big = urljoin(MFC_BASE, src)
        elif "/upload/items/0/" in src and small is None:
            small = urljoin(MFC_BASE, src)
    return big or small


_MAKER_SUFFIX_RE = re.compile(r"\s+as\s+(Manufacturer|Circle|Distributor|Sculptor|Artist).*$", re.I)


def _clean_maker(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return raw
    return _MAKER_SUFFIX_RE.sub("", raw).strip() or None


def parse_detail(html: str, item_id: int) -> ParsedFigure:
    soup = BeautifulSoup(html, "lxml")

    name_en, _ = _parse_name(soup)
    maker   = _clean_maker(_data_field(soup, "Company"))
    scale   = _parse_scale(soup)
    classif = _data_field(soup, "Category")
    character = _data_field(soup, "Character")
    origin    = _data_field(soup, "Origin")
    release   = _parse_release_date(soup)

    msrp = _parse_msrp_jpy(soup)
    image_url = _parse_image(soup)
    partner_prices = _parse_partner_prices(soup)

    raw = {
        "name_en": name_en, "maker_raw": _data_field(soup, "Company"),
        "scale": scale, "classification": classif, "character": character,
        "origin": origin, "release": release, "msrp_raw": msrp,
        "image_url": image_url, "partner_count": len(partner_prices),
    }

    return ParsedFigure(
        id=item_id,
        name_en=name_en,
        maker=maker,
        character_name=character,
        origin=origin,
        release_date=release,
        msrp_jpy=msrp,
        image_url=image_url,
        scale=scale,
        classification=classif,
        raw_fields=raw,
        partner_prices=partner_prices,
    )


def passes_filter(fig: ParsedFigure) -> bool:
    """Any scale, Prepainted classification."""
    if fig.classification and fig.classification.split()[0] not in ALLOWED_CLASSIFICATIONS:
        return False
    return True


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def download_image(client: httpx.Client, url: str, dest: Path) -> bool:
    if dest.exists():
        return True
    try:
        resp = client.get(url)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
        time.sleep(MFC_IMAGE_DELAY_SEC)
        return True
    except Exception as e:  # noqa: BLE001
        print(f"  ! image download failed {url}: {e}")
        return False


def upsert_figure(fig: ParsedFigure, client: httpx.Client) -> None:
    conn = connect()
    try:
        conn.execute(
            """
            INSERT INTO figures (id, name_en, maker, character_name, origin,
                                 release_date, msrp_jpy, raw_meta_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name_en        = excluded.name_en,
                maker          = excluded.maker,
                character_name = excluded.character_name,
                origin         = excluded.origin,
                release_date   = excluded.release_date,
                msrp_jpy       = excluded.msrp_jpy,
                raw_meta_json  = excluded.raw_meta_json,
                updated_at     = CURRENT_TIMESTAMP
            """,
            (
                fig.id, fig.name_en, fig.maker, fig.character_name, fig.origin,
                fig.release_date, fig.msrp_jpy,
                json.dumps(fig.raw_fields, ensure_ascii=False),
            ),
        )

        # Refresh canonical MFC photo only — leave user-confirmed images alone.
        conn.execute(
            "DELETE FROM figure_images WHERE figure_id = ? AND source = 'mfc'",
            (fig.id,),
        )
        if fig.image_url:
            figure_image_dir = IMAGE_DIR / str(fig.id)
            figure_image_dir.mkdir(parents=True, exist_ok=True)
            fname = Path(urlparse(fig.image_url).path).name
            local = figure_image_dir / fname
            if download_image(client, fig.image_url, local):
                conn.execute(
                    "INSERT INTO figure_images (figure_id, image_path, image_url, source) VALUES (?, ?, ?, 'mfc')",
                    (fig.id, str(local), fig.image_url),
                )

        # Replace partner-price snapshot. These are current asking prices and
        # only meaningful as a fresh snapshot — drop stale rows for this figure.
        conn.execute("DELETE FROM partner_prices WHERE figure_id = ?", (fig.id,))
        if fig.partner_prices:
            now = datetime.utcnow().isoformat(timespec="seconds")
            conn.executemany(
                """INSERT INTO partner_prices(figure_id, store, price, currency, observed_at)
                   VALUES (?, ?, ?, ?, ?)""",
                [(fig.id, store, price, ccy, now) for store, price, ccy in fig.partner_prices],
            )

        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def _existing_figure_ids() -> set[int]:
    conn = connect()
    try:
        return {row[0] for row in conn.execute("SELECT id FROM figures")}
    finally:
        conn.close()


def refresh_existing(max_items: Optional[int] = None) -> None:
    """Re-fetch every figure already in the DB by id, updating metadata and
    partner_prices in place. Bypasses listing pagination entirely.
    """
    ids = sorted(_existing_figure_ids())
    if max_items:
        ids = ids[:max_items]
    print(f"[refresh] {len(ids)} figures to re-fetch")
    saved = skipped = 0
    with _client() as client:
        for i, item_id in enumerate(ids, 1):
            try:
                detail_html = _get(client, f"{MFC_BASE}/item/{item_id}")
            except httpx.HTTPError as e:
                print(f"  ! item {item_id} fetch failed: {e}")
                continue
            try:
                fig = parse_detail(detail_html, item_id)
            except Exception as e:  # noqa: BLE001
                print(f"  ! item {item_id} parse failed: {e}")
                continue
            if not passes_filter(fig):
                skipped += 1
                continue
            upsert_figure(fig, client)
            saved += 1
            if i % 25 == 0:
                print(f"  [{i}/{len(ids)}] refreshed (saved={saved}, skipped={skipped})")
    print(f"[refresh] done. saved={saved}  skipped={skipped}")


def crawl(seed_urls: Iterable[str], max_items: Optional[int] = None,
          refresh: bool = False) -> None:
    seen_ids: set[int] = set()
    already_in_db = set() if refresh else _existing_figure_ids()
    saved = 0
    skipped = 0
    cached = 0

    # How many *consecutive* pages of all-already-seen IDs to tolerate before
    # giving up on a seed. 1 was too aggressive — popularity-sorted listings
    # start with pages full of already-known top items; we need to push past
    # those to discover the long tail.
    EARLY_EXIT_STREAK = 30

    with _client() as client:
        for seed in seed_urls:
            page_url: Optional[str] = seed
            consecutive_no_new = 0
            while page_url:
                print(f"[listing] {page_url}")
                try:
                    html = _get(client, page_url)
                except httpx.HTTPError as e:
                    print(f"  ! listing fetch failed: {e}")
                    break

                ids = extract_item_ids(html)
                if not ids:
                    print("  (no items found — stopping this seed)")
                    break

                # Early-exit: stop after EARLY_EXIT_STREAK *consecutive* pages
                # that contributed zero discovery. A single all-seen page is
                # expected at the top of a popularity-sorted listing when the
                # DB already has the top items; we only give up when we're
                # clearly past anything new.
                if not refresh:
                    new_on_page = sum(
                        1 for i in ids if i not in seen_ids and i not in already_in_db
                    )
                    if new_on_page == 0:
                        consecutive_no_new += 1
                        if consecutive_no_new >= EARLY_EXIT_STREAK:
                            print(f"  (no new items in {EARLY_EXIT_STREAK} pages — stopping seed)")
                            break
                    else:
                        consecutive_no_new = 0

                for item_id in ids:
                    if item_id in seen_ids:
                        continue
                    seen_ids.add(item_id)

                    if item_id in already_in_db:
                        cached += 1
                        continue

                    if max_items and saved >= max_items:
                        print(f"[done] hit max_items={max_items}")
                        return

                    detail_url = f"{MFC_BASE}/item/{item_id}"
                    try:
                        detail_html = _get(client, detail_url)
                    except httpx.HTTPError as e:
                        print(f"  ! item {item_id} fetch failed: {e}")
                        continue

                    try:
                        fig = parse_detail(detail_html, item_id)
                    except Exception as e:  # noqa: BLE001
                        print(f"  ! item {item_id} parse failed: {e}")
                        continue

                    if not passes_filter(fig):
                        skipped += 1
                        print(
                            f"[skip {item_id}] {fig.scale}/{fig.classification or '?'} "
                            f"— {fig.name_en or '(no name)'}"
                        )
                        continue

                    print(
                        f"[item {item_id}] {fig.maker} / {fig.scale} / "
                        f"{fig.name_en} (img={'yes' if fig.image_url else 'NO'}, "
                        f"partners={len(fig.partner_prices)})"
                    )
                    upsert_figure(fig, client)
                    saved += 1

                page_url = next_page_url(page_url, html)

    print(f"[summary] saved={saved}  skipped(filter)={skipped}  cached(db)={cached}  visited={len(seen_ids)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-items", type=int, default=None,
                    help="Stop after saving this many figures (smoke test).")
    ap.add_argument("--seeds", nargs="+", default=None,
                    help="Override seed URLs from config.")
    ap.add_argument("--refresh", action="store_true",
                    help="Bypass skip-if-exists during listing crawl.")
    ap.add_argument("--refresh-existing", action="store_true",
                    help="Skip listings entirely; re-fetch every figure already in DB by id.")
    args = ap.parse_args()
    if args.refresh_existing:
        refresh_existing(max_items=args.max_items)
    else:
        crawl(args.seeds or MFC_SEED_URLS, max_items=args.max_items, refresh=args.refresh)


if __name__ == "__main__":
    main()
