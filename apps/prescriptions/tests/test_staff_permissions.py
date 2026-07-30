from io import StringIO

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase

from apps.accounts.roles import PRESCRIPTION_REVIEWER


class PrescriptionStaffPermissionTests(TestCase):
    def test_reviewer_receives_prescription_permissions(self):
        call_command(
            "sync_staff_roles",
            stdout=StringIO(),
        )

        group = Group.objects.get(
            name=PRESCRIPTION_REVIEWER
        )

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
            ("prescriptions", "view_prescription"),
            ("prescriptions", "change_prescription"),
            ("prescriptions", "review_prescription"),
            ("prescriptions", "view_prescriptioneyevalue"),
            ("prescriptions", "add_prescriptioneyevalue"),
            ("prescriptions", "change_prescriptioneyevalue"),
        }

        self.assertTrue(expected.issubset(permissions))
