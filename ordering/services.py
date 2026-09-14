import logging

from django.db import transaction

from catalog.models import Product
from ordering.models import Cart, CartItem

logger = logging.getLogger(__name__)


class CartError(Exception):
    pass


def get_cart(user) -> Cart:
    cart, _ = Cart.objects.get_or_create(user=user)
    return cart


def _check_available(product: Product, quantity: int) -> None:
    if product.deleted_at is not None:
        raise CartError("That product is no longer available.")
    if quantity > product.stock:
        if product.stock == 0:
            raise CartError(f"{product.name} is out of stock.")
        raise CartError(f"Only {product.stock} of {product.name} available.")


def add_to_cart(user, product: Product, quantity: int = 1) -> CartItem:
    """Adds to the existing line for this product rather than creating a second one."""
    if quantity < 1:
        raise CartError("Quantity must be at least 1.")
    cart = get_cart(user)
    with transaction.atomic():
        item = CartItem.objects.select_for_update().filter(cart=cart, product=product).first()
        wanted = (item.quantity if item else 0) + quantity
        _check_available(product, wanted)
        if item is None:
            item = CartItem.objects.create(cart=cart, product=product, quantity=wanted)
        else:
            item.quantity = wanted
            item.save(update_fields=["quantity"])
    logger.info("Cart for user %s now holds %s of %s", user.pk, item.quantity, product.sku)
    return item


def set_quantity(user, product: Product, quantity: int) -> CartItem:
    if quantity < 1:
        raise CartError("Quantity must be at least 1. Remove the item instead.")
    cart = get_cart(user)
    with transaction.atomic():
        item = CartItem.objects.select_for_update().filter(cart=cart, product=product).first()
        if item is None:
            raise CartError("That product is not in your cart.")
        _check_available(product, quantity)
        item.quantity = quantity
        item.save(update_fields=["quantity"])
    return item


def remove_item(user, product: Product) -> None:
    CartItem.objects.filter(cart__user=user, product=product).delete()
    logger.info("Removed %s from cart for user %s", product.sku, user.pk)
