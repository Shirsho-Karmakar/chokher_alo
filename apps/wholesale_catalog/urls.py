from django.urls import path

from . import views


app_name = "wholesale_catalog"

urlpatterns = [
    path(
        "lenses/",
        views.compatible_lens_catalogue,
        name="lenses",
    ),
    path(
        "lenses/quote/",
        views.box_quote,
        name="quote",
    ),
]
