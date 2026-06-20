"""Idle upload screen — drag/drop, file picker, camera (file dialog on desktop)."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gui import theme
from gui.widgets.add_to_db import AddToDb


class UploadView(QWidget):
    fileChosen = Signal(bytes, str)  # raw image bytes, original filename
    figureAdded = Signal(object, str)  # FigureCandidate, status (forwarded from AddToDb)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        self._layout = layout

        # Drop zone
        self._drop = QFrame()
        self._drop.setProperty("role", "drop")
        self._drop.setMinimumHeight(320)
        drop_layout = QVBoxLayout(self._drop)
        drop_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_layout.setSpacing(14)

        icon = QLabel("📷")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("font-size: 48px;")
        drop_layout.addWidget(icon)

        title = QLabel("사진 한 장이면 끝")
        title.setProperty("role", "heading")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_layout.addWidget(title)

        subtitle = QLabel("피규어 사진을 올리면 어떤 피규어인지, 시세는 얼마인지 찾아줍니다.")
        subtitle.setProperty("role", "muted")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_layout.addWidget(subtitle)

        btn_row = QHBoxLayout()
        btn_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        btn_row.setSpacing(10)

        pick_btn = QPushButton("파일 선택")
        pick_btn.clicked.connect(self._open_file_dialog)
        btn_row.addWidget(pick_btn)

        # On desktop "camera" is just another file picker — the iOS-style
        # capture intent doesn't exist here. Keep the button as a secondary
        # action so the layout matches the web build.
        cam_btn = QPushButton("카메라/이미지")
        cam_btn.setProperty("variant", "secondary")
        cam_btn.clicked.connect(self._open_file_dialog)
        btn_row.addWidget(cam_btn)

        drop_layout.addLayout(btn_row)

        hint = QLabel("또는 여기로 드래그")
        hint.setProperty("role", "label")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_layout.addWidget(hint)

        tip = QLabel("💡  피규어 전체가 보이게 찍으면 인식률 ↑")
        tip.setProperty("role", "muted")
        tip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tip.setToolTip(
            "피규어가 화면에 다 들어오게 찍으면 학습된 풀바디 레퍼런스와\n"
            "더 잘 매칭됩니다. 얼굴/상반신만 잘린 클로즈업은 점수가 낮게\n"
            "나올 수 있어요."
        )
        drop_layout.addWidget(tip)

        layout.addWidget(self._drop)

        # ➕ DB에 추가하기 panel (collapsible) right below the drop zone.
        self._add_panel = AddToDb()
        self._add_panel.figureAdded.connect(self.figureAdded.emit)
        layout.addWidget(self._add_panel)

        # Without this stretcher both the drop zone and the add panel get
        # equal vertical weight from QVBoxLayout, so the add panel balloons
        # to fill the window. Pushing everything to the top keeps each card
        # at its natural height.
        layout.addStretch(1)

        # Re-polish styles on dynamic property change
        for w in self.findChildren(QLabel):
            w.style().unpolish(w); w.style().polish(w)

    # ---------- Drag & drop ----------

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._set_drop_active(True)

    def dragLeaveEvent(self, event) -> None:
        self._set_drop_active(False)

    def dropEvent(self, event: QDropEvent) -> None:
        self._set_drop_active(False)
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path:
                self._emit_path(path)
                break

    def _set_drop_active(self, active: bool) -> None:
        self._drop.setProperty("role", "drop-active" if active else "drop")
        self._drop.style().unpolish(self._drop); self._drop.style().polish(self._drop)

    # ---------- File picker ----------

    def _open_file_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "피규어 사진 선택", "",
            "이미지 (*.jpg *.jpeg *.png *.webp *.bmp);;모든 파일 (*)"
        )
        if path:
            self._emit_path(path)

    def _emit_path(self, path: str) -> None:
        try:
            with open(path, "rb") as f:
                data = f.read()
            self.fileChosen.emit(data, path)
        except OSError as e:
            # Just surface to console; the main window stays on this screen.
            print(f"[upload] failed to read {path}: {e}")
