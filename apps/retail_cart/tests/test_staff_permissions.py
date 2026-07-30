from io import StringIO

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase

from apps.accounts.roles import ORDER_MANAGER


class RetailCartStaffPermissionTests(TestCase):
    def test_order_manager_can_view_retail_carts(self):
        call_command(
            "sync_staff_roles",
            stdout=StringIO(),
        )

        group = Group.objects.get(name=ORDER_MANAGER)

        permissions = {
            (
                permission.content_type.app_label,
                permission.codename,
            )
            for permission in group.permissions.select_related(
                "content_type"
            )
        }

        expected = {
            ("retail_cart", "view_retailcart"),
            ("retail_cart", "view_retailcartitem"),
            (
                "retail_cart",
                "view_poweredeyewearconfiguration",
            ),
            (
                "retail_cart",
                "view_customerownedframeservice",
            ),
        }

        self.assertTrue(expected.issubset(permissions))
