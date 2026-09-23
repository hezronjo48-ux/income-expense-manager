#!/usr/bin/env python3
"""Generate placeholder screenshots for PWA manifest"""

from PIL import Image, ImageDraw, ImageFont
import os

icons_dir = r'C:\income_expense_manager\static\img'
os.makedirs(icons_dir, exist_ok=True)

# Colors
BG = '#f0f9ff'
PRIMARY = '#0ea5e9'
WHITE = '#ffffff'
DARK = '#1f2937'
GREEN = '#10b981'
RED = '#ef4444'
GRAY = '#94a3b8'
LIGHT_GRAY = '#e2e8f0'

def create_wide_screenshot():
    """Create wide screenshot (1280x720)"""
    w, h = 1280, 720
    img = Image.new('RGB', (w, h), BG)
    draw = ImageDraw.Draw(img)
    
    # Header bar
    draw.rectangle([0, 0, w, 80], fill=PRIMARY)
    
    # Logo/title
    try:
        font = ImageFont.truetype("arial.ttf", 32)
        font_small = ImageFont.truetype("arial.ttf", 18)
    except:
        font = ImageFont.load_default()
        font_small = ImageFont.load_default()
    
    draw.text((40, 22), "MyLedger", fill=WHITE, font=font)
    draw.text((40, 52), "Income & Expense Manager", fill='#bae6fd', font=font_small)
    
    # Sidebar
    draw.rectangle([0, 80, 280, h], fill='#0f172a')
    
    # Nav items
    nav_items = ['Dashboard', 'Income', 'Expenses', 'Customers', 'Reports', 'Settings']
    for i, item in enumerate(nav_items):
        y = 120 + i * 60
        active = i == 0
        if active:
            draw.rectangle([0, y-5, 280, y+35], fill='#1e3a5f')
            draw.rectangle([0, y-5, 4, y+35], fill=PRIMARY)
        draw.text((30, y), item, fill=WHITE if active else '#64748b', font=font_small)
    
    # Main content area
    content_x, content_y = 320, 120
    
    # Summary cards
    cards = [
        ("Total Income", "TZS 1,250,000", GREEN),
        ("Total Expenses", "TZS 480,000", RED),
        ("Balance", "TZS 770,000", PRIMARY),
    ]
    
    card_w = 280
    card_h = 120
    gap = 24
    
    for i, (label, value, color) in enumerate(cards):
        x = content_x + i * (card_w + gap)
        y = content_y
        
        # Card background
        draw.rounded_rectangle([x, y, x+card_w, y+card_h], radius=12, fill=WHITE, outline=LIGHT_GRAY)
        # Top accent
        draw.rounded_rectangle([x, y, x+card_w, y+4], radius=12, fill=color)
        
        draw.text((x+20, y+20), label, fill=GRAY, font=font_small)
        draw.text((x+20, y+50), value, fill=color, font=font)
    
    # Table
    table_y = content_y + card_h + 40
    table_w = w - content_x - 40
    
    # Table header
    headers = ['Date', 'Category', 'Description', 'Amount', 'Type']
    col_widths = [140, 200, 300, 180, 120]
    col_x = content_x
    
    draw.rounded_rectangle([content_x, table_y, content_x+table_w, table_y+50], radius=8, fill='#0f172a')
    for i, (header, cw) in enumerate(zip(headers, col_widths)):
        draw.text((col_x+15, table_y+12), header, fill=WHITE, font=font_small)
        col_x += cw
    
    # Table rows
    rows = [
        ['2026-01-15', 'Services', 'Consulting fee - Client A', 'TZS 500,000', 'Income'],
        ['2026-01-14', 'Rent', 'Office rent January', 'TZS 300,000', 'Expense'],
        ['2026-01-13', 'Fuel', 'Vehicle fuel', 'TZS 150,000', 'Expense'],
        ['2026-01-12', 'Director Income', 'Monthly director pay', 'TZS 1,000,000', 'Income'],
        ['2026-01-11', 'Internet', 'Office internet', 'TZS 80,000', 'Expense'],
    ]
    
    for row_idx, row in enumerate(rows):
        y = table_y + 50 + row_idx * 55
        bg = WHITE if row_idx % 2 == 0 else '#f8fafc'
        draw.rounded_rectangle([content_x, y, content_x+table_w, y+50], radius=8, fill=bg, outline=LIGHT_GRAY)
        
        col_x = content_x
        for col_idx, (cell, cw) in enumerate(zip(row, col_widths)):
            color = DARK
            if col_idx == 4:
                color = GREEN if cell == 'Income' else RED
            elif col_idx == 3:
                color = GREEN if row[col_idx+1] == 'Income' else RED
            draw.text((col_x+15, y+12), cell, fill=color, font=font_small)
            col_x += cw
    
    # Bottom bar hint
    draw.text((40, h-60), "Swipe from left for menu  |  Tap + to add transaction", fill=GRAY, font=font_small)
    
    filepath = os.path.join(icons_dir, 'screenshot-wide.png')
    img.save(filepath, 'PNG')
    print(f'Created: {filepath}')

