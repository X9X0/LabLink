# LabLink Icons and Images

This directory contains icon and image assets used throughout the LabLink application.

## Files

### `favicon.png`
- **Purpose**: Application window icon and taskbar icon
- **Used by**: Both launcher (`lablink.py`) and client (`client/main.py`)
- **Appears in**:
  - Window title bar
  - Windows taskbar
  - macOS Dock
  - Linux task switcher/panel
- **Format**: PNG (with transparency)
- **Size**: 64x64 pixels recommended for best quality

### `icon.ico`
- **Purpose**: Desktop shortcut icon
- **Platform**: Windows and Linux
- **Format**: ICO (Windows icon format, multi-resolution)
- **Usage**:
  - **Windows**: Right-click desktop → New → Shortcut
    - Target: `C:\Path\To\LabLink\lablink.py` (or use `lablink-client.bat`)
    - Icon: Browse to `C:\Path\To\LabLink\images\icon.ico`
  - **Linux**: Create `.desktop` file with `Icon=/path/to/LabLink/images/icon.ico`

### `Splash.png`
- **Purpose**: Splash screen or promotional image
- **Format**: PNG
- **Size**: Large format image

## Creating Desktop Shortcuts

### Windows

**Option 1: Using lablink.py directly**
1. Right-click on desktop → New → Shortcut
2. Location: `pythonw.exe "C:\Path\To\LabLink\lablink.py"`
3. Name: "LabLink Launcher"
4. Right-click shortcut → Properties → Change Icon
5. Browse to `C:\Path\To\LabLink\images\icon.ico`

**Option 2: Using lablink-client.bat (recommended)**
1. Right-click on desktop → New → Shortcut
2. Location: `"C:\Path\To\LabLink\lablink-client.bat"`
3. Name: "LabLink Client"
4. Right-click shortcut → Properties → Change Icon
5. Browse to `C:\Path\To\LabLink\images\icon.ico`

### Linux

Create a `.desktop` file at `~/.local/share/applications/lablink.desktop`:

```desktop
[Desktop Entry]
Type=Application
Name=LabLink Launcher
Comment=Laboratory Equipment Control System
Exec=/path/to/LabLink/lablink.py
Icon=/path/to/LabLink/images/icon.ico
Terminal=false
Categories=Science;Education;
```

Make it executable:
```bash
chmod +x ~/.local/share/applications/lablink.desktop
```

### macOS

1. Open Automator
2. Create new "Application"
3. Add "Run Shell Script" action
4. Script: `/path/to/LabLink/lablink.py`
5. Save as "LabLink" in Applications
6. Right-click app → Get Info → drag `favicon.png` to icon in top-left

## Technical Notes

- The icons are loaded at application startup in both `lablink.py` and `client/main.py`
- Icons appear in window title bars and system taskbars automatically via `QApplication.setWindowIcon()`
- PNG format is used for runtime icons for better cross-platform compatibility
- ICO format is provided for Windows shortcuts and Linux .desktop files
- Icons scale appropriately on high-DPI displays

## Icon Updates

If you need to update the icons:
1. Replace the appropriate file in this directory
2. Maintain the same filename and format
3. Recommended favicon.png size: 64x64 or 128x128 pixels
4. For icon.ico, include multiple resolutions (16x16, 32x32, 48x48, 256x256)
