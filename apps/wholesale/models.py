import secrets

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


WHOLESALE_REFERENCE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


def generate_wholesale_reference_id() -> str:
    """
    Generate a readable reference ID for wholesale verification calls.

    Ambiguous characters such as 0, O, 1 and I are excluded.
    The database unique constraint remains the final guarantee of uniqueness.
    """
    random_part = "".join(
        secrets.choice(WHOLESALE_REFERENCE_ALPHABET)
        for _ in range(10)
    )
    return f"CHA-WH-{random_part}"


class WholesaleAccount(models.Model):
    class Status(models.TextChoices):
        UNVERIFIED = "unverified", "Unverified"
        UNDER_REVIEW = "under_review", "Under Review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        SUSPENDED = "suspended", "Suspended"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="wholesale_account",
    )

    reference_id = models.CharField(
        max_length=20,
        unique=True,
        editable=False,
        default=generate_wholesale_reference_id,
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.UNVERIFIED,
        db_index=True,
    )

    # These fields are completed by the business after approval.
    business_name = models.CharField(max_length=255, blank=True)
    contact_person_name = models.CharField(max_length=255, blank=True)
    gstin = models.CharField(max_length=15, blank=True)
    invoice_email = models.EmailField(blank=True)

    internal_notes = models.TextField(
        blank=True,
        help_text="Visible only to authorized staff.",
    )

    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_wholesale_accounts",
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Wholesale account"
        verbose_name_plural = "Wholesale accounts"

    def clean(self):
        super().clean()

        if not self.user_id:
            return

        if not self.user.phone_number:
            raise ValidationError(
                {"user": "A wholesale account requires a phone number."}
            )

        if not self.user.phone_verified:
            raise ValidationError(
                {"user": "The user's phone number must be verified first."}
            )

    def __str__(self) -> str:
        phone_number = self.user.phone_number or "No phone"
        return f"{self.reference_id} — {phone_number}"
