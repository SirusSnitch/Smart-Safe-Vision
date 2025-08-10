# ============================================================================
# NOTIFICATION_SERVICE.PY - Version modifiée pour stockage image en base
# ============================================================================

import logging
import base64
from django.apps import apps
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.utils import timezone

logger = logging.getLogger(__name__)

class NotificationService:
    """Service centralisé pour gérer toutes les notifications"""
    
    @staticmethod
    def send_unauthorized_plate_notification(matricule, camera, location, confidence, image_bytes=None, detection_id=None):
        """
        Envoie une notification pour matricule non autorisée
        - Sauvegarde dans le modèle Notifications avec image en base
        - Envoie via WebSocket
        """
        try:
            # 1. Sauvegarder dans le modèle Notifications
            notification_obj = NotificationService._save_to_notifications_model(
                alert_type='unauthorized_plate',
                matricule=matricule,
                camera=camera,
                location=location,
                confidence=confidence,
                message=f"🚨 Matricule non autorisée: {matricule}",
                image_bytes=image_bytes
            )
            
            # 2. Envoyer via WebSocket
            success_websocket = NotificationService._send_websocket_notification({
                'alert_type': 'unauthorized_plate',
                'matricule': matricule,
                'camera': camera,
                'location': location,
                'timestamp': timezone.now().isoformat(),
                'confidence': confidence,
                'message': f"🚨 Matricule non autorisée: {matricule}",
                'image_base64': base64.b64encode(image_bytes).decode('utf-8') if image_bytes else None,
                'notification_id': notification_obj.id if notification_obj else None,
                'detection_id': detection_id
            })
            
            logger.info(f"✅ Notification complète envoyée pour matricule: {matricule}")
            logger.info(f"   - Base de données: {'✅' if notification_obj else '❌'}")
            logger.info(f"   - WebSocket: {'✅' if success_websocket else '❌'}")
            logger.info(f"   - Image stockée en base: {'✅' if (notification_obj and notification_obj.image_data) else '❌'}")
            
            return notification_obj
            
        except Exception as e:
            logger.error(f"❌ Erreur lors de l'envoi de notification: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    @staticmethod
    def send_authorized_plate_notification(matricule, camera, location, confidence, detection_id=None):
        """
        Envoie une notification pour matricule autorisée (optionnel)
        """
        try:
            # Sauvegarder dans Notifications (optionnel pour les autorisées)
            notification_obj = NotificationService._save_to_notifications_model(
                alert_type='authorized_plate',
                matricule=matricule,
                camera=camera,
                location=location,
                confidence=confidence,
                message=f"✅ Matricule autorisée: {matricule}",
                image_bytes=None  # Pas d'image pour les autorisées
            )
            
            # Envoyer via WebSocket (optionnel)
            NotificationService._send_websocket_notification({
                'alert_type': 'authorized_plate',
                'matricule': matricule,
                'camera': camera,
                'location': location,
                'timestamp': timezone.now().isoformat(),
                'confidence': confidence,
                'message': f"✅ Matricule autorisée: {matricule}",
                'notification_id': notification_obj.id if notification_obj else None,
                'detection_id': detection_id
            })
            
            logger.info(f"ℹ️ Notification matricule autorisée: {matricule}")
            return notification_obj
            
        except Exception as e:
            logger.error(f"❌ Erreur notification matricule autorisée: {e}")
            return None
    
    @staticmethod
    def _save_to_notifications_model(alert_type, matricule, camera, location, confidence, message, image_bytes=None):
        """Sauvegarde dans le modèle Notifications avec image en base"""
        try:
            Notifications = apps.get_model('gismap', 'Notifications')
            
            # Créer la notification
            notification = Notifications(
                alert_type=alert_type,
                matricule=matricule,
                camera=camera,  # Nom de la caméra (string)
                location=location,
                timestamp=timezone.now(),
                confidence=confidence,
                message=message
            )
            
            # 🆕 NOUVEAU: Stocker l'image directement en base de données
            if image_bytes:
                try:
                    notification.set_image_from_bytes(image_bytes, 'jpeg')
                    logger.info(f"🖼️ Image stockée directement en base ({len(image_bytes)} bytes)")
                except Exception as img_error:
                    logger.error(f"❌ Erreur stockage image en base: {img_error}")
                    # On continue même si l'image échoue
            
            # Sauvegarder la notification (avec image si elle existe)
            notification.save()
            logger.info(f"💾 Notification créée en base avec ID: {notification.id}")
            
            return notification
            
        except Exception as e:
            logger.error(f"❌ Erreur sauvegarde en base Notifications: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    @staticmethod
    def _send_websocket_notification(data):
        """Envoie la notification via WebSocket"""
        try:
            channel_layer = get_channel_layer()
            
            if not channel_layer:
                logger.error("❌ Channel layer non disponible")
                return False
            
            notification_data = {
                'type': 'send_notification',  # Méthode du consumer
                'data': data
            }
            
            # Envoi WebSocket
            async_to_sync(channel_layer.group_send)(
                'notifications',  # Groupe WebSocket
                notification_data
            )
            
            logger.info(f"📢 Notification WebSocket envoyée: {data.get('matricule', 'N/A')}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Erreur WebSocket: {e}")
            return False