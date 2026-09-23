@echo off
setlocal
cd /d "%~dp0.."
set "PYTHON=%CD%\.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
    echo Virtual environment not found: %PYTHON%
    exit /b 1
)
set FRONTEND_APP_DIR=frontend
set FRONTEND_DIST_DIR=%FRONTEND_APP_DIR%\dist

echo ==========================================
echo      WEScheduler Build Script
echo ==========================================

echo [1/5] Installing dependencies...
"%PYTHON%" -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo Failed to install dependencies.
    pause
    exit /b %errorlevel%
)

echo [2/5] Building frontend...
pushd %FRONTEND_APP_DIR%
call npm run build
if %errorlevel% neq 0 (
    popd
    echo Failed to build frontend.
    pause
    exit /b %errorlevel%
)
popd

echo [3/5] Cleaning up previous builds...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [4/5] Running PyInstaller...
"%PYTHON%" -m PyInstaller --noconsole --onefile --name "WEScheduler" ^
    --icon "%CD%\packaging\AppIcon.ico" ^
    --add-data "%CD%\%FRONTEND_DIST_DIR%;%FRONTEND_DIST_DIR%" ^
    --add-data "%CD%\packaging\AppIcon.ico;." ^
    --specpath build ^
    --hidden-import=pystray ^
    --hidden-import=PIL ^
    --hidden-import=psutil ^
    --hidden-import=win32gui ^
    --hidden-import=win32con ^
    --hidden-import=win32api ^
    --clean ^
    main.py

if %errorlevel% neq 0 (
    echo PyInstaller failed.
    pause
    exit /b %errorlevel%
)

echo [5/5] Preparing distribution folder...
copy README.md dist\README.md

echo ==========================================
echo      Build Complete!
echo      Executable is in: dist\WEScheduler.exe
echo ==========================================
pause
