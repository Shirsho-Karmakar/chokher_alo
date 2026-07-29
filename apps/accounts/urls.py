from django.urls import path

from . import views


app_name = "accounts"

urlpatterns = [
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
