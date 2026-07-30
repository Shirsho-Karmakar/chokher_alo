from django.contrib import admin
from django.urls import include, path


urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "auth/",
        include("apps.accounts.urls"),
    ),
    path(
        "wholesale/catalogue/",
        include("apps.wholesale_catalog.urls"),
    ),
    path(
        "wholesale/",
        include("apps.wholesale.urls"),
    ),
    path(
        "prescriptions/",
        include("apps.prescriptions.urls"),
    ),
    path(
        "lenses/",
        include("apps.lenses.urls"),
    ),
    path(
        "catalogue/",
        include("apps.catalog.urls"),
    ),
    path(
        "cart/",
        include("apps.retail_cart.urls"),
    ),
    path(
        "retail/",
        include("apps.retail_orders.urls"),
    ),
]
