from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.wholesale.models import WholesaleAccount


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
