from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.utils import timezone

from catalog.models import Product
from ordering import services
from ordering.models import Cart, CartItem

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


def test_cart_is_created_on_first_use(user):
    assert Cart.objects.count() == 0

    services.get_cart(user)

    assert Cart.objects.count() == 1


def test_adding_the_same_product_twice_merges_into_one_line(user):
    product = make_product()

    services.add_to_cart(user, product, 2)
    services.add_to_cart(user, product, 3)

    items = CartItem.objects.filter(cart__user=user)
    assert items.count() == 1
    assert items.first().quantity == 5


def test_adding_more_than_stock_is_refused(user):
    product = make_product(stock=3)

    with pytest.raises(services.CartError, match="Only 3"):
        services.add_to_cart(user, product, 4)

    assert CartItem.objects.count() == 0


def test_merged_quantity_is_checked_against_stock(user):
    product = make_product(stock=5)
    services.add_to_cart(user, product, 3)

    with pytest.raises(services.CartError, match="Only 5"):
        services.add_to_cart(user, product, 3)

    assert CartItem.objects.get(cart__user=user).quantity == 3


def test_out_of_stock_product_cannot_be_added(user):
    product = make_product(stock=0)

    with pytest.raises(services.CartError, match="out of stock"):
        services.add_to_cart(user, product, 1)


def test_soft_deleted_product_cannot_be_added(user):
    product = make_product()
    product.deleted_at = timezone.now()
    product.save()

    with pytest.raises(services.CartError, match="no longer available"):
        services.add_to_cart(user, product, 1)


def test_quantity_below_one_is_refused(user):
    product = make_product()

    with pytest.raises(services.CartError):
        services.add_to_cart(user, product, 0)


def test_set_quantity_replaces_rather_than_adds(user):
    product = make_product(stock=10)
    services.add_to_cart(user, product, 4)

    services.set_quantity(user, product, 2)

    assert CartItem.objects.get(cart__user=user).quantity == 2


def test_set_quantity_beyond_stock_is_refused(user):
    product = make_product(stock=5)
    services.add_to_cart(user, product, 2)

    with pytest.raises(services.CartError):
        services.set_quantity(user, product, 6)

    assert CartItem.objects.get(cart__user=user).quantity == 2


def test_set_quantity_to_zero_is_refused(user):
    product = make_product()
    services.add_to_cart(user, product, 2)

    with pytest.raises(services.CartError, match="Remove the item"):
        services.set_quantity(user, product, 0)


def test_set_quantity_for_a_product_not_in_the_cart_is_refused(user):
    product = make_product()

    with pytest.raises(services.CartError, match="not in your cart"):
        services.set_quantity(user, product, 1)


def test_remove_item_deletes_the_line(user):
    product = make_product()
    services.add_to_cart(user, product, 2)

    services.remove_item(user, product)

    assert CartItem.objects.count() == 0


def test_cart_total_is_exact_decimal(user):
    shoes = make_product(price=Decimal("89.99"), stock=10)
    cable = make_product(sku="UC-003", name="USB-C Cable", price=Decimal("4.99"), stock=10)
    services.add_to_cart(user, shoes, 2)
    services.add_to_cart(user, cable, 3)

    cart = services.get_cart(user)

    assert cart.total == Decimal("194.95")
    assert cart.item_count == 5


def test_database_rejects_a_duplicate_line_for_the_same_product(user):
    product = make_product()
    cart = services.get_cart(user)
    CartItem.objects.create(cart=cart, product=product, quantity=1)

    with pytest.raises(IntegrityError):
        CartItem.objects.create(cart=cart, product=product, quantity=1)


def test_database_rejects_a_zero_quantity_line(user):
    product = make_product()
    cart = services.get_cart(user)

    with pytest.raises(IntegrityError):
        CartItem.objects.create(cart=cart, product=product, quantity=0)


def test_carts_are_isolated_between_users(user):
    other = User.objects.create_user(email="other@example.com", password=PASSWORD)
    product = make_product()
    services.add_to_cart(user, product, 2)

    assert services.get_cart(other).items.count() == 0
