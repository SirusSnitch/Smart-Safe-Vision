import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smartVision.settings')

app = Celery('smartVision')

app.conf.update(
    worker_pool='threads',
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    worker_max_tasks_per_child=1000,
    worker_concurrency=4,
)

app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
