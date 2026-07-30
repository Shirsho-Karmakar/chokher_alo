from django.urls import path

from . import views


app_name = "prescriptions"

urlpatterns = [
    path(
        "",
        views.prescription_list,
        name="list",
    ),
    path(
        "upload/",
        views.upload_prescription,
        name="upload",
    ),
    path(
        "<int:prescription_id>/",
        views.prescription_detail,
        name="detail",
    ),
    path(
        "<int:prescription_id>/file/",
        views.prescription_file_download,
        name="file_download",
    ),
]
