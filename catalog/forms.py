from django import forms

from catalog.models import Product


class ProductSearchForm(forms.Form):
    q = forms.CharField(
        required=False,
        max_length=100,
        widget=forms.TextInput(attrs={"placeholder": "Search products", "autofocus": True}),
    )
    category = forms.ChoiceField(required=False)
    in_stock = forms.BooleanField(required=False, label="In stock only")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        categories = (
            Product.available.order_by("category")
            .values_list("category", flat=True)
            .distinct()
        )
        self.fields["category"].choices = [("", "All categories")] + [
            (name, name) for name in categories
        ]


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ("name", "sku", "description", "category", "price", "stock", "weight_kg")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            del self.fields["stock"]

    def clean_sku(self) -> str:
        sku = self.cleaned_data["sku"].strip().upper()
        clash = Product.objects.filter(sku=sku, deleted_at__isnull=True)
        if self.instance.pk:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise forms.ValidationError("An active product already uses this SKU.")
        return sku

    def clean_name(self) -> str:
        return self.cleaned_data["name"].strip()

    def clean_category(self) -> str:
        return self.cleaned_data["category"].strip()


class StockAdjustmentForm(forms.Form):
    delta = forms.IntegerField(
        label="Adjust stock by",
        help_text="Use a negative number to reduce stock.",
    )

    def clean_delta(self) -> int:
        delta = self.cleaned_data["delta"]
        if delta == 0:
            raise forms.ValidationError("Enter a non-zero adjustment.")
        return delta
