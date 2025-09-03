import os
from celery import Celery
from celery.schedules import crontab

# Set default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smartVision.settings')

# Create Celery app
app = Celery('smartVision')

# General Celery configuration
app.conf.update(
    worker_pool='threads',
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    worker_max_tasks_per_child=1000,
    worker_concurrency=4,
)

# Read config from Django settings, namespace='CELERY'
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks from all installed apps
app.autodiscover_tasks()

# --- Celery Beat Schedule ---
app.conf.beat_schedule = {
    "stream-all-cameras-every-10-seconds": {
        "task": "gismap.tasks.streaming_tasks.stream_all_cameras",
        "schedule": 10.0,  # every 10 seconds for testing; adjust as needed
    },
}
