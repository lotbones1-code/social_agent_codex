@echo off
echo ==========================================
echo   Social Agent Codex - Auto Setup ^& Run
echo ==========================================
echo.

REM Check Python installation
echo [1/5] Checking Python installation...
python --version >nul 2>&1
if %errorlevel% equ 0 (
    set PYTHON_CMD=python
    echo ✓ Found Python
) else (
    python3 --version >nul 2>&1
    if %errorlevel% equ 0 (
        set PYTHON_CMD=python3
        echo ✓ Found Python3
    ) else (
        echo ✗ Python not found. Please install Python 3.9+ from:
        echo    https://www.python.org/downloads/
        pause
        exit /b 1
    )
)

REM Install pip dependencies
echo.
echo [2/5] Installing Python dependencies...
%PYTHON_CMD% -m pip install -r requirements.txt --quiet --disable-pip-version-check
if %errorlevel% neq 0 (
    echo ✗ Failed to install dependencies
    pause
    exit /b 1
)
echo ✓ Dependencies installed

REM Install Playwright browsers
echo.
echo [3/5] Installing Playwright Chromium browser...
%PYTHON_CMD% -m playwright install chromium
if %errorlevel% neq 0 (
    echo ✗ Failed to install Playwright browser
    pause
    exit /b 1
)
echo ✓ Playwright browser installed

REM Check .env file
echo.
echo [4/5] Checking configuration...
if exist .env (
    echo ✓ Configuration file found (.env^)
) else (
    echo ✗ .env file not found!
    pause
    exit /b 1
)

REM Run the bot
echo.
echo [5/5] Starting the bot...
echo.
echo ==========================================
echo   Bot is now running! Press Ctrl+C to stop
echo ==========================================
echo.

%PYTHON_CMD% social_agent.py
pause
