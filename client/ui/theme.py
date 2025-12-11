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
