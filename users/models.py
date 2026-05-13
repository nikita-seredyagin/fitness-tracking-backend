from django.contrib.auth.models import AbstractUser
from django.db import models


class CustomUser(AbstractUser):
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(
        max_length=6,
        choices=[('male', 'Male'), ('female', 'Female')],
        blank=True, null=True,
    )
