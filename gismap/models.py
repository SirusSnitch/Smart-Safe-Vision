from django.contrib.gis.db import models
from django.utils import timezone


class Lieu(models.Model):
    name = models.CharField(max_length=100)
    polygon = models.PolygonField()
    area = models.FloatField(null=True, blank=True)  # Ajouté pour stocker l'aire

    def __str__(self):
        return self.name


class Camera(models.Model):
    name = models.CharField(max_length=1000)
    rtsp_url = models.URLField()
    hls_url = models.URLField()
    location = models.PointField()
    department = models.ForeignKey(
        Lieu, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='cameras'
    )

    def __str__(self):
        return self.name


class MatriculeAutorise(models.Model):  # ✅ Corrigé : nom de classe sans accent
    numero = models.CharField(max_length=20, unique=True)
    lieu = models.ForeignKey(
        Lieu, on_delete=models.CASCADE,
        related_name='matricules_autorises',
        null=True, blank=True
    )

    def __str__(self):
        return self.numero

class DetectionMatricule(models.Model):
    numero = models.CharField(max_length=255)
    image = models.BinaryField(null=True, blank=True)  # Stocker l’image directement
    timestamp = models.DateTimeField(default=timezone.now)
    est_autorise = models.BooleanField(default=False)
    camera = models.ForeignKey('Camera', on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.numero} - {self.camera.name} - {self.timestamp}"

# Dans votre models.py, remplacez le modèle Notifications par ceci :

class Notifications(models.Model):
    ALERT_TYPES = [
        ('unauthorized_plate', 'Plaque non autorisée'),
        ('authorized_plate', 'Plaque autorisée'),
    ]

    alert_type = models.CharField(max_length=50, choices=ALERT_TYPES)
    matricule = models.CharField(max_length=20)
    camera = models.CharField(max_length=100)
    location = models.CharField(max_length=100, blank=True, null=True)
    timestamp = models.DateTimeField(default=timezone.now)
    confidence = models.FloatField(default=0)
    message = models.TextField()
    
    # 🆕 CHANGEMENT: Image stockée directement en base de données
    image_data = models.BinaryField(blank=True, null=True)  # Données binaires de l'image
    image_type = models.CharField(max_length=10, default='jpeg', blank=True)  # Type d'image (jpeg, png, etc.)

    def __str__(self):
        return f"{self.matricule} - {self.alert_type} - {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
    
    def get_image_base64(self):
        """Retourne l'image en base64 pour affichage dans le template"""
        if self.image_data:
            import base64
            return base64.b64encode(self.image_data).decode('utf-8')
        return None
    
    def set_image_from_bytes(self, image_bytes, image_type='jpeg'):
        """Stocke les bytes d'image directement"""
        self.image_data = image_bytes
        self.image_type = image_type