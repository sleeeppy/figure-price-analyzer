"""Candidate card — figure image, meta, MSRP, confidence pill,
optional 'this photo is correct' confirm action."""
from __future__ import annotations
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from services.types import FigureCandidate
from gui import theme


def _distance_to_score(d: float) -> int:
    return max(0, min(100, round((1 - d) * 100)))


def _distance_label(d: float) -> str:
    if d < 0.35:
        return "high"
    if d < 0.55:
        return "medium"
    return "low"


class CandidateCard(QFrame):
    """One result card. Emits `confirmRequested(figure_id)` when the user
    clicks "이 사진이 맞아요" — caller drives the actual confirm_image call
    in a background worker.
    """

    confirmRequested = Signal(int)

    def __init__(
        self,
        candidate: FigureCandidate,
        hero: bool = False,
        *,
        confirmable: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self._candidate = candidate
        self.setProperty("class", "card-hero" if hero else "card")
        self.style().unpolish(self); self.style().polish(self)

        c = candidate
        # An "already-indexed" candidate is one we matched at near-zero
        # distance, i.e. the user's photo is essentially the reference itself.
        # Show a green badge instead of the confirm button.
        already_indexed = c.distance <= 0.0005

        row = QHBoxLayout(self)
        row.setContentsMargins(16, 16, 16, 16)
        row.setSpacing(16)

        # Image
        img = QLabel()
        img.setFixedSize(160 if hero else 88, 160 if hero else 88)
        img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        img.setStyleSheet(f"background-color: {theme.SURFACE_2}; border-radius: 12px;")
        if c.image_paths:
            path = c.image_paths[0]
            if Path(path).exists():
                pm = QPixmap(path)
                if not pm.isNull():
                    img.setPixmap(
                        pm.scaled(
                            img.size(),
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation,
                        )
                    )
        row.addWidget(img)

        # Meta column
        col = QVBoxLayout()
        col.setSpacing(2)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        meta_col = QVBoxLayout()
        meta_col.setSpacing(2)
        sub = QLabel(_subline(c))
        sub.setProperty("role", "label")
        meta_col.addWidget(sub)

        name = QLabel(c.character_name or "—")
        name.setProperty("role", "heading" if hero else "subheading")
        name.setWordWrap(True)
        meta_col.addWidget(name)

        origin = QLabel(c.origin or "")
        origin.setProperty("role", "muted")
        origin.setWordWrap(True)
        meta_col.addWidget(origin)

        top_row.addLayout(meta_col, stretch=1)

        # Confidence pill on the right
        score = _distance_to_score(c.distance)
        level = _distance_label(c.distance)
        pill = QLabel(f"{level.upper()}  {score}점")
        pill.setProperty("role", f"pill-{level}")
        pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pill.setFixedHeight(22)
        top_row.addWidget(pill, alignment=Qt.AlignmentFlag.AlignTop)

        col.addLayout(top_row)
        col.addSpacing(8)

        # MSRP + action row
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(10)

        msrp_box = QVBoxLayout()
        msrp_box.setSpacing(0)
        msrp_label = QLabel("정가")
        msrp_label.setProperty("role", "label")
        msrp_box.addWidget(msrp_label)
        msrp_val = QLabel(_fmt_krw(c.price.msrp_krw))
        msrp_val.setStyleSheet("font-size: 16px; font-weight: 700;")
        msrp_box.addWidget(msrp_val)
        bottom_row.addLayout(msrp_box)
        bottom_row.addStretch(1)

        if already_indexed:
            badge = QLabel("이미 등록된 사진")
            badge.setProperty("role", "success")
            bottom_row.addWidget(badge, alignment=Qt.AlignmentFlag.AlignVCenter)
            self._confirm_btn = None
        elif confirmable:
            self._confirm_btn = QPushButton("✅ 이 사진이 맞아요")
            self._confirm_btn.setToolTip(
                "내가 올린 사진을 이 figure의 참조 이미지로 추가 + 학습"
            )
            self._confirm_btn.clicked.connect(
                lambda: self.confirmRequested.emit(c.figure_id)
            )
            bottom_row.addWidget(self._confirm_btn)
        else:
            self._confirm_btn = None

        col.addLayout(bottom_row)

        # Inline status line (populated by parent when we get a result back).
        self._status = QLabel("")
        self._status.setProperty("role", "success")
        self._status.setVisible(False)
        col.addWidget(self._status)

        col.addStretch(1)
        row.addLayout(col, stretch=1)

        for w in self.findChildren(QLabel):
            w.style().unpolish(w); w.style().polish(w)

    # ----- API for the parent view to drive button state -----

    def set_confirming(self, on: bool) -> None:
        if self._confirm_btn:
            self._confirm_btn.setEnabled(not on)
            self._confirm_btn.setText("학습 중…" if on else "✅ 이 사진이 맞아요")

    def show_status(self, text: str, *, error: bool = False) -> None:
        self._status.setText(text)
        self._status.setProperty("role", "error" if error else "success")
        self._status.style().unpolish(self._status); self._status.style().polish(self._status)
        self._status.setVisible(True)


def _subline(c: FigureCandidate) -> str:
    parts = []
    if c.maker:
        parts.append(c.maker)
    if c.release_date:
        parts.append(c.release_date)
    return "  ·  ".join(parts) if parts else " "


def _fmt_krw(v) -> str:
    if v is None:
        return "—"
    return "₩" + format(int(v), ",")
