"""Plain dataclasses returned by the service layer.
The GUI consumes these directly — no JSON envelope.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PartnerPrice:
    store: str
    price: float
    currency: str
    price_krw: int


@dataclass
class PriceStats:
    msrp_jpy: Optional[int]
    msrp_krw: Optional[int]
    partners: list[PartnerPrice] = field(default_factory=list)


@dataclass
class FigureCandidate:
    figure_id: int
    name_en: Optional[str]
    maker: Optional[str]
    character_name: Optional[str]
    origin: Optional[str]
    release_date: Optional[str]
    image_paths: list[str]      # absolute disk paths (GUI loads via QPixmap)
    distance: float
    price: PriceStats


@dataclass
class RerankMeta:
    best_index: int
    confidence: str
    reason: str
    note: Optional[str] = None


@dataclass
class IdentifyResult:
    best: Optional[FigureCandidate]
    alternates: list[FigureCandidate]
    rerank: Optional[RerankMeta] = None
    fx_jpy_to_krw: float = 0.0


@dataclass
class LookupObservation:
    store: str
    price: float
    currency: str
    price_krw: Optional[int]
    url: Optional[str] = None


@dataclass
class LookupCandidate:
    name_en: Optional[str] = None
    character_name: Optional[str] = None
    origin: Optional[str] = None
    maker: Optional[str] = None
    scale: Optional[str] = None
    msrp_jpy: Optional[int] = None
    msrp_krw: Optional[int] = None
    release_date: Optional[str] = None
    source_url: Optional[str] = None
    image_url: Optional[str] = None
    observations: list[LookupObservation] = field(default_factory=list)
    confidence: Optional[str] = None
    why_this_match: Optional[str] = None


@dataclass
class LookupResult:
    candidates: list[LookupCandidate] = field(default_factory=list)
    notes: Optional[str] = None
    citations: list[str] = field(default_factory=list)
    error: Optional[str] = None
