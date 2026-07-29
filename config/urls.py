from django.contrib import admin
from django.urls import include, path


urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "auth/",
        include("apps.accounts.urls"),
    ),
    path(
        "wholesale/",
        include("apps.wholesale.urls"),
    ),
]
