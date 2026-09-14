import logging
import uuid
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from catalog.models import Product
from ordering.models import Cart, CartItem, Order, OrderItem
from ordering.payments import get_payment_gateway

logger = logging.getLogger(__name__)


class CartError(Exception):
    pass


class CheckoutError(Exception):
    pass


class PaymentDeclined(Exception):
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
    logger.info(
        "Cart for user %s now holds %s of %s",
        user.pk,
        item.quantity,
        product.sku,
        extra={
            "event": "cart.item_added",
            "actor_id": user.pk,
            "product_id": product.pk,
            "sku": product.sku,
            "quantity": item.quantity,
        },
    )
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
    logger.info(
        "Cart for user %s set to %s of %s",
        user.pk,
        quantity,
        product.sku,
        extra={
            "event": "cart.item_updated",
            "actor_id": user.pk,
            "product_id": product.pk,
            "sku": product.sku,
            "quantity": quantity,
        },
    )
    return item


def remove_item(user, product: Product) -> None:
    CartItem.objects.filter(cart__user=user, product=product).delete()
    logger.info(
        "Removed %s from cart for user %s",
        product.sku,
        user.pk,
        extra={
            "event": "cart.item_removed",
            "actor_id": user.pk,
            "product_id": product.pk,
            "sku": product.sku,
        },
    )


def _reference_for(order: Order) -> str:
    return f"ORD-{timezone.now():%Y}-{order.pk:05d}"


def place_order(user, card_number: str, idempotency_key: uuid.UUID) -> Order:
    """Charges the cart and records the order, rolling back stock if the payment is declined."""
    existing = Order.objects.filter(idempotency_key=idempotency_key).first()
    if existing is not None:
        logger.info(
            "Reusing order %s for a repeated idempotency key",
            existing.reference,
            extra={
                "event": "checkout.idempotent_replay",
                "actor_id": user.pk,
                "order_reference": existing.reference,
            },
        )
        return existing

    cart = get_cart(user)
    items = list(cart.items.select_related("product"))
    if not items:
        raise CheckoutError("Your cart is empty.")

    logger.info(
        "Checkout started by user %s with %s line(s)",
        user.pk,
        len(items),
        extra={"event": "checkout.started", "actor_id": user.pk, "lines": len(items)},
    )

    try:
        with transaction.atomic():
            total = Decimal("0.00")
            lines = []
            for item in items:
                product = item.product
                if product.deleted_at is not None:
                    raise CheckoutError(f"{product.name} is no longer available.")
                claimed = Product.objects.filter(
                    pk=product.pk, stock__gte=item.quantity
                ).update(stock=F("stock") - item.quantity)
                if not claimed:
                    logger.warning(
                        "Checkout for user %s refused: not enough stock for %s",
                        user.pk,
                        product.sku,
                        extra={
                            "event": "checkout.stock_unavailable",
                            "actor_id": user.pk,
                            "product_id": product.pk,
                            "sku": product.sku,
                            "requested": item.quantity,
                        },
                    )
                    raise CheckoutError(f"There is not enough stock for {product.name}.")
                total += product.price * item.quantity
                lines.append(
                    OrderItem(
                        product=product,
                        product_name=product.name,
                        product_sku=product.sku,
                        unit_price=product.price,
                        quantity=item.quantity,
                    )
                )

            order = Order(user=user, total=total, idempotency_key=idempotency_key)
            order.save()
            order.reference = _reference_for(order)

            for line in lines:
                line.order = order
            OrderItem.objects.bulk_create(lines)

            payment = get_payment_gateway().charge(total, card_number, str(idempotency_key))
            if not payment.success:
                raise PaymentDeclined(payment.message)

            order.payment_reference = payment.reference
            order.save(update_fields=["reference", "payment_reference"])
            cart.items.all().delete()
    except PaymentDeclined as declined:
        logger.warning(
            "Payment declined for user %s: %s",
            user.pk,
            declined,
            extra={
                "event": "payment.declined",
                "actor_id": user.pk,
                "amount": str(total),
                "reason": str(declined),
            },
        )
        raise CheckoutError(str(declined)) from declined
    except IntegrityError:
        duplicate = Order.objects.filter(idempotency_key=idempotency_key).first()
        if duplicate is not None:
            return duplicate
        raise

    logger.info(
        "Order %s placed by user %s for %s",
        order.reference,
        user.pk,
        order.total,
        extra={
            "event": "order.placed",
            "actor_id": user.pk,
            "order_reference": order.reference,
            "amount": str(order.total),
            "lines": len(lines),
            "payment_reference": order.payment_reference,
        },
    )
    return order
