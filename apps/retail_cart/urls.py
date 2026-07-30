from django.urls import path

from . import views


app_name = "retail_cart"

urlpatterns = [
    path(
        "",
        views.current_cart,
        name="current",
    ),
    path(
        "items/standard/",
        views.add_standard_item,
        name="add_standard",
    ),
    path(
        "items/powered/",
        views.add_powered_item,
        name="add_powered",
    ),
    path(
        "items/powered/<int:item_id>/configure/",
        views.configure_powered_item,
        name="configure_powered",
    ),
    path(
        "items/customer-owned-frame/",
        views.add_customer_owned_frame,
        name="add_customer_owned_frame",
    ),
    path(
        (
            "items/customer-owned-frame/"
            "<int:item_id>/configure/"
        ),
        views.configure_customer_owned_frame,
        name="configure_customer_owned_frame",
    ),
    path(
        "items/<int:item_id>/quantity/",
        views.update_item_quantity,
        name="update_quantity",
    ),
    path(
        "items/<int:item_id>/remove/",
        views.remove_item,
        name="remove_item",
    ),
]
