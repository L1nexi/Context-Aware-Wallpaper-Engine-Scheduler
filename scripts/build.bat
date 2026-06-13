@echo off
set FRONTEND_APP_DIR=frontend
set FRONTEND_DIST_DIR=%FRONTEND_APP_DIR%\dist

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
pyinstaller --noconsole --onefile --name "WEScheduler" ^
    --icon "packaging\AppIcon.ico" ^
    --add-data "%FRONTEND_DIST_DIR%;%FRONTEND_DIST_DIR%" ^
    --hidden-import=pystray ^
    --hidden-import=PIL ^
    --hidden-import=psutil ^
    --hidden-import=win32gui ^
    --hidden-import=win32con ^
    --hidden-import=win32api ^
    --exclude-module=matplotlib ^
    --exclude-module=numpy ^
    --clean ^
    main.py

if %errorlevel% neq 0 (
    echo PyInstaller failed.
    pause
    exit /b %errorlevel%
)

echo [5/5] Preparing distribution folder...
copy README.md dist\README.md
copy "packaging\Config Tools.bat" "dist\Config Tools.bat"
xcopy "config.example" "dist\config" /S /E /I /Y

echo ==========================================
echo      Build Complete!
echo      Executable is in: dist\WEScheduler.exe
echo ==========================================
pause
