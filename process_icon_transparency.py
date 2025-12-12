#!/usr/bin/env python3
"""Process lablink_multi.ico to remove black background and add transparency"""

from PIL import Image
import os
from pathlib import Path

# Paths
images_dir = Path(__file__).parent / "images"
source = images_dir / "lablink_multi.ico"
output_ico = images_dir / "icon.ico"
output_favicon = images_dir / "favicon.png"

def remove_black_background(img):
    """Remove black background from image and make it transparent"""
    img = img.convert("RGBA")
    data = img.getdata()
    new_data = []

    for pixel in data:
        # If pixel is black or very dark (R,G,B all < 30), make it transparent
        if pixel[0] < 30 and pixel[1] < 30 and pixel[2] < 30:
            new_data.append((0, 0, 0, 0))  # Transparent
        else:
            new_data.append(pixel)

    img.putdata(new_data)
    return img

print("Loading lablink_multi.ico...")

# PIL's ICO loader doesn't always handle multi-resolution ICOs well
# Load and process the largest size, then create multiple resolutions
with Image.open(source) as img:
    # Get the largest available size
    print(f"Source size: {img.size[0]}x{img.size[1]}")

    # Process the image to remove black background
    print("Removing black background...")
    processed = remove_black_background(img)

    # Generate multiple sizes for the .ico file
    print("\nGenerating multiple icon sizes...")
    sizes = [16, 20, 24, 32, 40, 48, 64, 256]
    icons = []
    sizes_processed = []

    for size in sizes:
        if size <= processed.size[0]:  # Only create sizes up to source size
            icon = processed.resize((size, size), Image.Resampling.LANCZOS)
            icons.append(icon)
            sizes_processed.append((size, size))
            print(f"  [OK] Created {size}x{size}")

    # Save the largest icon as favicon.png (128x128 preferred)
    print("\nGenerating favicon.png...")
    # Find or create 128x128 version
    favicon = None
    for icon in icons:
        if icon.size[0] == 128:
            favicon = icon
            break

    if favicon is None:
        # Create 128x128 from processed image
        favicon = processed.resize((128, 128), Image.Resampling.LANCZOS)

    favicon.save(output_favicon, "PNG")
    print(f"[OK] Created {output_favicon} at {favicon.size[0]}x{favicon.size[1]}")

    # Save all icons as a multi-resolution .ico file
    print("\nGenerating icon.ico with transparent background...")
    if len(icons) > 1:
        icons[0].save(output_ico, format="ICO", sizes=[icon.size for icon in icons], append_images=icons[1:])
    else:
        icons[0].save(output_ico, format="ICO")

    print(f"[OK] Created {output_ico}")
    print(f"     Sizes included: {', '.join([f'{s[0]}x{s[1]}' for s in sizes_processed])}")

    print("\n[SUCCESS] Icon processing complete!")
    print("Black background removed, transparent icons created.")
    print("Desktop shortcuts should now have transparent backgrounds and sharper icons.")
