import requests
import subprocess
import time
import sys

proc = subprocess.Popen([sys.executable, '-c', 'from app import app; app.run(host="0.0.0.0", port=8080, debug=False, use_reloader=False)'], cwd=r'C:\income_expense_manager')
time.sleep(3)
try:
    s = requests.Session()
    # Get login page first to get CSRF token
    r = s.get('http://127.0.0.1:8080/login')
    print('Login page:', r.status_code)
    
    # Extract CSRF token
    import re
    csrf_match = re.search(r'name="csrf_token" value="([^"]+)"', r.text)
    if csrf_match:
        csrf_token = csrf_match.group(1)
        print('CSRF token:', csrf_token[:20] + '...')
    else:
        csrf_token = ''
    
    # Login with CSRF
    r = s.post('http://127.0.0.1:8080/login', data={
        'username': 'admin',
        'password': 'admin123',
        'csrf_token': csrf_token
    })
    print('Login:', r.status_code, '->', r.url)
    
    # Test API endpoints
    for at in ['tzs', 'usd']:
        r = s.get(f'http://127.0.0.1:8080/api/customers/{at}')
        print(f'API /api/customers/{at}: {r.status_code} - {len(r.json()) if r.status_code==200 else "error"} customers')
    
    # Test reports generate
    # Get reports page for new CSRF
    r = s.get('http://127.0.0.1:8080/reports')
    csrf_match = re.search(r'name="csrf_token" value="([^"]+)"', r.text)
    csrf_token = csrf_match.group(1) if csrf_match else ''
    
    for at in ['normal', 'dollar']:
        r = s.post('http://127.0.0.1:8080/reports/generate', data={
            'report_type': 'monthly',
            'report_mode': 'standard',
            'account_type': at,
            'date': '2026-01-15',
            'csrf_token': csrf_token
        })
        print(f'Reports {at}: {r.status_code} - {len(r.text)} bytes')
    
finally:
    proc.terminate()