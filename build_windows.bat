@echo off
echo ========================================
echo    Fabricator Windows Build
echo ========================================
echo.

echo [1/4] Installing Python dependencies...
pip install -r requirements.txt
pip install pyinstaller
if errorlevel 1 goto :error

echo.
echo [2/4] Building Vue.js Frontend...
cd frontend
call npm install
call npm run build
cd ..
if errorlevel 1 goto :error

echo.
echo [3/4] Running PyInstaller...
python -m PyInstaller fabricator.spec --clean
if errorlevel 1 goto :error

echo.
echo ========================================
echo    BUILD SUCCESSFUL
echo ========================================
echo.
echo Output: dist\Fabricator.exe
echo.
pause
exit /b 0

:error
echo.
echo BUILD FAILED!
pause
exit /b 1
