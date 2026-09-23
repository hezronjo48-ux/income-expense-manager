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
    
    # Get reports page
    r = s.get('http://127.0.0.1:8080/reports')
    print('Reports page:', r.status_code)
    
    # Check for new elements
    checks = [
        'transaction_type',
        'Income Only',
        'Expenses Only',
        'All (Income + Expenses)',
        'cust_transaction_type',
        'filterCategoriesByType',
    ]
    
    for check in checks:
        found = check in r.text
        print(f'  {check}: {"OK" if found else "MISSING"}')
    
    # Check categories have class attributes
    if 'cat-income' in r.text and 'cat-expense' in r.text:
        print('  Category classes (cat-income/cat-expense): OK')
    else:
        print('  Category classes: MISSING')
    
finally:
    proc.terminate()