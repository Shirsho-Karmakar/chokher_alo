import uuid

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

    def _normalize_optional_identifiers(self):
        """
        Store missing unique identifiers as NULL rather than empty strings.

        PostgreSQL permits multiple NULL values in unique columns, but only
        one empty string.
        """
        self.email = self.email.strip() if self.email else None
        self.phone_number = (
            self.phone_number.strip()
            if self.phone_number
            else None
        )

    def clean(self):
        super().clean()
        self._normalize_optional_identifiers()

    def save(self, *args, **kwargs):
        # Model.save() and UserManager.create_user() do not automatically call
        # full_clean(), so normalization must also happen at the save boundary.
        self._normalize_optional_identifiers()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.email or self.phone_number or self.username


class PhoneOTPChallenge(models.Model):
    class Purpose(models.TextChoices):
        RETAIL_LOGIN = "retail_login", "Retail login"
        WHOLESALE_LOGIN = "wholesale_login", "Wholesale login"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    phone_number = models.CharField(
        max_length=13,
        db_index=True,
    )
    purpose = models.CharField(
        max_length=30,
        choices=Purpose.choices,
    )

    # The raw OTP is never stored.
    code_digest = models.CharField(
        max_length=64,
        editable=False,
    )

    attempt_count = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=5)

    provider_name = models.CharField(max_length=100)
    provider_message_id = models.CharField(
        max_length=255,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)
    invalidated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["phone_number", "purpose", "-created_at"],
                name="otp_phone_purpose_created",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    attempt_count__lte=models.F("max_attempts")
                ),
                name="otp_attempts_not_above_max",
            ),
        ]

    def __str__(self):
        return f"{self.phone_number} — {self.get_purpose_display()}"


class PhoneOTPThrottle(models.Model):
    """
    Per-phone send counters used to enforce resend and hourly limits.

    The service locks this row while issuing an OTP.
    """

    phone_number = models.CharField(max_length=13)
    purpose = models.CharField(
        max_length=30,
        choices=PhoneOTPChallenge.Purpose.choices,
    )

    window_started_at = models.DateTimeField(null=True, blank=True)
    sends_in_window = models.PositiveSmallIntegerField(default=0)
    last_sent_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["phone_number", "purpose"],
                name="unique_otp_throttle_phone_purpose",
            ),
        ]

    def __str__(self):
        return f"{self.phone_number} — {self.purpose}"
