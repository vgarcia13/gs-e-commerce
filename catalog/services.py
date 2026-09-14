import logging

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from catalog.models import Product

logger = logging.getLogger(__name__)


def _product_fields(product: Product) -> dict:
    return {"product_id": product.pk, "sku": product.sku}


def record_created(product: Product, user) -> None:
    logger.info(
        "Product %s created by user %s",
        product.sku,
        user.pk,
        extra={"event": "product.created", "actor_id": user.pk, **_product_fields(product)},
    )


def record_updated(product: Product, user) -> None:
    logger.info(
        "Product %s updated by user %s",
        product.sku,
        user.pk,
        extra={
            "event": "product.updated",
            "actor_id": user.pk,
            "price": str(product.price),
            **_product_fields(product),
        },
    )


def soft_delete(product: Product, user) -> None:
    product.deleted_at = timezone.now()
    product.save(update_fields=["deleted_at", "updated_at"])
    logger.info(
        "Product %s soft deleted by user %s",
        product.sku,
        user.pk,
        extra={"event": "product.deleted", "actor_id": user.pk, **_product_fields(product)},
    )


def restore(product: Product, user) -> bool:
    """Clears the deletion marker, returning False when an active product already holds the SKU."""
    try:
        with transaction.atomic():
            product.deleted_at = None
            product.save(update_fields=["deleted_at", "updated_at"])
    except IntegrityError:
        logger.warning(
            "Cannot restore product %s: SKU is in use",
            product.sku,
            extra={
                "event": "product.restore_refused",
                "actor_id": user.pk,
                "reason": "sku_in_use",
                **_product_fields(product),
            },
        )
        return False
    logger.info(
        "Product %s restored by user %s",
        product.sku,
        user.pk,
        extra={"event": "product.restored", "actor_id": user.pk, **_product_fields(product)},
    )
    return True


def adjust_stock(product: Product, delta: int, user) -> bool:
    """Applies a relative stock change in a single statement, returning False if it would go negative."""
    if delta == 0:
        return True
    updated = (
        Product.objects.filter(pk=product.pk, stock__gte=max(-delta, 0))
        .update(stock=F("stock") + delta, updated_at=timezone.now())
    )
    if not updated:
        logger.warning(
            "Stock adjustment of %s refused for product %s",
            delta,
            product.sku,
            extra={
                "event": "product.stock_adjust_refused",
                "actor_id": user.pk,
                "delta": delta,
                "reason": "would_go_negative",
                **_product_fields(product),
            },
        )
        return False
    product.refresh_from_db(fields=["stock"])
    logger.info(
        "Stock for %s adjusted by %s to %s by user %s",
        product.sku,
        delta,
        product.stock,
        user.pk,
        extra={
            "event": "product.stock_adjusted",
            "actor_id": user.pk,
            "delta": delta,
            "stock": product.stock,
            **_product_fields(product),
        },
    )
    return True
