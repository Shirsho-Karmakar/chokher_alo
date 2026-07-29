from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.otp.providers.base import (
    BaseOTPProvider,
    OTPDeliveryResult,
)
from apps.wholesale.models import WholesaleAccount


User = get_user_model()


class ViewRecordingOTPProvider(BaseOTPProvider):
    provider_name = "view-test"
    deliveries = []

    def send(
        self,
        *,
        phone_number: str,
        code: str,
        purpose: str,
    ) -> OTPDeliveryResult:
        self.__class__.deliveries.append(
            {
                "phone_number": phone_number,
                "code": code,
                "purpose": purpose,
            }
        )

        return OTPDeliveryResult(
            message_id=f"view-test-{len(self.deliveries)}"
        )


@override_settings(
    PHONE_OTP_PROVIDER=(
        "apps.accounts.tests.test_phone_auth_views."
        "ViewRecordingOTPProvider"
    ),
    PHONE_OTP_RESEND_SECONDS=0,
)
class PhoneAuthenticationViewTests(TestCase):
    phone_number = "9876543210"

    def setUp(self):
        ViewRecordingOTPProvider.deliveries.clear()

    def request_otp(self, url_name):
        response = self.client.post(
            reverse(url_name),
            {"phone_number": self.phone_number},
        )

        self.assertEqual(response.status_code, 201)

        return (
            response.json()["challenge_id"],
            ViewRecordingOTPProvider.deliveries[-1]["code"],
        )

    def test_retail_otp_creates_user_without_wholesale_account(self):
        challenge_id, code = self.request_otp(
            "accounts:phone_otp_request"
        )

        response = self.client.post(
            reverse("accounts:phone_otp_verify"),
            {
                "challenge_id": challenge_id,
                "code": code,
            },
        )

        self.assertEqual(response.status_code, 200)

        user = User.objects.get(
            phone_number="+919876543210"
        )

        self.assertTrue(user.phone_verified)
        self.assertFalse(user.has_usable_password())
        self.assertFalse(
            WholesaleAccount.objects.filter(user=user).exists()
        )
        self.assertEqual(
            str(user.pk),
            self.client.session["_auth_user_id"],
        )

    def test_wholesale_otp_creates_reference_id(self):
        challenge_id, code = self.request_otp(
            "wholesale:phone_otp_request"
        )

        response = self.client.post(
            reverse("wholesale:phone_otp_verify"),
            {
                "challenge_id": challenge_id,
                "code": code,
            },
        )

        self.assertEqual(response.status_code, 200)

        user = User.objects.get(
            phone_number="+919876543210"
        )
        account = WholesaleAccount.objects.get(user=user)

        self.assertTrue(
            account.reference_id.startswith("CHA-WH-")
        )
        self.assertEqual(
            response.json()["redirect_url"],
            reverse("wholesale:status"),
        )

    def test_retail_and_wholesale_login_reuse_same_user(self):
        retail_id, retail_code = self.request_otp(
            "accounts:phone_otp_request"
        )

        self.client.post(
            reverse("accounts:phone_otp_verify"),
            {
                "challenge_id": retail_id,
                "code": retail_code,
            },
        )

        self.client.logout()

        wholesale_id, wholesale_code = self.request_otp(
            "wholesale:phone_otp_request"
        )

        self.client.post(
            reverse("wholesale:phone_otp_verify"),
            {
                "challenge_id": wholesale_id,
                "code": wholesale_code,
            },
        )

        self.assertEqual(
            User.objects.filter(
                phone_number="+919876543210"
            ).count(),
            1,
        )
        self.assertEqual(
            WholesaleAccount.objects.count(),
            1,
        )

    def test_retail_otp_cannot_verify_wholesale_login(self):
        challenge_id, code = self.request_otp(
            "accounts:phone_otp_request"
        )

        wrong_endpoint_response = self.client.post(
            reverse("wholesale:phone_otp_verify"),
            {
                "challenge_id": challenge_id,
                "code": code,
            },
        )

        self.assertEqual(
            wrong_endpoint_response.status_code,
            400,
        )

        correct_response = self.client.post(
            reverse("accounts:phone_otp_verify"),
            {
                "challenge_id": challenge_id,
                "code": code,
            },
        )

        self.assertEqual(correct_response.status_code, 200)

    def test_approved_wholesale_account_redirects_to_dashboard(self):
        user = User.objects.create_user(
            username="existing-wholesale-user",
            phone_number="+919876543210",
            phone_verified=True,
        )
        WholesaleAccount.objects.create(
            user=user,
            status=WholesaleAccount.Status.APPROVED,
        )

        challenge_id, code = self.request_otp(
            "wholesale:phone_otp_request"
        )

        response = self.client.post(
            reverse("wholesale:phone_otp_verify"),
            {
                "challenge_id": challenge_id,
                "code": code,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["redirect_url"],
            reverse("wholesale:dashboard"),
        )

    def test_staff_account_cannot_use_public_phone_login(self):
        User.objects.create_superuser(
            username="site-owner",
            email="owner@example.com",
            password="strong-test-password",
            phone_number="+919876543210",
            phone_verified=True,
        )

        challenge_id, code = self.request_otp(
            "accounts:phone_otp_request"
        )

        response = self.client.post(
            reverse("accounts:phone_otp_verify"),
            {
                "challenge_id": challenge_id,
                "code": code,
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertNotIn(
            "_auth_user_id",
            self.client.session,
        )
