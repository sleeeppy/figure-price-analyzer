"""QThread workers — keep the UI responsive while embedder/Gemini/MFC run.

Each worker is a one-shot task: emits `done(result)` or `failed(message)`,
then quits. Connect signals from the caller.
"""
from __future__ import annotations
from typing import Optional

from PySide6.QtCore import QObject, QThread, Signal

from services.identify import identify
from services.types import IdentifyResult, LookupResult
from services.mutations import confirm_image, add_manual, add_by_mfc
from services.lookup import lookup as gemini_lookup


class IdentifyWorker(QObject):
    finished = Signal()
    done = Signal(object)   # IdentifyResult
    failed = Signal(str)
    progress = Signal(str)  # status message for the loading screen

    def __init__(self, image_bytes: bytes, *, rerank: bool, k: int):
        super().__init__()
        self._bytes = image_bytes
        self._rerank = rerank
        self._k = k

    def run(self) -> None:
        print("[worker] run() started")
        try:
            self.progress.emit("DINOv2 모델 로드…")
            from embeddings.embedder import get_embedder
            get_embedder()                                # warm cold-start here
            self.progress.emit("배경 제거 + 임베딩…")
            print("[worker] embedder ready, calling identify()")
            result: IdentifyResult = identify(
                self._bytes,
                rerank=self._rerank,
                k=self._k,
                multi_crop=True,
            )
            print(f"[worker] identify done: best={result.best.figure_id if result.best else None}")
            self.done.emit(result)
        except Exception as e:  # noqa: BLE001
            print(f"[worker] FAILED: {e}")
            import traceback
            traceback.print_exc()
            self.failed.emit(str(e))
        finally:
            print("[worker] emitting finished")
            self.finished.emit()


class LookupWorker(QObject):
    finished = Signal()
    done = Signal(object)   # LookupResult
    failed = Signal(str)

    def __init__(self, image_bytes: bytes, hint: str = ""):
        super().__init__()
        self._bytes = image_bytes
        self._hint = hint

    def run(self) -> None:
        try:
            result: LookupResult = gemini_lookup(self._bytes, hint=self._hint)
            self.done.emit(result)
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            self.failed.emit(str(e))
        finally:
            self.finished.emit()


class ConfirmImageWorker(QObject):
    finished = Signal()
    done = Signal(object, int, bool)   # candidate, count, inserted
    failed = Signal(str)

    def __init__(self, figure_id: int, image_bytes: bytes):
        super().__init__()
        self._fid = figure_id
        self._bytes = image_bytes

    def run(self) -> None:
        try:
            cand, count, inserted = confirm_image(self._fid, self._bytes)
            self.done.emit(cand, count, inserted)
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            self.failed.emit(str(e))
        finally:
            self.finished.emit()


class AddManualWorker(QObject):
    finished = Signal()
    done = Signal(object, int)   # candidate, new_figure_id
    failed = Signal(str)

    def __init__(self, *, image_bytes: bytes, **fields):
        super().__init__()
        self._bytes = image_bytes
        self._fields = fields

    def run(self) -> None:
        try:
            cand, fid = add_manual(image_bytes=self._bytes, **self._fields)
            self.done.emit(cand, fid)
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            self.failed.emit(str(e))
        finally:
            self.finished.emit()


class AddByMfcWorker(QObject):
    finished = Signal()
    done = Signal(object, bool)   # candidate, inserted
    failed = Signal(str)

    def __init__(self, url_or_id: str):
        super().__init__()
        self._url = url_or_id

    def run(self) -> None:
        try:
            cand, inserted = add_by_mfc(self._url)
            self.done.emit(cand, inserted)
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            self.failed.emit(str(e))
        finally:
            self.finished.emit()


def run_in_thread(worker: QObject, parent: QObject) -> QThread:
    """Spin up a QThread that owns `worker`. The caller binds done/failed
    *before* calling this so signals aren't missed. Thread quits on finish
    and deletes itself.
    """
    thread = QThread(parent)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)  # type: ignore[arg-type]
    worker.finished.connect(thread.quit)
    worker.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.start()
    return thread
