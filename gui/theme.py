"""Spotify-inspired dark Qt stylesheet + color tokens.

Mirrors what the old web build used so the desktop app looks the same:
near-black surfaces, Spotify green CTAs, white text, muted gray secondary.
"""

# Color tokens (also exposed for matplotlib + image rendering)
CANVAS = "#121212"
SURFACE_1 = "#181818"
SURFACE_2 = "#1f1f1f"
SURFACE_3 = "#252525"
SURFACE_4 = "#272727"
BORDER = "#4d4d4d"
INK = "#ffffff"
INK_MUTED = "#b3b3b3"
INK_DIM = "#7c7c7c"

PRIMARY = "#1ed760"          # Spotify green
PRIMARY_HOVER = "#1fdf64"
PRIMARY_PRESS = "#169c46"

ACCENT_BLUE = "#539df5"
ACCENT_ORANGE = "#ffa42b"
ACCENT_RED = "#f3727f"


STYLESHEET = f"""
* {{
    color: {INK};
    font-family: "Inter", "SF Pro Text", "Helvetica Neue", sans-serif;
    font-size: 13px;
}}

QMainWindow, QWidget {{
    background-color: {CANVAS};
}}

QLabel {{
    background: transparent;
}}

/* ---- Surfaces ---- */
.card {{
    background-color: {SURFACE_1};
    border-radius: 14px;
}}
.card-hero {{
    background-color: {SURFACE_1};
    border: 1px solid rgba(30, 215, 96, 0.5);
    border-radius: 14px;
}}
.card-accent-blue {{
    background-color: transparent;
    border: 1px solid rgba(83, 157, 245, 0.4);
    border-radius: 14px;
}}
.card-accent-red {{
    background-color: {SURFACE_1};
    border: 1px solid rgba(243, 114, 127, 0.5);
    border-radius: 14px;
}}

/* ---- Buttons (default = primary) ---- */
QPushButton {{
    background-color: {PRIMARY};
    color: #000000;
    border: none;
    border-radius: 500px;
    padding: 8px 22px;
    font-weight: 700;
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
}}
QPushButton[variant="secondary"]:hover {{
    background-color: {SURFACE_3};
}}

QPushButton[variant="ghost"] {{
    background-color: transparent;
    color: {INK};
    border: 1px solid {INK_DIM};
}}
QPushButton[variant="ghost"]:hover {{
    border-color: {INK};
    background-color: rgba(255,255,255,0.05);
}}

QPushButton[variant="tab-active"] {{
    background-color: {INK};
    color: #000000;
    border-radius: 500px;
    padding: 6px 14px;
    font-size: 11px;
}}
QPushButton[variant="tab"] {{
    background-color: {SURFACE_2};
    color: {INK};
    border-radius: 500px;
    padding: 6px 14px;
    font-size: 11px;
}}
QPushButton[variant="tab"]:hover {{
    background-color: {SURFACE_3};
}}

/* ---- Inputs ---- */
QLineEdit, QPlainTextEdit, QTextEdit {{
    background-color: {SURFACE_2};
    color: {INK};
    border: 1px solid {INK_DIM};
    border-radius: 10px;
    padding: 8px 12px;
    selection-background-color: {PRIMARY};
    selection-color: #000000;
}}
QLineEdit:focus {{
    border-color: {INK};
}}
QLineEdit::placeholder {{
    color: {INK_MUTED};
}}

/* ---- ScrollArea ---- */
QScrollArea {{
    background: transparent;
    border: none;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
}}
QScrollBar::handle:vertical {{
    background: {SURFACE_4};
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {BORDER};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

/* ---- Confidence pill (uses dynamic property `level`) ---- */
QLabel[role="pill-high"] {{
    background-color: {PRIMARY};
    color: #000000;
    border-radius: 500px;
    padding: 3px 10px;
    font-weight: 700;
    font-size: 11px;
}}
QLabel[role="pill-medium"] {{
    background-color: {ACCENT_ORANGE};
    color: #000000;
    border-radius: 500px;
    padding: 3px 10px;
    font-weight: 700;
    font-size: 11px;
}}
QLabel[role="pill-low"] {{
    background-color: {ACCENT_RED};
    color: #000000;
    border-radius: 500px;
    padding: 3px 10px;
    font-weight: 700;
    font-size: 11px;
}}

QLabel[role="heading"] {{
    font-size: 24px;
    font-weight: 700;
}}
QLabel[role="subheading"] {{
    font-size: 16px;
    font-weight: 700;
}}
QLabel[role="label"] {{
    color: {INK_MUTED};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
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
    font-weight: 700;
}}

/* ---- Drag-drop upload zone ---- */
QFrame[role="drop"] {{
    background-color: {SURFACE_1};
    border: 1px dashed {BORDER};
    border-radius: 16px;
}}
QFrame[role="drop-active"] {{
    background-color: {SURFACE_1};
    border: 2px solid {PRIMARY};
    border-radius: 16px;
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
