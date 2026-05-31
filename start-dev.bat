@echo off
chcp 65001 >nul
title MBForge Dev Mode

echo ========================================
echo   MBForge Development Mode
echo ========================================
echo.

REM Check if uv is available
where uv >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] uv not found. Please install uv: https://github.com/astral-sh/uv
    pause
    exit /b 1
)

REM Start Python server in new window
echo [1/3] Starting Python model server...
start "MBForge-Python" cmd /k "cd %~dp0 && uv run uvicorn mbforge.model_server.main:app --host 127.0.0.1 --port 18792"

REM Wait for Python server to start
timeout /t 3 /nobreak >nul

REM Check Python server
curl -s http://127.0.0.1:18792/api/v1/health >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARNING] Python server may not be ready yet
)

REM Start Vite dev server in new window
echo [2/3] Starting Vite frontend server...
start "MBForge-Frontend" cmd /k "cd %~dp0frontend && npm run dev"

REM Wait for Vite to start
timeout /t 5 /nobreak >nul

echo [3/3] Starting Tauri application...
echo.
echo ========================================
echo   Servers started!
echo   - Python:  http://127.0.0.1:18792
echo   - Frontend: Check the frontend window
echo   - Tauri:   Launching now...
echo ========================================
echo.

REM Start Tauri
cd %~dp0src-tauri && cargo tauri dev
