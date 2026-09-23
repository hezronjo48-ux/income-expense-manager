"""
Startup script for Income & Expense Management System.
Run this to initialize and start the application.
"""
import os
import sys
import webbrowser
from threading import Timer

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, init_db

def open_browser():
    webbrowser.open_new('http://127.0.0.1:5000')

if __name__ == '__main__':
    print('=' * 60)
    print('  Income & Expense Management System')
    print('  Initializing...')
    print('=' * 60)

    init_db()

    print()
    print('  Application is starting...')
    print('  Open your browser to: http://127.0.0.1:5000')
    print()
    print('  Default Admin Login:')
    print('    Username: admin')
    print('    Password: admin123')
    print()
    print('  Press Ctrl+C to stop the server.')
    print('=' * 60)
    print()

    # Open browser after a short delay
    Timer(1.5, open_browser).start()

    app.run(host='0.0.0.0', port=5000, debug=True)
