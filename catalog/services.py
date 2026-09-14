import logging

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from catalog.models import Product

logger = logging.getLogger(__name__)


def soft_delete(product: Product) -> None:
    product.deleted_at = timezone.now()
    product.save(update_fields=["deleted_at", "updated_at"])
    logger.info("Product %s (SKU %s) soft deleted", product.pk, product.sku)


def restore(product: Product) -> bool:
    """Clears the deletion marker, returning False when an active product already holds the SKU."""
    try:
        with transaction.atomic():
            product.deleted_at = None
            product.save(update_fields=["deleted_at", "updated_at"])
    except IntegrityError:
        logger.warning("Cannot restore product %s: SKU %s is in use", product.pk, product.sku)
        return False
    logger.info("Product %s (SKU %s) restored", product.pk, product.sku)
    return True


def adjust_stock(product: Product, delta: int) -> bool:
    """Applies a relative stock change in a single statement, returning False if it would go negative."""
    if delta == 0:
        return True
    updated = (
        Product.objects.filter(pk=product.pk, stock__gte=max(-delta, 0))
        .update(stock=F("stock") + delta, updated_at=timezone.now())
    )
    if not updated:
        logger.warning("Stock adjustment of %s refused for product %s", delta, product.pk)
        return False
    logger.info("Stock adjusted by %s for product %s (SKU %s)", delta, product.pk, product.sku)
    return True
