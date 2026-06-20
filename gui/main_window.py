"""Top-level QMainWindow holding the upload / loading / result screens."""
from __future__ import annotations

from PySide6.QtCore import Qt, QThread
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from db.connection import connect
from services.types import IdentifyResult
from gui import theme
from gui.workers import (
    AddByMfcWorker,
    AddManualWorker,
    ConfirmImageWorker,
    IdentifyWorker,
    run_in_thread,
)
from gui.widgets.upload_view import UploadView
from gui.widgets.result_view import ResultView
from gui.widgets.toggle_switch import ToggleSwitch


PAGE_UPLOAD = 0
PAGE_LOADING = 1
PAGE_RESULT = 2
PAGE_ERROR = 3


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FigurePrice")
        self.resize(820, 980)

        self._preview_bytes: bytes | None = None
        self._current_thread: QThread | None = None
        self._current_worker = None      # keep a strong ref — avoids GC mid-run
        self._rerank_enabled = False

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- Header ----
        header = QFrame()
        header.setStyleSheet(
            f"background-color: {theme.CANVAS}; "
            f"border-bottom: 1px solid {theme.BORDER};"
        )
        hbox = QHBoxLayout(header)
        hbox.setContentsMargins(20, 12, 20, 12)
        title = QLabel("FigurePrice")
        title.setStyleSheet("font-size: 18px; font-weight: 700;")
        hbox.addWidget(title)
        hbox.addStretch(1)
        # Rerank toggle — iOS-style switch + caption.
        rerank_label = QLabel("Gemini 재랭크")
        rerank_label.setStyleSheet("font-size: 12px; font-weight: 700;")
        hbox.addWidget(rerank_label)
        self._rerank_switch = ToggleSwitch(checked=False)
        self._rerank_switch.toggled.connect(self._on_rerank_toggled)
        hbox.addWidget(self._rerank_switch)
        root.addWidget(header)

        # ---- Page stack ----
        self._stack = QStackedWidget()
        content_wrap = QWidget()
        cwlayout = QVBoxLayout(content_wrap)
        cwlayout.setContentsMargins(24, 24, 24, 24)
        cwlayout.addWidget(self._stack)
        root.addWidget(content_wrap, stretch=1)

        # Upload
        self._upload = UploadView()
        self._upload.fileChosen.connect(self._on_file_chosen)
        self._upload.figureAdded.connect(self._on_figure_added)
        self._stack.addWidget(self._upload)

        # Loading
        self._loading = self._build_loading_page()
        self._stack.addWidget(self._loading)

        # Result
        self._result = ResultView()
        self._result.reset.connect(self._reset)
        self._result.confirmRequested.connect(self._on_confirm_requested)
        self._stack.addWidget(self._result)

        # Error
        self._error_page, self._error_label = self._build_error_page()
        self._stack.addWidget(self._error_page)

        # ---- Footer ----
        root.addWidget(self._build_footer())

        self._refresh_health()

    # ----- Pages -----

    def _build_loading_page(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(14)

        label = QLabel("찾는 중…")
        label.setProperty("role", "heading")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)

        # Status text the worker updates via progress signal.
        self._loading_status = QLabel("준비 중…")
        self._loading_status.setProperty("role", "muted")
        self._loading_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._loading_status)

        hint = QLabel("처음 한 번은 모델 로드 때문에 30~60초 걸릴 수 있어요.")
        hint.setProperty("role", "label")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)

        bar = QProgressBar()
        bar.setRange(0, 0)   # indeterminate
        bar.setFixedWidth(280)
        bar.setStyleSheet(
            f"QProgressBar {{ background: {theme.SURFACE_2}; border: none; "
            f"border-radius: 4px; height: 6px; text-align: center; color: transparent; }}"
            f"QProgressBar::chunk {{ background: {theme.PRIMARY}; border-radius: 4px; }}"
        )
        layout.addWidget(bar, alignment=Qt.AlignmentFlag.AlignCenter)
        return w

    def _build_error_page(self) -> tuple[QWidget, QLabel]:
        w = QFrame()
        w.setProperty("class", "card-accent-red")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)
        title = QLabel("문제가 생겼어요")
        title.setProperty("role", "heading")
        layout.addWidget(title)
        msg = QLabel("...")
        msg.setProperty("role", "muted")
        msg.setWordWrap(True)
        layout.addWidget(msg)
        again = QPushButton("다시 시도")
        again.clicked.connect(self._reset)
        layout.addWidget(again, alignment=Qt.AlignmentFlag.AlignLeft)
        return w, msg

    def _build_footer(self) -> QWidget:
        footer = QFrame()
        footer.setStyleSheet(
            f"background-color: {theme.CANVAS}; "
            f"border-top: 1px solid {theme.SURFACE_3};"
        )
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(20, 10, 20, 14)
        layout.setSpacing(20)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._stat_figures = self._stat_widget("FIGURES")
        self._stat_embeds = self._stat_widget("EMBEDDINGS")
        layout.addWidget(self._stat_figures)
        sep = QLabel(" | ")
        sep.setStyleSheet(f"color: {theme.BORDER};")
        layout.addWidget(sep)
        layout.addWidget(self._stat_embeds)
        return footer

    def _stat_widget(self, label_text: str) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        val = QLabel("—")
        val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        val.setStyleSheet("font-size: 13px; font-weight: 700;")
        layout.addWidget(val)
        lbl = QLabel(label_text)
        lbl.setProperty("role", "label")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl)
        w._value = val  # type: ignore[attr-defined]
        return w

    # ----- Lifecycle -----

    def _refresh_health(self) -> None:
        try:
            conn = connect()
            try:
                figs = conn.execute("SELECT COUNT(*) FROM figures").fetchone()[0]
                embs = conn.execute("SELECT COUNT(*) FROM figure_embeddings").fetchone()[0]
            finally:
                conn.close()
            self._stat_figures._value.setText(f"{figs:,}")  # type: ignore[attr-defined]
            self._stat_embeds._value.setText(f"{embs:,}")   # type: ignore[attr-defined]
        except Exception as e:  # noqa: BLE001
            print(f"[health] {e}")

    def _on_rerank_toggled(self, on: bool) -> None:
        self._rerank_enabled = on

    def _on_file_chosen(self, data: bytes, _path: str) -> None:
        print(f"[main] file chosen, {len(data)} bytes, rerank={self._rerank_enabled}")
        self._preview_bytes = data
        self._loading_status.setText("준비 중…")
        self._stack.setCurrentIndex(PAGE_LOADING)

        worker = IdentifyWorker(data, rerank=self._rerank_enabled, k=10)
        worker.done.connect(self._on_done)
        worker.failed.connect(self._on_failed)
        worker.progress.connect(self._loading_status.setText)
        # Strong refs so neither the worker nor the thread are GC'd before they run.
        self._current_worker = worker
        self._current_thread = run_in_thread(worker, self)
        print("[main] worker dispatched to thread")

    def _on_done(self, result: IdentifyResult) -> None:
        has_photo = self._preview_bytes is not None
        self._result.set_result(result, self._preview_bytes, has_user_photo=has_photo)
        self._stack.setCurrentIndex(PAGE_RESULT)

    # ----- Confirm "이 사진이 맞아요" → background confirm_image -----

    def _on_confirm_requested(self, figure_id: int) -> None:
        if self._preview_bytes is None:
            return
        card = self._result.card(figure_id)
        if card is None:
            return
        card.set_confirming(True)

        worker = ConfirmImageWorker(figure_id, self._preview_bytes)
        def _done(cand, count, inserted):
            card.set_confirming(False)
            msg = f"이미 등록된 사진이에요 (총 {count}장)"
            if inserted:
                msg = f"사진 추가 + 학습 완료 ✓ (총 {count}장)"
            card.show_status(msg)
            self._refresh_health()
        def _failed(err):
            card.set_confirming(False)
            card.show_status(err, error=True)
        worker.done.connect(_done)
        worker.failed.connect(_failed)
        self._current_confirm_worker = worker         # keep alive
        self._current_confirm_thread = run_in_thread(worker, self)

    def _on_failed(self, msg: str) -> None:
        self._error_label.setText(msg)
        self._stack.setCurrentIndex(PAGE_ERROR)

    def _on_figure_added(self, cand, message: str) -> None:
        """User added a figure via DB-add panel — jump straight to result page."""
        from services.types import IdentifyResult, RerankMeta
        result = IdentifyResult(
            best=cand,
            alternates=[],
            rerank=RerankMeta(best_index=0, confidence="high", reason=message),
            fx_jpy_to_krw=0.0,
        )
        # No user photo on this path → don't show "이 사진이 맞아요" buttons.
        self._preview_bytes = None
        self._result.set_result(result, None, has_user_photo=False)
        self._stack.setCurrentIndex(PAGE_RESULT)
        self._refresh_health()

    def _reset(self) -> None:
        self._preview_bytes = None
        self._stack.setCurrentIndex(PAGE_UPLOAD)
        self._refresh_health()
