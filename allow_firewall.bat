@echo off
netsh advfirewall firewall add rule name="IncomeExpenseManager" dir=in action=allow protocol=TCP localport=5000 profile=any
echo Done. Press any key to exit.
pause >nul
