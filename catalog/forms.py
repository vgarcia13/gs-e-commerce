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
