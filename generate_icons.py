"""Generate Teams app icons (color.png and outline.png) programmatically.

color.png   - 192x192 vibrant gradient icon with text HR
outline.png - 32x32 simplified monochrome outline for Teams app list

Run:
  python generate_icons.py
"""
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from pathlib import Path

APP_DIR = Path(__file__).parent
PKG_DIR = APP_DIR / 'appPackage'
PKG_DIR.mkdir(exist_ok=True)

# Files to write
COLOR_ICON = PKG_DIR / 'color.png'
OUTLINE_ICON = PKG_DIR / 'outline.png'


def generate_color_icon():
    size = 192
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Gradient background
    for y in range(size):
        # Purple -> blue gradient
        r = 70 + int(60 * (y / size))
        g = 71 + int(40 * (y / size))
        b = 180 + int(40 * (1 - y / size))
        draw.line([(0, y), (size, y)], fill=(r, g, b, 255))

    # Rounded rectangle overlay for subtle depth
    overlay = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    radius = 32
    od.rounded_rectangle([8, 8, size - 8, size - 8], radius, outline=(255, 255, 255, 60), width=4)
    img = Image.alpha_composite(img, overlay)

    # Text 'HR'
    text = 'HR'
    # Try a few fonts; fallback to default
    font = None
    for candidate in ["segoeuib.ttf", "SegoeUI-Bold.ttf", "arialbd.ttf", "arial.ttf"]:
        try:
            font = ImageFont.truetype(candidate, 88)
            break
        except Exception:
            continue
    if font is None:
        font = ImageFont.load_default()

    # Compute text size using textbbox for Pillow 10+
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text(((size - tw) / 2, (size - th) / 2 - 6), text, font=font, fill="white")

    # Glow effect
    glow = img.filter(ImageFilter.GaussianBlur(4))
    img = Image.alpha_composite(glow, img)

    img.save(COLOR_ICON)


def generate_outline_icon(border_color=(255, 255, 255, 255), text_color=None):
    """Generate a 32x32 outline icon with full transparent background.

    border_color: RGBA for the circular stroke.
    text_color:   RGBA for the letters; defaults to border_color if None.
    """
    size = 32
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))  # fully transparent background
    draw = ImageDraw.Draw(img)

    if text_color is None:
        text_color = border_color

    # Circle outline only (no fill) ensuring anti-aliasing crispness
    draw.ellipse([2, 2, size - 2, size - 2], outline=border_color, width=2)

    text = 'HR'
    font = None
    for candidate in ["segoeuib.ttf", "SegoeUI-Bold.ttf", "arialbd.ttf", "arial.ttf"]:
        try:
            font = ImageFont.truetype(candidate, 11)
            break
        except Exception:
            continue
    if font is None:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text(((size - tw) / 2, (size - th) / 2), text, font=font, fill=text_color)

    # Sanity: ensure no pixel has unintended background color (keep only stroke/text)
    # (Optional cleanup pass, not strictly needed because we started transparent.)
    img.save(OUTLINE_ICON)


def main():
    generate_color_icon()
    # White outline and text on transparent background
    generate_outline_icon()
    print(f"Generated: {COLOR_ICON} and {OUTLINE_ICON}")

if __name__ == '__main__':
    main()
