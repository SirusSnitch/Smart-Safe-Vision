# gismap/tasks/notification_tasks.py
"""
Tâches Celery pour la gestion des notifications et alertes
"""

from celery import shared_task
import logging
from django.utils import timezone
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import redis
import time
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Configuration Redis
redis_client = redis.StrictRedis(host='localhost', port=6379, db=0, socket_timeout=5)

@shared_task
def send_alert_notification(matricule, camera_id, camera_name=None, lieu=None, detection_id=None):
    """
    Envoyer une notification d'alerte via WebSocket
    """
    try:
        channel_layer = get_channel_layer()
        
        # Récupérer les informations de la caméra si non fournies
        if not camera_name or not lieu:
            try:
                from gismap.models import Camera
                camera = Camera.objects.select_related('department').get(id=camera_id)
                camera_name = camera_name or camera.name
                lieu = lieu or (camera.department.name if camera.department else "Non défini")
            except Exception as e:
                logger.warning(f"[NOTIF] Impossible de récupérer infos caméra {camera_id}: {e}")
                camera_name = camera_name or f"Caméra {camera_id}"
                lieu = lieu or "Non défini"
        
        # Préparer le message d'alerte
        alert_data = {
            "type": "send_alert",
            "message": "🚨 MATRICULE NON AUTORISÉ DÉTECTÉ",
            "matricule": matricule,
            "camera_id": camera_id,
            "camera_name": camera_name,
            "lieu": lieu,
            "timestamp": timezone.now().isoformat(),
            "detection_id": detection_id,
            "priority": "high"
        }
        
        # Envoyer via WebSocket
        async_to_sync(channel_layer.group_send)("alerts", alert_data)
        
        # Stocker dans Redis pour historique
        alert_key = f"alert_{camera_id}_{int(time.time())}"
        redis_client.setex(
            alert_key, 
            3600,  # 1 heure
            f"UNAUTHORIZED:{matricule}:{camera_name}:{lieu}"
        )
        
        logger.info(f"[NOTIF] ✅ Alerte envoyée: {matricule} - {camera_name}")
        
        # Optionnel: Envoyer aussi aux canaux spécifiques de la caméra
        camera_group = f"camera_{camera_id}_alerts"
        async_to_sync(channel_layer.group_send)(camera_group, alert_data)
        
        return {
            "success": True,
            "matricule": matricule,
            "camera_id": camera_id,
            "timestamp": timezone.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"[NOTIF] ❌ Erreur envoi notification: {e}")
        return {"success": False, "error": str(e)}

@shared_task
def send_system_alert(message, alert_type="system", priority="medium", details=None):
    """
    Envoyer une alerte système
    """
    try:
        channel_layer = get_channel_layer()
        
        alert_data = {
            "type": "send_system_alert",
            "message": message,
            "alert_type": alert_type,
            "priority": priority,
            "details": details or {},
            "timestamp": timezone.now().isoformat()
        }
        
        async_to_sync(channel_layer.group_send)("alerts", alert_data)
        
        logger.info(f"[SYSTEM] Alerte système envoyée: {message}")
        
        return {"success": True, "message": message}
        
    except Exception as e:
        logger.error(f"[SYSTEM] Erreur envoi alerte système: {e}")
        return {"success": False, "error": str(e)}

@shared_task
def update_camera_status(camera_id, status, message=None):
    """
    Mettre à jour le statut d'une caméra
    """
    try:
        channel_layer = get_channel_layer()
        
        status_data = {
            "type": "send_camera_status",
            "camera_id": camera_id,
            "status": status,
            "message": message or f"Caméra {camera_id}: {status}",
            "timestamp": timezone.now().isoformat()
        }
        
        # Envoyer aux groupes généraux et spécifiques
        async_to_sync(channel_layer.group_send)("alerts", status_data)
        async_to_sync(channel_layer.group_send)("camera_status", status_data)
        
        # Stocker dans Redis
        redis_client.setex(f"camera_status_{camera_id}", 300, status)  # 5 minutes
        
        logger.info(f"[CAMERA] Statut mis à jour - Caméra {camera_id}: {status}")
        
        return {"success": True, "camera_id": camera_id, "status": status}
        
    except Exception as e:
        logger.error(f"[CAMERA] Erreur mise à jour statut caméra {camera_id}: {e}")
        return {"success": False, "error": str(e)}

