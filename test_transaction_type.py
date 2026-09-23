import requests
import subprocess
import time
import sys
import re

proc = subprocess.Popen([sys.executable, '-c', 'from app import app; app.run(host="0.0.0.0", port=8080, debug=False, use_reloader=False)'], cwd=r'C:\income_expense_manager')
time.sleep(3)
try:
    s = requests.Session()
    # Get login page first to get CSRF token
    r = s.get('http://127.0.0.1:8080/login')
    csrf_match = re.search(r'name="csrf_token" value="([^"]+)"', r.text)
    csrf_token = csrf_match.group(1) if csrf_match else ''
    
    # Login with CSRF
    r = s.post('http://127.0.0.1:8080/login', data={
        'username': 'admin',
        'password': 'admin123',
        'csrf_token': csrf_token
    })
    
    # Get reports page for new CSRF
    r = s.get('http://127.0.0.1:8080/reports')
    csrf_match = re.search(r'name="csrf_token" value="([^"]+)"', r.text)
    csrf_token = csrf_match.group(1) if csrf_match else ''
    
    # Test 1: Income only
    print("Test 1: Income Only")
    r = s.post('http://127.0.0.1:8080/reports/generate', data={
        'report_type': 'monthly',
        'report_mode': 'standard',
        'account_type': 'normal',
        'date': '2026-01-15',
        'transaction_type': 'income',
        'csrf_token': csrf_token
    })
    print(f'  Status: {r.status_code}')
    # Check if only income is shown
    has_income = 'Income Records' in r.text
    has_expense = 'Expense Records' in r.text
    print(f'  Has Income section: {has_income}')
    print(f'  Has Expense section: {has_expense}')
    
    # Test 2: Expense only
    print("\nTest 2: Expense Only")
    r = s.post('http://127.0.0.1:8080/reports/generate', data={
        'report_type': 'monthly',
        'report_mode': 'standard',
        'account_type': 'normal',
        'date': '2026-01-15',
        'transaction_type': 'expense',
        'csrf_token': csrf_token
    })
    print(f'  Status: {r.status_code}')
    has_income = 'Income Records' in r.text
    has_expense = 'Expense Records' in r.text
    print(f'  Has Income section: {has_income}')
    print(f'  Has Expense section: {has_expense}')
    
    # Test 3: All (default)
    print("\nTest 3: All (Income + Expenses)")
    r = s.post('http://127.0.0.1:8080/reports/generate', data={
        'report_type': 'monthly',
        'report_mode': 'standard',
        'account_type': 'normal',
        'date': '2026-01-15',
        'transaction_type': 'all',
        'csrf_token': csrf_token
    })
    print(f'  Status: {r.status_code}')
    has_income = 'Income Records' in r.text
    has_expense = 'Expense Records' in r.text
    print(f'  Has Income section: {has_income}')
    print(f'  Has Expense section: {has_expense}')
    
finally:
    proc.terminate()