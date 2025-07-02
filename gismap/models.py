from django.contrib.gis.db import models



class Lieu(models.Model):
    name = models.CharField(max_length=100)
    polygon = models.PolygonField()
    area = models.FloatField(null=True, blank=True)  # Ajouté pour stocker l'aire
    
    def __str__(self):
        return self.name
    

class Camera(models.Model):
    name = models.CharField(max_length=100)
    url = models.URLField()
    location = models.PointField()
    department = models.ForeignKey(Lieu, on_delete=models.SET_NULL, null=True, blank=True, related_name='cameras')

    def __str__(self):
        return self.name