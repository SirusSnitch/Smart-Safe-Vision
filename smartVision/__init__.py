from .celery import app as celery_app

__all__ = ('celery_app',)
# Force l'import des modules de tâches
