from django.db import models
from django.contrib.gis.db import models


class Lieu(models.Model):
    name = models.CharField(max_length=100)
    polygon = models.PolygonField()
    area = models.FloatField(null=True, blank=True)  # Ajouté pour stocker l'aire
    
    def __str__(self):
        return self.name