@echo off
title Income & Expense Manager Setup
echo ============================================
echo   Income & Expense Management System
echo   Installing dependencies...
echo ============================================
echo.

cd /d "%~dp0"

echo Installing required packages...
pip install -r requirements.txt

if %errorlevel% neq 0 (
    echo.
    echo ERROR: Failed to install dependencies.
    echo Make sure Python and pip are installed.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   Setup complete!
echo.
echo   To start the application, double-click:
echo     start.bat
echo.
echo   Or run: python run.py
echo ============================================
echo.
pause
