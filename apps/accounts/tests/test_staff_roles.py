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


class LocationStaffPermissionTests(TestCase):
    def setUp(self):
        call_command(
            "sync_staff_roles",
            stdout=StringIO(),
        )

    def permission_keys_for(self, group_name):
        group = Group.objects.get(name=group_name)

        return {
            (
                permission.content_type.app_label,
                permission.codename,
            )
            for permission in group.permissions.select_related(
                "content_type"
            )
        }

    def test_accounts_manager_can_manage_customer_addresses(self):
        permissions = self.permission_keys_for(
            ACCOUNTS_MANAGER
        )

        expected = {
            ("locations", "view_address"),
            ("locations", "add_address"),
            ("locations", "change_address"),
        }

        self.assertTrue(expected.issubset(permissions))

    def test_order_manager_can_manage_serviceable_pin_codes(self):
        from apps.accounts.roles import ORDER_MANAGER

        permissions = self.permission_keys_for(
            ORDER_MANAGER
        )

        expected = {
            ("locations", "view_address"),
            ("locations", "view_serviceablepincode"),
            ("locations", "add_serviceablepincode"),
            ("locations", "change_serviceablepincode"),
        }

        self.assertTrue(expected.issubset(permissions))
