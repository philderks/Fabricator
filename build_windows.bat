@echo off
echo ========================================
echo    Fabricator Windows Build
echo ========================================
echo.

echo [1/5] Installing Python dependencies...
pip install -r requirements.txt
pip install pyinstaller
if errorlevel 1 goto :error

echo.
echo [2/5] Building Vue.js Frontend...
cd frontend
call npm install
call npm run build
cd ..
if errorlevel 1 goto :error

echo.
echo [3/5] Generating fabricator.spec...
python generate_spec.py
if errorlevel 1 goto :error

echo.
echo [4/5] Running PyInstaller...
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
