import uuid
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from catalog.models import Product
from ordering import services
from ordering.models import Order, OrderItem
from ordering.payments import DECLINE_CARD, EXAMPLE_CARD

User = get_user_model()

pytestmark = pytest.mark.django_db

PASSWORD = "s3cret-pass-99"


def make_product(**overrides):
    defaults = {
        "name": "Running Shoes",
        "sku": "RS-001",
        "description": "Lightweight running shoes",
        "category": "Footwear",
        "price": Decimal("89.99"),
        "stock": 10,
        "weight_kg": Decimal("0.35"),
    }
    return Product.objects.create(**{**defaults, **overrides})


@pytest.fixture
def user():
    return User.objects.create_user(email="buyer@example.com", password=PASSWORD)


def checkout(user, card=EXAMPLE_CARD, key=None):
    return services.place_order(user, card, key or uuid.uuid4())


def test_successful_checkout_creates_an_order(user):
    product = make_product(stock=10)
    services.add_to_cart(user, product, 2)

    order = checkout(user)

    assert order.total == Decimal("179.98")
    assert order.user == user
    assert order.payment_reference.startswith("FAKE-")


def test_successful_checkout_decrements_stock(user):
    product = make_product(stock=10)
    services.add_to_cart(user, product, 3)

    checkout(user)

    product.refresh_from_db()
    assert product.stock == 7


def test_successful_checkout_empties_the_cart(user):
    product = make_product(stock=10)
    services.add_to_cart(user, product, 2)

    checkout(user)

    assert services.get_cart(user).items.count() == 0


def test_order_reference_is_readable_and_unique(user):
    product = make_product(stock=10)
    services.add_to_cart(user, product, 1)
    first = checkout(user)
    services.add_to_cart(user, product, 1)
    second = checkout(user)

    year = timezone.now().year
    assert first.reference.startswith(f"ORD-{year}-")
    assert first.reference != second.reference


def test_declined_payment_creates_no_order(user):
    product = make_product(stock=10)
    services.add_to_cart(user, product, 2)

    with pytest.raises(services.CheckoutError, match="declined"):
        checkout(user, card=DECLINE_CARD)

    assert Order.objects.count() == 0
    assert OrderItem.objects.count() == 0


def test_declined_payment_rolls_stock_back(user):
    product = make_product(stock=10)
    services.add_to_cart(user, product, 3)

    with pytest.raises(services.CheckoutError):
        checkout(user, card=DECLINE_CARD)

    product.refresh_from_db()
    assert product.stock == 10


def test_declined_payment_leaves_the_cart_intact(user):
    product = make_product(stock=10)
    services.add_to_cart(user, product, 3)

    with pytest.raises(services.CheckoutError):
        checkout(user, card=DECLINE_CARD)

    assert services.get_cart(user).items.get().quantity == 3


def test_repeating_an_idempotency_key_does_not_charge_twice(user):
    product = make_product(stock=10)
    services.add_to_cart(user, product, 2)
    key = uuid.uuid4()

    first = checkout(user, key=key)
    second = checkout(user, key=key)

    assert first.pk == second.pk
    assert Order.objects.count() == 1
    product.refresh_from_db()
    assert product.stock == 8


def test_order_items_snapshot_price_and_naming(user):
    product = make_product(stock=10, price=Decimal("89.99"))
    services.add_to_cart(user, product, 1)
    order = checkout(user)

    product.name = "Renamed Shoes"
    product.price = Decimal("129.99")
    product.sku = "RS-999"
    product.save()

    item = order.items.get()
    assert item.product_name == "Running Shoes"
    assert item.product_sku == "RS-001"
    assert item.unit_price == Decimal("89.99")
    assert order.total == Decimal("89.99")


def test_checkout_refuses_when_stock_dropped_since_adding(user):
    product = make_product(stock=10)
    services.add_to_cart(user, product, 5)
    Product.objects.filter(pk=product.pk).update(stock=2)

    with pytest.raises(services.CheckoutError, match="not enough stock"):
        checkout(user)

    assert Order.objects.count() == 0
    product.refresh_from_db()
    assert product.stock == 2


def test_checkout_refuses_a_soft_deleted_product(user):
    product = make_product(stock=10)
    services.add_to_cart(user, product, 1)
    Product.objects.filter(pk=product.pk).update(deleted_at=timezone.now())

    with pytest.raises(services.CheckoutError, match="no longer available"):
        checkout(user)

    assert Order.objects.count() == 0


def test_empty_cart_cannot_be_checked_out(user):
    with pytest.raises(services.CheckoutError, match="empty"):
        checkout(user)


def test_two_buyers_cannot_take_the_same_last_unit(user):
    other = User.objects.create_user(email="other@example.com", password=PASSWORD)
    product = make_product(stock=1)
    services.add_to_cart(user, product, 1)
    services.add_to_cart(other, product, 1)

    checkout(user)

    with pytest.raises(services.CheckoutError, match="not enough stock"):
        checkout(other)

    product.refresh_from_db()
    assert product.stock == 0
    assert Order.objects.count() == 1


def test_partial_failure_rolls_back_every_line(user):
    shoes = make_product(stock=10)
    cable = make_product(sku="UC-003", name="USB-C Cable", price=Decimal("4.99"), stock=1)
    services.add_to_cart(user, shoes, 2)
    services.add_to_cart(user, cable, 1)
    Product.objects.filter(pk=cable.pk).update(stock=0)

    with pytest.raises(services.CheckoutError):
        checkout(user)

    shoes.refresh_from_db()
    assert shoes.stock == 10
    assert Order.objects.count() == 0


def test_card_number_is_never_persisted(user):
    product = make_product(stock=10)
    services.add_to_cart(user, product, 1)

    order = checkout(user, card=EXAMPLE_CARD)

    stored = " ".join(str(value) for value in Order.objects.filter(pk=order.pk).values()[0].values())
    stored += " ".join(str(value) for value in OrderItem.objects.values()[0].values())
    assert EXAMPLE_CARD not in stored
