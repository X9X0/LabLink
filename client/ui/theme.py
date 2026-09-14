"""
LabLink UI Theme and Styling
============================

Provides consistent theming across Windows, Linux, and macOS platforms.
Supports multiple theme modes: Light, Dark, and Auto (system default).
"""

import json
from pathlib import Path
from typing import Literal

ThemeMode = Literal["light", "dark", "auto"]

# Theme settings file location
THEME_SETTINGS_FILE = Path.home() / ".lablink" / "theme_settings.json"


def get_theme_setting() -> ThemeMode:
    """
    Get the saved theme preference.

    Returns:
        Theme mode: "light", "dark", or "auto"
    """
    try:
        if THEME_SETTINGS_FILE.exists():
            with open(THEME_SETTINGS_FILE, 'r') as f:
                settings = json.load(f)
                return settings.get("theme", "light")
    except Exception:
        pass
    return "light"


def save_theme_setting(theme: ThemeMode) -> None:
    """
    Save theme preference to disk.

    Args:
        theme: Theme mode to save
    """
    try:
        THEME_SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(THEME_SETTINGS_FILE, 'w') as f:
            json.dump({"theme": theme}, f)
    except Exception as e:
        print(f"Failed to save theme setting: {e}")


def dialog_palette(theme: ThemeMode = None) -> dict:
    """Colours for widgets that set their own stylesheet.

    A stylesheet set on a widget overrides the application one, so any dialog
    that hardcodes ``background-color: white`` stays white in dark mode --
    while its text colour still comes from the dark application sheet. White
    panel, pale grey text, and nothing readable on it. That was the reported
    symptom, and the cause is spread across several dialogs rather than being
    in the dark stylesheet at all.

    The fix is not to delete those stylesheets, which carry deliberate layout
    and light-mode styling, but to feed them colours that follow the theme.
    Format a stylesheet with ``**dialog_palette()``.

    ``accent``/``accent_hover`` are the application sheet's own button blue.
    A panel that must style a control the application sheet does not reach --
    a QCheckBox indicator, say -- takes the colour from here instead of
    choosing its own, which is how the app came to show two different blues.
    A control the application sheet already styles needs no stylesheet at all.

    ``auto`` resolves to the light values, matching ``_get_auto_stylesheet``.
    """
    if theme is None:
        theme = get_theme_setting()

    if theme == "dark":
        return {
            "window_bg": "#2b2b2b",
            "panel_bg": "#353535",
            "panel_border": "#4a4a4a",
            "text": "#e0e0e0",
            "muted_text": "#a0a0a0",
            "info_bg": "#3a3a3a",
            "field_bg": "#3c3c3c",
            "warn_bg": "#4a3f1f",
            "warn_text": "#ffd479",
            "accent": "#2196F3",
            "accent_hover": "#42A5F5",
        }

    return {
        "window_bg": "#ecf0f1",
        "panel_bg": "white",
        "panel_border": "#bdc3c7",
        "text": "#2c3e50",
        "muted_text": "#666666",
        "info_bg": "#f0f0f0",
        "field_bg": "white",
        "warn_bg": "#fff3cd",
        "warn_text": "#856404",
        "accent": "#2196F3",
        "accent_hover": "#1976D2",
    }


#: Canonical severity levels for table cells, worst last.
STATUS_LEVELS = ("healthy", "degraded", "warning", "critical")


