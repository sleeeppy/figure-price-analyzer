"""Gemini web-search panel + result tabs.

Shows up on the result page whenever the rerank confidence isn't 'high'
(or the user just wants to confirm). User can type a hint, hit search,
and gets up to 3 ranked candidates from Gemini + Google Search.
"""
from __future__ import annotations
from typing import Optional

from PySide6.QtCore import Qt, QThread, Signal, QUrl
from PySide6.QtGui import QDesktopServices, QImage, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from services.types import LookupCandidate, LookupResult
from gui import theme
from gui.workers import LookupWorker, run_in_thread
from gui.widgets.price_chart import PriceChart


class GeminiLookupPanel(QFrame):
    """Top-level lookup affordance — input + button + collapsible result."""

    def __init__(self, image_bytes: bytes | None = None,
                 confidence: str | None = None, parent=None):
        super().__init__(parent)
        self._image_bytes = image_bytes
        self.setProperty("class", "card-accent-blue")
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self.style().unpolish(self); self.style().polish(self)

        self._worker = None
        self._thread: QThread | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(8)

        # Banner explaining when this panel is useful
        banner_text = (
            f"매칭 신뢰도가 {confidence}예요. Gemini가 웹에서 직접 찾아볼까요?"
            if confidence and confidence != "high"
            else "DB 매칭이 마음에 안 든다면 Gemini로도 찾아볼 수 있어요."
        ) if confidence else "Gemini 재랭크가 꺼져있어 신뢰도 미상이에요."
        banner = QLabel(banner_text)
        banner.setProperty("role", "muted")
        banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        banner.setWordWrap(True)
        root.addWidget(banner)

        tag = QLabel("🌐 GEMINI 웹 검색")
        tag.setStyleSheet(
            f"color: {theme.ACCENT_BLUE}; font-size: 11px; "
            f"font-weight: 700; letter-spacing: 1px;"
        )
        root.addWidget(tag)

        # Hint input
        self._hint = QLineEdit()
        self._hint.setPlaceholderText("(선택) 힌트 — 예: Kadokawa KDcolle 1/7, Saber Lily 등")
        self._hint.returnPressed.connect(self._submit)
        root.addWidget(self._hint)

        # Action row
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self._btn = QPushButton("🌐 Gemini로 찾기")
        self._btn.clicked.connect(self._submit)
        self._btn.setEnabled(image_bytes is not None)
        btn_row.addWidget(self._btn)
        btn_row.addStretch(1)
        root.addLayout(btn_row)

        hint = QLabel("DB에 직접 추가하려면 메인 페이지 '➕ DB에 추가하기'를 이용하세요.")
        hint.setProperty("role", "label")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(hint)

        self._status = QLabel("")
        self._status.setProperty("role", "muted")
        self._status.setWordWrap(True)
        self._status.setVisible(False)
        root.addWidget(self._status)

        # Result area appears below the input panel once a search completes.
        self._result_holder = QVBoxLayout()
        self._result_holder.setSpacing(12)
        root.addLayout(self._result_holder)

        for lbl in self.findChildren(QLabel):
            lbl.style().unpolish(lbl); lbl.style().polish(lbl)

    # ------------------------------------------------------------------

    def _submit(self) -> None:
        if self._image_bytes is None:
            self._status.setText("올린 사진이 없어요.")
            self._status.setVisible(True)
            return
        self._btn.setEnabled(False)
        self._btn.setText("Gemini 검색 중…")
        self._status.setText("")
        self._status.setVisible(False)
        self._clear_results()

        worker = LookupWorker(self._image_bytes, self._hint.text().strip())
        worker.done.connect(self._on_done)
        worker.failed.connect(self._on_failed)
        self._worker = worker
        self._thread = run_in_thread(worker, self)

    def _on_done(self, result: LookupResult) -> None:
        self._btn.setEnabled(True)
        self._btn.setText("🔄 다시 검색")
        if result.error:
            self._status.setText(result.error)
            self._status.setProperty("role", "error")
            self._status.style().unpolish(self._status); self._status.style().polish(self._status)
            self._status.setVisible(True)
            return
        if not result.candidates:
            self._status.setText("Gemini가 일치하는 figure를 찾지 못했어요.")
            self._status.setVisible(True)
            return
        card = GeminiResultCard(result)
        self._result_holder.addWidget(card)

    def _on_failed(self, err: str) -> None:
        self._btn.setEnabled(True)
        self._btn.setText("🌐 Gemini로 찾기")
        self._status.setText(err)
        self._status.setProperty("role", "error")
        self._status.style().unpolish(self._status); self._status.style().polish(self._status)
        self._status.setVisible(True)

    def _clear_results(self) -> None:
        while self._result_holder.count():
            item = self._result_holder.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()


