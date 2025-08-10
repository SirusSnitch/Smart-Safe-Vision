import pytesseract
import cv2
import numpy as np
import redis
import re
from celery import shared_task
import logging

# NOUVEAUX IMPORTS POUR WEBSOCKET
from django.apps import apps
from django.utils import timezone
from django.core.files.base import ContentFile
import base64

# IMPORT DU NOUVEAU SERVICE
from .notification_service import NotificationService

# Configuration Tesseract
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# Redis Connection
r = redis.StrictRedis(host='localhost', port=6379, db=0)

def check_and_save_detection(license_plate, camera_id, confidence_score, image_bytes=None):
    """Vérifie autorisation et utilise le service unifié pour les notifications"""
    detection = None
    try:
        # Import des modèles Django
        DetectionMatricule = apps.get_model('gismap', 'DetectionMatricule')
        MatriculeAutorise = apps.get_model('gismap', 'MatriculeAutorise')
        Camera = apps.get_model('gismap', 'Camera')

        # Récupérer la caméra avec vérification d'existence
        try:
            camera = Camera.objects.get(id=camera_id)
            logging.info(f"📷 Caméra trouvée: {camera.name} (ID: {camera_id})")
        except Camera.DoesNotExist:
            logging.error(f"❌ Caméra avec ID {camera_id} n'existe pas dans la base de données")
            return None, False

        # Vérifier si autorisé dans ce lieu
        is_authorized = False
        if camera.department:
            is_authorized = MatriculeAutorise.objects.filter(
                numero=license_plate,
                lieu=camera.department
            ).exists()
            logging.info(f"🔍 Vérification autorisation pour {license_plate} dans {camera.department.name}: {'✅' if is_authorized else '❌'}")
        else:
            logging.warning(f"⚠️ Caméra {camera.name} n'a pas de département assigné")

        # Créer l'instance de détection avec gestion d'erreurs
        try:
            detection = DetectionMatricule.objects.create(
                numero=license_plate,
                camera=camera,
                est_autorise=is_authorized
            )
            logging.info(f"💾 DetectionMatricule créée avec ID: {detection.id}")
        except Exception as create_error:
            logging.error(f"❌ Erreur création DetectionMatricule: {create_error}")
            return None, False

        # Stocker l'image dans DetectionMatricule avec vérifications
        if image_bytes and detection:
            try:
                filename = f"{timezone.now().strftime('%Y%m%d_%H%M%S')}_{license_plate.replace(' ', '_')}.jpg"
                detection.image.save(filename, ContentFile(image_bytes), save=True)
                logging.info(f"🖼️ Image sauvegardée dans DetectionMatricule: {filename}")
            except Exception as img_error:
                logging.error(f"❌ Erreur sauvegarde image DetectionMatricule: {img_error}")
                # On continue même si l'image échoue

        # 🚨 NOUVELLE LOGIQUE : Utiliser NotificationService
        if not is_authorized:
            # Envoyer notification matricule non autorisée
            try:
                notification_obj = NotificationService.send_unauthorized_plate_notification(
                    matricule=license_plate,
                    camera=camera.name,  # Nom de la caméra
                    location=camera.department.name if camera.department else 'Inconnu',
                    confidence=confidence_score,
                    image_bytes=image_bytes,
                    detection_id=detection.id if detection else None
                )
                
                logging.warning(f"🚨 ALERTE: Matricule non autorisée {license_plate} (Cam: {camera.name})")
                logging.info(f"📝 Notification ID: {notification_obj.id if notification_obj else 'Échec sauvegarde'}")
            except Exception as notif_error:
                logging.error(f"❌ Erreur envoi notification: {notif_error}")
                # On continue même si la notification échoue
                
        else:
            logging.info(f"✅ Matricule autorisée: {license_plate} (Cam: {camera.name})")

        return detection, is_authorized

    except Exception as e:
        logging.error(f"❌ Erreur générale vérification matricule: {e}")
        import traceback
        logging.error(traceback.format_exc())
        return None, False

