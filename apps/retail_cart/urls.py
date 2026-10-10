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
    # Customer-owned frame service is intentionally not exposed.
    # Chokher Alo only fits prescription lenses into frames sold by the store.
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
