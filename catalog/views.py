from django.views.generic import DetailView, ListView

from catalog.forms import ProductSearchForm
from catalog.models import Product

PAGE_SIZE = 20


class ProductListView(ListView):
    model = Product
    paginate_by = PAGE_SIZE
    context_object_name = "products"

    def get_form(self) -> ProductSearchForm:
        return ProductSearchForm(self.request.GET or None)

    def get_queryset(self):
        form = self.get_form()
        products = Product.available.all()
        if not form.is_valid():
            return products
        products = products.search(form.cleaned_data["q"]).in_category(
            form.cleaned_data["category"]
        )
        if form.cleaned_data["in_stock"]:
            products = products.in_stock()
        return products

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = self.get_form()
        return context


class ProductDetailView(DetailView):
    context_object_name = "product"

    def get_queryset(self):
        return Product.available.all()
