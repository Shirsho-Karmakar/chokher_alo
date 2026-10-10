from django.urls import path

from . import views


app_name = "accounts"

urlpatterns = [
    path(
        "csrf/",
        views.csrf_cookie,
        name="csrf",
    ),
    path(
        "session/",
        views.session_status,
        name="session",
    ),
    path(
        "logout/",
        views.logout_view,
        name="logout",
    ),
    path(
        "phone/request/",
        views.request_retail_phone_otp,
        name="phone_otp_request",
    ),
    path(
        "phone/verify/",
        views.verify_retail_phone_otp,
        name="phone_otp_verify",
    ),
]
