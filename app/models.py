from django.db import models
from django.contrib.gis.db import models

class Lieu(models.Model):
    name = models.CharField(max_length=100)
    polygon = models.PolygonField()

    def __str__(self):
        return self.name
    

class Camera(models.Model):
    name = models.CharField(max_length=100)
    url = models.URLField()
    location = models.PointField()

    def __str__(self):
        return self.name