@echo off
setlocal
REM Always operate from the project root, regardless of where this .bat is invoked from.
cd /d "%~dp0.."
echo ========================================
echo    Fabricator Windows Build
echo ========================================
echo.

echo [1/6] Cleaning previous build artifacts...
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build
if exist fabricator.spec del /q fabricator.spec

echo.
echo [2/6] Installing Python dependencies...
pip install -r requirements.txt
if errorlevel 1 goto :error
pip install pyinstaller
if errorlevel 1 goto :error

echo.
echo [3/6] Installing frontend dependencies...
pushd frontend
call npm install
if errorlevel 1 (
    popd
    goto :error
)

echo.
echo [4/6] Building Vue.js frontend...
call npm run build
if errorlevel 1 (
    popd
    goto :error
)
popd

echo.
echo [5/6] Generating fabricator.spec...
python tools\generate_spec.py
if errorlevel 1 goto :error

echo.
echo [6/6] Running PyInstaller...
python -m PyInstaller fabricator.spec --clean --noconfirm
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
echo ========================================
echo    BUILD FAILED
echo ========================================
echo.
pause
exit /b 1
