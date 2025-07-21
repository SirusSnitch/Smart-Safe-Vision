from django.apps import AppConfig

class GismapConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'gismap'

    def ready(self):
        from .tasks import start_all_camera_threads
        try:
            start_all_camera_threads.delay()
        except Exception as e:
            print("[ERROR] Échec du lancement de la tâche Celery :", e)
