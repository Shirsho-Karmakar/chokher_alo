from django.urls import path

from apps.accounts import views as account_views

from . import views


app_name = "wholesale"

urlpatterns = [
    path(
        "login/",
        views.login_information,
        name="login",
    ),
    path(
        "auth/phone/request/",
        account_views.request_wholesale_phone_otp,
        name="phone_otp_request",
    ),
    path(
        "auth/phone/verify/",
        account_views.verify_wholesale_phone_otp,
        name="phone_otp_verify",
    ),
    path(
        "status/",
        views.status,
        name="status",
    ),
    path(
        "dashboard/",
        views.dashboard,
        name="dashboard",
    ),
]
