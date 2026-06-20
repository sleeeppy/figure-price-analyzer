"""Entry point: `python -m gui`.
Launches the native PySide6 desktop app. No web server, no browser.
"""
from __future__ import annotations
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import QApplication

from gui import theme
from gui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("FigurePrice")
    app.setStyle("Fusion")

    # Base palette tweak so native chrome (menus etc.) also goes dark.
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(theme.CANVAS))
    palette.setColor(QPalette.WindowText, QColor(theme.INK))
    palette.setColor(QPalette.Base, QColor(theme.SURFACE_2))
    palette.setColor(QPalette.AlternateBase, QColor(theme.SURFACE_3))
    palette.setColor(QPalette.Text, QColor(theme.INK))
    palette.setColor(QPalette.Button, QColor(theme.SURFACE_2))
    palette.setColor(QPalette.ButtonText, QColor(theme.INK))
    palette.setColor(QPalette.Highlight, QColor(theme.PRIMARY))
    palette.setColor(QPalette.HighlightedText, QColor("#000000"))
    palette.setColor(QPalette.ToolTipBase, QColor(theme.SURFACE_3))
    palette.setColor(QPalette.ToolTipText, QColor(theme.INK))
    app.setPalette(palette)

    app.setStyleSheet(theme.STYLESHEET)

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
