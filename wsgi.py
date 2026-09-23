import sys
path = '/home/Joash48/income_manager'
if path not in sys.path:
    sys.path.insert(0, path)
from app import app as application
