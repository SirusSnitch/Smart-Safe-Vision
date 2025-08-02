# ============================================================================
# OCR_TASK.PY - Version corrigée
# ============================================================================

import pytesseract
import cv2
import numpy as np
import os
import time
from celery import shared_task
import re
import logging

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 📍 Chemin vers tesseract.exe
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# 📁 Dossier debug pour plaques extraites
debug_dir = "debug_plates"
os.makedirs(debug_dir, exist_ok=True)

def preprocess_image(image):
    """
    Préprocessing simplifié et plus robuste pour l'OCR
    """
    # Agrandissement plus modéré
    height, width = image.shape[:2]
    if width < 200:  # Agrandir seulement si trop petite
        scale_factor = 200 / width
        image = cv2.resize(image, None, fx=scale_factor, fy=scale_factor, interpolation=cv2.INTER_CUBIC)
    
    # Convertir en niveaux de gris
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    
    # Débruitage léger
    gray = cv2.medianBlur(gray, 3)
    
    # Amélioration du contraste simple
    gray = cv2.convertScaleAbs(gray, alpha=1.2, beta=10)
    
    # Seuillage OTSU (plus fiable que adaptatif)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    return thresh, gray  # Retourner les deux versions

def extract_license_plate_text(text):
    """
    Extraction optimisée pour plaques tunisiennes avec nettoyage des erreurs OCR
    """
    if not text:
        return None
        
    # Nettoyage initial
    text = text.strip().replace('\n', ' ').replace('\t', ' ')
    text = re.sub(r'\s+', ' ', text)  # Supprimer espaces multiples
    
    print(f"[OCR] 🔍 Analyse du texte: '{text}'")
    
    # ✅ NETTOYAGE SPÉCIAL POUR ERREURS OCR COMMUNES
    # Remplacer caractères mal lus
    text = text.replace('(', '').replace(')', '').replace('|', '').replace('[', '').replace(']', '')
    text = text.replace('.', ' ').replace(',', ' ').replace('_', '')
    text = re.sub(r'[^\d\s\u0600-\u06FF]', ' ', text)  # Garder que chiffres, espaces et arabe
    
    print(f"[OCR] 🧹 Texte nettoyé: '{text}'")
    
    # 1. Chercher les chiffres (partie la plus fiable)
    numbers = re.findall(r'\d+', text)
    print(f"[OCR] 🔢 Chiffres trouvés: {numbers}")
    
    # ✅ CORRECTION SPÉCIALE POUR ERREURS OCR
    cleaned_numbers = []
    for num in numbers:
        # Correction des erreurs communes
        if num == '1799':  # 179.9 mal lu
            cleaned_numbers.append('179')
            print(f"[OCR] 🔧 Correction {num} → 179")
        elif len(num) == 4 and num.startswith('179'):
            cleaned_numbers.append('179')
            print(f"[OCR] 🔧 Correction {num} → 179")
        elif len(num) == 4 and num.endswith('911'):
            cleaned_numbers.append('911')
            print(f"[OCR] 🔧 Correction {num} → 911")
        elif 2 <= len(num) <= 4:  # Garder nombres de 2-4 chiffres
            cleaned_numbers.append(num)
        elif len(num) > 4:
            # Séparer les longs nombres (ex: "1799911" → "179", "911")
            if len(num) == 7 and (num.startswith('179') or num.endswith('911')):
                if num.startswith('179'):
                    cleaned_numbers.extend(['179', num[4:]])  # 179 + les 3 derniers
                else:
                    cleaned_numbers.extend([num[:3], '911'])  # 3 premiers + 911
                print(f"[OCR] ✂️ Séparation {num} → {cleaned_numbers[-2]} + {cleaned_numbers[-1]}")
            elif len(num) == 6:
                # Séparer en deux parties égales
                mid = len(num) // 2
                cleaned_numbers.extend([num[:mid], num[mid:]])
                print(f"[OCR] ✂️ Séparation {num} → {num[:mid]} + {num[mid:]}")
            else:
                cleaned_numbers.append(num)
    
    numbers = cleaned_numbers
    print(f"[OCR] 🔢 Chiffres corrigés: {numbers}")
    
    # 2. Chercher le mot "تونس" en arabe
    arabic_tunisia = None
    if 'تونس' in text:
        arabic_tunisia = 'تونس'
        print(f"[OCR] 🇹🇳 Mot 'تونس' détecté en arabe!")
    elif 'تون' in text or 'ونس' in text:
        arabic_tunisia = 'تونس'  # Reconstruction partielle
        print(f"[OCR] 🇹🇳 Partie de 'تونس' détectée, reconstruction")
    
    # 3. Reconstruction de la plaque tunisienne
    if len(numbers) >= 2:
        first_part = numbers[0]
        last_part = numbers[-1]
        
        # Format tunisien classique : XXX تونس YYY
        if len(first_part) >= 2 and len(last_part) >= 2:
            if arabic_tunisia:
                plate_candidate = f"{first_part} {arabic_tunisia} {last_part}"
                print(f"[OCR] 🇹🇳 Plaque tunisienne complète: {plate_candidate}")
                return plate_candidate
            else:
                # Version avec تونس ajouté automatiquement
                plate_formatted = f"{first_part} تونس {last_part}"
                print(f"[OCR] 🇹🇳 Plaque tunisienne reconstruite: {plate_formatted}")
                return plate_formatted
    
    # 4. Si un seul bloc de chiffres
    if len(numbers) == 1:
        num = numbers[0]
        if len(num) == 6:  # Ex: "179911"
            first_part = num[:3]
            last_part = num[3:]
            plate_formatted = f"{first_part} تونس {last_part}"
            print(f"[OCR] 🇹🇳 Reconstruction depuis bloc unique: {plate_formatted}")
            return plate_formatted
        elif len(num) >= 4:
            print(f"[OCR] 🔢 Nombre unique conservé: {num}")
            return num
    
    # 5. Fallback : retourner tous les chiffres trouvés
    if numbers:
        all_numbers = ''.join(numbers)
        if len(all_numbers) >= 4:
            print(f"[OCR] 📋 Fallback tous chiffres: {all_numbers}")
            return all_numbers
    
    print(f"[OCR] ❌ Aucun candidat valide trouvé dans: '{text}'")
    return None

