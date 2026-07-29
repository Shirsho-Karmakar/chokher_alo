from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = DjangoUserAdmin.fieldsets + (
        (
            "Contact and verification",
            {
                "fields": (
                    "phone_number",
                    "email_verified",
                    "phone_verified",
                )
            },
        ),
    )

    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        (
            "Contact information",
            {
                "fields": (
                    "email",
                    "phone_number",
                )
            },
        ),
    )

    list_display = (
        "username",
        "email",
        "phone_number",
        "email_verified",
        "phone_verified",
        "is_staff",
        "is_active",
    )

    search_fields = (
        "username",
        "email",
        "phone_number",
        "first_name",
        "last_name",
    )