def detect_h264_corruption(img):
    """Détection des artifacts de corruption H.264"""
    
    if img is None:
        return True
    
    # Conversion en niveaux de gris pour analyse
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img
    
    height, width = gray.shape
    
    # 1. Vérifier les blocs corrompus (macrobloques 16x16)
    corruption_score = 0
    
    # Parcourir par blocs de 16x16 (taille macrobloc H.264)
    for y in range(0, height-16, 16):
        for x in range(0, width-16, 16):
            block = gray[y:y+16, x:x+16]
            
            # Détecter les blocs uniformes suspects (corruption commune)
            if np.std(block) < 5:  # Bloc trop uniforme
                corruption_score += 1
            
            # Détecter les transitions brutales (erreurs de décodage)
            edges = cv2.Canny(block, 50, 150)
            if np.sum(edges) > 1000:  # Trop d'arêtes = artifacts
                corruption_score += 1
    
    total_blocks = (height//16) * (width//16)
    corruption_ratio = corruption_score / max(total_blocks, 1)
    
    return corruption_ratio > 0.3  # Plus de 30% de blocs suspects

def fix_h264_artifacts(img):
    """Correction spécialisée des artifacts H.264"""
    
    if img is None:
        return None
    
    # Conversion en niveaux de gris
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img.copy()
    
    # 1. Débruitage spécialisé pour H.264
    # Filtre bilateral pour préserver les bords tout en supprimant le bruit de compression
    denoised = cv2.bilateralFilter(gray, 9, 75, 75)
    
    # 2. Correction des artefacts de blocs
    # Filtre gaussien léger pour lisser les transitions entre macroblocs
    smoothed = cv2.GaussianBlur(denoised, (3, 3), 0.5)
    
    # 3. Reconstruction avec filtre médian pour éliminer les pixels isolés corrompus
    median_filtered = cv2.medianBlur(smoothed, 3)
    
    # 4. Amélioration du contraste après débruitage
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    enhanced = clahe.apply(median_filtered)
    
    return enhanced

def robust_preprocessing(img):
    """Préprocessing robuste contre la corruption H.264"""
    
    # 1. Détection et correction des artifacts H.264
    is_corrupted = detect_h264_corruption(img)
    
    if is_corrupted:
        logging.warning("🚨 Corruption H.264 détectée - Application des corrections")
        corrected = fix_h264_artifacts(img)
    else:
        # Image saine, traitement normal
        if len(img.shape) == 3:
            corrected = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            corrected = img.copy()
    
    # 2. Redimensionnement agressif pour compenser la perte de qualité
    height, width = corrected.shape
    target_height = 400  # Très haute résolution
    if height < target_height:
        scale_factor = target_height / height
        new_width = int(width * scale_factor * 2.5)  # Largeur très étendue
        corrected = cv2.resize(corrected, (new_width, target_height), interpolation=cv2.INTER_LANCZOS4)
    
    # 3. Amélioration finale du contraste
    # Étirement d'histogramme
    min_val, max_val = np.percentile(corrected, [2, 98])  # Ignorer les 2% d'outliers
    if max_val > min_val:
        stretched = np.clip((corrected - min_val) * 255 / (max_val - min_val), 0, 255).astype(np.uint8)
    else:
        stretched = corrected
    
    # 4. Correction gamma adaptative
    gamma = 1.3 if is_corrupted else 1.1  # Plus de correction si corruption
    lookup_table = np.array([((i / 255.0) ** (1.0 / gamma)) * 255 for i in np.arange(0, 256)]).astype("uint8")
    gamma_corrected = cv2.LUT(stretched, lookup_table)
    
    # 5. Seuillage adaptatif robust
    # Otsu avec pré-filtrage
    blur_light = cv2.GaussianBlur(gamma_corrected, (3, 3), 0)
    _, thresh_otsu = cv2.threshold(blur_light, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    # Adaptatif avec paramètres plus conservateurs
    thresh_adaptive = cv2.adaptiveThreshold(
        gamma_corrected, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
        cv2.THRESH_BINARY, 21, 8
    )
    
    # Versions inversées
    inverted_otsu = cv2.bitwise_not(thresh_otsu)
    inverted_adaptive = cv2.bitwise_not(thresh_adaptive)
    
    return {
        'original_processed': gamma_corrected,
        'otsu': thresh_otsu,
        'otsu_inv': inverted_otsu,
        'adaptive': thresh_adaptive,
        'adaptive_inv': inverted_adaptive,
        'corruption_detected': is_corrupted
    }

def extract_plate_components(text):
    """Extraction robuste des composants même avec OCR partiel"""
    
    if not text:
        return None, None, None
    
    # Nettoyer le texte
    cleaned = re.sub(r'[^\u0600-\u06FF0-9\s]', ' ', text)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    
    logging.info(f"🔍 Texte nettoyé pour extraction: '{cleaned}'")
    
    # 1. Pattern parfait: XXX تونس XXX
    perfect_match = re.search(r'(\d+)\s*(?:تونس|ثونس|توس|تون|فتن|فونس|توتس)\s*(\d+)', cleaned)
    if perfect_match:
        return perfect_match.group(1), 'تونس', perfect_match.group(2)
    
    # 2. Recherche flexible des chiffres
    digits = re.findall(r'\d+', cleaned)
    
    # 3. Recherche de fragments arabes
    arabic_fragments = re.findall(r'[\u0600-\u06FF]+', cleaned)
    
    logging.info(f"🔢 Chiffres trouvés: {digits}")
    logging.info(f"🔤 Fragments arabes: {arabic_fragments}")
    
    # 4. Reconstruction intelligente
    if len(digits) >= 2:
        # Prendre le premier et dernier groupe de chiffres
        left_digits = digits[0]
        right_digits = digits[-1]
        
        # Vérifier si on a des indices de "تونس"
        has_arabic_hint = bool(arabic_fragments) or any(
            hint in cleaned for hint in ['ت', 'و', 'ن', 'س', 'ف']
        )
        
        if has_arabic_hint or len(digits) == 2:
            return left_digits, 'تونس', right_digits
    
    # 5. Tentative désespérée: chercher juste des chiffres séparés
    if len(digits) >= 2:
        # Si on a au moins 2 groupes, supposer que c'est une plaque
        return digits[0], 'تونس', digits[-1]
    
    return None, None, None

def validate_reconstructed_plate(left, center, right):
    """Validation permissive pour images corrompues"""
    
    if not left or not right:
        return 0, ""
    
    # Nettoyer les composants
    left_clean = re.sub(r'[^\d]', '', str(left))
    right_clean = re.sub(r'[^\d]', '', str(right))
    
    # Critères minimaux
    if len(left_clean) < 1 or len(right_clean) < 1:
        return 0, ""
    
    if len(left_clean) > 5 or len(right_clean) > 5:
        return 0, ""
    
    # Construction finale
    final_plate = f"{left_clean} تونس {right_clean}"
    
    # Score permissif
    score = 40  # Score de base plus bas
    
    # Bonus pour longueur
    if 2 <= len(left_clean) <= 3 and 2 <= len(right_clean) <= 3:
        score += 30
    elif len(left_clean) >= 1 and len(right_clean) >= 1:
        score += 20
    
    # Bonus pour diversité des chiffres
    all_digits = left_clean + right_clean
    if len(set(all_digits)) > 1:
        score += 15
    
    # Bonus pour longueur totale raisonnable
    if 4 <= len(all_digits) <= 7:
        score += 10
    
    return score, final_plate

@shared_task
def run_ocr_task(image_bytes, camera_id):
    """OCR robuste contre les corruptions H.264 AVEC NOTIFICATIONS WEBSOCKET"""
    
    try:
        # 1. Décodage avec gestion d'erreurs
        np_arr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        
        if img is None:
            logging.error(f"❌ Image non décodable Cam {camera_id} - Possible corruption H.264")
            return {"success": False, "error": "Image corrompue (H.264?)"}
        
        # 2. Préprocessing robuste avec détection de corruption
        processed_data = robust_preprocessing(img)
        
        if processed_data['corruption_detected']:
            logging.warning(f"🚨 Corruption H.264 détectée et corrigée pour Cam {camera_id}")
        
        # 3. Configurations OCR adaptées aux images potentiellement corrompues
        robust_configs = [
            # Config très tolérante
            {"config": "--psm 8 -c tessedit_do_invert=0", "lang": "ara+eng", "priority": 20},
            {"config": "--psm 7 -c tessedit_do_invert=0", "lang": "ara+eng", "priority": 18},
            {"config": "--psm 6 -c tessedit_do_invert=0", "lang": "ara+eng", "priority": 15},
            
            # Config avec inversion automatique
            {"config": "--psm 8 -c tessedit_do_invert=1", "lang": "ara+eng", "priority": 16},
            {"config": "--psm 7 -c tessedit_do_invert=1", "lang": "ara+eng", "priority": 14},
            
            # Config de secours
            {"config": "--psm 8", "lang": "eng", "priority": 10},
            {"config": "--psm 7", "lang": "eng", "priority": 8},
        ]
        
        best_result = ""
        best_score = 0
        best_method = ""
        debug_results = []
        
        # 4. Test sur toutes les versions d'image
        image_versions = [
            ('original', processed_data['original_processed']),
            ('otsu', processed_data['otsu']),
            ('otsu_inv', processed_data['otsu_inv']),
            ('adaptive', processed_data['adaptive']),
            ('adaptive_inv', processed_data['adaptive_inv'])
        ]
        
        for img_name, img_version in image_versions:
            for config_data in robust_configs:
                try:
                    raw_text = pytesseract.image_to_string(
                        img_version,
                        lang=config_data["lang"],
                        config=config_data["config"]
                    ).strip()
                    
                    if raw_text:
                        debug_results.append(f"{img_name}_{config_data['lang']}: '{raw_text}'")
                        
                        # Extraction des composants
                        left, center, right = extract_plate_components(raw_text)
                        
                        if left and right:
                            score, validated = validate_reconstructed_plate(left, center, right)
                            total_score = score + config_data["priority"]
                            
                            if total_score > best_score:
                                best_score = total_score
                                best_result = validated
                                best_method = f"{img_name}_{config_data['lang']}"
                
                except Exception as e:
                    logging.warning(f"Erreur OCR {img_name}/{config_data['lang']}: {e}")
                    continue
        
        # 5. Debug complet
        logging.info(f"🔍 DEBUG Cam {camera_id} - H.264 corruption: {processed_data['corruption_detected']}")
        for result in debug_results[:8]:  # Limiter pour éviter spam
            logging.info(f"    {result}")
        
        # 6. Résultat final avec seuil plus bas pour images corrompues
        min_score = 40 if processed_data['corruption_detected'] else 50
        
        if best_result and best_score >= min_score:
            logging.info(f"✅ OCR Cam {camera_id}: '{best_result}' (score: {best_score}, method: {best_method})")
            
            # Sauvegarder dans Redis
            r.set(f"detected_plate_{camera_id}", best_result, ex=30)
            
            # 🚨 NOUVEAU: Vérification et notification avec service unifié
            detection, is_authorized = check_and_save_detection(
                best_result, camera_id, best_score, image_bytes=image_bytes
            )
            
            return {
                "success": True,
                "license_plate": best_result,
                "confidence_score": best_score,
                "h264_corruption": processed_data['corruption_detected'],
                "detection_method": best_method,
                "is_authorized": is_authorized,
                "detection_id": detection.id if detection else None
            }
        
        logging.error(f"❌ Échec OCR Cam {camera_id} - Score: {best_score}, H.264: {processed_data['corruption_detected']}")
        return {"success": False, "error": f"OCR failed (score: {best_score}, H.264: {processed_data['corruption_detected']})"}
        
    except Exception as e:
        logging.error(f"❌ Erreur critique OCR Cam {camera_id}: {e}")
        return {"success": False, "error": str(e)}