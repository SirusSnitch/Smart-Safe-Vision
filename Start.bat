@echo off
REM ===============================================
REM Smart-Safe-Vision Startup Script
REM Activates virtual environment, starts Uvicorn,
REM Celery beat & worker, and MediaMTX in order
REM ===============================================

REM Activate virtual environment
call venv311\Scripts\activate

REM -------------------------------
REM Start Uvicorn (API server)
REM -------------------------------
start cmd /k "call venv311\Scripts\activate && uvicorn smartVision.asgi:application --reload"

REM -------------------------------
REM Start Celery beat
REM -------------------------------
start cmd /k "call venv311\Scripts\activate && celery -A smartVision beat -l info"

REM -------------------------------
REM Wait a few seconds to ensure Uvicorn & DB are ready
REM -------------------------------
timeout /t 5 /nobreak >nul

REM -------------------------------
REM Start Celery worker
REM -------------------------------
start cmd /k "call venv311\Scripts\activate && celery -A smartVision worker --loglevel=info"

REM -------------------------------
REM Start MediaMTX from the mediamtx folder
REM -------------------------------
start cmd /k "cd /d %~dp0mediamtx && mediamtx.exe"
