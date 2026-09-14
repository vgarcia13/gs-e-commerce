from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, FormView, ListView, UpdateView

from accounts.mixins import StaffRequiredMixin
from catalog import services
from catalog.forms import ProductForm, StockAdjustmentForm
from catalog.models import Product

PAGE_SIZE = 25


class StaffProductListView(StaffRequiredMixin, ListView):
    model = Product
    paginate_by = PAGE_SIZE
    context_object_name = "products"
    template_name = "catalog/staff/product_list.html"

    def get_queryset(self):
        return Product.objects.all().search(self.request.GET.get("q", ""))


class StaffProductCreateView(StaffRequiredMixin, CreateView):
    model = Product
    form_class = ProductForm
    template_name = "catalog/staff/product_form.html"
    success_url = reverse_lazy("catalog_staff:product_list")

    def form_valid(self, form):
        response = super().form_valid(form)
        services.record_created(self.object, self.request.user)
        messages.success(self.request, f"Created {self.object.sku}.")
        return response


class StaffProductUpdateView(StaffRequiredMixin, UpdateView):
    model = Product
    form_class = ProductForm
    template_name = "catalog/staff/product_form.html"
    success_url = reverse_lazy("catalog_staff:product_list")

    def form_valid(self, form):
        response = super().form_valid(form)
        services.record_updated(self.object, self.request.user)
        messages.success(self.request, f"Updated {self.object.sku}.")
        return response


class StaffProductDeleteView(StaffRequiredMixin, View):
    template_name = "catalog/staff/product_confirm_delete.html"

    def get(self, request, *args, **kwargs):
        product = get_object_or_404(Product, pk=kwargs["pk"], deleted_at__isnull=True)
        return render(request, self.template_name, {"product": product})

    def post(self, request, *args, **kwargs):
        product = get_object_or_404(Product, pk=kwargs["pk"], deleted_at__isnull=True)
        services.soft_delete(product, request.user)
        messages.success(request, f"Deleted {product.sku}.")
        return redirect("catalog_staff:product_list")


class StaffProductRestoreView(StaffRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        product = get_object_or_404(Product, pk=kwargs["pk"], deleted_at__isnull=False)
        if services.restore(product, request.user):
            messages.success(request, f"Restored {product.sku}.")
        else:
            messages.error(
                request, f"Cannot restore {product.sku}: an active product already uses that SKU."
            )
        return redirect("catalog_staff:product_list")


class StaffStockAdjustView(StaffRequiredMixin, FormView):
    form_class = StockAdjustmentForm
    template_name = "catalog/staff/stock_adjust.html"

    def get_product(self) -> Product:
        return get_object_or_404(Product, pk=self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["product"] = self.get_product()
        return context

    def form_valid(self, form):
        product = self.get_product()
        delta = form.cleaned_data["delta"]
        if not services.adjust_stock(product, delta, self.request.user):
            form.add_error("delta", "Stock cannot fall below zero.")
            return self.form_invalid(form)
        messages.success(self.request, f"Stock for {product.sku} adjusted by {delta}.")
        return redirect(reverse("catalog_staff:product_list"))
