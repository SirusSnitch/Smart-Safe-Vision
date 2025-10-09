@echo off
REM ===============================================
REM Smart-Safe-Vision Stop Script
REM Stops Celery workers & beat, Uvicorn, MediaMTX,
REM and clears streaming flags in Redis
REM ===============================================

REM -------------------------------
REM Stop Celery workers
REM -------------------------------
echo 🔹 Stopping Celery workers...
taskkill /IM "celery.exe" /F /T >nul 2>&1
timeout /t 1 >nul

REM -------------------------------
REM Stop Celery beat
REM -------------------------------
echo 🔹 Stopping Celery beat...
taskkill /IM "celery.exe" /F /T >nul 2>&1
timeout /t 1 >nul

REM -------------------------------
REM Stop Uvicorn
REM -------------------------------
echo 🔹 Stopping Uvicorn...
taskkill /IM "python.exe" /F /T >nul 2>&1
timeout /t 1 >nul

REM -------------------------------
REM Stop MediaMTX
REM -------------------------------
echo 🔹 Stopping MediaMTX...
taskkill /IM "mediamtx.exe" /F /T >nul 2>&1
timeout /t 1 >nul

REM -------------------------------
REM Clear Redis streaming flags
REM -------------------------------
echo 🔹 Clearing streaming flags in Redis...
python clear_streaming_keys.py

echo ✅ All services stopped and streaming flags cleared.
pause
