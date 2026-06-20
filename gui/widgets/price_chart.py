"""Matplotlib bar chart embedded in a Qt widget.
Same semantics as the old Recharts version: cheapest at top, color-coded
vs MSRP (green = cheaper, orange = up to 2×, red = 2×+), dashed MSRP line.
"""
from __future__ import annotations
from typing import Optional

import matplotlib
matplotlib.use("QtAgg")  # noqa: E402
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
import matplotlib.font_manager as fm

from services.types import PartnerPrice
from gui import theme


# Pick the first Korean-capable font that's actually installed. The default
# DejaVu Sans doesn't have CJK glyphs and renders "정가" as ☐☐, which is what
# the bare matplotlib defaults give you on macOS.
def _resolve_ko_font() -> str:
    candidates = [
        "Apple SD Gothic Neo",
        "AppleGothic",
        "Nanum Gothic",
        "NanumGothic",
        "Malgun Gothic",
        "Noto Sans CJK KR",
        "Noto Sans KR",
    ]
    available = {f.name for f in fm.fontManager.ttflist}
    for name in candidates:
        if name in available:
            return name
    return "sans-serif"


_KO_FONT = _resolve_ko_font()
matplotlib.rcParams["font.family"] = [_KO_FONT, "Helvetica Neue", "sans-serif"]
# Negative sign rendering glitch on some Korean fonts → use ASCII hyphen.
matplotlib.rcParams["axes.unicode_minus"] = False


class PriceChart(FigureCanvasQTAgg):
    def __init__(self, parent=None):
        # Build a small headless figure; the Qt widget owns its rendering.
        self.fig = Figure(figsize=(5, 2.5), dpi=110, facecolor=theme.MPL_BG)
        super().__init__(self.fig)
        if parent is not None:
            self.setParent(parent)

    def render(self, partners: list[PartnerPrice], msrp_krw: Optional[int]) -> None:
        # Callers should check `partners` themselves and skip rendering the
        # chart when empty — empty-state messaging lives in ResultView (Qt)
        # for proper styling. We only handle the populated case here.
        self.fig.clear()
        if not partners:
            self.draw()
            return

        # Sort cheapest → most expensive
        rows = sorted(
            [p for p in partners if p.price_krw > 0],
            key=lambda p: p.price_krw,
        )
        stores = [p.store for p in rows]
        prices = [p.price_krw for p in rows]

        def color_for(krw: int) -> str:
            if msrp_krw is None:
                return theme.MPL_BLUE
            if krw < msrp_krw:
                return theme.MPL_GREEN
            if krw < msrp_krw * 2:
                return theme.MPL_ORANGE
            return theme.MPL_RED

        bar_colors = [color_for(p) for p in prices]

        # Dynamic height based on row count
        n = len(rows)
        self.fig.set_size_inches(5, max(2.2, 0.45 * n + 0.8))

        ax = self.fig.add_subplot(111)
        ax.set_facecolor(theme.MPL_BG)

        # `barh` puts first item at bottom by default; flip so cheapest is on top.
        ax.barh(range(n), prices, color=bar_colors, height=0.65)
        ax.invert_yaxis()
        ax.set_yticks(range(n))
        ax.set_yticklabels(stores, color=theme.MPL_AXIS, fontsize=10)

        # Format x-axis ticks as ₩Xk
        ax.tick_params(axis="x", colors=theme.MPL_MUTED, labelsize=9)
        ax.set_xlabel("")
        ax.xaxis.set_major_formatter(
            matplotlib.ticker.FuncFormatter(lambda v, _p: f"₩{int(v/1000)}k")
        )

        # Value labels at end of each bar
        for i, v in enumerate(prices):
            ax.text(
                v, i, f"  ₩{v:,}",
                va="center", ha="left",
                color=theme.MPL_AXIS, fontsize=9, fontweight="bold",
            )

        # MSRP reference line
        if msrp_krw is not None:
            ax.axvline(msrp_krw, color=theme.MPL_MUTED, linestyle="--", linewidth=1)
            ax.text(
                msrp_krw, -0.7, " 정가",
                color=theme.MPL_MUTED, fontsize=9,
                ha="left", va="center",
            )

        # Pad right so value labels don't get clipped
        ax.set_xlim(0, max(prices) * 1.25)

        # Hide spines
        for side in ("top", "right", "bottom", "left"):
            ax.spines[side].set_visible(False)
        ax.grid(axis="x", color=theme.MPL_GRID, linestyle="-", linewidth=0.5, alpha=0.6)
        ax.set_axisbelow(True)

        self.fig.tight_layout(pad=0.4)
        self.draw()
