from django.contrib.gis.db import models
from django.utils import timezone


class Lieu(models.Model):
    name = models.CharField(max_length=100)
    polygon = models.PolygonField()
    area = models.FloatField(null=True, blank=True)  # Ajouté pour stocker l'aire

    def __str__(self):
        return self.name


class Camera(models.Model):
    name = models.CharField(max_length=100)
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
    image = models.ImageField(upload_to='matricules/', null=True, blank=True)
    timestamp = models.DateTimeField(default=timezone.now)
    est_autorise = models.BooleanField(default=False)
    camera = models.ForeignKey('Camera', on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.numero} - {self.camera.name} - {self.timestamp}"
