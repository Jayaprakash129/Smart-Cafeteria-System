@echo off
echo Starting Smart Cafeteria System...
start "Backend"  cmd /k "cd /d D:\FYP\backend && python -m uvicorn app.main:app --reload --port 8000"
timeout /t 4 >nul
start "Frontend" cmd /k "cd /d D:\FYP\frontend && npm run dev"
timeout /t 4 >nul
start http://localhost:5173
