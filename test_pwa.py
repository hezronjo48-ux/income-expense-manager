import subprocess
import time
import requests
import sys

proc = subprocess.Popen([sys.executable, '-c', 'from app import app; app.run(host="0.0.0.0", port=8080, debug=False, use_reloader=False)'], cwd=r'C:\income_expense_manager')
time.sleep(3)
try:
    r = requests.get('http://127.0.0.1:8080/', timeout=3)
    print('Status:', r.status_code)
    print('Has manifest:', 'manifest.json' in r.text)
    print('Has SW:', 'serviceWorker' in r.text)
    print('Has icons:', 'icon-192' in r.text)
    print('Title check:', 'Income' in r.text or 'Login' in r.text)
finally:
    proc.terminate()