from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from apps.wholesale.models import WholesaleAccount
from apps.wholesale.permissions import (
    approved_wholesale_required,
    has_approved_wholesale_access,
)


User = get_user_model()


def protected_view(request):
    return HttpResponse("Allowed")


class ApprovedWholesaleAccessTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username="wholesale-access-user",
            phone_number="+919876543211",
            phone_verified=True,
        )

    def request_for(self, user):
        request = self.factory.get("/wholesale/catalogue/")
        request.user = user
        return request

    def test_anonymous_user_is_redirected_to_wholesale_login(self):
        request = self.request_for(AnonymousUser())
        view = approved_wholesale_required(protected_view)

        response = view(request)

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            response.url.startswith("/wholesale/login/?next=")
        )

    def test_retail_user_without_wholesale_account_is_denied(self):
        request = self.request_for(self.user)
        view = approved_wholesale_required(protected_view)

        with self.assertRaises(PermissionDenied):
            view(request)

    def test_unverified_wholesale_account_is_denied(self):
        WholesaleAccount.objects.create(user=self.user)

        self.assertFalse(
            has_approved_wholesale_access(self.user)
        )

    def test_approved_wholesale_account_is_allowed(self):
        account = WholesaleAccount.objects.create(
            user=self.user,
            status=WholesaleAccount.Status.APPROVED,
        )

        request = self.request_for(self.user)
        view = approved_wholesale_required(protected_view)

        response = view(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"Allowed")
        self.assertTrue(account.is_approved)

    def test_suspended_wholesale_account_is_denied(self):
        WholesaleAccount.objects.create(
            user=self.user,
            status=WholesaleAccount.Status.SUSPENDED,
        )

        self.assertFalse(
            has_approved_wholesale_access(self.user)
        )

    def test_inactive_user_is_denied(self):
        WholesaleAccount.objects.create(
            user=self.user,
            status=WholesaleAccount.Status.APPROVED,
        )
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])

        self.assertFalse(
            has_approved_wholesale_access(self.user)
        )