@shared_task
def monitor_camera_health():
    """
    Surveiller la santé des caméras et envoyer des alertes si nécessaire
    """
    try:
        from gismap.models import Camera
        
        cameras = Camera.objects.all()
        offline_cameras = []
        online_cameras = []
        
        for camera in cameras:
            camera_id = camera.id
            frame_key = f"camera_frame_{camera_id}"
            
            # Vérifier si la caméra envoie des frames récentes
            frame_exists = redis_client.exists(frame_key)
            
            if frame_exists:
                # Vérifier l'âge de la dernière frame
                frame_ttl = redis_client.ttl(frame_key)
                if frame_ttl > 0:  # Frame récente
                    online_cameras.append(camera_id)
                    # Mettre à jour le statut comme en ligne
                    update_camera_status.delay(camera_id, "online")
                else:
                    offline_cameras.append(camera_id)
            else:
                offline_cameras.append(camera_id)
        
        # Envoyer alertes pour caméras hors ligne
        for camera_id in offline_cameras:
            try:
                camera = Camera.objects.get(id=camera_id)
                send_system_alert.delay(
                    f"⚠️ Caméra '{camera.name}' hors ligne",
                    alert_type="camera_offline",
                    priority="medium",
                    details={"camera_id": camera_id, "camera_name": camera.name}
                )
                update_camera_status.delay(camera_id, "offline", "Aucune frame reçue")
            except:
                pass
        
        # Statistiques globales
        total_cameras = len(cameras)
        online_count = len(online_cameras)
        offline_count = len(offline_cameras)
        
        logger.info(f"[MONITOR] Santé caméras - En ligne: {online_count}/{total_cameras}")
        
        # Envoyer mise à jour globale
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)("alerts", {
            "type": "send_detection_update",
            "camera_count": total_cameras,
            "online_cameras": online_count,
            "offline_cameras": offline_count,
            "timestamp": timezone.now().isoformat()
        })
        
        return {
            "total_cameras": total_cameras,
            "online": online_count,
            "offline": offline_count,
            "offline_cameras": offline_cameras
        }
        
    except Exception as e:
        logger.error(f"[MONITOR] Erreur surveillance caméras: {e}")
        return {"error": str(e)}

@shared_task
def generate_daily_report():
    """
    Générer un rapport quotidien des détections
    """
    try:
        from gismap.models import DetectionMatricule, Camera
        
        today = timezone.now().date()
        
        # Statistiques du jour
        total_detections = DetectionMatricule.objects.filter(date_detection=today).count()
        unauthorized_detections = DetectionMatricule.objects.filter(
            date_detection=today, 
            est_autorise=False
        ).count()
        authorized_detections = total_detections - unauthorized_detections
        
        # Détections par caméra
        camera_stats = {}
        for camera in Camera.objects.all():
            camera_detections = DetectionMatricule.objects.filter(
                date_detection=today,
                camera=camera
            ).count()
            camera_unauthorized = DetectionMatricule.objects.filter(
                date_detection=today,
                camera=camera,
                est_autorise=False
            ).count()
            
            camera_stats[camera.name] = {
                "total": camera_detections,
                "unauthorized": camera_unauthorized,
                "authorized": camera_detections - camera_unauthorized
            }
        
        # Préparer le rapport
        report = {
            "date": today.isoformat(),
            "summary": {
                "total_detections": total_detections,
                "authorized": authorized_detections,
                "unauthorized": unauthorized_detections,
                "unauthorized_percentage": round((unauthorized_detections / total_detections * 100) if total_detections > 0 else 0, 2)
            },
            "cameras": camera_stats
        }
        
        # Envoyer rapport via WebSocket si des alertes
        if unauthorized_detections > 0:
            send_system_alert.delay(
                f"📊 Rapport quotidien: {unauthorized_detections} matricules non autorisés détectés",
                alert_type="daily_report",
                priority="low",
                details=report
            )
        
        logger.info(f"[REPORT] Rapport quotidien généré: {total_detections} détections, {unauthorized_detections} non autorisées")
        
        return report
        
    except Exception as e:
        logger.error(f"[REPORT] Erreur génération rapport quotidien: {e}")
        return {"error": str(e)}

@shared_task
def cleanup_old_alerts():
    """
    Nettoyer les anciennes alertes de Redis
    """
    try:
        # Nettoyer les alertes de plus de 24h
        current_time = int(time.time())
        deleted_count = 0
        
        # Récupérer toutes les clés d'alertes
        alert_keys = redis_client.keys("alert_*")
        
        for key in alert_keys:
            try:
                # Extraire le timestamp de la clé
                key_parts = key.decode().split('_')
                if len(key_parts) >= 3:
                    timestamp = int(key_parts[2])
                    age = current_time - timestamp
                    
                    # Supprimer si plus de 24h (86400 secondes)
                    if age > 86400:
                        redis_client.delete(key)
                        deleted_count += 1
            except:
                continue
        
        logger.info(f"[CLEANUP] {deleted_count} anciennes alertes nettoyées")
        
        return {"deleted_alerts": deleted_count}
        
    except Exception as e:
        logger.error(f"[CLEANUP] Erreur nettoyage alertes: {e}")
        return {"error": str(e)}

