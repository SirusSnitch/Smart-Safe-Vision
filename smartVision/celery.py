import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smartVision.settings')

app = Celery('smartVision')

# Configuration spécifique pour Python 3.13
app.conf.update(
    worker_pool='threads',  # Utiliser threads au lieu de processes
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    worker_max_tasks_per_child=1000,
    worker_concurrency=4,  # Ajustez selon vos besoins
)

app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()