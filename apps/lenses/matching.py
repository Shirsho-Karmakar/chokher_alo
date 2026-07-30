from decimal import Decimal

from apps.catalog.models import ProductOffer
from apps.prescriptions.models import (
    Prescription,
    PrescriptionEyeValue,
)

from .models import (
    LensPrescriptionRule,
    LensSpecification,
)


def _value_matches_range(
    value,
    minimum_value,
    maximum_value,
) -> bool:
    if minimum_value is None and maximum_value is None:
        return True

    if value is None:
        return False

    if minimum_value is not None and value < minimum_value:
        return False

    if maximum_value is not None and value > maximum_value:
        return False

    return True


def _axis_distance(first_axis: int, second_axis: int) -> int:
    direct_distance = abs(first_axis - second_axis)

    return min(
        direct_distance,
        180 - direct_distance,
    )


def _axis_matches(eye_value, rule) -> bool:
    if rule.axis_mode in {
        LensPrescriptionRule.AxisMode.ANY,
        LensPrescriptionRule.AxisMode.NOT_REQUIRED,
    }:
        return True

    if eye_value.axis is None:
        return False

    allowed_axes = [
        allowed_axis.axis
        for allowed_axis in rule.allowed_axes.all()
    ]

    if not allowed_axes:
        return False

    return any(
        _axis_distance(
            eye_value.axis,
            allowed_axis,
        )
        <= rule.axis_tolerance_degrees
        for allowed_axis in allowed_axes
    )


def prescription_eye_matches_rule(
    *,
    eye_value,
    rule,
) -> bool:
    if not rule.is_active:
        return False

    if (
        eye_value.prism_diopters is not None
        and eye_value.prism_diopters > Decimal("0.00")
        and not rule.supports_prism
    ):
        return False

    if not _value_matches_range(
        eye_value.sphere,
        rule.minimum_sphere,
        rule.maximum_sphere,
    ):
        return False

    if not _value_matches_range(
        eye_value.cylinder,
        rule.minimum_cylinder,
        rule.maximum_cylinder,
    ):
        return False

    if not _value_matches_range(
        eye_value.add_power,
        rule.minimum_add_power,
        rule.maximum_add_power,
    ):
        return False

    return _axis_matches(eye_value, rule)


def compatible_lenses_for_prescription(
    prescription,
) -> list[LensSpecification]:
    """
    Return active lens specifications compatible with an approved
    prescription.

    This is a catalogue-filtering system, not a medical diagnosis.
    """

    if prescription.status != Prescription.Status.APPROVED:
        return []

    eye_values = {
        eye_value.eye: eye_value
        for eye_value in prescription.eye_values.all()
    }

    if not eye_values:
        return []

    specifications = (
        LensSpecification.objects
        .filter(is_active=True)
        .select_related(
            "offer",
            "offer__variant",
            "offer__variant__design",
            "vision_type",
            "refractive_index",
        )
        .prefetch_related(
            "coatings",
            "prescription_rules__allowed_axes",
        )
    )

    compatible_lenses = []

    for specification in specifications:
        offer_status = specification.offer.effective_status

        if offer_status in {
            ProductOffer.Status.DRAFT,
            ProductOffer.Status.DISCONTINUED,
        }:
            continue

        if not specification.is_powered:
            continue

        if specification.require_both_eyes:
            required_eyes = {
                PrescriptionEyeValue.Eye.RIGHT,
                PrescriptionEyeValue.Eye.LEFT,
            }

            if not required_eyes.issubset(eye_values):
                continue

        rules = [
            rule
            for rule in specification.prescription_rules.all()
            if rule.is_active
        ]

        if not rules:
            continue

        values_to_check = list(eye_values.values())

        all_eyes_match = all(
            any(
                prescription_eye_matches_rule(
                    eye_value=eye_value,
                    rule=rule,
                )
                for rule in rules
            )
            for eye_value in values_to_check
        )

        if all_eyes_match:
            compatible_lenses.append(specification)

    return compatible_lenses
