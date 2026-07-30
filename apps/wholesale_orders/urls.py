from django.urls import path

from . import views


app_name = "wholesale_orders"

urlpatterns = [
    path(
        "checkout/create/",
        views.checkout_create,
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
        "orders/<str:order_number>/invoice/",
        views.invoice_detail,
        name="invoice_detail",
    ),
    path(
        "orders/<str:order_number>/",
        views.order_detail,
        name="order_detail",
    ),
    path(
        "orders/<str:order_number>/cancel/",
        views.order_cancel,
        name="order_cancel",
    ),
    path(
        "staff/orders/",
        views.staff_order_list,
        name="staff_order_list",
    ),
    path(
        "staff/orders/<str:order_number>/",
        views.staff_order_detail,
        name="staff_order_detail",
    ),
    path(
        "staff/orders/<str:order_number>/"
        "confirm-bank-transfer/",
        views.staff_confirm_bank_transfer,
        name="staff_confirm_bank_transfer",
    ),
    path(
        "staff/orders/<str:order_number>/"
        "start-processing/",
        views.staff_start_processing,
        name="staff_start_processing",
    ),
    path(
        "staff/orders/<str:order_number>/"
        "mark-shipped/",
        views.staff_mark_shipped,
        name="staff_mark_shipped",
    ),
    path(
        "staff/orders/<str:order_number>/"
        "mark-delivered/",
        views.staff_mark_delivered,
        name="staff_mark_delivered",
    ),
]
