"""Gemini-powered helpers for the /identify pipeline.

`rerank()` — picks the best of our top-K visual candidates.
`web_lookup()` — fallback when our DB has nothing: Gemini identifies the figure
                 via Google Search grounding and returns structured metadata.

Rerank: GEMINI_MODEL. /lookup: GEMINI_LOOKUP_SEARCH_MODEL + Google Search when enabled,
else GEMINI_LOOKUP_MODEL (3.1, high RPD). Free tier cannot run Search on 3.1-*.
"""
from __future__ import annotations
import json
import re
from pathlib import Path

from google import genai
from google.genai import types
from PIL import Image

from config import (
    GEMINI_API_KEY,
    GEMINI_LOOKUP_MODEL,
    GEMINI_LOOKUP_SEARCH_MODEL,
    GEMINI_LOOKUP_USE_SEARCH,
    GEMINI_MODEL,
)


_client: genai.Client | None = None


def _get_client() -> genai.Client | None:
    global _client
    if not GEMINI_API_KEY:
        return None
    if _client is None:
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


PROMPT = """You are matching anime figure photos to a catalog.

The FIRST image is the user's query photo of a figure.
The remaining images are catalog candidates, in order (index 0, 1, 2, ...).

Task: pick which catalog candidate (if any) depicts the SAME figure as the
query - i.e. the same character, same maker, same sculpt, same scale/version.
Different versions (e.g. swimsuit variant, recolor) count as DIFFERENT.

Respond with strict JSON only, no prose:
{
  "best_index": <0-based int into the candidates, or -1 if no match>,
  "confidence": "high" | "medium" | "low",
  "reason": "<one short sentence>"
}
"""


def _friendly_error(e: Exception, *, model: str | None = None) -> str:
    """Turn google-genai errors into a one-line UI-friendly message.
    Distinguishes short-window throttling (RPM, retry < ~5min) from
    actual daily quota exhaustion.
    """
    model = model or GEMINI_MODEL
    msg = str(e)
    prefix = f"{model} 호출 실패: "
    print(f"[gemini_error] model={model} error={msg!r}")
    if "RESOURCE_EXHAUSTED" in msg or "429" in msg:
        quota_model = re.search(r"'model': '([^']+)'", msg)
        if quota_model and quota_model.group(1) != model:
            prefix = f"{quota_model.group(1)} 한도 초과 (요청 모델 {model}): "
        m = re.search(r"retry in ([\d.]+)s", msg) or re.search(r"retryDelay'?:\s*'?(\d+)s", msg)
        secs: float | None = None
        if m:
            try:
                secs = float(m.group(1))
            except ValueError:
                secs = None
        # Per-minute throttling vs daily exhaustion: distinguish by retry delay.
        if secs is not None and secs <= 300:
            s = int(round(secs))
            return f"{prefix}호출이 몰렸어요. {s}초만 기다렸다 다시 눌러주세요. (분당 한도)"
        if secs is not None:
            mins = int(round(secs / 60))
            return f"{prefix}무료 한도를 다 썼어요. {mins}분 후 다시 시도하거나, 내일 다시 써주세요."
        if model.startswith("gemini-3.") and "google_search" not in msg.lower():
            return (
                f"{prefix}무료 티어에서는 3.1 모델에 Google Search를 쓸 수 없어요. "
                f".env에 GEMINI_LOOKUP_SEARCH_MODEL=gemini-2.5-flash 를 두거나 유료 플랜을 켜주세요."
            )
        detail = msg[:500].replace("\n", " ")
        return f"{prefix}한도에 걸렸어요. 원문: {detail}"
    return f"{prefix}{msg[:240]}"


# Free tier: Search Grounding on 2.5-* (~1.5K RPD) >> Web Grounding on 3.1-* (~500).
_LOOKUP_SEARCH_FALLBACK = "gemini-2.5-flash"


def _lookup_api_model(*, use_search: bool) -> str:
    if use_search:
        return GEMINI_LOOKUP_SEARCH_MODEL
    return GEMINI_LOOKUP_MODEL


def _lookup_search_models(primary: str) -> list[str]:
    """Models to try for grounded lookup, highest-quota first."""
    models: list[str] = []
    for m in (primary, _LOOKUP_SEARCH_FALLBACK):
        if m not in models:
            models.append(m)
    return models


def _lookup_generate(
    client: genai.Client,
    *,
    model: str,
    prompt: str,
    img: types.Part,
    use_search: bool,
):
    cfg = types.GenerateContentConfig(temperature=0.0)
    if use_search:
        cfg.tools = [types.Tool(google_search=types.GoogleSearch())]
    return client.models.generate_content(
        model=model,
        contents=[prompt, img],
        config=cfg,
    )


