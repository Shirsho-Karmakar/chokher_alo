import uuid
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import (
    FileExtensionValidator,
    MaxValueValidator,
    MinValueValidator,
)
from django.db import models


MAX_PRESCRIPTION_FILE_SIZE = 10 * 1024 * 1024


def validate_prescription_file_size(uploaded_file):
    if uploaded_file.size > MAX_PRESCRIPTION_FILE_SIZE:
        raise ValidationError(
            "Prescription files must not exceed 10 MB."
        )


def prescription_upload_path(instance, filename):
    """
    Store prescription files using randomized names.

    The original filename is deliberately not exposed in the storage path.
    """
    extension = Path(filename).suffix.lower()

    return (
        f"private/prescriptions/"
        f"{instance.user_id}/"
        f"{uuid.uuid4().hex}{extension}"
    )


class Prescription(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending review"
        UNDER_REVIEW = "under_review", "Under review"
        APPROVED = "approved", "Approved"
        CLARIFICATION_REQUIRED = (
            "clarification_required",
            "Clarification required",
        )
        REJECTED = "rejected", "Rejected"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="prescriptions",
    )

    prescription_file = models.FileField(
        upload_to=prescription_upload_path,
        validators=[
            FileExtensionValidator(
                allowed_extensions=[
                    "jpg",
                    "jpeg",
                    "png",
                    "webp",
                    "pdf",
                ]
            ),
            validate_prescription_file_size,
        ],
        help_text=(
            "Upload a clear prescription image or PDF. "
            "Written values are optional."
        ),
    )

    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )

    customer_notes = models.TextField(blank=True)
    admin_notes = models.TextField(
        blank=True,
        help_text="Visible only to authorized staff.",
    )

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_prescriptions",
    )
    reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        permissions = [
            (
                "review_prescription",
                "Can review and approve prescriptions",
            ),
        ]

    def clean(self):
        super().clean()

        self.customer_notes = self.customer_notes.strip()
        self.admin_notes = self.admin_notes.strip()

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def is_approved(self):
        return self.status == self.Status.APPROVED

    def __str__(self):
        return (
            f"Prescription #{self.pk or 'new'} "
            f"for {self.user}"
        )


class PrescriptionEyeValue(models.Model):
    class Eye(models.TextChoices):
        RIGHT = "right", "Right eye"
        LEFT = "left", "Left eye"

    class PrismBase(models.TextChoices):
        UP = "up", "Up"
        DOWN = "down", "Down"
        IN = "in", "In"
        OUT = "out", "Out"

    prescription = models.ForeignKey(
        Prescription,
        on_delete=models.CASCADE,
        related_name="eye_values",
    )
    eye = models.CharField(
        max_length=10,
        choices=Eye.choices,
    )

    sphere = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    cylinder = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    axis = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[
            MinValueValidator(0),
            MaxValueValidator(180),
        ],
    )
    add_power = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )

    distance_pd_mm = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    near_pd_mm = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )

    prism_diopters = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    prism_base = models.CharField(
        max_length=10,
        choices=PrismBase.choices,
        blank=True,
    )

    class Meta:
        ordering = ["prescription", "eye"]
        constraints = [
            models.UniqueConstraint(
                fields=["prescription", "eye"],
                name="uniq_eye_per_prescription",
            ),
        ]

    def clean(self):
        super().clean()

        errors = {}

        if self.axis is not None and self.cylinder is None:
            errors["axis"] = (
                "Cylinder must be entered when an axis is provided."
            )

        if (
            self.prism_diopters is not None
            and not self.prism_base
        ):
            errors["prism_base"] = (
                "Select a prism base when prism power is entered."
            )

        if (
            self.prism_base
            and self.prism_diopters is None
        ):
            errors["prism_diopters"] = (
                "Enter prism power when a prism base is selected."
            )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.get_eye_display()} — "
            f"Prescription #{self.prescription_id}"
        )
