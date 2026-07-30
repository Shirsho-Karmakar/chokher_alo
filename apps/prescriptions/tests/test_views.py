import tempfile

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.prescriptions.models import (
    Prescription,
    PrescriptionEyeValue,
)


User = get_user_model()


class PrescriptionViewTests(TestCase):
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
            username="prescription-customer",
            phone_number="+919876543210",
            phone_verified=True,
        )
        self.other_user = User.objects.create_user(
            username="other-customer",
            phone_number="+919876543211",
            phone_verified=True,
        )

    def uploaded_file(self):
        return SimpleUploadedFile(
            "prescription.jpg",
            b"test-prescription-file",
            content_type="image/jpeg",
        )

    def create_prescription(self, user=None):
        return Prescription.objects.create(
            user=user or self.user,
            prescription_file=self.uploaded_file(),
        )

    def test_upload_requires_login(self):
        response = self.client.post(
            reverse("prescriptions:upload"),
        )

        self.assertEqual(response.status_code, 302)

    def test_image_is_required(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("prescriptions:upload"),
            {"customer_notes": "No file"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Prescription.objects.count(), 0)

    def test_upload_without_written_values_succeeds(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("prescriptions:upload"),
            {
                "prescription_file": self.uploaded_file(),
                "customer_notes": "Please review.",
            },
        )

        self.assertEqual(response.status_code, 201)

        prescription = Prescription.objects.get()

        self.assertEqual(prescription.user, self.user)
        self.assertEqual(
            prescription.status,
            Prescription.Status.PENDING,
        )
        self.assertEqual(prescription.eye_values.count(), 0)

    def test_upload_with_both_eye_values_succeeds(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("prescriptions:upload"),
            {
                "prescription_file": self.uploaded_file(),
                "right-sphere": "-2.00",
                "right-cylinder": "-0.50",
                "right-axis": "90",
                "left-sphere": "-1.75",
                "left-distance_pd_mm": "31.50",
            },
        )

        self.assertEqual(response.status_code, 201)

        prescription = Prescription.objects.get()

        self.assertEqual(prescription.eye_values.count(), 2)
        self.assertTrue(
            prescription.eye_values.filter(
                eye=PrescriptionEyeValue.Eye.RIGHT,
                axis=90,
            ).exists()
        )

    def test_invalid_eye_values_do_not_create_prescription(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("prescriptions:upload"),
            {
                "prescription_file": self.uploaded_file(),
                "right-axis": "90",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Prescription.objects.count(), 0)

    def test_list_only_contains_current_users_prescriptions(self):
        own_prescription = self.create_prescription()
        self.create_prescription(user=self.other_user)

        self.client.force_login(self.user)

        response = self.client.get(
            reverse("prescriptions:list")
        )

        self.assertEqual(response.status_code, 200)

        prescription_ids = {
            item["id"]
            for item in response.json()["prescriptions"]
        }

        self.assertEqual(
            prescription_ids,
            {own_prescription.pk},
        )

    def test_customer_cannot_view_another_users_prescription(self):
        prescription = self.create_prescription(
            user=self.other_user
        )
        self.client.force_login(self.user)

        response = self.client.get(
            reverse(
                "prescriptions:detail",
                kwargs={
                    "prescription_id": prescription.pk,
                },
            )
        )

        self.assertEqual(response.status_code, 404)

    def test_customer_can_download_own_file(self):
        prescription = self.create_prescription()
        self.client.force_login(self.user)

        response = self.client.get(
            reverse(
                "prescriptions:file_download",
                kwargs={
                    "prescription_id": prescription.pk,
                },
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["X-Content-Type-Options"],
            "nosniff",
        )
        self.assertIn(
            "attachment;",
            response["Content-Disposition"],
        )

    def test_other_customer_cannot_download_file(self):
        prescription = self.create_prescription(
            user=self.other_user
        )
        self.client.force_login(self.user)

        response = self.client.get(
            reverse(
                "prescriptions:file_download",
                kwargs={
                    "prescription_id": prescription.pk,
                },
            )
        )

        self.assertEqual(response.status_code, 404)

    def test_authorized_staff_can_download_customer_file(self):
        prescription = self.create_prescription()

        reviewer = User.objects.create_user(
            username="prescription-reviewer",
            password="test-password",
            is_staff=True,
        )
        reviewer.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="prescriptions",
                codename="view_prescription",
            )
        )

        self.client.force_login(reviewer)

        response = self.client.get(
            reverse(
                "prescriptions:file_download",
                kwargs={
                    "prescription_id": prescription.pk,
                },
            )
        )

        self.assertEqual(response.status_code, 200)

    def test_customer_response_does_not_expose_admin_notes(self):
        prescription = self.create_prescription()
        prescription.admin_notes = "Private reviewer notes."
        prescription.save()

        self.client.force_login(self.user)

        response = self.client.get(
            reverse(
                "prescriptions:detail",
                kwargs={
                    "prescription_id": prescription.pk,
                },
            )
        )

        response_text = response.content.decode()

        self.assertNotIn("admin_notes", response_text)
        self.assertNotIn(
            "Private reviewer notes.",
            response_text,
        )