@shared_task
def send_periodic_stats():
    """
    Envoyer des statistiques périodiques via WebSocket
    """
    try:
        from gismap.models import DetectionMatricule, Camera
        
        today = timezone.now().date()
        last_hour = timezone.now() - timedelta(hours=1)
        
        # Calculer statistiques
        stats = {
            "total_detections_today": DetectionMatricule.objects.filter(
                date_detection=today
            ).count(),
            "unauthorized_today": DetectionMatricule.objects.filter(
                date_detection=today,
                est_autorise=False
            ).count(),
            "detections_last_hour": DetectionMatricule.objects.filter(
                date_detection=today,
                heure_detection__gte=last_hour.time()
            ).count(),
            "total_cameras": Camera.objects.count(),
            "timestamp": timezone.now().isoformat()
        }
        
        # Envoyer via WebSocket
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)("alerts", {
            "type": "send_detection_update",
            "stats": stats,
            "timestamp": timezone.now().isoformat()
        })
        
        return stats
        
    except Exception as e:
        logger.error(f"[STATS] Erreur envoi statistiques périodiques: {e}")
        return {"error": str(e)}

# ============================================================================
# TÂCHES DE MAINTENANCE
# ============================================================================

@shared_task
def backup_detections():
    """
    Sauvegarder les détections importantes
    """
    try:
        from gismap.models import DetectionMatricule
        import json
        import os
        
        # Créer dossier backup si nécessaire
        backup_dir = "backups/detections"
        os.makedirs(backup_dir, exist_ok=True)
        
        today = timezone.now().date()
        
        # Récupérer les détections non autorisées du jour
        unauthorized_detections = DetectionMatricule.objects.filter(
            date_detection=today,
            est_autorise=False
        ).select_related('camera', 'camera__department')
        
        backup_data = []
        for detection in unauthorized_detections:
            backup_data.append({
                "id": detection.id,
                "numero": detection.numero,
                "date_detection": detection.date_detection.isoformat(),
                "heure_detection": detection.heure_detection.isoformat(),
                "camera_id": detection.camera.id,
                "camera_name": detection.camera.name,
                "lieu": detection.camera.department.name if detection.camera.department else None,
                "est_autorise": detection.est_autorise
            })
        
        # Sauvegarder dans un fichier JSON
        backup_filename = f"{backup_dir}/unauthorized_detections_{today.isoformat()}.json"
        with open(backup_filename, 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"[BACKUP] {len(backup_data)} détections sauvegardées dans {backup_filename}")
        
        return {
            "backed_up_count": len(backup_data),
            "filename": backup_filename
        }
        
    except Exception as e:
        logger.error(f"[BACKUP] Erreur sauvegarde détections: {e}")
        return {"error": str(e)}

@shared_task
def test_notification_system():
    """
    Tester le système de notifications
    """
    try:
        # Envoyer une alerte de test
        send_system_alert.delay(
            "🧪 Test du système de notifications - Tout fonctionne correctement",
            alert_type="test",
            priority="low",
            details={"test_time": timezone.now().isoformat()}
        )
        
        logger.info("[TEST] Test notification système envoyé")
        
        return {"success": True, "message": "Test notification envoyé"}
        
    except Exception as e:
        logger.error(f"[TEST] Erreur test notifications: {e}")
        return {"success": False, "error": str(e)}
    

# the new alerts for human related incidents 

# ... your existing code unchanged above ...

@shared_task
def send_human_boxes_alert(camera_id, camera_name=None, details=None):
    """
    Envoyer une notification quand une personne porte une boîte est détectée
    """
    try:
        message = "🚨 Personne avec boîte détectée"
        send_system_alert.delay(
            message=message,
            alert_type="human_boxes",
            priority="medium",
            details={
                "camera_id": camera_id,
                "camera_name": camera_name,
                **(details or {})
            }
        )
        logger.info(f"[NOTIF] Alerte human-boxes envoyée - Caméra {camera_id}")
        return {"success": True, "camera_id": camera_id}
    except Exception as e:
        logger.error(f"[NOTIF] Erreur envoi alerte human-boxes: {e}")
        return {"success": False, "error": str(e)}

@shared_task
def send_fallen_alert(camera_id, camera_name=None, details=None):
    """
    Envoyer une notification quand une personne tombée est détectée
    """
    try:
        message = "⚠️ Personne tombée détectée"
        send_system_alert.delay(
            message=message,
            alert_type="fallen",
            priority="high",
            details={
                "camera_id": camera_id,
                "camera_name": camera_name,
                **(details or {})
            }
        )
        logger.info(f"[NOTIF] Alerte Fallen envoyée - Caméra {camera_id}")
        return {"success": True, "camera_id": camera_id}
    except Exception as e:
        logger.error(f"[NOTIF] Erreur envoi alerte Fallen: {e}")
        return {"success": False, "error": str(e)}

@shared_task
def send_aggression_alert(camera_id, camera_name=None, details=None):
    """
    Envoyer une notification quand une agression est détectée
    """
    try:
        message = "⚠️ Agression détectée"
        send_system_alert.delay(
            message=message,
            alert_type="aggression",
            priority="high",
            details={
                "camera_id": camera_id,
                "camera_name": camera_name,
                **(details or {})
            }
        )
        logger.info(f"[NOTIF] Alerte Aggression envoyée - Caméra {camera_id}")
        return {"success": True, "camera_id": camera_id}
    except Exception as e:
        logger.error(f"[NOTIF] Erreur envoi alerte Aggression: {e}")
        return {"success": False, "error": str(e)}
