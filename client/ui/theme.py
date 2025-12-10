"""
LabLink UI Theme and Styling
============================

Provides consistent theming across Windows, Linux, and macOS platforms.
Uses a modern, high-contrast design with proper button styling.
"""

def get_app_stylesheet() -> str:
    """
    Get the main application stylesheet.

    Provides comprehensive styling for:
    - Better text contrast
    - Styled buttons with hover states
    - Consistent colors across widgets
    - Professional appearance on all platforms

    Returns:
        Complete application stylesheet string
    """
    return """
    /* ========================================
       General Application Styling
       ======================================== */

    QMainWindow {
        background-color: #f5f5f5;
    }

    QWidget {
        background-color: #f5f5f5;
        color: #212121;
        font-size: 9pt;
    }

    /* ========================================
       Labels and Text
       ======================================== */

    QLabel {
        color: #212121;
        background-color: transparent;
    }

    QLabel[heading="true"] {
        font-size: 14pt;
        font-weight: bold;
        color: #1976D2;
    }

    /* ========================================
       Buttons
       ======================================== */

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

    /* Secondary button style */
    QPushButton[buttonStyle="secondary"] {
        background-color: #757575;
        color: white;
    }

    QPushButton[buttonStyle="secondary"]:hover {
        background-color: #616161;
    }

    /* Success/positive button style */
    QPushButton[buttonStyle="success"] {
        background-color: #4CAF50;
        color: white;
    }

    QPushButton[buttonStyle="success"]:hover {
        background-color: #388E3C;
    }

    /* Warning button style */
    QPushButton[buttonStyle="warning"] {
        background-color: #FF9800;
        color: white;
    }

    QPushButton[buttonStyle="warning"]:hover {
        background-color: #F57C00;
    }

    /* Danger/destructive button style */
    QPushButton[buttonStyle="danger"] {
        background-color: #F44336;
        color: white;
    }

    QPushButton[buttonStyle="danger"]:hover {
        background-color: #D32F2F;
    }

    /* ========================================
       Input Fields
       ======================================== */

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

    /* ========================================
       ComboBox (Dropdowns)
       ======================================== */

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

    /* ========================================
       Tab Widget
       ======================================== */

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

    /* ========================================
       Group Box
       ======================================== */

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

    /* ========================================
       Table Widget
       ======================================== */

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

    /* ========================================
       Progress Bar
       ======================================== */

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

    /* ========================================
       Scroll Bars
       ======================================== */

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

    /* ========================================
       Status Bar
       ======================================== */

    QStatusBar {
        background-color: #F5F5F5;
        color: #424242;
        border-top: 1px solid #BDBDBD;
    }

    /* ========================================
       Menu Bar and Menus
       ======================================== */

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

    /* ========================================
       Checkboxes and Radio Buttons
       ======================================== */

    QCheckBox, QRadioButton {
        color: #212121;
        spacing: 6px;
    }

    QCheckBox:disabled, QRadioButton:disabled {
        color: #9E9E9E;
    }

    /* ========================================
       Spin Box
       ======================================== */

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

    /* ========================================
       Tooltips
       ======================================== */

    QToolTip {
        background-color: #424242;
        color: white;
        border: 1px solid #212121;
        padding: 4px;
        border-radius: 4px;
    }
    """
