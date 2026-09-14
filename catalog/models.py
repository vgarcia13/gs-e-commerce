from django.db import models
from django.db.models import Q


class AvailableProductManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


class Product(models.Model):
    name = models.CharField(max_length=200)
    sku = models.CharField(max_length=50)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.PositiveIntegerField()
    weight_kg = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    available = AvailableProductManager()

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["sku"],
                condition=Q(deleted_at__isnull=True),
                name="product_unique_active_sku",
            ),
            models.CheckConstraint(
                condition=~Q(name=""),
                name="product_name_not_empty",
            ),
            models.CheckConstraint(
                condition=~Q(sku=""),
                name="product_sku_not_empty",
            ),
            models.CheckConstraint(
                condition=~Q(category=""),
                name="product_category_not_empty",
            ),
            models.CheckConstraint(
                condition=Q(price__gte=0),
                name="product_price_not_negative",
            ),
            models.CheckConstraint(
                condition=Q(weight_kg__isnull=True) | Q(weight_kg__gte=0),
                name="product_weight_not_negative",
            ),
        ]
        indexes = [
            models.Index(fields=["category"]),
            models.Index(fields=["name"]),
        ]

    def __str__(self):
        return f"{self.sku} - {self.name}"

    def save(self, *args, **kwargs):
        """Normalises SKU to uppercase and trims the free-text fields before writing."""
        self.sku = self.sku.strip().upper()
        self.name = self.name.strip()
        self.category = self.category.strip()
        super().save(*args, **kwargs)

    @property
    def is_available(self) -> bool:
        return self.deleted_at is None and self.stock > 0
