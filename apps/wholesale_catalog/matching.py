from dataclasses import dataclass

from django.db.models import Prefetch

from apps.lenses.matching import prescription_eye_matches_rule
from apps.prescriptions.models import (
    Prescription,
    PrescriptionEyeValue,
)

from .models import (
    WholesaleBulkPriceTier,
    WholesaleLensVariant,
)


@dataclass(frozen=True)
class WholesaleVariantMatch:
    variant: WholesaleLensVariant
    matching_eyes: tuple[str, ...]


def matching_eyes_for_variant(
    *,
    prescription: Prescription,
    variant: WholesaleLensVariant,
) -> tuple[str, ...]:
    """
    Return the prescription eyes that match this wholesale price row.

    Wholesale rows are matched per eye because the right and left eyes may
    fall into different prescription ranges and therefore different prices.
    """
    if prescription.status != Prescription.Status.APPROVED:
        return ()

    eye_values = {
        eye_value.eye: eye_value
        for eye_value in prescription.eye_values.all()
    }

    matching_eyes = []

    for eye in (
        PrescriptionEyeValue.Eye.RIGHT,
        PrescriptionEyeValue.Eye.LEFT,
    ):
        eye_value = eye_values.get(eye)

        if eye_value is None:
            continue

        if prescription_eye_matches_rule(
            eye_value=eye_value,
            rule=variant.prescription_rule,
        ):
            matching_eyes.append(eye)

    return tuple(matching_eyes)


def compatible_wholesale_variants_for_prescription(
    prescription: Prescription,
) -> list[WholesaleVariantMatch]:
    """
    Return visible wholesale variants matching at least one prescription eye.

    Draft and discontinued rows are excluded. Sold-out and coming-soon rows
    remain visible according to their price-visibility rules.
    """
    if prescription.status != Prescription.Status.APPROVED:
        return []

    if not prescription.eye_values.exists():
        return []

    variants = (
        WholesaleLensVariant.objects
        .filter(
            is_active=True,
            listing__is_active=True,
            listing__lens__is_active=True,
            listing__lens__is_powered=True,
        )
        .select_related(
            "listing",
            "listing__lens",
            "listing__lens__offer",
            "listing__lens__offer__variant",
            "listing__lens__offer__variant__design",
            "listing__lens__offer__variant__design__brand",
            "listing__lens__vision_type",
            "listing__lens__refractive_index",
            "prescription_rule",
            "coating",
        )
        .prefetch_related(
            "prescription_rule__allowed_axes",
            Prefetch(
                "bulk_price_tiers",
                queryset=(
                    WholesaleBulkPriceTier.objects
                    .filter(is_active=True)
                    .order_by("minimum_boxes")
                ),
                to_attr="active_bulk_price_tiers",
            ),
        )
    )

    matches = []

    for variant in variants:
        if variant.effective_status in {
            WholesaleLensVariant.Status.DRAFT,
            WholesaleLensVariant.Status.DISCONTINUED,
        }:
            continue

        matching_eyes = matching_eyes_for_variant(
            prescription=prescription,
            variant=variant,
        )

        if not matching_eyes:
            continue

        matches.append(
            WholesaleVariantMatch(
                variant=variant,
                matching_eyes=matching_eyes,
            )
        )

    return matches
