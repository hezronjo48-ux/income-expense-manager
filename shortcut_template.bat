@echo off
echo ========================================
echo   Income & Expense System Launcher
echo ========================================
echo.
echo This creates a desktop shortcut.
echo.
set /p server_ip="Enter SERVER IP address (e.g. 192.168.1.10): "
echo.
echo Creating shortcut on desktop...
powershell -Command "$WS = New-Object -ComObject WScript.Shell; $SC = $WS.CreateShortcut('%userprofile%\Desktop\Income Expense System.lnk'); $SC.TargetPath = '%%windir%%\system32\cmd.exe'; $SC.Arguments = '/c start http://%server_ip%:5000'; $SC.Description = 'Income & Expense Management System'; $SC.Save()"
echo.
echo Done! Shortcut created on desktop.
pause
