"""Central configuration."""
from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("DATA_DIR", ROOT / "data"))
IMAGE_DIR = DATA_DIR / "images"
DB_PATH = DATA_DIR / "figures.db"

DATA_DIR.mkdir(parents=True, exist_ok=True)
IMAGE_DIR.mkdir(parents=True, exist_ok=True)

# DINOv2
DINOV2_MODEL = "facebook/dinov2-large"
EMBED_DIM = 1024                 # ViT-L/14 hidden size
TORCH_DEVICE = "mps"             # Apple Silicon; falls back in embedder

# MFC crawl
MFC_BASE = "https://myfigurecollection.net"
# robots.txt sets no Crawl-delay for generic UAs; 1.0s = polite 1 RPS to origin.
MFC_REQUEST_DELAY_SEC = 1.0
# Images live on static.myfigurecollection.net (separate CDN); cheaper to hit.
MFC_IMAGE_DELAY_SEC = 0.2
MFC_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Apple Silicon) "
    "FigurePriceAnalyzer/0.1 (personal research; contact: local)"
)

# Seed browse URLs for MVP scope: scaled prepainted, 1/7 and 1/8.
# MFC's category/scale taxonomy uses tag IDs in URL.
# These are paginated listing pages — verify in your browser then paste here.
# Format hint: https://myfigurecollection.net/browse.v4.php?...&scaleId=...
# MFC search URLs filtered by scale (1/7, 1/8). `ftk` is a per-session token —
# may need refresh if MFC starts rejecting; the rest of the params are stable.
MFC_SEED_URLS = [
    # 1/7 scale, sorted by owner count desc (popular figures → richer Loose/MIB data)
    "https://myfigurecollection.net/?rootId=0&categoryId=-1&contentLevel=-1&scale=7"
    "&_tb=item&mode=browse&tab=search&output=2&sort=popularity&order=desc",
    # 1/8 scale, sorted by owner count desc
    "https://myfigurecollection.net/?rootId=0&categoryId=-1&contentLevel=-1&scale=8"
    "&_tb=item&mode=browse&tab=search&output=2&sort=popularity&order=desc",
]

# FX (frankfurter.dev: free, no API key, ECB-sourced rates)
FX_API_URL = "https://api.frankfurter.dev/v1/latest?base=JPY&symbols=KRW,USD"

# Gemini
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


# Probed this account's quotas (2026-05); see ai.google.dev/gemini-api/docs/pricing:
#   gemini-3.1-flash-lite  → ~500 RPD text generate (free); Search = Web Grounding ~500.
#   gemini-2.5-flash-lite  → ~20 RPD text generate.
#   gemini-2.5-flash       → ~20 RPD text generate; Search = Search Grounding ~1.5K RPD.
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")
# /lookup vision-only fallback after Search quota errors (high text RPD).
GEMINI_LOOKUP_MODEL = os.environ.get("GEMINI_LOOKUP_MODEL", "gemini-3.1-flash-lite")
# /lookup + Google Search — use 2.5-flash for the larger Search Grounding bucket.
GEMINI_LOOKUP_SEARCH_MODEL = os.environ.get(
    "GEMINI_LOOKUP_SEARCH_MODEL", "gemini-2.5-flash"
)
GEMINI_LOOKUP_USE_SEARCH = _env_bool("GEMINI_LOOKUP_USE_SEARCH", True)
RERANK_TOP_K = 10
