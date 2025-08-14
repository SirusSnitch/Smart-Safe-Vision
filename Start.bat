@echo off

REM Activate virtual environment
call venv\Scripts\activate

REM Start Uvicorn in a new terminal
start cmd /k "call venv\Scripts\activate && uvicorn smartVision.asgi:application --reload"

REM Start Celery beat in a new terminal
start cmd /k "call venv\Scripts\activate && celery -A smartVision beat -l info"

REM Start Celery worker in a new terminal
start cmd /k "call venv\Scripts\activate && celery -A smartVision worker -l info"

echo All services started.
pause
