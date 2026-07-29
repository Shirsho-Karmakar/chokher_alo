from datetime import timedelta

from django.test import (
    SimpleTestCase,
    TestCase,
    override_settings,
)
from django.utils import timezone

from apps.accounts.models import PhoneOTPChallenge
from apps.accounts.otp.exceptions import (
    InvalidPhoneNumber,
    OTPAlreadyUsed,
    OTPExpired,
    OTPInvalidCode,
    OTPResendTooSoon,
    OTPSendLimitExceeded,
    OTPTooManyAttempts,
)
from apps.accounts.otp.phone import (
    normalize_indian_phone_number,
)
from apps.accounts.otp.providers.base import (
    BaseOTPProvider,
    OTPDeliveryResult,
)
from apps.accounts.otp.services import (
    issue_phone_otp,
    verify_phone_otp,
)


class RecordingOTPProvider(BaseOTPProvider):
    provider_name = "test"
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
            message_id=f"test-{len(self.deliveries)}"
        )


class IndianPhoneNumberTests(SimpleTestCase):
    def test_common_indian_number_formats_are_normalized(self):
        numbers = (
            "9876543210",
            "09876543210",
            "919876543210",
            "+91 98765 43210",
            "+91-98765-43210",
        )

        for number in numbers:
            with self.subTest(number=number):
                self.assertEqual(
                    normalize_indian_phone_number(number),
                    "+919876543210",
                )

    def test_non_indian_number_is_rejected(self):
        with self.assertRaises(InvalidPhoneNumber):
            normalize_indian_phone_number(
                "+1 415 555 2671"
            )


@override_settings(
    PHONE_OTP_PROVIDER=(
        "apps.accounts.tests.test_phone_otp."
        "RecordingOTPProvider"
    ),
)
class PhoneOTPServiceTests(TestCase):
    phone_number = "9876543210"
    purpose = PhoneOTPChallenge.Purpose.RETAIL_LOGIN

    def setUp(self):
        RecordingOTPProvider.deliveries.clear()

    def issue(self):
        return issue_phone_otp(
            phone_number=self.phone_number,
            purpose=self.purpose,
        )

    def delivered_code(self):
        return RecordingOTPProvider.deliveries[-1]["code"]

    def test_otp_is_issued_and_verified_once(self):
        challenge = self.issue()
        code = self.delivered_code()

        self.assertEqual(
            challenge.phone_number,
            "+919876543210",
        )
        self.assertIsNotNone(challenge.sent_at)
        self.assertNotEqual(challenge.code_digest, code)
        self.assertEqual(len(challenge.code_digest), 64)

        verified = verify_phone_otp(
            challenge_id=challenge.id,
            code=code,
        )

        self.assertEqual(verified.id, challenge.id)
        self.assertIsNotNone(verified.consumed_at)

        with self.assertRaises(OTPAlreadyUsed):
            verify_phone_otp(
                challenge_id=challenge.id,
                code=code,
            )

    def test_immediate_resend_is_blocked(self):
        self.issue()

        with self.assertRaises(OTPResendTooSoon):
            self.issue()

    @override_settings(PHONE_OTP_RESEND_SECONDS=0)
    def test_newest_otp_invalidates_previous_otp(self):
        first = self.issue()
        second = self.issue()

        first.refresh_from_db()
        second.refresh_from_db()

        self.assertIsNotNone(first.invalidated_at)
        self.assertIsNone(second.invalidated_at)

    @override_settings(
        PHONE_OTP_RESEND_SECONDS=0,
        PHONE_OTP_MAX_SENDS_PER_HOUR=2,
    )
    def test_hourly_send_limit_is_enforced(self):
        self.issue()
        self.issue()

        with self.assertRaises(OTPSendLimitExceeded):
            self.issue()

    @override_settings(PHONE_OTP_MAX_ATTEMPTS=2)
    def test_failed_attempts_lock_the_challenge(self):
        challenge = self.issue()
        real_code = self.delivered_code()

        wrong_code = (
            "000000"
            if real_code != "000000"
            else "111111"
        )

        with self.assertRaises(OTPInvalidCode):
            verify_phone_otp(
                challenge_id=challenge.id,
                code=wrong_code,
            )

        with self.assertRaises(OTPTooManyAttempts):
            verify_phone_otp(
                challenge_id=challenge.id,
                code=wrong_code,
            )

        challenge.refresh_from_db()

        self.assertEqual(challenge.attempt_count, 2)
        self.assertIsNotNone(challenge.invalidated_at)

    def test_expired_otp_is_rejected_and_invalidated(self):
        challenge = self.issue()

        PhoneOTPChallenge.objects.filter(
            pk=challenge.pk
        ).update(
            expires_at=timezone.now()
            - timedelta(seconds=1)
        )

        with self.assertRaises(OTPExpired):
            verify_phone_otp(
                challenge_id=challenge.id,
                code=self.delivered_code(),
            )

        challenge.refresh_from_db()
        self.assertIsNotNone(challenge.invalidated_at)
