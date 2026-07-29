from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.wholesale.models import (
    WholesaleAccount,
    WholesaleVerificationContact,
)


User = get_user_model()


class WholesaleAccountModelTests(TestCase):
    def test_account_gets_reference_id_and_unverified_status(self):
        user = User.objects.create_user(
            username="wholesale-test-user",
            phone_number="+919876543210",
            phone_verified=True,
        )

        account = WholesaleAccount.objects.create(user=user)

        self.assertTrue(account.reference_id.startswith("CHA-WH-"))
        self.assertEqual(
            account.status,
            WholesaleAccount.Status.UNVERIFIED,
        )
        self.assertEqual(user.wholesale_account, account)


class WholesaleVerificationContactModelTests(TestCase):
    def test_phone_number_is_normalized_before_saving(self):
        contact = WholesaleVerificationContact.objects.create(
            label="Wholesale Support",
            phone_number="9876543210",
        )

        self.assertEqual(
            contact.phone_number,
            "+919876543210",
        )

    def test_invalid_phone_number_is_rejected(self):
        contact = WholesaleVerificationContact(
            phone_number="12345",
        )

        with self.assertRaises(ValidationError):
            contact.save()
