from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction

from apps.accounts.otp.exceptions import InvalidPhoneNumber
from apps.accounts.otp.phone import normalize_indian_phone_number

from .constants import IndianState
from .validators import normalize_indian_pin_code


class Address(models.Model):
    """
    A reusable customer address.

    An order will later copy these values into an immutable address snapshot,
    so editing this record will not alter previous orders or invoices.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="addresses",
    )

    label = models.CharField(
        max_length=50,
        blank=True,
        help_text="Optional label such as Home, Office, or Shop.",
    )
    recipient_name = models.CharField(max_length=150)
    phone_number = models.CharField(max_length=13)

    address_line_1 = models.CharField(max_length=255)
    address_line_2 = models.CharField(
        max_length=255,
        blank=True,
    )
    landmark = models.CharField(
        max_length=150,
        blank=True,
    )

    city = models.CharField(max_length=100)
    district = models.CharField(max_length=100)
    state = models.CharField(
        max_length=2,
        choices=IndianState.choices,
    )
    postal_code = models.CharField(
        max_length=6,
        db_index=True,
    )

    is_default_delivery = models.BooleanField(default=False)
    is_default_billing = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_default_delivery", "-updated_at"]
        indexes = [
            models.Index(
                fields=["user", "is_active"],
                name="addr_user_active_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(is_default_delivery=True),
                name="uniq_user_default_delivery",
            ),
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(is_default_billing=True),
                name="uniq_user_default_billing",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(is_default_delivery=False)
                    | models.Q(is_active=True)
                ),
                name="addr_delivery_default_active",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(is_default_billing=False)
                    | models.Q(is_active=True)
                ),
                name="addr_billing_default_active",
            ),
        ]

    def clean(self):
        super().clean()

        try:
            self.phone_number = normalize_indian_phone_number(
                self.phone_number
            )
        except InvalidPhoneNumber as exc:
            raise ValidationError(
                {"phone_number": str(exc)}
            ) from exc

        try:
            self.postal_code = normalize_indian_pin_code(
                self.postal_code
            )
        except ValidationError as exc:
            raise ValidationError(
                {"postal_code": exc.messages}
            ) from exc

        self.label = self.label.strip()
        self.recipient_name = self.recipient_name.strip()
        self.address_line_1 = self.address_line_1.strip()
        self.address_line_2 = self.address_line_2.strip()
        self.landmark = self.landmark.strip()
        self.city = self.city.strip()
        self.district = self.district.strip()

        errors = {}

        if not self.is_active and self.is_default_delivery:
            errors["is_default_delivery"] = (
                "An inactive address cannot be the default "
                "delivery address."
            )

        if not self.is_active and self.is_default_billing:
            errors["is_default_billing"] = (
                "An inactive address cannot be the default "
                "billing address."
            )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        # Model.save() does not call full_clean() automatically, so this model
        # validates itself before programmatic saves as well as admin saves.
        self.full_clean(validate_constraints=False)

        with transaction.atomic():
            if self.is_default_delivery:
                (
                    Address.objects
                    .filter(
                        user_id=self.user_id,
                        is_default_delivery=True,
                    )
                    .exclude(pk=self.pk)
                    .update(is_default_delivery=False)
                )

            if self.is_default_billing:
                (
                    Address.objects
                    .filter(
                        user_id=self.user_id,
                        is_default_billing=True,
                    )
                    .exclude(pk=self.pk)
                    .update(is_default_billing=False)
                )

            return super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.recipient_name} — "
            f"{self.city}, {self.postal_code}"
        )


class ServiceablePincode(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Delivery available"
        INACTIVE = "inactive", "Delivery unavailable"
        COMING_SOON = "coming_soon", "Coming soon"

    postal_code = models.CharField(
        max_length=6,
        unique=True,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.INACTIVE,
        db_index=True,
    )

    state = models.CharField(
        max_length=2,
        choices=IndianState.choices,
    )
    city = models.CharField(
        max_length=100,
        blank=True,
    )
    district = models.CharField(
        max_length=100,
        blank=True,
    )

    internal_notes = models.TextField(
        blank=True,
        help_text="Visible only to authorized staff.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["postal_code"]
        verbose_name = "Serviceable PIN code"
        verbose_name_plural = "Serviceable PIN codes"

    def clean(self):
        super().clean()

        try:
            self.postal_code = normalize_indian_pin_code(
                self.postal_code
            )
        except ValidationError as exc:
            raise ValidationError(
                {"postal_code": exc.messages}
            ) from exc

        self.city = self.city.strip()
        self.district = self.district.strip()

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def delivery_available(self) -> bool:
        return self.status == self.Status.ACTIVE

    def __str__(self):
        return f"{self.postal_code} — {self.get_status_display()}"
