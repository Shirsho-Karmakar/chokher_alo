from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.locations.constants import IndianState
from apps.locations.models import Address
from apps.wholesale.models import WholesaleAccount


User = get_user_model()


class WholesaleCheckoutReadinessTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="checkout-ready-user",
            phone_number="+919876543210",
            phone_verified=True,
        )

    def create_billing_address(self):
        return Address.objects.create(
            user=self.user,
            recipient_name="Business Recipient",
            phone_number="9876543210",
            address_line_1="10 Wholesale Road",
            city="Kolkata",
            district="Kolkata",
            state=IndianState.WEST_BENGAL,
            postal_code="700001",
            is_default_billing=True,
        )

    def test_gstin_is_optional_for_checkout_readiness(self):
        account = WholesaleAccount.objects.create(
            user=self.user,
            status=WholesaleAccount.Status.APPROVED,
            business_name="Example Optical Store",
            contact_person_name="Example Contact",
            invoice_email="invoice@example.com",
            gstin="",
        )
        self.create_billing_address()

        self.assertEqual(
            account.missing_checkout_details(),
            (),
        )
        self.assertTrue(account.business_details_complete)
        self.assertTrue(account.is_checkout_ready)

    def test_missing_business_details_are_reported(self):
        account = WholesaleAccount.objects.create(
            user=self.user,
            status=WholesaleAccount.Status.APPROVED,
        )

        self.assertEqual(
            set(account.missing_checkout_details()),
            {
                "business_name",
                "contact_person_name",
                "invoice_email",
                "billing_address",
            },
        )
        self.assertFalse(account.is_checkout_ready)

    def test_unapproved_account_is_not_checkout_ready(self):
        account = WholesaleAccount.objects.create(
            user=self.user,
            status=WholesaleAccount.Status.UNVERIFIED,
            business_name="Example Optical Store",
            contact_person_name="Example Contact",
            invoice_email="invoice@example.com",
        )
        self.create_billing_address()

        self.assertTrue(account.business_details_complete)
        self.assertFalse(account.is_checkout_ready)
