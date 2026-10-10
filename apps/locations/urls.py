from django.urls import path

from . import views


app_name = "locations"

urlpatterns = [
    path("serviceability/", views.serviceability, name="serviceability"),
    path("addresses/", views.address_list_create, name="addresses"),
    path("addresses/<int:address_id>/", views.address_update, name="address_update"),
    path("addresses/<int:address_id>/deactivate/", views.address_deactivate, name="address_deactivate"),
]
