from io import StringIO

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase

from apps.accounts.roles import (
    ACCOUNTS_MANAGER,
    STAFF_GROUP_NAMES,
)


class StaffRoleCommandTests(TestCase):
    def test_command_creates_all_staff_groups(self):
        call_command(
            "sync_staff_roles",
            stdout=StringIO(),
        )

        group_names = set(
            Group.objects.filter(
                name__in=STAFF_GROUP_NAMES
            ).values_list("name", flat=True)
        )

        self.assertEqual(group_names, set(STAFF_GROUP_NAMES))

    def test_command_is_idempotent(self):
        call_command(
            "sync_staff_roles",
            stdout=StringIO(),
        )
        call_command(
            "sync_staff_roles",
            stdout=StringIO(),
        )

        self.assertEqual(
            Group.objects.filter(
                name__in=STAFF_GROUP_NAMES
            ).count(),
            len(STAFF_GROUP_NAMES),
        )

    def test_accounts_manager_receives_expected_permissions(self):
        call_command(
            "sync_staff_roles",
            stdout=StringIO(),
        )

        group = Group.objects.get(name=ACCOUNTS_MANAGER)

        permissions = {
            (
                permission.content_type.app_label,
                permission.codename,
            )
            for permission in group.permissions.select_related(
                "content_type"
            )
        }

        expected_permissions = {
            ("accounts", "view_user"),
            ("wholesale", "view_wholesaleaccount"),
            ("wholesale", "change_wholesaleaccount"),
            ("wholesale", "review_wholesale_account"),
        }

        self.assertTrue(
            expected_permissions.issubset(permissions)
        )
