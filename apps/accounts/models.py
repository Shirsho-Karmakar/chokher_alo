from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    Shared identity for retail customers, wholesale users, and staff.

    Retail users will later authenticate through Google or phone OTP.
    Wholesale users will authenticate through phone OTP.
    """

    email = models.EmailField(
        unique=True,
        null=True,
        blank=True,
    )
    phone_number = models.CharField(
        max_length=16,
        unique=True,
        null=True,
        blank=True,
        help_text="Phone number in international format, such as +919876543210.",
    )
    email_verified = models.BooleanField(default=False)
    phone_verified = models.BooleanField(default=False)

    def clean(self):
        super().clean()

        # PostgreSQL permits multiple NULL values in unique columns, but not
        # multiple empty strings. Normalize blank optional identifiers to NULL.
        self.email = self.email or None
        self.phone_number = self.phone_number or None

    def __str__(self):
        return self.email or self.phone_number or self.username
