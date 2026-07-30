from io import StringIO

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase

from apps.accounts.roles import CATALOGUE_MANAGER


class CatalogueStaffPermissionTests(TestCase):
    def test_catalogue_manager_receives_catalogue_permissions(self):
        call_command(
            "sync_staff_roles",
            stdout=StringIO(),
        )

        group = Group.objects.get(name=CATALOGUE_MANAGER)

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
            ("catalog", "view_productdesign"),
            ("catalog", "add_productdesign"),
            ("catalog", "change_productdesign"),
            ("catalog", "view_productvariant"),
            ("catalog", "add_productvariant"),
            ("catalog", "change_productvariant"),
            ("catalog", "view_productoffer"),
            ("catalog", "add_productoffer"),
            ("catalog", "change_productoffer"),
            ("catalog", "view_productimage"),
            ("catalog", "add_productimage"),
            ("catalog", "change_productimage"),
        }

        self.assertTrue(
            expected_permissions.issubset(permissions)
        )