def _should_fallback_lookup_without_search(exc: Exception) -> bool:
    msg = str(exc)
    if "RESOURCE_EXHAUSTED" not in msg and "429" not in msg:
        return False
    # 3.1 + Search on free tier, or Search daily cap on 2.5-*.
    return True


def _load_image_part(path: str) -> types.Part | None:
    """Read a local image into a Part the SDK can send."""
    p = Path(path)
    if not p.exists():
        return None
    mime = "image/jpeg"
    suffix = p.suffix.lower()
    if suffix == ".png":
        mime = "image/png"
    elif suffix == ".webp":
        mime = "image/webp"
    return types.Part.from_bytes(data=p.read_bytes(), mime_type=mime)


def rerank(query_image_path: str, candidate_image_paths: list[str]) -> dict:
    """Return {'best_index', 'confidence', 'reason'} or a fallback dict."""
    client = _get_client()
    if client is None:
        return {"best_index": 0, "confidence": "low",
                "reason": "GEMINI_API_KEY not set; using top-1 from vector search."}
    if not candidate_image_paths:
        return {"best_index": -1, "confidence": "low", "reason": "no candidates"}

    query_part = _load_image_part(query_image_path)
    if query_part is None:
        return {"best_index": 0, "confidence": "low",
                "reason": f"query image missing on disk: {query_image_path}"}

    parts: list = [PROMPT, query_part]
    for p in candidate_image_paths:
        part = _load_image_part(p)
        if part is not None:
            parts.append(part)

    try:
        resp = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=parts,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.0,
            ),
        )
        text = (resp.text or "").strip()
    except Exception as e:  # noqa: BLE001
        return {"best_index": 0, "confidence": "low",
                "reason": _friendly_error(e, model=GEMINI_MODEL)}

    # response_mime_type=json should already give us clean JSON, but strip fences just in case.
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    try:
        data = json.loads(text)
        idx = int(data.get("best_index", -1))
        if idx >= len(candidate_image_paths):
            idx = -1
        return {
            "best_index": idx,
            "confidence": str(data.get("confidence", "low")),
            "reason": str(data.get("reason", ""))[:200],
        }
    except Exception:
        return {"best_index": 0, "confidence": "low",
                "reason": f"could not parse Gemini reply: {text[:120]}"}


# ---------------------------------------------------------------------------
# Fallback: external lookup with Google Search grounding
# ---------------------------------------------------------------------------

LOOKUP_PROMPT = """OUTPUT ONLY JSON. No prose, no markdown fences, no preface.
Your entire response must be exactly one JSON object starting with `{` and
ending with `}`. Do not write anything before the `{` or after the `}`.

Task: identify an anime/game prepainted figure from the photo.

Same character often has many *different* figure releases (different makers,
scales, poses, outfits). Each is a distinct product. **Pay attention to pose,
outfit, base, and visible scale clues** before committing — character match
alone is not enough.

Use Google Search to find UP TO 3 distinct product candidates that could match.
Order them most-likely first.

For EACH candidate provide:
- exact product name (English),
- character / series / maker / scale,
- official MSRP in JPY,
- **image_url (REQUIRED)** — a *direct image file* URL ending in .jpg/.jpeg/.png/.webp
  that renders the figure. Prefer these sources in order:
    1. static.myfigurecollection.net/upload/items/1/<id>-<hash>.jpg (MFC main shot),
    2. goodsmile.info/.../<file>.jpg (GSC official product image),
    3. img.amiami.com/.../<file>.jpg (AmiAmi product shot).
  Do NOT return product *page* URLs here (e.g. /product/15730/Foo.html). If you
  cannot find a direct image URL, leave this field as null — never a page URL.
- 2-6 current retail listings (store + asking price + currency) — prefer
  AmiAmi, Solaris Japan, Nin-Nin Game, Mandarake, JFigure, eBay, Amazon JP,
- a one-sentence "why_this_match" anchored in *visual* cues you observed.

{USER_HINT}

Respond with strict JSON only, no prose:
{
  "candidates": [
    {
      "name_en": "<full product title>",
      "character_name": "<character>",
      "origin": "<series/franchise>",
      "maker": "<manufacturer>",
      "scale": "<e.g. 1/7 or null>",
      "msrp_jpy": <integer or null>,
      "release_date": "<YYYY-MM or YYYY-MM-DD or null>",
      "source_url": "<canonical product page URL (MFC item page preferred)>",
      "image_url": "<direct image URL of the figure>",
      "observations": [
        {"store": "<name>", "price": <number>,
         "currency": "JPY"|"USD"|"EUR"|...,
         "url": "<listing URL>"}
      ],
      "confidence": "high" | "medium" | "low",
      "why_this_match": "<one short sentence anchored in visible features>"
    }
  ],
  "notes": "<one optional overall remark, e.g. ambiguity warnings>"
}

If you genuinely cannot identify anything, return candidates: []. Never invent
prices or URLs — omit fields you can't verify.

REMINDER: Reply with ONLY the JSON object. No commentary before or after.
Begin your response with `{` and end it with `}`.
"""


