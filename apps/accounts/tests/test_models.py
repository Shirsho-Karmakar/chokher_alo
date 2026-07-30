from django.contrib.auth import get_user_model
from django.test import TestCase


User = get_user_model()


class UserModelTests(TestCase):
    def test_multiple_phone_users_can_have_no_email(self):
        first_user = User.objects.create_user(
            username="first-phone-user",
            phone_number="+919876543210",
            phone_verified=True,
        )
        second_user = User.objects.create_user(
            username="second-phone-user",
            phone_number="+919876543211",
            phone_verified=True,
        )

        first_user.refresh_from_db()
        second_user.refresh_from_db()

        self.assertIsNone(first_user.email)
        self.assertIsNone(second_user.email)
        self.assertEqual(User.objects.count(), 2)

    def test_explicit_blank_email_is_stored_as_null(self):
        user = User.objects.create_user(
            username="blank-email-user",
            email="",
        )

        user.refresh_from_db()

        self.assertIsNone(user.email)
