#!/usr/bin/env python3
"""Regenerate ultra-sharp icons from high-res Splash.png"""

from PIL import Image
from pathlib import Path

# Paths
images_dir = Path(__file__).parent / "images"
source = images_dir / "Splash.png"
output_ico = images_dir / "icon.ico"
output_favicon = images_dir / "favicon.png"

print("Loading Splash.png (1024x1024 high-resolution source)...")
img = Image.open(source)
print(f"Source image: {img.size[0]}x{img.size[1]}")

# Convert to RGBA
img = img.convert("RGBA")

# Remove black background and make transparent
print("Removing black background...")
data = img.getdata()
new_data = []

for pixel in data:
    # If pixel is black or very dark (R,G,B all < 30), make it transparent
    # Also check for near-black pixels (< 40) for better edge cleanup
    if pixel[0] < 40 and pixel[1] < 40 and pixel[2] < 40:
        new_data.append((0, 0, 0, 0))  # Transparent
    else:
        new_data.append(pixel)

img.putdata(new_data)
print("[OK] Black background removed")

# Generate multiple high-quality sizes
print("\nGenerating multiple icon sizes with maximum quality...")
# Windows 11 benefits from these specific sizes
sizes = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]
icons = []

for size in sizes:
    print(f"  Creating {size}x{size}...")
    # Use LANCZOS for highest quality downsampling
    icon = img.resize((size, size), Image.Resampling.LANCZOS)
    icons.append(icon)
    print(f"  [OK] {size}x{size}")

# Save favicon.png at 128x128
print("\nGenerating favicon.png...")
favicon = img.resize((128, 128), Image.Resampling.LANCZOS)
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

print("\n[SUCCESS] Ultra-sharp icons generated from 1024x1024 source!")
print("These icons should be MUCH sharper on Windows 11.")
print("\nTo update your desktop icon:")
print("1. Right-click shortcut -> Properties -> Change Icon")
print("2. Browse to the icon.ico file")
print("3. Click OK to apply")
