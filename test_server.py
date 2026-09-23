import subprocess
import time
import requests
import sys

# Start the app
proc = subprocess.Popen([sys.executable, '-c', 'from app import app; app.run(host="0.0.0.0", port=8080, debug=False, use_reloader=False)'], cwd=r'C:\income_expense_manager')
time.sleep(3)

try:
    r = requests.get('http://127.0.0.1:8080/', timeout=3)
    print('Status:', r.status_code)
    print('Our app:', 'Income & Expense' in r.text or 'Dashboard' in r.text or 'login' in r.text.lower())
    if '<title>' in r.text:
        print('Title:', r.text[r.text.find('<title>')+7:r.text.find('</title>')])
finally:
    proc.terminate()