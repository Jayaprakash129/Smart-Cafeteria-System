@echo off
setlocal
cd /d "%~dp0"
echo Starting Smart Cafeteria System...

rem ---- Backend: create the virtual environment on first run --------------
if not exist "backend\.venv\Scripts\python.exe" (
    echo [setup] Creating Python virtual environment in backend\.venv ...
    python -m venv backend\.venv || goto :fail
)
rem Idempotent: a few seconds when everything is already installed, and it
rem picks up any package added to requirements.txt since the last run.
echo [setup] Checking Python packages...
backend\.venv\Scripts\python.exe -m pip install -q -r backend\requirements.txt || goto :fail

rem ---- Frontend: install node packages on first run ----------------------
if not exist "frontend\node_modules" (
    echo [setup] Installing frontend packages ^(first run only^)...
    pushd frontend
    call npm install
    if errorlevel 1 ( popd & goto :fail )
    popd
)

rem ---- Launch -------------------------------------------------------------
start "Backend"  cmd /k "cd /d "%~dp0backend" && .venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000"
timeout /t 4 >nul
start "Frontend" cmd /k "cd /d "%~dp0frontend" && npm run dev"
timeout /t 4 >nul
start http://localhost:5173

echo.
echo On the very first run the backend seeds the demo data and trains the
echo models (about a minute). Wait for "Bootstrap complete" in the Backend
echo window before logging in.
exit /b 0

:fail
echo.
echo Setup failed - see the error above. Requires Python 3.10+ and Node 20+ on PATH.
pause
exit /b 1
