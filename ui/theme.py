"""Central color tokens and Qt style sheets for both application themes."""
from __future__ import annotations

import re
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication
from utils.paths import asset_path


PALETTES = {
    "dark": {
        "background": "#0B0B0F", "surface": "#14141A", "raised": "#1B1B23",
        "border": "#292932", "text": "#F1F0F7", "muted": "#9694A9",
        "subtle": "#707083", "hover": "#23232D", "input": "#101016",
        "success": "#73D5B1", "danger": "#FF929F", "warning": "#EBC080",
    },
    "light": {
        "background": "#F5F5FA", "surface": "#FFFFFF", "raised": "#F0EFF7",
        "border": "#DEDDE8", "text": "#20202B", "muted": "#666379",
        "subtle": "#77748A", "hover": "#EAE8F3", "input": "#FAF9FD",
        "success": "#187B5C", "danger": "#B42C43", "warning": "#8C631F",
    },
}


def colors(theme: str = "dark", accent: str = "#7C5CFF") -> dict[str, str]:
    """Return validated theme tokens, including accent-derived colors."""
    tokens = PALETTES.get(theme, PALETTES["dark"]).copy()
    tokens["accent"] = accent if re.fullmatch(r"#[0-9a-fA-F]{6}", accent) else "#7C5CFF"
    color = QColor(tokens["accent"])
    tokens["accent_hover"] = color.lighter(115).name()
    tokens["accent_pressed"] = color.darker(115).name()
    # A readable foreground remains essential when the user picks a pale accent.
    luminance = .2126 * color.redF() + .7152 * color.greenF() + .0722 * color.blueF()
    tokens["accent_text"] = "#11111A" if luminance > .62 else "#FFFFFF"
    tokens["accent_soft"] = QColor(
        int(color.red() * .16 + QColor(tokens["surface"]).red() * .84),
        int(color.green() * .16 + QColor(tokens["surface"]).green() * .84),
        int(color.blue() * .16 + QColor(tokens["surface"]).blue() * .84),
    ).name()
    return tokens


