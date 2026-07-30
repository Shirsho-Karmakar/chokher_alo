import tempfile
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from apps.prescriptions.models import (
    Prescription,
    PrescriptionEyeValue,
)


User = get_user_model()


class PrescriptionModelTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.temporary_media = tempfile.TemporaryDirectory()
        cls.media_override = override_settings(
            MEDIA_ROOT=cls.temporary_media.name
        )
        cls.media_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls.media_override.disable()
        cls.temporary_media.cleanup()

        super().tearDownClass()

    def setUp(self):
        self.user = User.objects.create_user(
            username="prescription-user",
            phone_number="+919876543210",
            phone_verified=True,
        )

    def uploaded_file(self, filename="prescription.jpg"):
        return SimpleUploadedFile(
            filename,
            b"test-prescription-file",
            content_type="image/jpeg",
        )

    def create_prescription(self):
        return Prescription.objects.create(
            user=self.user,
            prescription_file=self.uploaded_file(),
        )

    def test_prescription_file_is_stored_privately(self):
        prescription = self.create_prescription()

        self.assertTrue(
            prescription.prescription_file.name.startswith(
                f"private/prescriptions/{self.user.pk}/"
            )
        )
        self.assertNotIn(
            "prescription.jpg",
            prescription.prescription_file.name,
        )

    def test_written_values_are_optional(self):
        prescription = self.create_prescription()

        self.assertEqual(prescription.eye_values.count(), 0)
        self.assertEqual(
            prescription.status,
            Prescription.Status.PENDING,
        )

    def test_right_and_left_eye_values_can_be_saved(self):
        prescription = self.create_prescription()

        right_eye = PrescriptionEyeValue.objects.create(
            prescription=prescription,
            eye=PrescriptionEyeValue.Eye.RIGHT,
            sphere=Decimal("-2.00"),
            cylinder=Decimal("-0.50"),
            axis=90,
        )
        left_eye = PrescriptionEyeValue.objects.create(
            prescription=prescription,
            eye=PrescriptionEyeValue.Eye.LEFT,
            sphere=Decimal("-1.75"),
        )

        self.assertEqual(right_eye.axis, 90)
        self.assertEqual(left_eye.sphere, Decimal("-1.75"))
        self.assertEqual(prescription.eye_values.count(), 2)

    def test_axis_requires_cylinder(self):
        prescription = self.create_prescription()

        eye_value = PrescriptionEyeValue(
            prescription=prescription,
            eye=PrescriptionEyeValue.Eye.RIGHT,
            sphere=Decimal("-2.00"),
            axis=90,
        )

        with self.assertRaises(ValidationError):
            eye_value.save()

    def test_prism_requires_base_direction(self):
        prescription = self.create_prescription()

        eye_value = PrescriptionEyeValue(
            prescription=prescription,
            eye=PrescriptionEyeValue.Eye.RIGHT,
            prism_diopters=Decimal("1.00"),
        )

        with self.assertRaises(ValidationError):
            eye_value.save()

    def test_duplicate_eye_is_rejected(self):
        prescription = self.create_prescription()

        PrescriptionEyeValue.objects.create(
            prescription=prescription,
            eye=PrescriptionEyeValue.Eye.RIGHT,
        )

        duplicate = PrescriptionEyeValue(
            prescription=prescription,
            eye=PrescriptionEyeValue.Eye.RIGHT,
        )

        with self.assertRaises(ValidationError):
            duplicate.save()

    def test_approved_property_reflects_status(self):
        prescription = self.create_prescription()

        self.assertFalse(prescription.is_approved)

        prescription.status = Prescription.Status.APPROVED
        prescription.save()

        self.assertTrue(prescription.is_approved)
