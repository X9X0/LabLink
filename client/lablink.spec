# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for LabLink GUI Client

import sys
from pathlib import Path

block_cipher = None

# Get the client directory
client_dir = Path('.')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('ui/*.py', 'ui'),
        ('api/*.py', 'api'),
        ('models/*.py', 'models'),
        ('utils/*.py', 'utils'),
    ],
    hiddenimports=[
        # PyQt6
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'PyQt6.sip',

        # Network
        'requests',
        'websockets',
        'aiohttp',

        # Data
        'numpy',
        'pandas',

        # UI modules
        'ui.main_window',
        'ui.connection_dialog',
        'ui.equipment_panel',
        'ui.acquisition_panel',
        'ui.alarm_panel',
        'ui.scheduler_panel',
        'ui.diagnostics_panel',

        # API
        'api.client',

        # Models
        'models.equipment',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',  # Exclude if not using yet
        'pyqtgraph',   # Exclude if not using yet
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='LabLink',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Windowed mode (no console)
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='resources/icon.ico',  # Add your icon file here
)

# macOS app bundle
if sys.platform == 'darwin':
    app = BUNDLE(
        exe,
        name='LabLink.app',
        # icon='resources/icon.icns',
        bundle_identifier='com.lablink.client',
        info_plist={
            'NSPrincipalClass': 'NSApplication',
            'NSAppleScriptEnabled': False,
            'CFBundleName': 'LabLink',
            'CFBundleDisplayName': 'LabLink',
            'CFBundleGetInfoString': 'Laboratory Equipment Control',
            'CFBundleVersion': '1.0.0',
            'CFBundleShortVersionString': '1.0.0',
            'NSHumanReadableCopyright': 'Copyright © 2024 LabLink Project',
        },
    )
