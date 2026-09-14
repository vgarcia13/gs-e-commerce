from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q

from catalog.models import Product


class Cart(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cart"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Cart for {self.user}"

    @property
    def total(self) -> Decimal:
        return sum((item.subtotal for item in self.items.all()), Decimal("0.00"))

    @property
    def item_count(self) -> int:
        return sum(item.quantity for item in self.items.all())


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="cart_items")
    quantity = models.PositiveIntegerField()
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["added_at"]
        constraints = [
            models.UniqueConstraint(fields=["cart", "product"], name="cartitem_unique_product"),
            models.CheckConstraint(condition=Q(quantity__gt=0), name="cartitem_quantity_positive"),
        ]

    def __str__(self) -> str:
        return f"{self.quantity} x {self.product.sku}"

    @property
    def subtotal(self) -> Decimal:
        return self.product.price * self.quantity
