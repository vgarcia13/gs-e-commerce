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


class Order(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders"
    )
    reference = models.CharField(max_length=20, unique=True, null=True)
    idempotency_key = models.UUIDField(unique=True)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    payment_reference = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=Q(total__gte=0), name="order_total_not_negative"),
        ]

    def __str__(self) -> str:
        return self.reference or f"Order {self.pk}"

    @property
    def item_count(self) -> int:
        return sum(item.quantity for item in self.items.all())


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="order_items")
    product_name = models.CharField(max_length=200)
    product_sku = models.CharField(max_length=50)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField()

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name="orderitem_quantity_positive"),
            models.CheckConstraint(
                condition=Q(unit_price__gte=0), name="orderitem_unit_price_not_negative"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.quantity} x {self.product_sku}"

    @property
    def subtotal(self) -> Decimal:
        return self.unit_price * self.quantity
