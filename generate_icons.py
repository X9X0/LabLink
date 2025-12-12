#!/usr/bin/env python3
"""Generate favicon.png and icon.ico from Splash.png"""

from PIL import Image
from pathlib import Path

# Paths
images_dir = Path(__file__).parent / "images"
source = images_dir / "Splash.png"
favicon_out = images_dir / "favicon.png"
ico_out = images_dir / "icon.ico"

print("Loading source image...")
img = Image.open(source)
print(f"Source image: {img.size[0]}x{img.size[1]}")

# Generate favicon.png at 128x128
print("\nGenerating favicon.png (128x128)...")
favicon = img.resize((128, 128), Image.Resampling.LANCZOS)
favicon.save(favicon_out, "PNG")
print(f"[OK] Created {favicon_out}")

# Generate icon.ico with multiple resolutions
print("\nGenerating icon.ico with multiple resolutions...")
sizes = [(16, 16), (32, 32), (48, 48), (256, 256)]
icons = []

for size in sizes:
    icon = img.resize(size, Image.Resampling.LANCZOS)
    icons.append(icon)
    print(f"  - {size[0]}x{size[1]}")

# Save all sizes to a single .ico file
icons[0].save(ico_out, format="ICO", sizes=[icon.size for icon in icons], append_images=icons[1:])
print(f"[OK] Created {ico_out}")

print("\n[SUCCESS] Icon generation complete!")
print(f"   favicon.png: 128x128 (for window/taskbar)")
print(f"   icon.ico: 16x16, 32x32, 48x48, 256x256 (for shortcuts)")