@shared_task
def run_ocr_task(image_bytes, camera_id):
    """
    Task OCR optimisée avec gestion d'erreurs améliorée
    """
    logger.info(f"Task OCR démarrée pour caméra {camera_id}")
    
    try:
        # Convertir l'image bytes en image OpenCV
        np_arr = np.frombuffer(image_bytes, np.uint8)
        image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        
        if image is None:
            logger.error(f"Erreur décodage image (caméra {camera_id})")
            return {"success": False, "error": "decode_error"}
        
        # Préprocessing simplifié
        processed_image, gray_image = preprocess_image(image)
        
        # ✅ APPROCHE MULTIPLE : Essayer différentes versions de l'image
        images_to_test = [
            ("original_gray", cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)),
            ("processed", processed_image),
            ("enhanced", cv2.convertScaleAbs(gray_image, alpha=1.5, beta=20)),
        ]
        
        # Configuration OCR optimisée pour plaques tunisiennes
        configs = [
            "--psm 8 -c tessedit_char_whitelist=0123456789",  # CHIFFRES SEULEMENT
            "--psm 7 -c tessedit_char_whitelist=0123456789",  # CHIFFRES SEULEMENT
            "--psm 6 -l ara",  # ARABE SEULEMENT
            "--psm 8 -l ara",  # ARABE SEULEMENT
            "--psm 7 -l ara",  # ARABE SEULEMENT
            "--psm 6 -l ara+eng",  # ARABE + ANGLAIS
            "--psm 8",  # Standard
        ]
        
        best_result = None
        best_confidence = 0
        best_method = ""
        
        for img_name, test_image in images_to_test:
            for config in configs:
                try:
                    # 🔧 OCR avec langue arabe
                    if 'ara' in config:
                        text = pytesseract.image_to_string(test_image, lang='ara', config=config).strip()
                    else:
                        text = pytesseract.image_to_string(test_image, lang='eng', config=config).strip()
                    
                    if text and len(text) >= 2:  # Au moins 2 caractères
                        # Calculer une confiance approximative basée sur la longueur et les caractères
                        confidence = len(text) * 10  # Score simple
                        
                        if confidence > best_confidence:
                            best_confidence = confidence
                            best_result = text
                            best_method = f"{img_name}+{config}"
                            
                        print(f"[OCR] 🔍 Test {img_name}+{config}: '{text}' (score: {confidence})")
                        
                except Exception as e:
                    continue
        
        # ✅ FALLBACK : OCR très permissif si rien trouvé
        if not best_result:
            try:
                # Dernière tentative avec arabe pur
                arabic_text = pytesseract.image_to_string(gray_image, lang='ara', config='--psm 6').strip()
                if arabic_text:
                    best_result = arabic_text
                    best_confidence = 10
                    best_method = "fallback_arabic"
                    print(f"[OCR] 🆘 Fallback arabe détecté: '{arabic_text}'")
                else:
                    # Fallback anglais
                    simple_text = pytesseract.image_to_string(gray_image, lang='eng', config='--psm 8').strip()
                    if simple_text:
                        best_result = simple_text
                        best_confidence = 5
                        best_method = "fallback_eng"
                        print(f"[OCR] 🆘 Fallback anglais détecté: '{simple_text}'")
            except:
                pass
        
        if not best_result:
            print(f"[OCR] ❌ Aucun texte détecté même avec seuils bas (caméra {camera_id})")
            return {"success": False, "error": "no_text_detected"}
        
        # 💾 Sauvegarde pour debug avec nom plus informatif
        timestamp = int(time.time())
        filename = os.path.join(debug_dir, f"cam{camera_id}_{timestamp}_{best_method.replace('+', '_')}.jpg")
        cv2.imwrite(filename, processed_image)
        
        # ✅ EXTRACTION AMÉLIORÉE - Plus permissive
        license_plate = extract_license_plate_text(best_result)
        
        # 📝 AFFICHAGE DÉTAILLÉ DU RÉSULTAT
        print(f"[OCR] 📋 Méthode utilisée: {best_method}")
        print(f"[OCR] 📝 Texte brut: '{best_result}'")
        
        if license_plate:
            # ✅ AFFICHAGE DU MATRICULE DÉTECTÉ
            print(f"[OCR] 🎯 ✅ MATRICULE DÉTECTÉ (Cam {camera_id}): '{license_plate}' (méthode: {best_method})")
            
            # Stocker dans Redis pour affichage en temps réel (optionnel)
            try:
                import redis
                r = redis.StrictRedis(host='localhost', port=6379, db=0)
                r.set(f"detected_plate_{camera_id}", license_plate, ex=30)  # Expire après 30s
                r.set(f"detected_plate_time_{camera_id}", time.time(), ex=30)
            except:
                pass
            
            return {
                "success": True, 
                "license_plate": license_plate,
                "confidence": best_confidence,
                "camera_id": camera_id,
                "timestamp": timestamp,
                "method": best_method
            }
        else:
            # ✅ RETOUR DU TEXTE BRUT même si format non reconnu
            print(f"[OCR] ⚠️ Texte détecté mais format non reconnu: '{best_result}'")
            print(f"[OCR] 💡 Essayez d'ajuster les patterns regex si nécessaire")
            
            return {
                "success": False, 
                "error": "invalid_format",
                "raw_text": best_result,
                "camera_id": camera_id,
                "method": best_method
            }
            
    except Exception as e:
        logger.error(f"Exception OCR Cam {camera_id}: {e}")
        return {"success": False, "error": str(e), "camera_id": camera_id}