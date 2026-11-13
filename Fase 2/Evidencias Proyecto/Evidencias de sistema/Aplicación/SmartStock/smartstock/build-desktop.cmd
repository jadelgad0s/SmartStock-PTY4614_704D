@echo off
setlocal
cd /d "%~dp0"

python -c "import struct, sys; sys.exit(sys.version_info[:3] != (3, 13, 7) or struct.calcsize('P') != 8)"
if errorlevel 1 (
    echo Se necesita Python 3.13.7 de 64 bits en el PATH para compilar.
    exit /b 1
)

python -m venv .venv-desktop || exit /b 1
set "PY_DESKTOP=.venv-desktop\Scripts\python.exe"
"%PY_DESKTOP%" -m pip install -r requirements-desktop-build.txt || exit /b 1
"%PY_DESKTOP%" -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name SmartStock --icon icono.ico --add-data "icono.ico:." --add-data "desktop_splash.html:." ^
    --exclude-module django --collect-all webview desktop.py || exit /b 1

echo Ejecutable creado en dist\SmartStock.exe
