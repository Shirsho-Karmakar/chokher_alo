from django.urls import path

from . import views


app_name = "retail_orders"

urlpatterns = [
    path(
        "checkout/preview/",
        views.checkout_preview,
        name="checkout_preview",
    ),
    path(
        "checkout/create/",
        views.create_checkout,
        name="checkout_create",
    ),
    path(
        "payments/razorpay/confirm/",
        views.confirm_razorpay_payment,
        name="razorpay_confirm",
    ),
    path(
        "payments/razorpay/webhook/",
        views.razorpay_webhook,
        name="razorpay_webhook",
    ),
    path(
        "orders/",
        views.order_list,
        name="order_list",
    ),
    path(
        "orders/<str:order_number>/",
        views.order_detail,
        name="order_detail",
    ),
    path(
        "orders/<str:order_number>/cancel/",
        views.cancel_order,
        name="order_cancel",
    ),
]
