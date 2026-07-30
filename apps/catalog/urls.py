from django.urls import path

from . import views


app_name = "catalog"

urlpatterns = [
    path(
        "filters/",
        views.catalogue_filters,
        name="filters",
    ),
    path(
        "products/",
        views.product_list,
        name="product_list",
    ),
    path(
        "products/<str:sku>/",
        views.product_detail,
        name="product_detail",
    ),
    path(
        "images/<int:image_id>/",
        views.product_image,
        name="product_image",
    ),
    path(
        "stock-alerts/",
        views.stock_alert_list,
        name="stock_alert_list",
    ),
    path(
        "stock-alerts/create/",
        views.create_stock_alert,
        name="stock_alert_create",
    ),
    path(
        "stock-alerts/<int:alert_id>/cancel/",
        views.cancel_stock_alert,
        name="stock_alert_cancel",
    ),
]
