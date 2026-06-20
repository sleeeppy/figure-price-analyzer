"""Autocomplete QLineEdit — debounced lookup against services.suggest()."""
from __future__ import annotations

from PySide6.QtCore import QStringListModel, Qt, QTimer, Signal
from PySide6.QtWidgets import QCompleter, QLineEdit

from services.mutations import suggest


class AutocompleteLineEdit(QLineEdit):
    def __init__(self, field: str, placeholder: str = "", parent=None):
        super().__init__(parent)
        self._field = field
        self.setPlaceholderText(placeholder)

        self._model = QStringListModel(self)
        completer = QCompleter(self._model, self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.setCompleter(completer)

        # Debounce text-changed so we don't hammer the DB every keystroke.
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(150)
        self._timer.timeout.connect(self._refresh_suggestions)
        self.textEdited.connect(lambda _t: self._timer.start())

    def _refresh_suggestions(self) -> None:
        try:
            rows = suggest(self._field, self.text(), limit=12)
        except Exception:
            rows = []
        self._model.setStringList([v for v, _n in rows])