def status_palette(theme: ThemeMode = None) -> dict:
    """Background and foreground pairs for status cells in tables.

    Cells used to set a background and no foreground. The fills are pale by
    design -- pale green for healthy, pale yellow for degraded -- so under the
    dark application sheet its #e0e0e0 text landed on them at a contrast ratio
    of about 1.2:1. "healthy" on pale green was effectively invisible; the
    colour that was meant to convey the status destroyed the word carrying it.

    A background is therefore never set without the matching foreground, and
    both come from here. Every pair clears WCAG AA (4.5:1), which the tests
    assert rather than trust.

    Returns:
        ``{level: (background_hex, foreground_hex)}`` for STATUS_LEVELS.
    """
    if theme is None:
        theme = get_theme_setting()

    if theme == "dark":
        # Muted fills, so a table of statuses does not glow against the dark
        # sheet, with the hue carried by the text instead.
        return {
            "healthy": ("#1e3a24", "#8fe39d"),
            "degraded": ("#3a361a", "#e6d76b"),
            "warning": ("#3d2f1c", "#f3b169"),
            "critical": ("#3d2020", "#f59a9a"),
        }

    # The fills light mode always had, now with text dark enough to read.
    return {
        "healthy": ("#c8ffc8", "#14532d"),
        "degraded": ("#ffffc8", "#544a07"),
        "warning": ("#ffe6c8", "#5c3a0a"),
        "critical": ("#ffc8c8", "#6b1111"),
    }


def apply_status_colors(item, level: str, theme: ThemeMode = None) -> bool:
    """Colour a table or list item for `level`, background and text together.

    Qt is imported inside the function so this module stays importable without
    a GUI, which the settings helpers above rely on.

    Args:
        item: a QTableWidgetItem or QListWidgetItem
        level: one of STATUS_LEVELS; anything else leaves the item alone, so an
            unrecognised status keeps the table's own readable colours rather
            than getting a fill with no matching text colour.

    Returns:
        Whether the level was recognised and applied.
    """
    from PyQt6.QtGui import QBrush, QColor

    pair = status_palette(theme).get(level)
    if pair is None:
        return False

    background, foreground = pair
    item.setBackground(QBrush(QColor(background)))
    item.setForeground(QBrush(QColor(foreground)))
    return True


def get_app_stylesheet(theme: ThemeMode = "light") -> str:
    """
    Get the application stylesheet for the specified theme.

    Args:
        theme: Theme mode - "light", "dark", or "auto"

    Returns:
        Complete application stylesheet string
    """
    if theme == "dark":
        return _get_dark_stylesheet()
    elif theme == "auto":
        # For now, auto mode uses a medium theme
        # In the future, this could detect system theme
        return _get_auto_stylesheet()
    else:
        return _get_light_stylesheet()


