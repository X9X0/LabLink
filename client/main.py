#!/usr/bin/env python3
"""LabLink GUI Client - Main entry point."""

import argparse
import os
import asyncio
import logging
import sys
from pathlib import Path

# Add the repo root to path, so `client.*` resolves as a package when this
# file is run directly (`python client\main.py`) rather than via `-m`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import qasync
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from client.ui.main_window import MainWindow
from client.ui.theme import get_app_stylesheet, get_theme_setting


def setup_logging(debug=False):
    """Set up logging configuration.

    Args:
        debug: Enable debug logging if True
    """
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler("lablink_client.log")],
    )


def _restart_client(drop_easter_egg=False):
    """Restart this client so newly checked-out code is actually loaded.

    Python caches imported modules in sys.modules. MainWindow and everything
    it pulls in -- including the Raspberry Pi image builder -- are imported at
    the top of this file, before main() runs. Anything that rewrites those
    files afterwards, whether the easter-egg branch selector or a client
    self-update, changes nothing at all for the running process: it keeps
    executing the code it loaded at startup while reporting success.

    Args:
        drop_easter_egg: strip --easter-egg from the restarted command, so the
            branch dialog does not reappear on every launch.

    This does not return: the process is replaced, or exits.
    """
    argv = list(sys.argv)
    if drop_easter_egg:
        argv = [a for a in argv if a != "--easter-egg"]

    print("🔄 Restarting to load the updated code...\n")
    sys.stdout.flush()

    if os.name == "nt":
        # os.execv on Windows detaches the child from the console in a way
        # that loses its output, so spawn a replacement and exit instead.
        import subprocess

        subprocess.Popen([sys.executable] + argv)
        sys.exit(0)

    os.execv(sys.executable, [sys.executable] + argv)


