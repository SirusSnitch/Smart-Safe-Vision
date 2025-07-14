from celery import shared_task
import cv2
import os
from datetime import datetime
from django.conf import settings
from .models import Camera

@shared_task
def capture_frame(camera_id, rtsp_url):
    print(f"[{camera_id}] Capture frame")

    try:
        cap = cv2.VideoCapture(rtsp_url)
        if not cap.isOpened():
            print(f"[{camera_id}] Impossible d'ouvrir le flux RTSP")
            return f"[{camera_id}] Failed to open RTSP stream"

        ret, frame = cap.read()
        if not ret:
            print(f"[{camera_id}] Frame non reçue")
            cap.release()
            return f"[{camera_id}] Failed to capture frame"

        # Utiliser MEDIA_ROOT au lieu de chemin relatif
        camera_dir = os.path.join(settings.MEDIA_ROOT, 'captures', f'camera_{camera_id}')
        os.makedirs(camera_dir, exist_ok=True)
        
        # Vérifier que le dossier est créé
        print(f"[{camera_id}] Dossier créé: {camera_dir}")
        print(f"[{camera_id}] Dossier existe: {os.path.exists(camera_dir)}")

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = os.path.join(camera_dir, f"frame_{timestamp}.jpg")
        
        # Vérifier l'écriture du fichier
        success = cv2.imwrite(filename, frame)
        print(f"[{camera_id}] cv2.imwrite success: {success}")
        print(f"[{camera_id}] Fichier créé: {os.path.exists(filename)}")
        
        if success and os.path.exists(filename):
            print(f"[{camera_id}] Image enregistrée: {filename}")
        else:
            print(f"[{camera_id}] ERREUR: Échec de l'enregistrement")

        cap.release()
        return f"[{camera_id}] Frame captured and saved: {filename}"

    except Exception as e:
        print(f"[{camera_id}] Exception capturée: {e}")
        return f"[{camera_id}] Exception: {e}"


@shared_task
def capture_all_cameras_once():
    cameras = Camera.objects.all()
    results = []
    
    print(f"[DEBUG] Nombre de caméras: {cameras.count()}")
    print(f"[DEBUG] MEDIA_ROOT: {settings.MEDIA_ROOT}")
    
    for camera in cameras:
        try:
            # CORRECTION: Appeler directement la fonction au lieu d'utiliser .apply()
            # Option 1: Appel synchrone (recommandé pour le débogage)
            result = capture_frame(camera.id, camera.rtsp_url)
            results.append(result)
            
            # Option 2: Si vous voulez vraiment utiliser Celery de manière asynchrone
            # result = capture_frame.delay(camera.id, camera.rtsp_url)
            # results.append(result.get(timeout=30))
            
        except Exception as e:
            error_msg = f"Erreur sur caméra {camera.id} : {e}"
            print(f"[ERROR] {error_msg}")
            results.append(error_msg)
    
    return results