def _get_light_stylesheet() -> str:
    """Get the light theme stylesheet."""
    return """
    /* ========================================
       LIGHT THEME - General Application Styling
       ======================================== */

    QMainWindow {
        background-color: #f5f5f5;
    }

    QWidget {
        background-color: #f5f5f5;
        color: #212121;
        font-size: 9pt;
    }

    /* Labels and Text */
    QLabel {
        color: #212121;
        background-color: transparent;
    }

    QLabel[heading="true"] {
        font-size: 14pt;
        font-weight: bold;
        color: #1976D2;
    }

    /* Buttons */
    QPushButton {
        background-color: #2196F3;
        color: white;
        border: none;
        border-radius: 4px;
        padding: 6px 16px;
        font-weight: bold;
        min-height: 24px;
    }

    QPushButton:hover {
        background-color: #1976D2;
    }

    QPushButton:pressed {
        background-color: #1565C0;
    }

    QPushButton:disabled {
        background-color: #BDBDBD;
        color: #757575;
    }

    QPushButton[buttonStyle="secondary"] {
        background-color: #757575;
        color: white;
    }

    QPushButton[buttonStyle="secondary"]:hover {
        background-color: #616161;
    }

    QPushButton[buttonStyle="success"] {
        background-color: #4CAF50;
        color: white;
    }

    QPushButton[buttonStyle="success"]:hover {
        background-color: #388E3C;
    }

    QPushButton[buttonStyle="warning"] {
        background-color: #FF9800;
        color: white;
    }

    QPushButton[buttonStyle="warning"]:hover {
        background-color: #F57C00;
    }

    QPushButton[buttonStyle="danger"] {
        background-color: #F44336;
        color: white;
    }

    QPushButton[buttonStyle="danger"]:hover {
        background-color: #D32F2F;
    }

    /* Launcher-Specific Styles */
    QLabel[headerLabel="true"] {
        padding: 20px;
        background-color: #1a252f;
        color: white;
        border-radius: 8px;
        border: 2px solid #0d1419;
    }

    QLabel[headerLabel="true"][debugMode="true"] {
        background-color: #c0392b;
        border: 2px solid #e74c3c;
    }

    QLabel[statusLabel="true"] {
        padding: 8px;
        background-color: white;
        border: 1px solid #BDBDBD;
        border-radius: 4px;
        color: #212121;
    }

    QLabel[infoLabel="true"] {
        color: #757575;
        padding: 10px;
    }

    /* Input Fields */
    QLineEdit, QTextEdit, QPlainTextEdit {
        background-color: white;
        color: #212121;
        border: 1px solid #BDBDBD;
        border-radius: 4px;
        padding: 4px 8px;
        selection-background-color: #2196F3;
        selection-color: white;
    }

    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
        border: 2px solid #2196F3;
    }

    QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled {
        background-color: #F5F5F5;
        color: #9E9E9E;
    }

    /* ComboBox */
    QComboBox {
        background-color: white;
        color: #212121;
        border: 1px solid #BDBDBD;
        border-radius: 4px;
        padding: 4px 8px;
        min-height: 24px;
    }

    QComboBox:hover {
        border: 1px solid #2196F3;
    }

    QComboBox:focus {
        border: 2px solid #2196F3;
    }

    QComboBox::drop-down {
        border: none;
        width: 20px;
    }

    QComboBox::down-arrow {
        image: none;
        border-left: 4px solid transparent;
        border-right: 4px solid transparent;
        border-top: 6px solid #757575;
        margin-right: 6px;
    }

    QComboBox QAbstractItemView {
        background-color: white;
        color: #212121;
        selection-background-color: #E3F2FD;
        selection-color: #212121;
        border: 1px solid #BDBDBD;
        outline: none;
    }

    QComboBox QAbstractItemView::item {
        padding: 4px 8px;
        min-height: 24px;
    }

    QComboBox QAbstractItemView::item:hover {
        background-color: #BBDEFB;
        color: #212121;
    }

    QComboBox QAbstractItemView::item:selected {
        background-color: #90CAF9;
        color: #212121;
    }

    /* Tab Widget */
    QTabWidget::pane {
        border: 1px solid #BDBDBD;
        background-color: white;
        border-radius: 4px;
    }

    QTabBar::tab {
        background-color: #E0E0E0;
        color: #424242;
        padding: 8px 16px;
        margin-right: 2px;
        border-top-left-radius: 4px;
        border-top-right-radius: 4px;
    }

    QTabBar::tab:hover {
        background-color: #D5D5D5;
    }

    QTabBar::tab:selected {
        background-color: white;
        color: #1976D2;
        font-weight: bold;
    }

    /* Group Box */
    QGroupBox {
        background-color: white;
        border: 1px solid #BDBDBD;
        border-radius: 6px;
        margin-top: 12px;
        padding-top: 12px;
        font-weight: bold;
    }

    QGroupBox::title {
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 10px;
        padding: 0 5px;
        color: #1976D2;
    }

    /* Table Widget */
    QTableWidget {
        background-color: white;
        alternate-background-color: #FAFAFA;
        gridline-color: #E0E0E0;
        border: 1px solid #BDBDBD;
        border-radius: 4px;
        selection-background-color: #E3F2FD;
        selection-color: #212121;
    }

    QTableWidget::item {
        padding: 4px;
        color: #212121;
    }

    QTableWidget::item:selected {
        background-color: #90CAF9;
        color: #212121;
    }

    QHeaderView::section {
        background-color: #F5F5F5;
        color: #424242;
        font-weight: bold;
        padding: 6px;
        border: none;
        border-bottom: 2px solid #1976D2;
    }

    /* Progress Bar */
    QProgressBar {
        background-color: #E0E0E0;
        border: 1px solid #BDBDBD;
        border-radius: 4px;
        text-align: center;
        color: #212121;
        font-weight: bold;
    }

    QProgressBar::chunk {
        background-color: #2196F3;
        border-radius: 3px;
    }

    /* Scroll Bars */
    QScrollBar:vertical {
        background-color: #F5F5F5;
        width: 12px;
        border-radius: 6px;
    }

    QScrollBar::handle:vertical {
        background-color: #BDBDBD;
        border-radius: 6px;
        min-height: 20px;
    }

    QScrollBar::handle:vertical:hover {
        background-color: #9E9E9E;
    }

    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0px;
    }

    QScrollBar:horizontal {
        background-color: #F5F5F5;
        height: 12px;
        border-radius: 6px;
    }

    QScrollBar::handle:horizontal {
        background-color: #BDBDBD;
        border-radius: 6px;
        min-width: 20px;
    }

    QScrollBar::handle:horizontal:hover {
        background-color: #9E9E9E;
    }

    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
        width: 0px;
    }

    /* Status Bar */
    QStatusBar {
        background-color: #F5F5F5;
        color: #424242;
        border-top: 1px solid #BDBDBD;
    }

    /* Menu Bar and Menus */
    QMenuBar {
        background-color: #F5F5F5;
        color: #212121;
        border-bottom: 1px solid #BDBDBD;
    }

    QMenuBar::item {
        padding: 4px 12px;
        background-color: transparent;
    }

    QMenuBar::item:selected {
        background-color: #E3F2FD;
    }

    QMenu {
        background-color: white;
        color: #212121;
        border: 1px solid #BDBDBD;
    }

    QMenu::item {
        padding: 6px 24px 6px 12px;
    }

    QMenu::item:selected {
        background-color: #E3F2FD;
    }

    /* Checkboxes and Radio Buttons */
    QCheckBox, QRadioButton {
        color: #212121;
        spacing: 6px;
    }

    QCheckBox:disabled, QRadioButton:disabled {
        color: #9E9E9E;
    }

    /* Spin Box */
    QSpinBox, QDoubleSpinBox {
        background-color: white;
        color: #212121;
        border: 1px solid #BDBDBD;
        border-radius: 4px;
        padding: 4px 8px;
    }

    QSpinBox:focus, QDoubleSpinBox:focus {
        border: 2px solid #2196F3;
    }

    /* Tooltips */
    QToolTip {
        background-color: #424242;
        color: white;
        border: 1px solid #212121;
        padding: 4px;
        border-radius: 4px;
    }

    /* Dialog */
    QDialog {
        background-color: #f5f5f5;
    }
    """


