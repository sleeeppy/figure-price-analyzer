"""Soft modern dark theme for the FigurePrice desktop app.

Warm charcoal surfaces, generous radii, soft borders — less Spotify-pill,
more contemporary app chrome.
"""

# Color tokens (also exposed for matplotlib + image rendering)
CANVAS = "#101012"
SURFACE_1 = "#1c1c20"
SURFACE_2 = "#26262c"
SURFACE_3 = "#303038"
SURFACE_4 = "#3a3a44"
BORDER = "#3f3f4a"
BORDER_SOFT = "rgba(255, 255, 255, 0.08)"
INK = "#f5f5f7"
INK_MUTED = "#a1a1aa"
INK_DIM = "#71717a"

PRIMARY = "#2dd26a"
PRIMARY_HOVER = "#3adf78"
PRIMARY_PRESS = "#22b85a"

ACCENT_BLUE = "#60a5fa"
ACCENT_ORANGE = "#fb923c"
ACCENT_RED = "#f87171"

# Shared radii
RADIUS_WINDOW = 20
RADIUS_CARD = 18
RADIUS_CONTROL = 12
RADIUS_INPUT = 12
RADIUS_PILL = 999


STYLESHEET = f"""
* {{
    color: {INK};
    font-family: "SF Pro Text", "SF Pro Display", "Helvetica Neue", "Inter", sans-serif;
    font-size: 13px;
}}

QMainWindow {{
    background: transparent;
}}

QWidget {{
    background-color: transparent;
}}

QLabel {{
    background: transparent;
}}

/* ---- App shell background is painted in code (mask + border stay aligned) ---- */
QFrame#appShell {{
    background: transparent;
    border: none;
}}

QFrame#appHeader {{
    background-color: transparent;
    border: none;
    border-bottom: 1px solid {BORDER_SOFT};
}}

QFrame#appFooter {{
    background-color: transparent;
    border: none;
    border-top: 1px solid {BORDER_SOFT};
}}

/* ---- Surfaces ---- */
.card {{
    background-color: {SURFACE_1};
    border: 1px solid {BORDER_SOFT};
    border-radius: {RADIUS_CARD}px;
}}
.card-hero {{
    background-color: {SURFACE_1};
    border: 1px solid rgba(45, 210, 106, 0.35);
    border-radius: {RADIUS_CARD}px;
}}
.card-accent-blue {{
    background-color: rgba(96, 165, 250, 0.06);
    border: 1px solid rgba(96, 165, 250, 0.28);
    border-radius: {RADIUS_CARD}px;
}}
.card-accent-red {{
    background-color: rgba(248, 113, 113, 0.06);
    border: 1px solid rgba(248, 113, 113, 0.35);
    border-radius: {RADIUS_CARD}px;
}}

/* ---- Buttons (soft rounded rect, not full pill) ---- */
QPushButton {{
    background-color: {PRIMARY};
    color: #0a0a0b;
    border: none;
    border-radius: {RADIUS_CONTROL}px;
    padding: 9px 18px;
    font-weight: 600;
    font-size: 13px;
}}
QPushButton:hover {{
    background-color: {PRIMARY_HOVER};
}}
QPushButton:pressed {{
    background-color: {PRIMARY_PRESS};
}}
QPushButton:disabled {{
    background-color: {SURFACE_3};
    color: {INK_DIM};
}}

QPushButton[variant="secondary"] {{
    background-color: {SURFACE_2};
    color: {INK};
    border: 1px solid {BORDER_SOFT};
}}
QPushButton[variant="secondary"]:hover {{
    background-color: {SURFACE_3};
}}

QPushButton[variant="ghost"] {{
    background-color: transparent;
    color: {INK};
    border: 1px solid {BORDER};
}}
QPushButton[variant="ghost"]:hover {{
    border-color: {INK_MUTED};
    background-color: rgba(255, 255, 255, 0.04);
}}

QPushButton[variant="tab-active"] {{
    background-color: {INK};
    color: #0a0a0b;
    border-radius: {RADIUS_CONTROL}px;
    padding: 6px 14px;
    font-size: 11px;
    font-weight: 600;
}}
QPushButton[variant="tab"] {{
    background-color: {SURFACE_2};
    color: {INK_MUTED};
    border: 1px solid {BORDER_SOFT};
    border-radius: {RADIUS_CONTROL}px;
    padding: 6px 14px;
    font-size: 11px;
    font-weight: 600;
}}
QPushButton[variant="tab"]:hover {{
    background-color: {SURFACE_3};
    color: {INK};
}}

QPushButton[variant="window"] {{
    background-color: transparent;
    color: {INK_MUTED};
    border: none;
    border-radius: 8px;
    padding: 4px 8px;
    font-size: 12px;
    font-weight: 600;
    min-width: 28px;
}}
QPushButton[variant="window"]:hover {{
    background-color: rgba(255, 255, 255, 0.08);
    color: {INK};
}}
QPushButton[variant="window-close"]:hover {{
    background-color: {ACCENT_RED};
    color: #0a0a0b;
}}

/* ---- Inputs ---- */
QLineEdit, QPlainTextEdit, QTextEdit {{
    background-color: {SURFACE_2};
    color: {INK};
    border: 1px solid {BORDER_SOFT};
    border-radius: {RADIUS_INPUT}px;
    padding: 9px 12px;
    selection-background-color: {PRIMARY};
    selection-color: #0a0a0b;
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {{
    border-color: rgba(45, 210, 106, 0.55);
}}
QLineEdit::placeholder {{
    color: {INK_DIM};
}}

/* ---- ScrollArea ---- */
QScrollArea {{
    background: transparent;
    border: none;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 4px 2px;
}}
QScrollBar::handle:vertical {{
    background: {SURFACE_4};
    border-radius: 4px;
    min-height: 28px;
}}
QScrollBar::handle:vertical:hover {{
    background: {BORDER};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

/* ---- Confidence pills ---- */
QLabel[role="pill-high"] {{
    background-color: {PRIMARY};
    color: #0a0a0b;
    border-radius: {RADIUS_CONTROL}px;
    padding: 4px 10px;
    font-weight: 700;
    font-size: 11px;
}}
QLabel[role="pill-medium"] {{
    background-color: {ACCENT_ORANGE};
    color: #0a0a0b;
    border-radius: {RADIUS_CONTROL}px;
    padding: 4px 10px;
    font-weight: 700;
    font-size: 11px;
}}
QLabel[role="pill-low"] {{
    background-color: {ACCENT_RED};
    color: #0a0a0b;
    border-radius: {RADIUS_CONTROL}px;
    padding: 4px 10px;
    font-weight: 700;
    font-size: 11px;
}}

QLabel[role="heading"] {{
    font-size: 24px;
    font-weight: 700;
    letter-spacing: -0.3px;
}}
QLabel[role="subheading"] {{
    font-size: 16px;
    font-weight: 650;
    letter-spacing: -0.2px;
}}
QLabel[role="label"] {{
    color: {INK_MUTED};
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.6px;
}}
QLabel[role="muted"] {{
    color: {INK_MUTED};
    font-size: 12px;
}}
QLabel[role="error"] {{
    color: {ACCENT_RED};
    font-size: 12px;
}}
QLabel[role="success"] {{
    color: {PRIMARY};
    font-size: 12px;
    font-weight: 600;
}}

/* ---- Drag-drop upload zone ---- */
QFrame[role="drop"] {{
    background-color: {SURFACE_1};
    border: 1.5px dashed {BORDER};
    border-radius: {RADIUS_CARD}px;
}}
QFrame[role="drop-active"] {{
    background-color: rgba(45, 210, 106, 0.06);
    border: 1.5px solid {PRIMARY};
    border-radius: {RADIUS_CARD}px;
}}
"""


# ---- matplotlib palette mirror ----
MPL_BG = CANVAS
MPL_AXIS = INK
MPL_GRID = SURFACE_4
MPL_MUTED = INK_MUTED
MPL_GREEN = PRIMARY
MPL_ORANGE = ACCENT_ORANGE
MPL_RED = ACCENT_RED
MPL_BLUE = ACCENT_BLUE
