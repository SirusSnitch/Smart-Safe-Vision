from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator, MinLengthValidator
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = 'ADMIN', 'Administrateur'
        SUPERVISEUR = 'SUPER', 'Superviseur'
        AGENT = 'AGENT', 'Agent'

    username = None  # On désactive le username par défaut

    cin = models.CharField(max_length=8,unique=True,validators=[
        RegexValidator(regex='^[0-9]{8}$',message='Le CIN doit contenir exactement 8 chiffres.',code='invalid_cin'), MinLengthValidator(8) ])

    email = models.EmailField(unique=True)
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.AGENT)
    phone = models.CharField(max_length=20, blank=True)
    lieu = models.ForeignKey('gismap.Lieu',on_delete=models.SET_NULL,null=True,blank=True, verbose_name="Secteur d'affectation")


    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['cin']  # On garde 'username' mais ce n'est plus le login principal

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}"

 # def __str__(self):
   #     return f"{self.get_full_name()} ({self.role})






