#!/usr/bin/env python3
"""Generate PWA icons for the Income & Expense Manager"""

from PIL import Image, ImageDraw, ImageFont
import os

# Create icons directory
icons_dir = r'C:\income_expense_manager\static\img'
os.makedirs(icons_dir, exist_ok=True)

# Colors
PRIMARY = '#0EA5E9'  # Sky Blue
SECONDARY = '#0369A1'  # Deep Sky Blue
WHITE = '#ffffff'
DARK = '#0369A1'

sizes = [72, 96, 128, 144, 152, 192, 384, 512]

def create_icon(size):
    """Create a PWA icon with IE letters"""
    img = Image.new('RGBA', (size, size), PRIMARY)
    draw = ImageDraw.Draw(img)
    
    # Rounded corners mask
    mask = Image.new('L', (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    radius = size // 6
    mask_draw.rounded_rectangle([0, 0, size, size], radius=radius, fill=255)
    img.putalpha(mask)
    
    # Draw background gradient effect
    for i in range(size):
        alpha = int(255 * (1 - i / size * 0.3))
        color = (*tuple(int(PRIMARY.lstrip('#')[j:j+2], 16) for j in (0, 2, 4)), alpha)
        draw.line([(0, i), (size, i)], fill=color)
    
    # Draw "IE" letters in center
    try:
        font_size = max(24, size // 3)
        font = ImageFont.truetype("arial.ttf", font_size)
    except:
        font = ImageFont.load_default()
    
    text = "IE"
    text_bbox = draw.textbbox((0, 0), text, font=font)
    text_w = text_bbox[2] - text_bbox[0]
    text_h = text_bbox[3] - text_bbox[1]
    text_x = (size - text_w) // 2
    text_y = (size - text_h) // 2
    
    # Draw text with shadow for depth
    shadow_offset = max(2, size // 100)
    draw.text((text_x + shadow_offset, text_y + shadow_offset), text, fill=(0, 0, 0, 80), font=font)
    draw.text((text_x, text_y), text, fill=WHITE, font=font)
    
    # Save
    filepath = os.path.join(icons_dir, f'icon-{size}.png')
    img.save(filepath, 'PNG')
    print(f'Created: {filepath} ({size}x{size})')

if __name__ == '__main__':
    for size in sizes:
        create_icon(size)
    print('\nAll icons generated successfully!')
    print('Remember to also create screenshot-wide.png (1280x720) and screenshot-narrow.png (750x1334) for the manifest')