@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo [1/5] Reading version from README.md...
for /f "delims=" %%V in ('python -c "import re,sys; t=open('README.md',encoding='utf-8').read(); m=re.search(r'Version-v([0-9]+\\.[0-9]+\\.[0-9]+)', t); sys.exit(1) if not m else print(m.group(1))"') do set APP_VERSION=%%V
if not defined APP_VERSION (
    echo Failed to read version from README.md badge ^(Version-vX.Y.Z^).
    exit /b 1
)
echo Version: v!APP_VERSION!

echo [2/5] Preparing virtual environment...
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
    if errorlevel 1 (
        echo Failed to create virtual environment.
        exit /b 1
    )
)

echo [3/5] Installing dependencies...
".venv\Scripts\python.exe" -m pip install -q --upgrade pip
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt pyinstaller
if errorlevel 1 (
    echo Failed to install dependencies.
    exit /b 1
)

echo [4/5] Preparing exe icon...
if not exist "dist\icon.png" (
    echo Missing dist\icon.png
    exit /b 1
)
".venv\Scripts\python.exe" -c "from PIL import Image; img=Image.open('dist/icon.png').convert('RGBA'); img.save('dist/icon.ico', format='ICO', sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)])"

echo [5/5] Building single-file exe...
".venv\Scripts\pyinstaller.exe" --noconfirm --clean PixCakeXmpConverter.spec
if errorlevel 1 (
    echo Build failed.
    exit /b 1
)

set "OUTPUT=dist\PixCakeXmpConverter-v!APP_VERSION!.exe"
move /Y "dist\PixCakeXmpConverter.exe" "!OUTPUT!" >nul
if errorlevel 1 (
    echo Failed to rename output exe.
    exit /b 1
)

for %%F in ("!OUTPUT!") do (
    echo.
    echo Build complete: !OUTPUT!
    echo Size: %%~zF bytes
)
endlocal
