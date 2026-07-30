from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.locations.constants import IndianState
from apps.locations.models import (
    Address,
    ServiceablePincode,
)


User = get_user_model()


class AddressModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="address-user",
            phone_number="+919876543210",
            phone_verified=True,
        )

    def address_data(self, **overrides):
        data = {
            "user": self.user,
            "label": "Home",
            "recipient_name": "Test Customer",
            "phone_number": "9876543210",
            "address_line_1": "10 Example Road",
            "address_line_2": "",
            "landmark": "",
            "city": "Kolkata",
            "district": "Kolkata",
            "state": IndianState.WEST_BENGAL,
            "postal_code": "700001",
        }
        data.update(overrides)
        return data

    def test_address_normalizes_phone_and_pin_code(self):
        address = Address.objects.create(
            **self.address_data()
        )

        self.assertEqual(
            address.phone_number,
            "+919876543210",
        )
        self.assertEqual(address.postal_code, "700001")

    def test_new_default_delivery_replaces_previous_default(self):
        first = Address.objects.create(
            **self.address_data(
                postal_code="700001",
                is_default_delivery=True,
            )
        )
        second = Address.objects.create(
            **self.address_data(
                label="Office",
                address_line_1="20 Business Street",
                postal_code="700002",
                is_default_delivery=True,
            )
        )

        first.refresh_from_db()
        second.refresh_from_db()

        self.assertFalse(first.is_default_delivery)
        self.assertTrue(second.is_default_delivery)

    def test_one_address_can_be_both_defaults(self):
        address = Address.objects.create(
            **self.address_data(
                is_default_delivery=True,
                is_default_billing=True,
            )
        )

        self.assertTrue(address.is_default_delivery)
        self.assertTrue(address.is_default_billing)

    def test_inactive_address_cannot_be_default(self):
        address = Address(
            **self.address_data(
                is_active=False,
                is_default_delivery=True,
            )
        )

        with self.assertRaises(ValidationError):
            address.save()

    def test_invalid_pin_code_is_rejected(self):
        address = Address(
            **self.address_data(postal_code="01234")
        )

        with self.assertRaises(ValidationError):
            address.save()


class ServiceablePincodeModelTests(TestCase):
    def test_active_pin_code_is_serviceable(self):
        pincode = ServiceablePincode.objects.create(
            postal_code="700001",
            state=IndianState.WEST_BENGAL,
            city="Kolkata",
            status=ServiceablePincode.Status.ACTIVE,
        )

        self.assertTrue(pincode.delivery_available)

    def test_coming_soon_pin_code_is_not_serviceable(self):
        pincode = ServiceablePincode.objects.create(
            postal_code="700002",
            state=IndianState.WEST_BENGAL,
            status=ServiceablePincode.Status.COMING_SOON,
        )

        self.assertFalse(pincode.delivery_available)

    def test_duplicate_pin_code_is_rejected(self):
        ServiceablePincode.objects.create(
            postal_code="700001",
            state=IndianState.WEST_BENGAL,
        )

        duplicate = ServiceablePincode(
            postal_code="700001",
            state=IndianState.WEST_BENGAL,
        )

        with self.assertRaises(ValidationError):
            duplicate.save()
