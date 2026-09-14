import uuid

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import DetailView, FormView, ListView, TemplateView

from catalog.models import Product
from ordering import services
from ordering.forms import CheckoutForm
from ordering.models import Order


class CartView(LoginRequiredMixin, TemplateView):
    template_name = "ordering/cart.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["cart"] = services.get_cart(self.request.user)
        return context


class CartActionView(LoginRequiredMixin, View):
    def get_product(self) -> Product:
        return get_object_or_404(Product, pk=self.kwargs["pk"])

    def redirect_back(self):
        return redirect(self.request.POST.get("next") or "ordering:cart")


class AddToCartView(CartActionView):
    def post(self, request, *args, **kwargs):
        product = self.get_product()
        try:
            quantity = int(request.POST.get("quantity", 1))
        except ValueError:
            quantity = 1
        try:
            services.add_to_cart(request.user, product, quantity)
        except services.CartError as error:
            messages.error(request, str(error))
        else:
            messages.success(request, f"Added {product.name} to your cart.")
        return self.redirect_back()


class UpdateCartItemView(CartActionView):
    def post(self, request, *args, **kwargs):
        product = self.get_product()
        try:
            quantity = int(request.POST.get("quantity", 0))
        except ValueError:
            quantity = 0
        try:
            services.set_quantity(request.user, product, quantity)
        except services.CartError as error:
            messages.error(request, str(error))
        else:
            messages.success(request, f"Updated {product.name}.")
        return self.redirect_back()


class RemoveCartItemView(CartActionView):
    def post(self, request, *args, **kwargs):
        product = self.get_product()
        services.remove_item(request.user, product)
        messages.success(request, f"Removed {product.name} from your cart.")
        return self.redirect_back()


class CheckoutView(LoginRequiredMixin, FormView):
    form_class = CheckoutForm
    template_name = "ordering/checkout.html"

    def get_initial(self):
        return {**super().get_initial(), "idempotency_key": uuid.uuid4()}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["cart"] = services.get_cart(self.request.user)
        return context

    def form_valid(self, form):
        try:
            order = services.place_order(
                self.request.user,
                form.cleaned_data["card_number"],
                form.cleaned_data["idempotency_key"],
            )
        except services.CheckoutError as error:
            messages.error(self.request, str(error))
            return redirect("ordering:cart")
        messages.success(self.request, f"Order {order.reference} placed.")
        return redirect("orders:order_detail", reference=order.reference)


class OrderListView(LoginRequiredMixin, ListView):
    template_name = "ordering/order_list.html"
    context_object_name = "orders"
    paginate_by = 20

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).prefetch_related("items")


class OrderDetailView(LoginRequiredMixin, DetailView):
    template_name = "ordering/order_detail.html"
    context_object_name = "order"
    slug_field = "reference"
    slug_url_kwarg = "reference"

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).prefetch_related("items")
