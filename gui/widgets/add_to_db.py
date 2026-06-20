"""Collapsible "DB에 추가하기" panel — MFC URL tab + manual form tab.

Sits below the upload zone on the idle screen. Both flows end up emitting
`figureAdded(candidate, message)` to the main window, which pops up the
result page with the new figure as best.
"""
from __future__ import annotations
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
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

from services.types import FigureCandidate
from gui import theme
from gui.workers import AddByMfcWorker, AddManualWorker, run_in_thread
from gui.widgets.autocomplete import AutocompleteLineEdit


class AddToDb(QFrame):
    figureAdded = Signal(object, str)   # FigureCandidate, status message

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("class", "card-accent-blue")
        # Hug content vertically so the parent layout doesn't stretch this card
        # to fill the window when the body is collapsed.
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self.style().unpolish(self); self.style().polish(self)

        self._collapsed = True
        self._worker = None
        self._thread: QThread | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        # Header row (always visible, toggles collapse)
        header = QHBoxLayout()
        title = QLabel("➕ DB에 추가하기")
        title.setProperty("role", "label")
        title.setStyleSheet(f"color: {theme.ACCENT_BLUE}; font-size: 11px; font-weight: 700; letter-spacing: 1px;")
        header.addWidget(title)
        header.addStretch(1)
        self._toggle_btn = QPushButton("열기")
        self._toggle_btn.setProperty("variant", "secondary")
        self._toggle_btn.setMinimumWidth(72)
        self._toggle_btn.clicked.connect(self._toggle)
        header.addWidget(self._toggle_btn)
        root.addLayout(header)

        # Subtitle (always visible)
        sub = QLabel("못 찾는 figure를 직접 추가하고 임베딩까지 학습시킵니다.")
        sub.setProperty("role", "muted")
        root.addWidget(sub)

        # Body (collapsible)
        self._body = QWidget()
        body_layout = QVBoxLayout(self._body)
        body_layout.setContentsMargins(0, 4, 0, 0)
        body_layout.setSpacing(10)

        # Tab buttons
        tab_row = QHBoxLayout()
        tab_row.setSpacing(6)
        self._tab_mfc_btn = QPushButton("🔗 MFC URL")
        self._tab_mfc_btn.setProperty("variant", "tab-active")
        self._tab_mfc_btn.clicked.connect(lambda: self._set_tab(0))
        self._tab_manual_btn = QPushButton("✏️ 직접 입력")
        self._tab_manual_btn.setProperty("variant", "tab")
        self._tab_manual_btn.clicked.connect(lambda: self._set_tab(1))
        tab_row.addWidget(self._tab_mfc_btn)
        tab_row.addWidget(self._tab_manual_btn)
        tab_row.addStretch(1)
        body_layout.addLayout(tab_row)

        self._stack = QStackedWidget()
        # Default QStackedWidget vertical policy is Expanding which makes the
        # active page balloon when the AddToDb card is taller than the page
        # needs. Hug content instead.
        self._stack.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self._stack.addWidget(self._build_mfc_tab())
        self._stack.addWidget(self._build_manual_tab())
        body_layout.addWidget(self._stack)

        root.addWidget(self._body)
        self._body.setVisible(False)

        # Polish dynamic role styles on children.
        for cls in (QLabel, QPushButton):
            for w in self.findChildren(cls):
                w.style().unpolish(w); w.style().polish(w)

    # ---------------------------------------------------------------- helpers

    def _toggle(self) -> None:
        self._collapsed = not self._collapsed
        self._body.setVisible(not self._collapsed)
        self._toggle_btn.setText("열기" if self._collapsed else "접기")

    def _set_tab(self, idx: int) -> None:
        self._stack.setCurrentIndex(idx)
        for i, btn in enumerate([self._tab_mfc_btn, self._tab_manual_btn]):
            btn.setProperty("variant", "tab-active" if i == idx else "tab")
            btn.style().unpolish(btn); btn.style().polish(btn)

    # ---------------------------------------------------------------- MFC tab

    def _build_mfc_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)

        hint = QLabel("MFC 아이템 페이지 URL 또는 아이템 ID를 붙여넣으면 즉시 크롤 + 임베딩.")
        hint.setProperty("role", "muted")
        v.addWidget(hint)

        row = QHBoxLayout()
        row.setSpacing(8)
        self._mfc_url = QLineEdit()
        self._mfc_url.setPlaceholderText("https://myfigurecollection.net/item/12345 또는 12345")
        self._mfc_url.returnPressed.connect(self._submit_mfc)
        row.addWidget(self._mfc_url, stretch=1)
        self._mfc_btn = QPushButton("추가")
        self._mfc_btn.setProperty("variant", "secondary")
        self._mfc_btn.clicked.connect(self._submit_mfc)
        row.addWidget(self._mfc_btn)
        v.addLayout(row)

        self._mfc_status = QLabel("")
        self._mfc_status.setProperty("role", "muted")
        self._mfc_status.setWordWrap(True)
        v.addWidget(self._mfc_status)
        v.addStretch(1)   # push content to the top of the tab page
        return w

    def _submit_mfc(self) -> None:
        url = self._mfc_url.text().strip()
        if not url:
            return
        self._mfc_btn.setEnabled(False)
        self._mfc_btn.setText("크롤 중…")
        self._mfc_status.setText("")
        worker = AddByMfcWorker(url)
        worker.done.connect(self._mfc_done)
        worker.failed.connect(self._mfc_failed)
        self._worker = worker
        self._thread = run_in_thread(worker, self)

    def _mfc_done(self, cand: FigureCandidate, inserted: bool) -> None:
        self._mfc_btn.setEnabled(True)
        self._mfc_btn.setText("추가")
        msg = "DB에 새로 추가됐어요 ✓" if inserted else "이미 DB에 있어요"
        self._mfc_status.setText(msg)
        self._mfc_url.clear()
        self.figureAdded.emit(cand, msg)

    def _mfc_failed(self, err: str) -> None:
        self._mfc_btn.setEnabled(True)
        self._mfc_btn.setText("추가")
        self._mfc_status.setText(err)
        self._mfc_status.setProperty("role", "error")
        self._mfc_status.style().unpolish(self._mfc_status); self._mfc_status.style().polish(self._mfc_status)

    # ------------------------------------------------------------- Manual tab

    def _build_manual_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 6, 0, 0)
        v.setSpacing(14)

        # ---- form rows ----
        self._mn_name = QLineEdit()
        self._mn_name.setPlaceholderText("예: Fate/Stay Night - Saber - 1/7 (Good Smile Company)")
        v.addLayout(self._labeled_row("이름 *", self._mn_name))

        self._mn_char = AutocompleteLineEdit("character_name", "예: Altria Pendragon")
        self._mn_origin = AutocompleteLineEdit("origin", "예: Fate/Stay Night")
        # Two-column grid for shorter fields
        v.addLayout(self._two_col(
            ("캐릭터", self._mn_char),
            ("작품", self._mn_origin),
        ))

        self._mn_maker = AutocompleteLineEdit("maker", "예: Good Smile Company")
        self._mn_scale = QLineEdit(); self._mn_scale.setPlaceholderText("예: 1/7")
        v.addLayout(self._two_col(
            ("제조사", self._mn_maker),
            ("스케일", self._mn_scale),
        ))

        self._mn_release = QLineEdit()
        self._mn_release.setPlaceholderText("2026-05 또는 2026-05-15")
        self._mn_msrp = QLineEdit()
        self._mn_msrp.setPlaceholderText("예: 22000")
        v.addLayout(self._two_col(
            ("발매일", self._mn_release),
            ("정가 (JPY)", self._mn_msrp),
        ))

        # ---- image picker (its own labeled row) ----
        pick_row = QHBoxLayout()
        pick_row.setSpacing(10)
        self._mn_pick = QPushButton("📁 이미지 선택")
        self._mn_pick.setProperty("variant", "secondary")
        self._mn_pick.clicked.connect(self._pick_manual_image)
        pick_row.addWidget(self._mn_pick)
        self._mn_filelabel = QLabel("선택된 파일 없음")
        self._mn_filelabel.setProperty("role", "muted")
        pick_row.addWidget(self._mn_filelabel, stretch=1)
        v.addLayout(self._labeled_row("참조 이미지 *", pick_row, is_layout=True))

        # ---- submit footer ----
        v.addSpacing(4)
        footer = QHBoxLayout()
        self._mn_status = QLabel("")
        self._mn_status.setProperty("role", "muted")
        self._mn_status.setWordWrap(True)
        footer.addWidget(self._mn_status, stretch=1)
        self._mn_btn = QPushButton("DB에 추가")
        self._mn_btn.clicked.connect(self._submit_manual)
        footer.addWidget(self._mn_btn)
        v.addLayout(footer)
        v.addStretch(1)   # push content to the top of the tab page

        self._mn_image_bytes: bytes | None = None
        for label in w.findChildren(QLabel):
            label.style().unpolish(label); label.style().polish(label)
        return w

    # ---------- form-row helpers ----------

    def _labeled_row(self, _label: str, field, *, is_layout: bool = False) -> QVBoxLayout:
        """Was a label + field pair; per design the outer label is now dropped,
        so this just wraps the field in a single-item column so the
        2-column grid still works. The placeholder text inside each input
        carries the field name now.
        """
        col = QVBoxLayout()
        col.setSpacing(0)
        if is_layout:
            col.addLayout(field)
        else:
            col.addWidget(field)
        return col

    def _two_col(self, left: tuple, right: tuple) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)
        row.addLayout(self._labeled_row(left[0], left[1]), stretch=1)
        row.addLayout(self._labeled_row(right[0], right[1]), stretch=1)
        return row

    def _field_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setProperty("role", "label")
        lbl.style().unpolish(lbl); lbl.style().polish(lbl)
        return lbl

    def _pick_manual_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "참조 이미지 선택", "",
            "이미지 (*.jpg *.jpeg *.png *.webp *.bmp);;모든 파일 (*)"
        )
        if not path:
            return
        try:
            self._mn_image_bytes = Path(path).read_bytes()
            self._mn_filelabel.setText(
                f"{Path(path).name}  ({len(self._mn_image_bytes)//1024} KB)"
            )
        except OSError as e:
            self._mn_status.setText(f"읽기 실패: {e}")
            self._mn_image_bytes = None

    def _submit_manual(self) -> None:
        if not self._mn_name.text().strip():
            self._mn_status.setText("이름은 필수예요")
            return
        if not self._mn_image_bytes:
            self._mn_status.setText("이미지는 필수예요")
            return
        self._mn_btn.setEnabled(False)
        self._mn_btn.setText("추가 + 학습 중…")
        self._mn_status.setText("")
        worker = AddManualWorker(
            image_bytes=self._mn_image_bytes,
            name_en=self._mn_name.text(),
            character_name=self._mn_char.text(),
            origin=self._mn_origin.text(),
            maker=self._mn_maker.text(),
            scale=self._mn_scale.text(),
            release_date=self._mn_release.text(),
            msrp_jpy=self._mn_msrp.text(),
        )
        worker.done.connect(self._manual_done)
        worker.failed.connect(self._manual_failed)
        self._worker = worker
        self._thread = run_in_thread(worker, self)

    def _manual_done(self, cand: FigureCandidate, fid: int) -> None:
        self._mn_btn.setEnabled(True)
        self._mn_btn.setText("DB에 추가")
        msg = f"figure_id={fid}로 추가됐어요 ✓ (임베딩 학습 완료)"
        self._mn_status.setText(msg)
        for inp in (self._mn_name, self._mn_char, self._mn_origin,
                    self._mn_maker, self._mn_scale, self._mn_release, self._mn_msrp):
            inp.clear()
        self._mn_image_bytes = None
        self._mn_filelabel.setText("선택된 파일 없음")
        self.figureAdded.emit(cand, msg)

    def _manual_failed(self, err: str) -> None:
        self._mn_btn.setEnabled(True)
        self._mn_btn.setText("DB에 추가")
        self._mn_status.setText(err)
        self._mn_status.setProperty("role", "error")
        self._mn_status.style().unpolish(self._mn_status); self._mn_status.style().polish(self._mn_status)
