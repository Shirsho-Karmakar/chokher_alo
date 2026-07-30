from django import forms

from .models import (
    Brand,
    Category,
    Colour,
    FrameShape,
    FrameType,
    Material,
    ProductOffer,
    ProductStockAlert,
)


PUBLIC_STATUS_CHOICES = (
    (
        ProductOffer.Status.AVAILABLE,
        ProductOffer.Status.AVAILABLE.label,
    ),
    (
        ProductOffer.Status.SOLD_OUT,
        ProductOffer.Status.SOLD_OUT.label,
    ),
    (
        ProductOffer.Status.COMING_SOON,
        ProductOffer.Status.COMING_SOON.label,
    ),
)


class CatalogueFilterForm(forms.Form):
    q = forms.CharField(
        required=False,
        max_length=150,
    )
    category = forms.ModelChoiceField(
        queryset=Category.objects.filter(
            is_active=True,
            slug__isnull=False,
        ),
        required=False,
        to_field_name="slug",
    )
    brand = forms.ModelChoiceField(
        queryset=Brand.objects.filter(is_active=True),
        required=False,
    )
    gender = forms.ChoiceField(
        required=False,
        choices=(("", "Any"), *(
            (
                value,
                label,
            )
            for value, label in (
                ("men", "Men"),
                ("women", "Women"),
                ("unisex", "Unisex"),
                ("kids", "Kids"),
            )
        )),
    )
    frame_shape = forms.ModelChoiceField(
        queryset=FrameShape.objects.filter(is_active=True),
        required=False,
    )
    frame_type = forms.ModelChoiceField(
        queryset=FrameType.objects.filter(is_active=True),
        required=False,
    )
    material = forms.ModelChoiceField(
        queryset=Material.objects.filter(is_active=True),
        required=False,
    )
    colour = forms.ModelChoiceField(
        queryset=Colour.objects.filter(is_active=True),
        required=False,
    )
    size = forms.CharField(
        required=False,
        max_length=50,
    )
    offer_type = forms.ChoiceField(
        required=False,
        choices=(
            ("", "Any"),
            *ProductOffer.OfferType.choices,
        ),
    )
    availability = forms.ChoiceField(
        required=False,
        choices=(
            ("", "Any"),
            *PUBLIC_STATUS_CHOICES,
        ),
    )
    minimum_price = forms.DecimalField(
        required=False,
        min_value=0,
        max_digits=12,
        decimal_places=2,
    )
    maximum_price = forms.DecimalField(
        required=False,
        min_value=0,
        max_digits=12,
        decimal_places=2,
    )
    ordering = forms.ChoiceField(
        required=False,
        choices=(
            ("newest", "Newest"),
            ("name", "Name"),
            ("price_asc", "Price: low to high"),
            ("price_desc", "Price: high to low"),
        ),
    )
    page = forms.IntegerField(
        required=False,
        min_value=1,
    )
    page_size = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=48,
    )

    def clean(self):
        cleaned_data = super().clean()

        minimum_price = cleaned_data.get("minimum_price")
        maximum_price = cleaned_data.get("maximum_price")

        if (
            minimum_price is not None
            and maximum_price is not None
            and minimum_price > maximum_price
        ):
            self.add_error(
                "maximum_price",
                "Maximum price must be greater than or equal "
                "to minimum price.",
            )

        return cleaned_data


class ProductStockAlertRequestForm(forms.Form):
    sku = forms.CharField(
        max_length=20,
    )
    channel = forms.ChoiceField(
        choices=ProductStockAlert.Channel.choices,
    )
