#!/usr/bin/env python3
"""Generate final icons from LL.png (logo only, no text)"""

from PIL import Image
from pathlib import Path

# Paths
images_dir = Path(__file__).parent / "images"
source = images_dir / "LL.png"
output_ico = images_dir / "icon.ico"
output_favicon = images_dir / "favicon.png"

print("Loading LL.png (logo only, no text)...")
img = Image.open(source)
print(f"Source image: {img.size[0]}x{img.size[1]}")

# Convert to RGBA if not already
img = img.convert("RGBA")

# Check if we need to remove black background
# (LL.png might already have transparency)
data = img.getdata()
has_transparency = any(pixel[3] < 255 for pixel in data)

if has_transparency:
    print("Source already has transparency - using as-is")
    processed = img
else:
    print("Removing black background and adding transparency...")
    new_data = []
    for pixel in data:
        # If pixel is black or very dark (R,G,B all < 40), make it transparent
        if pixel[0] < 40 and pixel[1] < 40 and pixel[2] < 40:
            new_data.append((0, 0, 0, 0))  # Transparent
        else:
            new_data.append(pixel)

    processed = Image.new("RGBA", img.size)
    processed.putdata(new_data)
    print("[OK] Black background removed")

# Generate multiple high-quality sizes
print("\nGenerating multiple icon sizes with maximum quality...")
# Windows 11 benefits from these specific sizes
sizes = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]
icons = []

for size in sizes:
    print(f"  Creating {size}x{size}...")
    # Use LANCZOS for highest quality downsampling
    icon = processed.resize((size, size), Image.Resampling.LANCZOS)
    icons.append(icon)
    print(f"  [OK] {size}x{size}")

# Save favicon.png at 128x128
print("\nGenerating favicon.png...")
favicon = processed.resize((128, 128), Image.Resampling.LANCZOS)
favicon.save(output_favicon, "PNG", optimize=True)
print(f"[OK] Created {output_favicon} at 128x128")

# Save multi-resolution .ico with all sizes
print("\nGenerating icon.ico with all resolutions...")
# Important: Save largest to smallest for best Windows compatibility
icons_sorted = sorted(icons, key=lambda x: x.size[0], reverse=True)
icons_sorted[0].save(
    output_ico,
    format="ICO",
    sizes=[icon.size for icon in icons_sorted],
    append_images=icons_sorted[1:]
)

print(f"[OK] Created {output_ico}")
print(f"     Sizes: 16, 20, 24, 32, 40, 48, 64, 96, 128, 256")
print(f"     All with transparent backgrounds")

print("\n[SUCCESS] Icons generated from logo-only image (no text)!")
print("Icons now contain ONLY the logo symbol, no 'LabLink' text.")
print("\nTo update your desktop icon:")
print("1. Right-click shortcut -> Properties -> Change Icon")
print("2. Browse to icon.ico")
print("3. Click OK to apply")
