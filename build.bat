@echo off
setlocal
cd /d "%~dp0"

echo [1/3] Preparing virtual environment...
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
    if errorlevel 1 (
        echo Failed to create virtual environment.
        exit /b 1
    )
)

echo [2/3] Installing dependencies...
".venv\Scripts\python.exe" -m pip install -q --upgrade pip
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt pyinstaller
if errorlevel 1 (
    echo Failed to install dependencies.
    exit /b 1
)

echo [3/4] Preparing exe icon...
if not exist "dist\icon.png" (
    echo Missing dist\icon.png
    exit /b 1
)
".venv\Scripts\python.exe" -c "from PIL import Image; img=Image.open('dist/icon.png').convert('RGBA'); img.save('dist/icon.ico', format='ICO', sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)])"

echo [4/4] Building single-file exe...
".venv\Scripts\pyinstaller.exe" --noconfirm --clean PixCakeXmpConverter.spec
if errorlevel 1 (
    echo Build failed.
    exit /b 1
)

for %%F in ("dist\PixCakeXmpConverter.exe") do (
    echo.
    echo Build complete: dist\PixCakeXmpConverter.exe
    echo Size: %%~zF bytes
)
endlocal