def create_narrow_screenshot():
    """Create narrow screenshot (750x1334) - mobile view"""
    w, h = 750, 1334
    img = Image.new('RGB', (w, h), BG)
    draw = ImageDraw.Draw(img)
    
    # Header
    draw.rectangle([0, 0, w, 70], fill=PRIMARY)
    
    try:
        font = ImageFont.truetype("arial.ttf", 28)
        font_small = ImageFont.truetype("arial.ttf", 16)
        font_mono = ImageFont.truetype("arial.ttf", 20)
    except:
        font = ImageFont.load_default()
        font_small = ImageFont.load_default()
        font_mono = ImageFont.load_default()
    
    draw.text((20, 18), "MyLedger", fill=WHITE, font=font)
    
    # Hamburger menu
    draw.rectangle([w-70, 15, w-20, 55], outline=WHITE, width=2)
    for i in range(3):
        draw.rectangle([w-55, 22+i*10, w-35, 26+i*10], fill=WHITE)
    
    # Balance card
    card_y = 100
    draw.rounded_rectangle([20, card_y, w-20, card_y+160], radius=16, fill=WHITE, outline=LIGHT_GRAY)
    
    draw.text((40, card_y+20), "Total Balance", fill=GRAY, font=font_small)
    draw.text((40, card_y+55), "TZS 770,000.00", fill=PRIMARY, font=font)
    draw.text((40, card_y+100), "Income: TZS 1,250,000  |  Expenses: TZS 480,000", fill=GRAY, font=font_small)
    
    # Quick actions
    actions_y = card_y + 190
    actions = [
        ("Add Income", GREEN, "➕"),
        ("Add Expense", RED, "➖"),
        ("View Reports", PRIMARY, "📊"),
    ]
    
    btn_w = (w - 60) // 3
    for i, (label, color, icon) in enumerate(actions):
        x = 20 + i * (btn_w + 10)
        draw.rounded_rectangle([x, actions_y, x+btn_w, actions_y+90], radius=12, fill=color)
        draw.text((x+btn_w//2-20, actions_y+20), icon, fill=WHITE, font=font)
        draw.text((x+15, actions_y+55), label, fill=WHITE, font=font_small)
    
    # Recent transactions
    list_y = actions_y + 120
    draw.text((30, list_y), "Recent Transactions", fill=DARK, font=font)
    
    transactions = [
        ('Today', 'Services', 'Consulting fee', '+500,000', GREEN),
        ('Yesterday', 'Rent', 'Office rent', '-300,000', RED),
        ('2 days ago', 'Fuel', 'Vehicle', '-150,000', RED),
        ('Jan 12', 'Director Income', 'Monthly pay', '+1,000,000', GREEN),
        ('Jan 11', 'Internet', 'Office', '-80,000', RED),
    ]
    
    for i, (date, cat, desc, amount, color) in enumerate(transactions):
        y = list_y + 40 + i * 85
        
        # Transaction card
        draw.rounded_rectangle([20, y, w-20, y+75], radius=10, fill=WHITE, outline=LIGHT_GRAY)
        
        # Left side - category icon
        draw.rounded_rectangle([35, y+12, 70, y+63], radius=8, fill=color)
        draw.text((42, y+20), "💰" if color == GREEN else "💸", fill=WHITE, font=font_small)
        
        # Middle - info
        draw.text((90, y+12), cat, fill=DARK, font=font_small)
        draw.text((90, y+38), desc, fill=GRAY, font=font_small)
        draw.text((90, y+55), date, fill=GRAY, font=font_small)
        
        # Right - amount
        draw.text((w-180, y+28), amount, fill=color, font=font_mono)
    
    # Bottom nav bar
    draw.rectangle([0, h-90, w, h], fill=WHITE)
    draw.line([0, h-90, w, h-90], fill=LIGHT_GRAY, width=2)
    
    nav_icons = ['🏠', '💰', '💸', '👥', '📊']
    for i, icon in enumerate(nav_icons):
        x = (w // 5) * i + (w // 10) - 15
        color = PRIMARY if i == 0 else GRAY
        draw.text((x, h-70), icon, fill=color, font=font)
    
    filepath = os.path.join(icons_dir, 'screenshot-narrow.png')
    img.save(filepath, 'PNG')
    print(f'Created: {filepath}')

if __name__ == '__main__':
    create_wide_screenshot()
    create_narrow_screenshot()
    print('\nScreenshots generated successfully!')