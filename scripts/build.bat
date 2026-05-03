@echo off
echo ==========================================
echo      WEScheduler Build Script
echo ==========================================

echo [1/4] Installing dependencies...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo Failed to install dependencies.
    pause
    exit /b %errorlevel%
)

echo [2/4] Cleaning up previous builds...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist *.spec del /q *.spec

echo [3/4] Running PyInstaller...
pyinstaller --noconsole --onefile --name "WEScheduler" ^
    --icon "AppIcon.ico" ^
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

echo [4/4] Preparing distribution folder...
if not exist dist\scheduler_config.json (
    echo Copying default config...
    copy scheduler_config.example.json dist\scheduler_config.json
)
copy README.md dist\README.md

echo ==========================================
echo      Build Complete!
echo      Executable is in: dist\WEScheduler.exe
echo ==========================================
pause
