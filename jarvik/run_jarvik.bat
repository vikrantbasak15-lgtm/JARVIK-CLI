@echo off
setlocal

rem Always run from the folder this .bat file lives in, no matter where it's launched from
cd /d "%~dp0"

echo ============================================
echo   JARVIK launcher
echo ============================================

rem --- Find a working Python command ---
where python >nul 2>nul
if %errorlevel%==0 (
    set "PYCMD=python"
) else (
    where py >nul 2>nul
    if %errorlevel%==0 (
        set "PYCMD=py"
    ) else (
        echo.
        echo Python was not found on this computer.
        echo Please install Python 3.10 or newer from https://www.python.org/downloads/
        echo During install, make sure to check "Add python.exe to PATH".
        echo.
        pause
        exit /b 1
    )
)

rem --- First run: create the virtual environment and install dependencies ---
if not exist "venv\Scripts\activate.bat" (
    echo.
    echo First time setup - this may take a minute, please wait...
    echo.
    %PYCMD% -m venv venv
    if errorlevel 1 (
        echo Failed to create the virtual environment.
        pause
        exit /b 1
    )
    call venv\Scripts\activate.bat
    pip install --upgrade pip >nul
    pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo Something went wrong installing dependencies. See the messages above.
        pause
        exit /b 1
    )
    echo.
    echo Setup complete.
    echo.
) else (
    call venv\Scripts\activate.bat
)

rem --- Launch JARVIK ---
python -m jarvik

echo.
echo JARVIK closed.
pause