def _get_dark_stylesheet() -> str:
    """Get the dark theme stylesheet."""
    return """
    /* ========================================
       DARK THEME - General Application Styling
       ======================================== */

    QMainWindow {
        background-color: #1e1e1e;
    }

    QWidget {
        background-color: #1e1e1e;
        color: #e0e0e0;
        font-size: 9pt;
    }

    /* Labels and Text */
    QLabel {
        color: #e0e0e0;
        background-color: transparent;
    }

    QLabel[heading="true"] {
        font-size: 14pt;
        font-weight: bold;
        color: #64B5F6;
    }

    /* Buttons */
    QPushButton {
        background-color: #2196F3;
        color: white;
        border: none;
        border-radius: 4px;
        padding: 6px 16px;
        font-weight: bold;
        min-height: 24px;
    }

    QPushButton:hover {
        background-color: #42A5F5;
    }

    QPushButton:pressed {
        background-color: #1E88E5;
    }

    QPushButton:disabled {
        background-color: #424242;
        color: #757575;
    }

    QPushButton[buttonStyle="secondary"] {
        background-color: #616161;
        color: white;
    }

    QPushButton[buttonStyle="secondary"]:hover {
        background-color: #757575;
    }

    QPushButton[buttonStyle="success"] {
        background-color: #4CAF50;
        color: white;
    }

    QPushButton[buttonStyle="success"]:hover {
        background-color: #66BB6A;
    }

    QPushButton[buttonStyle="warning"] {
        background-color: #FF9800;
        color: white;
    }

    QPushButton[buttonStyle="warning"]:hover {
        background-color: #FFA726;
    }

    QPushButton[buttonStyle="danger"] {
        background-color: #F44336;
        color: white;
    }

    QPushButton[buttonStyle="danger"]:hover {
        background-color: #EF5350;
    }

    /* Launcher-Specific Styles */
    QLabel[headerLabel="true"] {
        padding: 20px;
        background-color: #1a252f;
        color: white;
        border-radius: 8px;
        border: 2px solid #0d1419;
    }

    QLabel[headerLabel="true"][debugMode="true"] {
        background-color: #c0392b;
        border: 2px solid #e74c3c;
    }

    QLabel[statusLabel="true"] {
        padding: 8px;
        background-color: #2b2b2b;
        border: 1px solid #424242;
        border-radius: 4px;
        color: #e0e0e0;
    }

    QLabel[infoLabel="true"] {
        color: #9E9E9E;
        padding: 10px;
    }

    /* Input Fields */
    QLineEdit, QTextEdit, QPlainTextEdit {
        background-color: #2b2b2b;
        color: #e0e0e0;
        border: 1px solid #424242;
        border-radius: 4px;
        padding: 4px 8px;
        selection-background-color: #2196F3;
        selection-color: white;
    }

    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
        border: 2px solid #2196F3;
    }

    QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled {
        background-color: #1e1e1e;
        color: #616161;
    }

    /* ComboBox */
    QComboBox {
        background-color: #2b2b2b;
        color: #e0e0e0;
        border: 1px solid #424242;
        border-radius: 4px;
        padding: 4px 8px;
        min-height: 24px;
    }

    QComboBox:hover {
        border: 1px solid #2196F3;
    }

    QComboBox:focus {
        border: 2px solid #2196F3;
    }

    QComboBox::drop-down {
        border: none;
        width: 20px;
    }

    QComboBox::down-arrow {
        image: none;
        border-left: 4px solid transparent;
        border-right: 4px solid transparent;
        border-top: 6px solid #9E9E9E;
        margin-right: 6px;
    }

    QComboBox QAbstractItemView {
        background-color: #2b2b2b;
        color: #e0e0e0;
        selection-background-color: #1565C0;
        selection-color: white;
        border: 1px solid #424242;
        outline: none;
    }

    QComboBox QAbstractItemView::item {
        padding: 4px 8px;
        min-height: 24px;
    }

    QComboBox QAbstractItemView::item:hover {
        background-color: #1976D2;
        color: white;
    }

    QComboBox QAbstractItemView::item:selected {
        background-color: #1565C0;
        color: white;
    }

    /* Tab Widget */
    QTabWidget::pane {
        border: 1px solid #424242;
        background-color: #2b2b2b;
        border-radius: 4px;
    }

    QTabBar::tab {
        background-color: #2b2b2b;
        color: #9E9E9E;
        padding: 8px 16px;
        margin-right: 2px;
        border-top-left-radius: 4px;
        border-top-right-radius: 4px;
    }

    QTabBar::tab:hover {
        background-color: #424242;
    }

    QTabBar::tab:selected {
        background-color: #1e1e1e;
        color: #64B5F6;
        font-weight: bold;
    }

    /* Group Box */
    QGroupBox {
        background-color: #2b2b2b;
        border: 1px solid #424242;
        border-radius: 6px;
        margin-top: 12px;
        padding-top: 12px;
        font-weight: bold;
    }

    QGroupBox::title {
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 10px;
        padding: 0 5px;
        color: #64B5F6;
    }

    /* Table Widget */
    QTableWidget {
        background-color: #2b2b2b;
        alternate-background-color: #252525;
        gridline-color: #424242;
        border: 1px solid #424242;
        border-radius: 4px;
        selection-background-color: #1565C0;
        selection-color: white;
    }

    QTableWidget::item {
        padding: 4px;
        color: #e0e0e0;
    }

    QTableWidget::item:selected {
        background-color: #1976D2;
        color: white;
    }

    QHeaderView::section {
        background-color: #2b2b2b;
        color: #BDBDBD;
        font-weight: bold;
        padding: 6px;
        border: none;
        border-bottom: 2px solid #2196F3;
    }

    /* Progress Bar */
    QProgressBar {
        background-color: #2b2b2b;
        border: 1px solid #424242;
        border-radius: 4px;
        text-align: center;
        color: #e0e0e0;
        font-weight: bold;
    }

    QProgressBar::chunk {
        background-color: #2196F3;
        border-radius: 3px;
    }

    /* Scroll Bars */
    QScrollBar:vertical {
        background-color: #1e1e1e;
        width: 12px;
        border-radius: 6px;
    }

    QScrollBar::handle:vertical {
        background-color: #424242;
        border-radius: 6px;
        min-height: 20px;
    }

    QScrollBar::handle:vertical:hover {
        background-color: #616161;
    }

    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0px;
    }

    QScrollBar:horizontal {
        background-color: #1e1e1e;
        height: 12px;
        border-radius: 6px;
    }

    QScrollBar::handle:horizontal {
        background-color: #424242;
        border-radius: 6px;
        min-width: 20px;
    }

    QScrollBar::handle:horizontal:hover {
        background-color: #616161;
    }

    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
        width: 0px;
    }

    /* Status Bar */
    QStatusBar {
        background-color: #1e1e1e;
        color: #BDBDBD;
        border-top: 1px solid #424242;
    }

    /* Menu Bar and Menus */
    QMenuBar {
        background-color: #1e1e1e;
        color: #e0e0e0;
        border-bottom: 1px solid #424242;
    }

    QMenuBar::item {
        padding: 4px 12px;
        background-color: transparent;
    }

    QMenuBar::item:selected {
        background-color: #2b2b2b;
    }

    QMenu {
        background-color: #2b2b2b;
        color: #e0e0e0;
        border: 1px solid #424242;
    }

    QMenu::item {
        padding: 6px 24px 6px 12px;
    }

    QMenu::item:selected {
        background-color: #1976D2;
    }

    /* Checkboxes and Radio Buttons */
    QCheckBox, QRadioButton {
        color: #e0e0e0;
        spacing: 6px;
    }

    QCheckBox:disabled, QRadioButton:disabled {
        color: #616161;
    }

    /* Spin Box */
    QSpinBox, QDoubleSpinBox {
        background-color: #2b2b2b;
        color: #e0e0e0;
        border: 1px solid #424242;
        border-radius: 4px;
        padding: 4px 8px;
    }

    QSpinBox:focus, QDoubleSpinBox:focus {
        border: 2px solid #2196F3;
    }

    /* Tooltips */
    QToolTip {
        background-color: #424242;
        color: white;
        border: 1px solid #616161;
        padding: 4px;
        border-radius: 4px;
    }

    /* Dialog */
    QDialog {
        background-color: #1e1e1e;
    }
    """


