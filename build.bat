@echo off
setlocal
cd /d "%~dp0"

echo Installing dependencies...
python -m pip install -r requirements.txt || goto :error

echo.
echo Rendering icon...
python tools\make_icon.py || goto :error

echo.
echo Building Audy.exe...
python -m PyInstaller --noconfirm --clean Audy.spec || goto :error

echo.
echo Done. Find Audy.exe in the dist\ folder.
pause
exit /b 0

:error
echo.
echo Build failed.
pause
exit /b 1
