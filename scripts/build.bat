@echo off
set DASHBOARD_APP_DIR=dashboard
set DASHBOARD_DIST_DIR=%DASHBOARD_APP_DIR%\dist
set FRONTEND_APP_DIR=frontend
set FRONTEND_DIST_DIR=%FRONTEND_APP_DIR%\dist

echo ==========================================
echo      WEScheduler Build Script
echo ==========================================

echo [1/6] Installing dependencies...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo Failed to install dependencies.
    pause
    exit /b %errorlevel%
)

echo [2/6] Building dashboard...
pushd %DASHBOARD_APP_DIR%
call npm run build-only
if %errorlevel% neq 0 (
    popd
    echo Failed to build dashboard.
    pause
    exit /b %errorlevel%
)
popd

echo [3/6] Building setup frontend...
pushd %FRONTEND_APP_DIR%
call npm run build
if %errorlevel% neq 0 (
    popd
    echo Failed to build setup frontend.
    pause
    exit /b %errorlevel%
)
popd

echo [4/6] Cleaning up previous builds...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [5/6] Running PyInstaller...
pyinstaller --noconsole --onefile --name "WEScheduler" ^
    --icon "%CD%\packaging\AppIcon.ico" ^
    --add-data "%CD%\%DASHBOARD_DIST_DIR%;%DASHBOARD_DIST_DIR%" ^
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

echo [6/6] Preparing distribution folder...
copy README.md dist\README.md

echo ==========================================
echo      Build Complete!
echo      Executable is in: dist\WEScheduler.exe
echo ==========================================
pause
