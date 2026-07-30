from django.urls import path

from . import views


app_name = "lenses"

urlpatterns = [
    path(
        "compatible/",
        views.compatible_lens_catalogue,
        name="compatible",
    ),
    path(
        "quote/",
        views.lens_quote,
        name="quote",
    ),
]