def main():
    """Main application entry point."""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="LabLink GUI Client")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging (verbose output)"
    )
    parser.add_argument(
        "--easter-egg",
        action="store_true",
        help=argparse.SUPPRESS  # Hidden argument for easter egg mode
    )
    args = parser.parse_args()

    # Set up logging
    setup_logging(debug=args.debug)
    logger = logging.getLogger(__name__)

    _version_file = Path(__file__).parent.parent / "VERSION"
    _version = _version_file.read_text().strip() if _version_file.exists() else "unknown"
    if args.debug:
        logger.info(f"Starting LabLink GUI Client v{_version} with async WebSocket support (DEBUG MODE)")
    else:
        logger.info(f"Starting LabLink GUI Client v{_version} with async WebSocket support")

    # Check for pending client update
    from client.utils.self_update import check_update_flag, clear_update_flag, perform_client_update

    update_flag = check_update_flag()
    if update_flag:
        ref = update_flag.get("ref")
        mode = update_flag.get("mode", "stable")

        logger.info(f"Pending client update detected: {ref} ({mode} mode)")
        print(f"\n{'='*60}")
        print(f"Applying client update to {ref} ({mode} mode)...")
        print(f"{'='*60}\n")

        # Perform the update
        if perform_client_update(ref):
            print(f"✅ Client successfully updated to {ref}")
            clear_update_flag()
            # Same trap as the easter-egg checkout: the files on disk are now
            # the new version, but this process is still running the old one.
            # The flag is cleared first, so the restart cannot loop.
            print(f"\n{'='*60}\n")
            _restart_client()
        else:
            print(f"❌ Failed to update client to {ref}")
            print("The application will continue with the current version.")

        print(f"\n{'='*60}\n")

    # Enable high DPI support
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    # Create application
    app = QApplication(sys.argv)
    app.setApplicationName("LabLink")

    # Set application icon (appears in taskbar and window title)
    icon_path = Path(__file__).parent.parent / "images" / "favicon.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    # Read version from VERSION file (single source of truth)
    version_file = Path(__file__).parent.parent / "VERSION"
    version = version_file.read_text().strip() if version_file.exists() else "1.2.0"
    app.setApplicationVersion(version)
    app.setOrganizationName("LabLink Project")

    # Set application style
    app.setStyle("Fusion")

    # Load saved theme preference and apply it
    current_theme = get_theme_setting()
    app.setStyleSheet(get_app_stylesheet(current_theme))

    # Store theme setting on app for access by windows
    app.setProperty("theme", current_theme)

    # Create qasync event loop for asyncio integration
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    # Easter egg mode: Show branch selector before launching
    if args.easter_egg:
        from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QVBoxLayout, QLabel, QComboBox, QPushButton, QMessageBox
        from client.utils.git_operations import get_git_branches, get_git_tags, get_current_git_branch, checkout_git_ref

        logger.info("Easter egg mode activated!")

        class BranchSelectorDialog(QDialog):
            """Secret branch selector dialog for developers."""

            def __init__(self):
                super().__init__()
                self.setWindowTitle("🥚 Secret Developer Mode")
                self.resize(500, 350)

                layout = QVBoxLayout(self)

                # Title
                title = QLabel("<h2>🥚 Easter Egg Mode 🥚</h2>")
                title.setStyleSheet("color: #e74c3c; font-weight: bold; padding: 10px;")
                layout.addWidget(title)

                # Description
                desc = QLabel(
                    "You've discovered the secret developer mode!\n\n"
                    "Select a branch or tag to checkout before launching:"
                )
                desc.setWordWrap(True)
                layout.addWidget(desc)

                # Mode selector
                mode_layout = QVBoxLayout()
                mode_layout.addWidget(QLabel("<b>Mode:</b>"))

                self.mode_combo = QComboBox()
                self.mode_combo.addItem("Branches (Development)", "branches")
                self.mode_combo.addItem("Tags (Releases)", "tags")
                self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
                mode_layout.addWidget(self.mode_combo)

                layout.addLayout(mode_layout)

                # Show all branches checkbox (only for branches mode)
                from PyQt6.QtWidgets import QCheckBox
                self.show_all_checkbox = QCheckBox("Show all branches (including inactive)")
                self.show_all_checkbox.setToolTip(
                    "When unchecked, only shows current and active branches (with commits in last 6 months).\n"
                    "When checked, shows all branches."
                )
                self.show_all_checkbox.stateChanged.connect(self._populate_refs)
                layout.addWidget(self.show_all_checkbox)

                # Ref selector
                ref_layout = QVBoxLayout()
                ref_layout.addWidget(QLabel("<b>Select:</b>"))

                self.ref_combo = QComboBox()
                ref_layout.addWidget(self.ref_combo)

                self.refresh_btn = QPushButton("Refresh List")
                self.refresh_btn.clicked.connect(self._populate_refs)
                ref_layout.addWidget(self.refresh_btn)

                layout.addLayout(ref_layout)

                # Current info
                current_branch = get_current_git_branch()
                if current_branch:
                    current_label = QLabel(f"<i>Current branch: {current_branch}</i>")
                    current_label.setStyleSheet("color: gray;")
                    layout.addWidget(current_label)

                # Buttons
                button_box = QDialogButtonBox(
                    QDialogButtonBox.StandardButton.Ok |
                    QDialogButtonBox.StandardButton.Cancel
                )
                button_box.accepted.connect(self.accept)
                button_box.rejected.connect(self.reject)
                layout.addWidget(button_box)

                # Populate initial list
                self._populate_refs()

            def _on_mode_changed(self):
                """Handle mode change."""
                # Show/hide checkbox based on mode
                mode = self.mode_combo.currentData()
                self.show_all_checkbox.setVisible(mode == "branches")
                self._populate_refs()

            def _populate_refs(self):
                """Populate ref selector based on mode."""
                mode = self.mode_combo.currentData()

                self.ref_combo.clear()

                if mode == "branches":
                    show_all = self.show_all_checkbox.isChecked()
                    refs = get_git_branches(show_all=show_all, sort_by_date=True)
                else:  # tags
                    refs = get_git_tags()

                for ref in refs:
                    self.ref_combo.addItem(ref, ref)

            def get_selected_ref(self):
                """Get selected ref."""
                return self.ref_combo.currentData()

        # Show branch selector
        dialog = BranchSelectorDialog()
        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected_ref = dialog.get_selected_ref()
            if selected_ref:
                logger.info(f"Easter egg: Checking out {selected_ref}...")
                print(f"\n🥚 Checking out {selected_ref}...")

                if checkout_git_ref(selected_ref):
                    print(f"✅ Successfully checked out {selected_ref}\n")
                    logger.info(f"Successfully checked out {selected_ref}")
                    # Say so on screen, not only on stdout: launched from a
                    # shortcut or lablink-client.bat there is often no console
                    # to read, which is how a failed checkout looks exactly
                    # like a successful one.
                    QMessageBox.information(
                        None,
                        "Switched branch",
                        f"Now on {selected_ref}.\n\n"
                        "LabLink will restart so the checked-out code is "
                        "actually loaded.",
                    )
                    # Restart, or the checkout has no effect on this run.
                    # MainWindow and everything it imports were loaded from the
                    # previous branch's files before main() started, and Python
                    # caches modules in sys.modules -- changing the files on
                    # disk afterwards changes nothing until the process
                    # restarts. Without this the client silently keeps running
                    # the old code while reporting a successful checkout.
                    _restart_client(drop_easter_egg=True)
                else:
                    print(f"❌ Failed to checkout {selected_ref}\n")
                    logger.error(f"Failed to checkout {selected_ref}")

                    from client.utils.git_operations import (is_git_checkout,
                                                             repo_dir)

                    if not is_git_checkout():
                        detail = (
                            f"{repo_dir()} is not a git clone.\n\n"
                            "Branch switching needs one. A ZIP download or a "
                            "packaged install cannot switch branches; clone "
                            "the repository instead."
                        )
                    else:
                        detail = (
                            "git refused the checkout. The usual cause is "
                            "uncommitted local changes.\n\n"
                            f"In {repo_dir()}, check `git status`, then commit "
                            "or stash them and try again."
                        )
                    print(f"   {detail}\n")
                    QMessageBox.warning(
                        None, "Could not switch branch",
                        f"Staying on the current branch.\n\n{detail}",
                    )

    # Create and show main window
    window = MainWindow()
    window.show()

    # Show connection dialog on startup
    window.show_connection_dialog()

    # Run application with qasync event loop
    with loop:
        sys.exit(loop.run_forever())


if __name__ == "__main__":
    main()