def web_lookup(query_image_path: str, hint: str = "") -> dict | None:
    """Identify a figure from a photo; uses Google Search when configured.

    Returns the structured JSON dict, or None if not configured / call failed.
    `hint` is an optional natural-language nudge from the user
    (e.g. "Kadokawa KDcolle 1/7 version") used when the first lookup was wrong.
    """
    client = _get_client()
    if client is None:
        return None
    img = _load_image_part(query_image_path)
    if img is None:
        return None

    user_hint_block = ""
    if hint and hint.strip():
        user_hint_block = (
            "User hint (treat as a strong but not absolute prior; still verify "
            f"against the photo): \"{hint.strip()[:300]}\""
        )
    prompt = LOOKUP_PROMPT.replace("{USER_HINT}", user_hint_block)

    use_search = GEMINI_LOOKUP_USE_SEARCH
    model = _lookup_api_model(use_search=use_search)
    fallback_note = ""
    resp = None
    last_exc: Exception | None = None

    if use_search:
        for try_model in _lookup_search_models(model):
            try:
                resp = _lookup_generate(
                    client,
                    model=try_model,
                    prompt=prompt,
                    img=img,
                    use_search=True,
                )
                model = try_model
                break
            except Exception as e:  # noqa: BLE001
                last_exc = e
                if not _should_fallback_lookup_without_search(e):
                    return {"error": _friendly_error(e, model=try_model)}
                print(
                    f"[web_lookup] search failed ({e!r}); "
                    f"next model in chain (after {try_model})"
                )
        if resp is None and last_exc is not None:
            model = GEMINI_LOOKUP_MODEL
            use_search = False
            fallback_note = (
                "Google Search 한도/무료 티어 제한으로 "
                f"{GEMINI_LOOKUP_MODEL} 오프라인 추정으로 전환했어요."
            )
            print(
                f"[web_lookup] all search models exhausted ({last_exc!r}); "
                f"fallback model={model}"
            )
            try:
                resp = _lookup_generate(
                    client, model=model, prompt=prompt, img=img, use_search=False,
                )
            except Exception as e2:  # noqa: BLE001
                return {"error": _friendly_error(e2, model=model)}
    else:
        try:
            resp = _lookup_generate(
                client, model=model, prompt=prompt, img=img, use_search=False,
            )
        except Exception as e:  # noqa: BLE001
            return {"error": _friendly_error(e, model=model)}

    text = (resp.text or "").strip()

    # Helpful debug log — we want to see what Gemini Lite actually emits
    # when it strays from the JSON-only instruction.
    print(f"[web_lookup] raw reply ({len(text)} chars): {text[:400]!r}")

    # Strip code fences and any stray prose around the JSON body.
    text_clean = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    # Greedy match so we capture the outermost { ... }; balanced braces aren't
    # important here because the schema only has one top-level object.
    m = re.search(r"\{[\s\S]*\}", text_clean)
    if not m:
        snippet = text[:200].replace("\n", " ")
        return {"error": f"Gemini가 JSON 대신 텍스트를 반환했어요: \"{snippet}…\""}
    try:
        data = json.loads(m.group(0))
    except Exception as e:  # noqa: BLE001
        snippet = m.group(0)[:200].replace("\n", " ")
        return {"error": f"JSON 파싱 실패 ({e}): \"{snippet}…\""}

    # Collect grounding citations from response metadata for transparency.
    citations: list[str] = []
    try:
        gm = resp.candidates[0].grounding_metadata
        for chunk in (gm.grounding_chunks or []):
            if chunk.web and chunk.web.uri:
                citations.append(chunk.web.uri)
    except Exception:
        pass
    if citations:
        data["citations"] = citations[:5]
    if fallback_note:
        prev = (data.get("notes") or "").strip()
        data["notes"] = f"{prev} {fallback_note}".strip() if prev else fallback_note
    return data
