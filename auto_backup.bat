@echo off
title Auto Backup - Income & Expense
cd /d "%~dp0"

set BACKUP_DEST=D:\OfficeBackups

echo ========================================
echo   Creating system backup...
echo ========================================

:: Run the Flask backup route via curl (requires local server running)
python -c "
import sys
sys.path.insert(0, '.')
from app import app, init_db, _db_path, _backup_path, log_audit
import zipfile, os, shutil
from datetime import datetime

init_db()

# Create backup entry
db_path = _db_path()
backup_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backup')
os.makedirs(backup_dir, exist_ok=True)
zip_path = _backup_path()
timestamp = datetime.now().strftime('%%Y%%m%%d_%%H%%M%%S')
entry_name = f'backup_{timestamp}.db'

with open(db_path, 'rb') as f:
    db_data = f.read()

mode = 'a' if os.path.exists(zip_path) else 'w'
with zipfile.ZipFile(zip_path, mode, zipfile.ZIP_DEFLATED) as z:
    z.writestr(entry_name, db_data)

print(f'[OK] Backup created: {entry_name}')

# Copy backup archive to safe location
safe_dest = r'%BACKUP_DEST%'
os.makedirs(safe_dest, exist_ok=True)
shutil.copy2(zip_path, os.path.join(safe_dest, 'backups.zip'))
print(f'[OK] Backup copied to: {safe_dest}')
"

echo.
echo Done!
pause
