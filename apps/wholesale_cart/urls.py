from django.urls import path

from . import views


app_name = "wholesale_cart"

urlpatterns = [
    path("", views.current_cart, name="current"),
    path("items/set/", views.set_item, name="set_item"),
    path("items/<int:item_id>/remove/", views.remove_item, name="remove_item"),
]
