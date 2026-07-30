from django.contrib import admin

from .models import (
    LensAllowedAxis,
    LensCoating,
    LensPrescriptionRule,
    LensPriceRule,
    LensRefractiveIndex,
    LensSpecification,
    LensVisionType,
)


@admin.register(LensVisionType)
class LensVisionTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "is_active")
    list_editable = ("is_active",)
    search_fields = ("name", "code")


@admin.register(LensRefractiveIndex)
class LensRefractiveIndexAdmin(admin.ModelAdmin):
    list_display = (
        "value",
        "display_name",
        "is_active",
    )
    list_editable = (
        "display_name",
        "is_active",
    )
    search_fields = (
        "display_name",
    )


@admin.register(LensCoating)
class LensCoatingAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "is_active",
    )
    list_editable = ("is_active",)
    search_fields = (
        "code",
        "name",
        "description",
    )


@admin.register(LensSpecification)
class LensSpecificationAdmin(admin.ModelAdmin):
    list_display = (
        "offer",
        "vision_type",
        "refractive_index",
        "is_powered",
        "selling_unit",
        "is_active",
    )
    list_filter = (
        "vision_type",
        "refractive_index",
        "is_powered",
        "selling_unit",
        "is_active",
    )
    search_fields = (
        "offer__sku",
        "offer__variant__design__name",
        "offer__variant__design__supplier_model_number",
        "vision_type__name",
    )
    autocomplete_fields = (
        "offer",
        "vision_type",
        "refractive_index",
    )
    filter_horizontal = ("coatings",)
    readonly_fields = (
        "created_at",
        "updated_at",
    )


class LensAllowedAxisInline(admin.TabularInline):
    model = LensAllowedAxis
    extra = 0


@admin.register(LensPrescriptionRule)
class LensPrescriptionRuleAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "lens",
        "axis_mode",
        "supports_prism",
        "priority",
        "is_active",
    )
    list_filter = (
        "axis_mode",
        "supports_prism",
        "is_active",
        "lens__vision_type",
        "lens__refractive_index",
    )
    search_fields = (
        "name",
        "lens__offer__sku",
        "lens__offer__variant__design__name",
    )
    autocomplete_fields = ("lens",)
    readonly_fields = (
        "created_at",
        "updated_at",
    )
    inlines = (LensAllowedAxisInline,)


@admin.register(LensAllowedAxis)
class LensAllowedAxisAdmin(admin.ModelAdmin):
    list_display = (
        "axis",
        "rule",
    )
    list_filter = (
        "axis",
        "rule__axis_mode",
    )
    search_fields = (
        "rule__name",
        "rule__lens__offer__sku",
    )
    autocomplete_fields = ("rule",)


@admin.register(LensPriceRule)
class LensPriceRuleAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "lens",
        "rule_type",
        "amount_including_gst",
        "priority",
        "is_stackable",
        "is_active",
    )
    list_filter = (
        "rule_type",
        "is_stackable",
        "is_active",
        "lens__vision_type",
        "lens__refractive_index",
    )
    search_fields = (
        "name",
        "lens__offer__sku",
        "lens__offer__variant__design__name",
        "coating__code",
        "coating__name",
    )
    autocomplete_fields = (
        "lens",
        "coating",
        "frame_type",
        "frame_shape",
        "material",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (
            "Rule",
            {
                "fields": (
                    "lens",
                    "rule_type",
                    "name",
                    "amount_including_gst",
                    "priority",
                    "is_stackable",
                    "is_active",
                )
            },
        ),
        (
            "Coating condition",
            {
                "fields": ("coating",),
            },
        ),
        (
            "Power conditions",
            {
                "fields": (
                    "minimum_abs_sphere",
                    "maximum_abs_sphere",
                    "minimum_abs_cylinder",
                    "maximum_abs_cylinder",
                    "minimum_add_power",
                    "maximum_add_power",
                )
            },
        ),
        (
            "Frame conditions",
            {
                "fields": (
                    "frame_type",
                    "frame_shape",
                    "material",
                )
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )
