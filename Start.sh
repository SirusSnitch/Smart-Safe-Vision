#!/bin/bash
set -e

# Start Django + Celery in background processes
echo "Starting Uvicorn..."
uvicorn smartVision.asgi:application --host 0.0.0.0 --port 8000 --reload &

echo "Starting Celery Worker..."
celery -A smartVision worker -l info &

echo "Starting Celery Beat..."
celery -A smartVision beat -l info &

# Wait so container stays alive
wait -n
