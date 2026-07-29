from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.wholesale.models import (
    WholesaleAccount,
    WholesaleVerificationContact,
)


User = get_user_model()


class WholesaleStatusViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="wholesale-status-user",
            phone_number="+919876543210",
            phone_verified=True,
        )
        self.account = WholesaleAccount.objects.create(
            user=self.user,
        )
        self.client.force_login(self.user)

    def test_status_includes_active_verification_contacts(self):
        WholesaleVerificationContact.objects.create(
            label="Primary Support",
            phone_number="9876543211",
            is_active=True,
            display_order=1,
        )
        WholesaleVerificationContact.objects.create(
            label="Secondary Support",
            phone_number="9876543212",
            is_active=True,
            display_order=2,
        )
        WholesaleVerificationContact.objects.create(
            label="Unavailable",
            phone_number="9876543213",
            is_active=False,
            display_order=0,
        )

        response = self.client.get(
            reverse("wholesale:status")
        )

        self.assertEqual(response.status_code, 200)

        data = response.json()

        self.assertEqual(
            data["reference_id"],
            self.account.reference_id,
        )
        self.assertEqual(
            len(data["verification"]["contacts"]),
            2,
        )
        self.assertEqual(
            data["verification"]["contacts"][0],
            {
                "label": "Primary Support",
                "phone_number": "+919876543211",
            },
        )

    def test_status_works_when_no_contacts_are_active(self):
        response = self.client.get(
            reverse("wholesale:status")
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["verification"]["contacts"],
            [],
        )

    def test_status_requires_login(self):
        self.client.logout()

        response = self.client.get(
            reverse("wholesale:status")
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            response.url.startswith("/wholesale/login/?next=")
        )
