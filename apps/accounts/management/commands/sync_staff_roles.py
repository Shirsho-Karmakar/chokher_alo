from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.roles import (
    STAFF_GROUP_NAMES,
    STAFF_GROUP_PERMISSIONS,
)


class Command(BaseCommand):
    help = "Create the standard staff groups and assign their permissions."

    @transaction.atomic
    def handle(self, *args, **options):
        for group_name in STAFF_GROUP_NAMES:
            group, created = Group.objects.get_or_create(name=group_name)

            permission_keys = STAFF_GROUP_PERMISSIONS[group_name]
            permissions = []

            for app_label, codename in permission_keys:
                try:
                    permission = Permission.objects.get(
                        content_type__app_label=app_label,
                        codename=codename,
                    )
                except Permission.DoesNotExist as exc:
                    raise CommandError(
                        "Required permission does not exist: "
                        f"{app_label}.{codename}. "
                        "Run migrations before syncing staff roles."
                    ) from exc

                permissions.append(permission)

            if permissions:
                # Add configured permissions without removing permissions
                # that may be introduced by later backend modules.
                group.permissions.add(*permissions)

            action = "Created" if created else "Updated"
            self.stdout.write(f"{action}: {group_name}")

        self.stdout.write(
            self.style.SUCCESS("Staff roles synchronized successfully.")
        )
