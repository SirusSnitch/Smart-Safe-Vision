from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = 'ADMIN', 'Administrateur'
        SUPERVISEUR = 'SUPER', 'Superviseur'
        AGENT = 'AGENT', 'Agent'

    username = models.CharField(max_length=150, blank=True, null=True, unique=True)
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.AGENT)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(unique=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []  # On garde 'username' mais ce n'est plus le login principal

    def __str__(self):
        return f"{self.get_full_name()} ({self.role})"






