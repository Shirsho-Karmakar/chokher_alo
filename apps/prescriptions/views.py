import mimetypes
from pathlib import Path

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from .forms import (
    PrescriptionEyeValueForm,
    PrescriptionUploadForm,
)
from .models import Prescription, PrescriptionEyeValue


def _form_errors(form):
    return form.errors.get_json_data(
        escape_html=True,
    )


def _decimal_value(value):
    if value is None:
        return None

    return str(value)


def _serialize_eye_value(eye_value):
    return {
        "eye": eye_value.eye,
        "eye_label": eye_value.get_eye_display(),
        "sphere": _decimal_value(eye_value.sphere),
        "cylinder": _decimal_value(eye_value.cylinder),
        "axis": eye_value.axis,
        "add_power": _decimal_value(eye_value.add_power),
        "distance_pd_mm": _decimal_value(
            eye_value.distance_pd_mm
        ),
        "near_pd_mm": _decimal_value(
            eye_value.near_pd_mm
        ),
        "prism_diopters": _decimal_value(
            eye_value.prism_diopters
        ),
        "prism_base": eye_value.prism_base or None,
        "prism_base_label": (
            eye_value.get_prism_base_display()
            if eye_value.prism_base
            else None
        ),
    }


def _serialize_prescription(
    prescription,
    *,
    include_eye_values=True,
):
    data = {
        "id": prescription.pk,
        "status": prescription.status,
        "status_label": prescription.get_status_display(),
        "customer_notes": prescription.customer_notes,
        "is_approved": prescription.is_approved,
        "created_at": prescription.created_at.isoformat(),
        "updated_at": prescription.updated_at.isoformat(),
        "reviewed_at": (
            prescription.reviewed_at.isoformat()
            if prescription.reviewed_at
            else None
        ),
        "file_download_url": reverse(
            "prescriptions:file_download",
            kwargs={"prescription_id": prescription.pk},
        ),
    }

    if include_eye_values:
        data["eye_values"] = [
            _serialize_eye_value(eye_value)
            for eye_value in prescription.eye_values.all()
        ]

    return data


def _accessible_prescription(*, user, prescription_id):
    queryset = Prescription.objects.prefetch_related(
        "eye_values"
    )

    if (
        user.is_superuser
        or (
            user.is_staff
            and user.has_perm(
                "prescriptions.view_prescription"
            )
        )
    ):
        return get_object_or_404(
            queryset,
            pk=prescription_id,
        )

    return get_object_or_404(
        queryset,
        pk=prescription_id,
        user=user,
    )


@login_required
@require_POST
def upload_prescription(request):
    prescription_form = PrescriptionUploadForm(
        request.POST,
        request.FILES,
    )
    right_eye_form = PrescriptionEyeValueForm(
        request.POST,
        prefix="right",
    )
    left_eye_form = PrescriptionEyeValueForm(
        request.POST,
        prefix="left",
    )

    forms = {
        "prescription": prescription_form,
        "right_eye": right_eye_form,
        "left_eye": left_eye_form,
    }

    forms_are_valid = all(
        form.is_valid()
        for form in forms.values()
    )

    if not forms_are_valid:
        return JsonResponse(
            {
                "ok": False,
                "error": {
                    "code": "invalid_prescription",
                    "message": (
                        "Correct the prescription information "
                        "and try again."
                    ),
                    "fields": {
                        name: _form_errors(form)
                        for name, form in forms.items()
                        if form.errors
                    },
                },
            },
            status=400,
        )

    with transaction.atomic():
        prescription = prescription_form.save(commit=False)
        prescription.user = request.user
        prescription.status = Prescription.Status.PENDING
        prescription.save()

        eye_forms = (
            (
                PrescriptionEyeValue.Eye.RIGHT,
                right_eye_form,
            ),
            (
                PrescriptionEyeValue.Eye.LEFT,
                left_eye_form,
            ),
        )

        for eye, eye_form in eye_forms:
            if not eye_form.has_written_values:
                continue

            PrescriptionEyeValue.objects.create(
                prescription=prescription,
                eye=eye,
                **eye_form.cleaned_data,
            )

    prescription = (
        Prescription.objects
        .prefetch_related("eye_values")
        .get(pk=prescription.pk)
    )

    return JsonResponse(
        {
            "ok": True,
            "prescription": _serialize_prescription(
                prescription
            ),
        },
        status=201,
    )


@login_required
@require_GET
def prescription_list(request):
    prescriptions = (
        Prescription.objects
        .filter(user=request.user)
        .prefetch_related("eye_values")
        .order_by("-created_at")
    )

    return JsonResponse(
        {
            "ok": True,
            "prescriptions": [
                _serialize_prescription(prescription)
                for prescription in prescriptions
            ],
        }
    )


@login_required
@require_GET
def prescription_detail(request, prescription_id):
    prescription = _accessible_prescription(
        user=request.user,
        prescription_id=prescription_id,
    )

    return JsonResponse(
        {
            "ok": True,
            "prescription": _serialize_prescription(
                prescription
            ),
        }
    )


@login_required
@require_GET
def prescription_file_download(
    request,
    prescription_id,
):
    prescription = _accessible_prescription(
        user=request.user,
        prescription_id=prescription_id,
    )

    if not prescription.prescription_file:
        raise Http404("Prescription file not found.")

    original_extension = Path(
        prescription.prescription_file.name
    ).suffix.lower()

    download_name = (
        f"prescription-{prescription.pk}"
        f"{original_extension}"
    )

    content_type, _ = mimetypes.guess_type(download_name)

    response = FileResponse(
        prescription.prescription_file.open("rb"),
        as_attachment=True,
        filename=download_name,
        content_type=(
            content_type or "application/octet-stream"
        ),
    )

    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = (
        "private, no-store, max-age=0"
    )

    return response
