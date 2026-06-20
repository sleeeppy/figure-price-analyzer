"""Result screen — best card, price chart, alternates list, rerank note."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from gui import theme
from gui.widgets.candidate_card import CandidateCard
from gui.widgets.gemini_lookup import GeminiLookupPanel
from gui.widgets.price_chart import PriceChart
from services.types import IdentifyResult


def _clear_layout(layout: QLayout) -> None:
    """Remove every item from *layout* and schedule widgets for deletion.

    takeAt() on a nested QHBoxLayout returns item.widget() == None; without
    recursing, those rows (e.g. the back button) leak and stack on repaint.
    """
    while layout.count():
        item = layout.takeAt(0)
        if item is None:
            continue
        w = item.widget()
        if w is not None:
            w.deleteLater()
            continue
        sub = item.layout()
        if sub is not None:
            _clear_layout(sub)
            sub.deleteLater()


class ResultView(QWidget):
    reset = Signal()  # user wants to upload another photo
    confirmRequested = Signal(int)  # figure_id the user wants to attach their photo to

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards: dict[int, "CandidateCard"] = {}
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._scroll)

        self._holder = QWidget()
        self._holder_layout = QVBoxLayout(self._holder)
        self._holder_layout.setContentsMargins(0, 0, 0, 0)
        self._holder_layout.setSpacing(16)
        self._scroll.setWidget(self._holder)

    def set_result(self, result: IdentifyResult, preview_bytes: bytes | None,
                   *, has_user_photo: bool = True) -> None:
        # Clear previous children (including nested layouts from addLayout).
        self._cards.clear()
        _clear_layout(self._holder_layout)

        # Top row: preview + reset button
        if preview_bytes:
            top = QFrame()
            top.setProperty("class", "card")
            row = QHBoxLayout(top)
            row.setContentsMargins(12, 12, 12, 12)
            row.setSpacing(12)
            preview = QLabel()
            preview.setFixedSize(72, 72)
            preview.setStyleSheet(f"background-color: {theme.SURFACE_2}; border-radius: 12px;")
            pm = QPixmap()
            pm.loadFromData(preview_bytes)
            if not pm.isNull():
                preview.setPixmap(
                    pm.scaled(72, 72, Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.SmoothTransformation)
                )
            row.addWidget(preview)
            row.addWidget(QLabel("올린 사진"), stretch=1)
            reset_btn = QPushButton("다시 올리기")
            reset_btn.setProperty("variant", "ghost")
            reset_btn.clicked.connect(self.reset.emit)
            row.addWidget(reset_btn)
            self._holder_layout.addWidget(top)

        if result.best is None:
            empty = QLabel("DB에 비슷한 게 없어요. 다른 사진으로 시도해보세요.")
            empty.setProperty("role", "muted")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._holder_layout.addWidget(empty)
            self._holder_layout.addStretch(1)
            return

        # Rerank note (optional)
        if result.rerank:
            note = QFrame()
            note.setProperty("class", "card-accent-blue")
            note_layout = QVBoxLayout(note)
            note_layout.setContentsMargins(12, 10, 12, 10)
            tag = QLabel(f"Gemini 판정 — confidence: {result.rerank.confidence}")
            tag.setProperty("role", "label")
            note_layout.addWidget(tag)
            reason = QLabel(result.rerank.reason or "(no reason)")
            reason.setWordWrap(True)
            note_layout.addWidget(reason)
            self._holder_layout.addWidget(note)

        # Best
        best_card = CandidateCard(result.best, hero=True, confirmable=has_user_photo)
        best_card.confirmRequested.connect(self.confirmRequested.emit)
        self._cards[result.best.figure_id] = best_card
        self._holder_layout.addWidget(best_card)

        # Price chart
        chart_card = QFrame()
        chart_card.setProperty("class", "card")
        chart_layout = QVBoxLayout(chart_card)
        chart_layout.setContentsMargins(12, 12, 12, 12)
        chart_layout.setSpacing(8)
        header = QHBoxLayout()
        title = QLabel("가격")
        title.setProperty("role", "subheading")
        header.addWidget(title, stretch=1)
        msrp_box = QVBoxLayout()
        msrp_box.setSpacing(0)
        msrp_lbl = QLabel("정가")
        msrp_lbl.setProperty("role", "label")
        msrp_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        msrp_val = QLabel(
            f"₩{result.best.price.msrp_krw:,}" if result.best.price.msrp_krw is not None else "—"
        )
        msrp_val.setAlignment(Qt.AlignmentFlag.AlignRight)
        msrp_val.setStyleSheet("font-size: 18px; font-weight: 700;")
        msrp_box.addWidget(msrp_lbl)
        msrp_box.addWidget(msrp_val)
        header.addLayout(msrp_box)
        chart_layout.addLayout(header)
        if result.best.price.partners:
            chart = PriceChart()
            chart.render(result.best.price.partners, result.best.price.msrp_krw)
            chart_layout.addWidget(chart)
        else:
            # Friendly empty-state — most of these are old/discontinued
            # figures that no partner store still stocks. Don't show an
            # empty chart canvas; explain why.
            empty = QFrame()
            empty.setStyleSheet(
                f"background-color: {theme.SURFACE_2}; border-radius: 12px;"
            )
            ev = QVBoxLayout(empty)
            ev.setContentsMargins(16, 18, 16, 18)
            ev.setSpacing(6)
            icon = QLabel("🛒")
            icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon.setStyleSheet("font-size: 26px;")
            ev.addWidget(icon)
            title2 = QLabel("지금 파는 스토어가 없어요")
            title2.setAlignment(Qt.AlignmentFlag.AlignCenter)
            title2.setStyleSheet("font-size: 14px; font-weight: 700;")
            ev.addWidget(title2)
            sub2 = QLabel("구작이거나 디스컨된 상품일 수 있어요. 위 정가는 발매 당시 MFC 기재 가격이에요.")
            sub2.setProperty("role", "muted")
            sub2.setWordWrap(True)
            sub2.setAlignment(Qt.AlignmentFlag.AlignCenter)
            ev.addWidget(sub2)
            chart_layout.addWidget(empty)
        self._holder_layout.addWidget(chart_card)

        # Alternates
        if result.alternates:
            alt_label = QLabel("아니면 이건가요?")
            alt_label.setProperty("role", "subheading")
            self._holder_layout.addWidget(alt_label)
            for alt in result.alternates[:5]:
                alt_card = CandidateCard(alt, confirmable=has_user_photo)
                alt_card.confirmRequested.connect(self.confirmRequested.emit)
                self._cards[alt.figure_id] = alt_card
                self._holder_layout.addWidget(alt_card)

        # Gemini web-search panel — surface when we don't have a confident
        # match, or the user wants a second opinion. Only meaningful when we
        # actually have the user's photo to send.
        if preview_bytes:
            conf = result.rerank.confidence if result.rerank else None
            self._holder_layout.addWidget(
                GeminiLookupPanel(image_bytes=preview_bytes, confidence=conf)
            )

        # Bottom escape hatch — QWidget wrapper so clear_layout always deletes it.
        back_wrap = QWidget()
        back_row = QHBoxLayout(back_wrap)
        back_row.setContentsMargins(0, 8, 0, 4)
        back_row.addStretch(1)
        back_btn = QPushButton("← 메인으로 돌아가기")
        back_btn.setProperty("variant", "secondary")
        back_btn.clicked.connect(self.reset.emit)
        back_row.addWidget(back_btn)
        back_row.addStretch(1)
        self._holder_layout.addWidget(back_wrap)

        self._holder_layout.addStretch(1)

        for w in (*self.findChildren(QLabel), *self.findChildren(QPushButton)):
            w.style().unpolish(w)
            w.style().polish(w)

    # ----- External hooks for the confirm worker -----

    def card(self, figure_id: int):
        return self._cards.get(figure_id)
