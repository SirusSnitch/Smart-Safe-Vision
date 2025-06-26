from django.db import models
from django.contrib.gis.db import models


class Commentaire(models.Model):
    auteur = models.CharField(max_length=100)
    contenu = models.TextField()
    date_creation = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.auteur} - {self.date_creation}"


class Lieu(models.Model):
    nom = models.CharField(max_length=100)
    position = models.PointField()  # champ géospatial Point

    def __str__(self):
        return self.nom