from functools import wraps

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied

from .models import WholesaleAccount


def has_approved_wholesale_access(user) -> bool:
    """
    Return True only for an active, phone-verified user whose wholesale
    account is currently approved.
    """
    if not getattr(user, "is_authenticated", False):
        return False

    if not user.is_active or not user.phone_verified:
        return False

    try:
        wholesale_account = user.wholesale_account
    except WholesaleAccount.DoesNotExist:
        return False

    return wholesale_account.status == WholesaleAccount.Status.APPROVED


def approved_wholesale_required(view_function):
    """
    Protect wholesale catalogue, cart, checkout, and order views.

    Unauthenticated users are redirected to wholesale login.
    Authenticated but unapproved users receive HTTP 403.
    """

    @wraps(view_function)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(
                request.get_full_path(),
                login_url=settings.WHOLESALE_LOGIN_URL,
            )

        if not has_approved_wholesale_access(request.user):
            raise PermissionDenied(
                "An approved wholesale account is required."
            )

        return view_function(request, *args, **kwargs)

    return wrapper