class GeminiResultCard(QFrame):
    """Tabbed result — N candidates with image + meta + (optional) prices."""

    def __init__(self, result: LookupResult, parent=None):
        super().__init__(parent)
        self.setProperty("class", "card-accent-blue")
        self.style().unpolish(self); self.style().polish(self)

        self._net = QNetworkAccessManager(self)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        title = QLabel(f"🌐 GEMINI 웹 검색 후보 {len(result.candidates)}건")
        title.setStyleSheet(
            f"color: {theme.ACCENT_BLUE}; font-size: 11px; "
            f"font-weight: 700; letter-spacing: 1px;"
        )
        root.addWidget(title)

        # Tab bar
        self._tab_buttons: list[QPushButton] = []
        tab_row = QHBoxLayout()
        tab_row.setSpacing(6)
        for i, c in enumerate(result.candidates):
            label = (c.character_name or (c.name_en or "(이름 없음)")[:24])
            btn = QPushButton(f"#{i+1}  {label}")
            btn.setProperty("variant", "tab-active" if i == 0 else "tab")
            btn.clicked.connect(lambda _checked=False, idx=i: self._set_tab(idx))
            tab_row.addWidget(btn)
            self._tab_buttons.append(btn)
        tab_row.addStretch(1)
        root.addLayout(tab_row)

        self._stack = QStackedWidget()
        self._pages = []
        for c in result.candidates:
            page = self._build_candidate_page(c)
            self._stack.addWidget(page)
            self._pages.append(page)
        root.addWidget(self._stack)

        if result.notes:
            note = QLabel(f'"{result.notes}"')
            note.setProperty("role", "muted")
            note.setWordWrap(True)
            root.addWidget(note)

        for btn in self._tab_buttons:
            btn.style().unpolish(btn); btn.style().polish(btn)
        for lbl in self.findChildren(QLabel):
            lbl.style().unpolish(lbl); lbl.style().polish(lbl)

    def _set_tab(self, idx: int) -> None:
        self._stack.setCurrentIndex(idx)
        for i, btn in enumerate(self._tab_buttons):
            btn.setProperty("variant", "tab-active" if i == idx else "tab")
            btn.style().unpolish(btn); btn.style().polish(btn)

    # ----- candidate body -----

    def _build_candidate_page(self, c: LookupCandidate) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 8, 0, 0)
        v.setSpacing(12)

        # Hero image (async fetch)
        img_label = QLabel()
        img_label.setFixedHeight(220)
        img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        img_label.setStyleSheet(
            f"background-color: {theme.SURFACE_2}; border-radius: 12px;"
        )
        img_label.setText("🖼️  이미지 미리보기 없음")
        if c.image_url:
            self._fetch_image_async(c.image_url, img_label)
        v.addWidget(img_label)

        # Meta column
        if c.name_en:
            name = QLabel(c.name_en)
            name.setStyleSheet("font-size: 15px; font-weight: 700;")
            name.setWordWrap(True)
            v.addWidget(name)

        rows = QVBoxLayout()
        rows.setSpacing(4)
        for label, value in [
            ("캐릭터", c.character_name),
            ("작품", c.origin),
            ("제조사", c.maker),
            ("스케일", c.scale),
            ("발매", c.release_date),
            ("정가", _format_msrp(c.msrp_jpy, c.msrp_krw)),
        ]:
            if not value:
                continue
            line = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setProperty("role", "label")
            lbl.setFixedWidth(56)
            line.addWidget(lbl)
            val = QLabel(value)
            val.setWordWrap(True)
            line.addWidget(val, stretch=1)
            rows.addLayout(line)
        v.addLayout(rows)

        if c.why_this_match:
            reason = QLabel(f'"{c.why_this_match}"')
            reason.setProperty("role", "muted")
            reason.setWordWrap(True)
            reason.setStyleSheet(
                f"background-color: {theme.SURFACE_2}; "
                f"border-radius: 12px; padding: 8px;"
            )
            v.addWidget(reason)

        # Source link
        if c.source_url:
            link = QPushButton(f"↗  {c.source_url[:60]}…" if len(c.source_url) > 60 else f"↗  {c.source_url}")
            link.setProperty("variant", "ghost")
            link.clicked.connect(lambda _=None, u=c.source_url: QDesktopServices.openUrl(QUrl(u)))
            v.addWidget(link, alignment=Qt.AlignmentFlag.AlignLeft)

        # Price card — same look as the main result page's PriceSection:
        # header with "가격" on the left + 정가 on the right, then a color-
        # coded matplotlib bar chart. Empty state mirrors the result view too.
        priced = [o for o in c.observations if o.price_krw]
        if c.msrp_krw is not None or priced:
            v.addWidget(self._price_card(c, priced))

        for lbl in w.findChildren(QLabel):
            lbl.style().unpolish(lbl); lbl.style().polish(lbl)
        return w

    def _price_card(self, c: LookupCandidate, priced: list) -> QFrame:
        """Build the same-styled price card the main ResultView uses."""
        card = QFrame()
        card.setProperty("class", "card")
        card.setStyleSheet(
            f"QFrame[class=\"card\"] {{ background-color: {theme.SURFACE_1}; border-radius: 8px; }}"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        # Header: "가격" + 정가 on the right
        header = QHBoxLayout()
        title = QLabel("가격")
        title.setProperty("role", "subheading")
        header.addWidget(title, stretch=1)

        msrp_box = QVBoxLayout()
        msrp_box.setSpacing(0)
        msrp_lbl = QLabel("정가")
        msrp_lbl.setProperty("role", "label")
        msrp_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        msrp_box.addWidget(msrp_lbl)
        msrp_val = QLabel(
            f"₩{c.msrp_krw:,}" if c.msrp_krw is not None else "—"
        )
        msrp_val.setAlignment(Qt.AlignmentFlag.AlignRight)
        msrp_val.setStyleSheet("font-size: 18px; font-weight: 700;")
        msrp_box.addWidget(msrp_val)
        if c.msrp_jpy is not None:
            jpy_label = QLabel(f"¥{c.msrp_jpy:,}")
            jpy_label.setProperty("role", "muted")
            jpy_label.setAlignment(Qt.AlignmentFlag.AlignRight)
            msrp_box.addWidget(jpy_label)
        header.addLayout(msrp_box)
        layout.addLayout(header)

        if priced:
            chart = PriceChart()
            chart.render(priced, c.msrp_krw)
            layout.addWidget(chart)
        else:
            # Empty state — same Spotify treatment as the main result view.
            empty = QFrame()
            empty.setStyleSheet(
                f"background-color: {theme.SURFACE_2}; border-radius: 12px;"
            )
            ev = QVBoxLayout(empty)
            ev.setContentsMargins(16, 18, 16, 18)
            ev.setSpacing(6)
            icon = QLabel("🛒")
            icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon.setStyleSheet("font-size: 22px;")
            ev.addWidget(icon)
            title2 = QLabel("호가 정보를 찾지 못했어요")
            title2.setAlignment(Qt.AlignmentFlag.AlignCenter)
            title2.setStyleSheet("font-size: 13px; font-weight: 700;")
            ev.addWidget(title2)
            sub2 = QLabel("Gemini가 가격 데이터를 못 찾았어요. 위 출처 링크에서 직접 확인해주세요.")
            sub2.setProperty("role", "muted")
            sub2.setWordWrap(True)
            sub2.setAlignment(Qt.AlignmentFlag.AlignCenter)
            ev.addWidget(sub2)
            layout.addWidget(empty)

        for w in card.findChildren(QLabel):
            w.style().unpolish(w); w.style().polish(w)
        return card

    def _fetch_image_async(self, url: str, target: QLabel) -> None:
        request = QNetworkRequest(QUrl(url))
        request.setRawHeader(b"User-Agent", b"FigurePriceAnalyzer/0.1")
        reply = self._net.get(request)

        def _on_finish() -> None:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                target.setText("🖼️  이미지를 불러올 수 없어요")
                reply.deleteLater()
                return
            data = reply.readAll().data()
            pm = QPixmap()
            if pm.loadFromData(data):
                target.setPixmap(
                    pm.scaled(
                        target.width(), target.height(),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
                target.setText("")
            reply.deleteLater()

        reply.finished.connect(_on_finish)


def _format_msrp(jpy: Optional[int], krw: Optional[int]) -> Optional[str]:
    if jpy is None and krw is None:
        return None
    parts = []
    if krw is not None:
        parts.append(f"₩{krw:,}")
    if jpy is not None:
        parts.append(f"(¥{jpy:,})")
    return " ".join(parts)
