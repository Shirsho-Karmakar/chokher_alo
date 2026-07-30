from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

from apps.catalog.models import ProductOffer, ProductVariant
from apps.prescriptions.models import Prescription

from .matching import compatible_lenses_for_prescription
from .models import (
    LensCoating,
    LensPriceRule,
    LensSpecification,
)


MONEY_PLACES = Decimal("0.01")


class LensPricingError(Exception):
    """Raised when a valid lens quotation cannot be produced."""


@dataclass(frozen=True)
class LensQuoteLine:
    code: str
    name: str
    amount_including_gst: Decimal
    rule_id: int | None = None


@dataclass(frozen=True)
class LensQuote:
    lens_id: int
    offer_id: int
    prescription_id: int
    selling_unit: str
    gst_rate: Decimal
    lines: tuple[LensQuoteLine, ...]
    total_including_gst: Decimal


def _money(value: Decimal) -> Decimal:
    return value.quantize(
        MONEY_PLACES,
        rounding=ROUND_HALF_UP,
    )


def _metric_matches(
    value: Decimal,
    minimum_value: Decimal | None,
    maximum_value: Decimal | None,
) -> bool:
    if minimum_value is not None and value < minimum_value:
        return False

    if maximum_value is not None and value > maximum_value:
        return False

    return True


def _strongest_prescription_values(
    prescription: Prescription,
) -> dict[str, Decimal]:
    eye_values = list(prescription.eye_values.all())

    def strongest(field_name: str) -> Decimal:
        values = [
            abs(getattr(eye_value, field_name))
            for eye_value in eye_values
            if getattr(eye_value, field_name) is not None
        ]

        return max(values, default=Decimal("0.00"))

    return {
        "sphere": strongest("sphere"),
        "cylinder": strongest("cylinder"),
        "add_power": strongest("add_power"),
    }


def _power_rule_matches(
    rule: LensPriceRule,
    *,
    metrics: dict[str, Decimal],
) -> bool:
    return (
        _metric_matches(
            metrics["sphere"],
            rule.minimum_abs_sphere,
            rule.maximum_abs_sphere,
        )
        and _metric_matches(
            metrics["cylinder"],
            rule.minimum_abs_cylinder,
            rule.maximum_abs_cylinder,
        )
        and _metric_matches(
            metrics["add_power"],
            rule.minimum_add_power,
            rule.maximum_add_power,
        )
    )


def _frame_rule_matches(
    rule: LensPriceRule,
    *,
    frame_variant: ProductVariant,
) -> bool:
    design = frame_variant.design

    if (
        rule.frame_type_id is not None
        and design.frame_type_id != rule.frame_type_id
    ):
        return False

    if (
        rule.frame_shape_id is not None
        and design.frame_shape_id != rule.frame_shape_id
    ):
        return False

    if (
        rule.material_id is not None
        and design.material_id != rule.material_id
    ):
        return False

    return True


def _select_matching_rules(
    rules: Iterable[LensPriceRule],
) -> list[LensPriceRule]:
    rules = list(rules)

    stackable_rules = [
        rule
        for rule in rules
        if rule.is_stackable
    ]
    non_stackable_rules = sorted(
        (
            rule
            for rule in rules
            if not rule.is_stackable
        ),
        key=lambda rule: (
            rule.priority,
            rule.amount_including_gst,
            rule.pk or 0,
        ),
        reverse=True,
    )

    selected = sorted(
        stackable_rules,
        key=lambda rule: (
            rule.priority,
            rule.pk or 0,
        ),
    )

    if non_stackable_rules:
        selected.append(non_stackable_rules[0])

    return selected


def _line_from_rule(rule: LensPriceRule) -> LensQuoteLine:
    return LensQuoteLine(
        code=rule.rule_type,
        name=rule.name,
        amount_including_gst=_money(
            rule.amount_including_gst
        ),
        rule_id=rule.pk,
    )


def quote_lens(
    *,
    lens: LensSpecification,
    prescription: Prescription,
    selected_coatings: Iterable[LensCoating] = (),
    frame_variant: ProductVariant | None = None,
) -> LensQuote:
    """
    Produce a server-side GST-inclusive quotation for one lens selling unit.

    This quotation is informational until an order item snapshots it.
    """

    if prescription.status != Prescription.Status.APPROVED:
        raise LensPricingError(
            "An approved prescription is required."
        )

    compatible_lenses = compatible_lenses_for_prescription(
        prescription
    )

    if lens not in compatible_lenses:
        raise LensPricingError(
            "The selected lens is not compatible with "
            "this prescription."
        )

    offer = lens.offer

    if offer.effective_status not in {
        ProductOffer.Status.AVAILABLE,
        ProductOffer.Status.SOLD_OUT,
    }:
        raise LensPricingError(
            "This lens does not currently have a visible price."
        )

    if offer.selling_price_including_gst is None:
        raise LensPricingError(
            "The lens base price is not configured."
        )

    selected_coatings = tuple(selected_coatings)
    selected_coating_ids = {
        coating.pk
        for coating in selected_coatings
    }

    allowed_coating_ids = set(
        lens.coatings.values_list("pk", flat=True)
    )

    if not selected_coating_ids.issubset(
        allowed_coating_ids
    ):
        raise LensPricingError(
            "One or more selected coatings are unavailable "
            "for this lens."
        )

    lines = [
        LensQuoteLine(
            code="base",
            name="Base lens price",
            amount_including_gst=_money(
                offer.selling_price_including_gst
            ),
        )
    ]

    active_rules = list(
        lens.price_rules
        .filter(is_active=True)
        .select_related(
            "coating",
            "frame_type",
            "frame_shape",
            "material",
        )
    )

    index_rules = _select_matching_rules(
        rule
        for rule in active_rules
        if rule.rule_type == LensPriceRule.RuleType.INDEX
    )
    lines.extend(
        _line_from_rule(rule)
        for rule in index_rules
    )

    for coating in selected_coatings:
        coating_rules = _select_matching_rules(
            rule
            for rule in active_rules
            if (
                rule.rule_type
                == LensPriceRule.RuleType.COATING
                and rule.coating_id == coating.pk
            )
        )
        lines.extend(
            _line_from_rule(rule)
            for rule in coating_rules
        )

    metrics = _strongest_prescription_values(
        prescription
    )

    power_rules = _select_matching_rules(
        rule
        for rule in active_rules
        if (
            rule.rule_type == LensPriceRule.RuleType.POWER
            and _power_rule_matches(
                rule,
                metrics=metrics,
            )
        )
    )
    lines.extend(
        _line_from_rule(rule)
        for rule in power_rules
    )

    if frame_variant is not None:
        frame_rules = _select_matching_rules(
            rule
            for rule in active_rules
            if (
                rule.rule_type == LensPriceRule.RuleType.FRAME
                and _frame_rule_matches(
                    rule,
                    frame_variant=frame_variant,
                )
            )
        )
        lines.extend(
            _line_from_rule(rule)
            for rule in frame_rules
        )

    total = _money(
        sum(
            (
                line.amount_including_gst
                for line in lines
            ),
            start=Decimal("0.00"),
        )
    )

    return LensQuote(
        lens_id=lens.pk,
        offer_id=offer.pk,
        prescription_id=prescription.pk,
        selling_unit=lens.selling_unit,
        gst_rate=offer.gst_rate,
        lines=tuple(lines),
        total_including_gst=total,
    )
