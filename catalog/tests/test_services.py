from decimal import Decimal

import pytest
from django.utils import timezone

from catalog import services
from catalog.models import Product

pytestmark = pytest.mark.django_db


def make_product(**overrides):
    defaults = {
        "name": "Running Shoes",
        "sku": "RS-001",
        "description": "Lightweight running shoes",
        "category": "Footwear",
        "price": Decimal("89.99"),
        "stock": 150,
        "weight_kg": Decimal("0.35"),
    }
    return Product.objects.create(**{**defaults, **overrides})


def test_soft_delete_marks_the_row_without_removing_it():
    product = make_product()

    services.soft_delete(product)

    product.refresh_from_db()
    assert product.deleted_at is not None
    assert Product.objects.count() == 1
    assert Product.available.count() == 0


def test_restore_clears_the_deletion_marker():
    product = make_product()
    services.soft_delete(product)

    assert services.restore(product) is True

    product.refresh_from_db()
    assert product.deleted_at is None
    assert Product.available.count() == 1


def test_restore_fails_when_an_active_product_holds_the_sku():
    deleted = make_product()
    services.soft_delete(deleted)
    make_product(name="Replacement Shoes")

    assert services.restore(deleted) is False

    deleted.refresh_from_db()
    assert deleted.deleted_at is not None
    assert Product.available.count() == 1


def test_adjust_stock_increases():
    product = make_product(stock=10)

    assert services.adjust_stock(product, 5) is True

    product.refresh_from_db()
    assert product.stock == 15


def test_adjust_stock_decreases():
    product = make_product(stock=10)

    assert services.adjust_stock(product, -4) is True

    product.refresh_from_db()
    assert product.stock == 6


def test_adjust_stock_to_exactly_zero_is_allowed():
    product = make_product(stock=10)

    assert services.adjust_stock(product, -10) is True

    product.refresh_from_db()
    assert product.stock == 0


def test_adjust_stock_refuses_to_go_negative():
    product = make_product(stock=3)

    assert services.adjust_stock(product, -4) is False

    product.refresh_from_db()
    assert product.stock == 3


def test_adjust_stock_by_zero_is_a_no_op():
    product = make_product(stock=3)

    assert services.adjust_stock(product, 0) is True

    product.refresh_from_db()
    assert product.stock == 3


def test_concurrent_decrements_cannot_oversell():
    product = make_product(stock=1)

    first = services.adjust_stock(product, -1)
    second = services.adjust_stock(product, -1)

    assert (first, second) == (True, False)
    product.refresh_from_db()
    assert product.stock == 0
