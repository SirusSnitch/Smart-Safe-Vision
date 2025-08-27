@echo off

REM Activate virtual environment
call venv311\Scripts\activate

REM Start Uvicorn in a new terminal
start cmd /k "call venv311\Scripts\activate && uvicorn smartVision.asgi:application"

REM Start Celery beat in a new terminal
start cmd /k "call venv311\Scripts\activate && celery -A smartVision beat -l info"

REM Start Celery worker in a new terminal
start cmd /k "call venv311\Scripts\activate && celery -A smartVision worker -l info"