def apply_theme(app: QApplication, theme: str = "dark", accent: str = "#7C5CFF") -> None:
    """Apply consistent widget colors, native dialog palette and typography."""
    c = colors(theme, accent)
    arrow = asset_path("icons/chevron-down.svg").as_posix()
    app.setFont(QFont("Segoe UI Variable", 10))
    palette = QPalette()
    roles = {
        QPalette.ColorRole.Window: "background", QPalette.ColorRole.WindowText: "text",
        QPalette.ColorRole.Base: "input", QPalette.ColorRole.AlternateBase: "surface",
        QPalette.ColorRole.Text: "text", QPalette.ColorRole.Button: "raised",
        QPalette.ColorRole.ButtonText: "text", QPalette.ColorRole.Highlight: "accent",
        QPalette.ColorRole.HighlightedText: "accent_text",
        QPalette.ColorRole.ToolTipBase: "raised", QPalette.ColorRole.ToolTipText: "text",
        QPalette.ColorRole.PlaceholderText: "subtle",
    }
    for role, token in roles.items():
        palette.setColor(role, QColor(c[token]))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(c["subtle"]))
    app.setPalette(palette)
    app.setStyleSheet(f"""
    * {{ font-family: 'Segoe UI Variable', 'Segoe UI', sans-serif; font-size: 13px; }}
    QMainWindow, QDialog {{ background: {c['background']}; color: {c['text']}; }}
    QWidget {{ color: {c['text']}; }}
    QWidget#WindowShell {{ background: {c['background']}; border: 1px solid {c['border']}; border-radius: 14px; }}
    QFrame#Sidebar {{ background: {c['surface']}; border: none; border-right: 1px solid {c['border']}; }}
    QWidget#TitleBar {{ background: transparent; }}
    QFrame#Card {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 14px; }}
    QFrame#SoftCard {{ background: {c['raised']}; border: none; border-radius: 12px; }}
    QFrame#Notice {{ background: {c['accent_soft']}; border: 1px solid {c['border']}; border-radius: 10px; }}
    QFrame#Divider {{ background: {c['border']}; border: none; max-height: 1px; }}
    QLabel {{ background: transparent; border: none; }}
    QLabel[role='hero'] {{ font-size: 33px; font-weight: 650; letter-spacing: -1px; }}
    QLabel[role='heading'] {{ font-size: 26px; font-weight: 650; letter-spacing: -0.5px; }}
    QLabel[role='section'] {{ font-size: 16px; font-weight: 600; }}
    QLabel[role='muted'] {{ color: {c['muted']}; }}
    QLabel[role='caption'] {{ color: {c['muted']}; font-size: 11px; }}
    QLabel[role='eyebrow'] {{ color: {c['accent']}; font-size: 10px; font-weight: 700; letter-spacing: 2px; }}
    QLabel[role='success'] {{ color: {c['success']}; }}
    QLabel[role='error'] {{ color: {c['danger']}; }}
    QPushButton, QToolButton {{ background: {c['raised']}; border: 1px solid {c['border']};
        border-radius: 9px; padding: 9px 14px; font-weight: 500; }}
    QPushButton:hover, QToolButton:hover {{ background: {c['hover']}; border-color: {c['subtle']}; }}
    QPushButton:pressed, QToolButton:pressed {{ background: {c['input']}; }}
    QPushButton:focus, QToolButton:focus {{ border: 1px solid {c['accent']}; }}
    QPushButton:disabled, QToolButton:disabled {{ color: {c['subtle']}; border-color: {c['border']}; background: {c['surface']}; }}
    QPushButton[role='primary'] {{ color: {c['accent_text']}; background: {c['accent']}; border: none;
        border-radius: 20px; padding: 12px 24px; font-size: 14px; font-weight: 600; }}
    QPushButton[role='primary']:hover {{ background: {c['accent_hover']}; }}
    QPushButton[role='primary']:pressed {{ background: {c['accent_pressed']}; }}
    QPushButton[role='primary']:disabled {{ background: {c['raised']}; color: {c['subtle']}; }}
    QPushButton[role='ghost'], QToolButton[role='ghost'] {{ border: 1px solid transparent; background: transparent; }}
    QPushButton[role='ghost']:hover, QToolButton[role='ghost']:hover {{ background: {c['hover']}; }}
    QPushButton[role='nav'] {{ text-align: left; padding: 12px 14px; border: none; background: transparent;
        border-radius: 10px; color: {c['muted']}; font-size: 13px; }}
    QPushButton[role='nav']:hover {{ background: {c['hover']}; color: {c['text']}; }}
    QPushButton[role='nav']:checked {{ background: {c['accent_soft']}; color: {c['text']}; }}
    QPushButton[role='danger'] {{ color: {c['danger']}; }}
    QToolButton[role='close']:hover {{ background: #B73246; color: white; }}
    QLineEdit, QPlainTextEdit, QSpinBox, QComboBox, QDateEdit {{ background: {c['input']}; border: 1px solid {c['border']};
        border-radius: 9px; padding: 9px 11px; selection-background-color: {c['accent']}; }}
    QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QComboBox:focus {{ border-color: {c['accent']}; }}
    QPlainTextEdit#LinkInput {{ font-size: 16px; padding: 15px; border-radius: 12px; }}
    QComboBox {{ padding-right: 28px; min-height: 17px; }}
    QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: top right; width: 25px; border: none; }}
    QComboBox::down-arrow {{ image: url("{arrow}"); width: 13px; height: 13px; }}
    QComboBox QAbstractItemView {{ background: {c['raised']}; color: {c['text']}; border: 1px solid {c['border']};
        selection-background-color: {c['accent_soft']}; padding: 5px; outline: none; }}
    QSpinBox::up-button, QSpinBox::down-button {{ width: 18px; border: none; }}
    QCheckBox {{ spacing: 9px; padding: 4px 0px; }}
    QCheckBox::indicator {{ width: 17px; height: 17px; border: 1px solid {c['subtle']}; background: {c['input']}; border-radius: 5px; }}
    QCheckBox::indicator:checked {{ background: {c['accent']}; border-color: {c['accent']}; }}
    QCheckBox::indicator:indeterminate {{ background: {c['accent_soft']}; border-color: {c['accent']}; }}
    QCheckBox::indicator:hover {{ border-color: {c['accent']}; }}
    QRadioButton {{ spacing: 8px; padding: 5px; }}
    QProgressBar {{ background: {c['raised']}; border: none; border-radius: 3px; min-height: 6px; max-height: 6px; }}
    QProgressBar::chunk {{ background: {c['accent']}; border-radius: 3px; }}
    QScrollArea, QStackedWidget {{ background: transparent; border: none; }}
    QScrollArea > QWidget > QWidget {{ background: transparent; }}
    QScrollBar:vertical {{ background: transparent; width: 9px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {c['border']}; border-radius: 3px; min-height: 30px; }}
    QScrollBar::handle:vertical:hover {{ background: {c['subtle']}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
    QScrollBar:horizontal {{ background: transparent; height: 9px; margin: 2px; }}
    QScrollBar::handle:horizontal {{ background: {c['border']}; border-radius: 3px; min-width: 30px; }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: transparent; }}
    QListWidget, QTableWidget {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 12px;
        alternate-background-color: {c['surface']}; gridline-color: {c['border']}; outline: none; }}
    QListWidget::item {{ padding: 10px; border-bottom: 1px solid {c['border']}; }}
    QListWidget::item:selected, QTableWidget::item:selected {{ background: {c['accent_soft']}; color: {c['text']}; }}
    QTableWidget::item {{ padding: 8px; border-bottom: 1px solid {c['border']}; }}
    QHeaderView::section {{ background: {c['surface']}; color: {c['muted']}; border: none;
        border-bottom: 1px solid {c['border']}; padding: 12px 8px; font-size: 11px; font-weight: 500; }}
    QMenu {{ background: {c['raised']}; border: 1px solid {c['border']}; border-radius: 9px; padding: 6px; }}
    QMenu::item {{ padding: 9px 24px 9px 12px; border-radius: 5px; }}
    QMenu::item:selected {{ background: {c['accent_soft']}; }}
    QMenu::separator {{ height: 1px; background: {c['border']}; margin: 5px; }}
    QToolTip {{ color: {c['text']}; background: {c['raised']}; border: 1px solid {c['border']}; padding: 7px; }}
    QMessageBox {{ background: {c['surface']}; }}
    """)
