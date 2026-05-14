@echo off
set DASHBOARD_APP_DIR=dashboard
set DASHBOARD_DIST_DIR=%DASHBOARD_APP_DIR%\dist

echo ==========================================
echo      WEScheduler Build Script
echo ==========================================

echo [1/5] Installing dependencies...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo Failed to install dependencies.
    pause
    exit /b %errorlevel%
)

echo [2/5] Building dashboard...
pushd %DASHBOARD_APP_DIR%
call npm run build-only
if %errorlevel% neq 0 (
    popd
    echo Failed to build dashboard.
    pause
    exit /b %errorlevel%
)
popd

echo [3/5] Cleaning up previous builds...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [4/5] Running PyInstaller...
pyinstaller --noconsole --onefile --name "WEScheduler" ^
    --icon "AppIcon.ico" ^
    --add-data "%DASHBOARD_DIST_DIR%;%DASHBOARD_DIST_DIR%" ^
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
copy "Config Tools.bat" "dist\Config Tools.bat"

echo ==========================================
echo      Build Complete!
echo      Executable is in: dist\WEScheduler.exe
echo ==========================================
pause