def _get_auto_stylesheet() -> str:
    """Get the auto/medium theme stylesheet."""
    return """
    /* ========================================
       AUTO THEME - Medium Contrast
       ======================================== */

    QMainWindow {
        background-color: #e8e8e8;
    }

    QWidget {
        background-color: #e8e8e8;
        color: #1a1a1a;
        font-size: 9pt;
    }

    /* Labels and Text */
    QLabel {
        color: #1a1a1a;
        background-color: transparent;
    }

    QLabel[heading="true"] {
        font-size: 14pt;
        font-weight: bold;
        color: #1976D2;
    }

    /* Buttons */
    QPushButton {
        background-color: #2196F3;
        color: white;
        border: none;
        border-radius: 4px;
        padding: 6px 16px;
        font-weight: bold;
        min-height: 24px;
    }

    QPushButton:hover {
        background-color: #1976D2;
    }

    QPushButton:pressed {
        background-color: #1565C0;
    }

    QPushButton:disabled {
        background-color: #BDBDBD;
        color: #757575;
    }

    QPushButton[buttonStyle="secondary"] {
        background-color: #757575;
        color: white;
    }

    QPushButton[buttonStyle="secondary"]:hover {
        background-color: #616161;
    }

    QPushButton[buttonStyle="success"] {
        background-color: #4CAF50;
        color: white;
    }

    QPushButton[buttonStyle="success"]:hover {
        background-color: #388E3C;
    }

    QPushButton[buttonStyle="warning"] {
        background-color: #FF9800;
        color: white;
    }

    QPushButton[buttonStyle="warning"]:hover {
        background-color: #F57C00;
    }

    QPushButton[buttonStyle="danger"] {
        background-color: #F44336;
        color: white;
    }

    QPushButton[buttonStyle="danger"]:hover {
        background-color: #D32F2F;
    }

    /* Launcher-Specific Styles */
    QLabel[headerLabel="true"] {
        padding: 20px;
        background-color: #1a252f;
        color: white;
        border-radius: 8px;
        border: 2px solid #0d1419;
    }

    QLabel[headerLabel="true"][debugMode="true"] {
        background-color: #c0392b;
        border: 2px solid #e74c3c;
    }

    QLabel[statusLabel="true"] {
        padding: 8px;
        background-color: #f5f5f5;
        border: 1px solid #9E9E9E;
        border-radius: 4px;
        color: #1a1a1a;
    }

    QLabel[infoLabel="true"] {
        color: #616161;
        padding: 10px;
    }

    /* Input Fields */
    QLineEdit, QTextEdit, QPlainTextEdit {
        background-color: #f5f5f5;
        color: #1a1a1a;
        border: 1px solid #9E9E9E;
        border-radius: 4px;
        padding: 4px 8px;
        selection-background-color: #2196F3;
        selection-color: white;
    }

    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
        border: 2px solid #2196F3;
    }

    QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled {
        background-color: #E0E0E0;
        color: #9E9E9E;
    }

    /* ComboBox */
    QComboBox {
        background-color: #f5f5f5;
        color: #1a1a1a;
        border: 1px solid #9E9E9E;
        border-radius: 4px;
        padding: 4px 8px;
        min-height: 24px;
    }

    QComboBox:hover {
        border: 1px solid #2196F3;
    }

    QComboBox:focus {
        border: 2px solid #2196F3;
    }

    QComboBox::drop-down {
        border: none;
        width: 20px;
    }

    QComboBox::down-arrow {
        image: none;
        border-left: 4px solid transparent;
        border-right: 4px solid transparent;
        border-top: 6px solid #616161;
        margin-right: 6px;
    }

    QComboBox QAbstractItemView {
        background-color: #f5f5f5;
        color: #1a1a1a;
        selection-background-color: #BBDEFB;
        selection-color: #1a1a1a;
        border: 1px solid #9E9E9E;
        outline: none;
    }

    QComboBox QAbstractItemView::item {
        padding: 4px 8px;
        min-height: 24px;
    }

    QComboBox QAbstractItemView::item:hover {
        background-color: #90CAF9;
        color: #1a1a1a;
    }

    QComboBox QAbstractItemView::item:selected {
        background-color: #64B5F6;
        color: #1a1a1a;
    }

    /* Tab Widget */
    QTabWidget::pane {
        border: 1px solid #9E9E9E;
        background-color: #f5f5f5;
        border-radius: 4px;
    }

    QTabBar::tab {
        background-color: #D5D5D5;
        color: #424242;
        padding: 8px 16px;
        margin-right: 2px;
        border-top-left-radius: 4px;
        border-top-right-radius: 4px;
    }

    QTabBar::tab:hover {
        background-color: #C5C5C5;
    }

    QTabBar::tab:selected {
        background-color: #f5f5f5;
        color: #1976D2;
        font-weight: bold;
    }

    /* Group Box */
    QGroupBox {
        background-color: #f5f5f5;
        border: 1px solid #9E9E9E;
        border-radius: 6px;
        margin-top: 12px;
        padding-top: 12px;
        font-weight: bold;
    }

    QGroupBox::title {
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 10px;
        padding: 0 5px;
        color: #1976D2;
    }

    /* Table Widget */
    QTableWidget {
        background-color: #f5f5f5;
        alternate-background-color: #eeeeee;
        gridline-color: #BDBDBD;
        border: 1px solid #9E9E9E;
        border-radius: 4px;
        selection-background-color: #BBDEFB;
        selection-color: #1a1a1a;
    }

    QTableWidget::item {
        padding: 4px;
        color: #1a1a1a;
    }

    QTableWidget::item:selected {
        background-color: #64B5F6;
        color: #1a1a1a;
    }

    QHeaderView::section {
        background-color: #E0E0E0;
        color: #424242;
        font-weight: bold;
        padding: 6px;
        border: none;
        border-bottom: 2px solid #1976D2;
    }

    /* Progress Bar */
    QProgressBar {
        background-color: #D5D5D5;
        border: 1px solid #9E9E9E;
        border-radius: 4px;
        text-align: center;
        color: #1a1a1a;
        font-weight: bold;
    }

    QProgressBar::chunk {
        background-color: #2196F3;
        border-radius: 3px;
    }

    /* Scroll Bars */
    QScrollBar:vertical {
        background-color: #e8e8e8;
        width: 12px;
        border-radius: 6px;
    }

    QScrollBar::handle:vertical {
        background-color: #9E9E9E;
        border-radius: 6px;
        min-height: 20px;
    }

    QScrollBar::handle:vertical:hover {
        background-color: #757575;
    }

    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0px;
    }

    QScrollBar:horizontal {
        background-color: #e8e8e8;
        height: 12px;
        border-radius: 6px;
    }

    QScrollBar::handle:horizontal {
        background-color: #9E9E9E;
        border-radius: 6px;
        min-width: 20px;
    }

    QScrollBar::handle:horizontal:hover {
        background-color: #757575;
    }

    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
        width: 0px;
    }

    /* Status Bar */
    QStatusBar {
        background-color: #e8e8e8;
        color: #424242;
        border-top: 1px solid #9E9E9E;
    }

    /* Menu Bar and Menus */
    QMenuBar {
        background-color: #e8e8e8;
        color: #1a1a1a;
        border-bottom: 1px solid #9E9E9E;
    }

    QMenuBar::item {
        padding: 4px 12px;
        background-color: transparent;
    }

    QMenuBar::item:selected {
        background-color: #D5D5D5;
    }

    QMenu {
        background-color: #f5f5f5;
        color: #1a1a1a;
        border: 1px solid #9E9E9E;
    }

    QMenu::item {
        padding: 6px 24px 6px 12px;
    }

    QMenu::item:selected {
        background-color: #BBDEFB;
    }

    /* Checkboxes and Radio Buttons */
    QCheckBox, QRadioButton {
        color: #1a1a1a;
        spacing: 6px;
    }

    QCheckBox:disabled, QRadioButton:disabled {
        color: #9E9E9E;
    }

    /* Spin Box */
    QSpinBox, QDoubleSpinBox {
        background-color: #f5f5f5;
        color: #1a1a1a;
        border: 1px solid #9E9E9E;
        border-radius: 4px;
        padding: 4px 8px;
    }

    QSpinBox:focus, QDoubleSpinBox:focus {
        border: 2px solid #2196F3;
    }

    /* Tooltips */
    QToolTip {
        background-color: #424242;
        color: white;
        border: 1px solid #212121;
        padding: 4px;
        border-radius: 4px;
    }

    /* Dialog */
    QDialog {
        background-color: #e8e8e8;
    }
    """
