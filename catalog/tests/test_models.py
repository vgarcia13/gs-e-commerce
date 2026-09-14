from decimal import Decimal

import pytest
from django.db import IntegrityError
from django.utils import timezone

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


def test_sku_is_uppercased_and_trimmed_on_save():
    product = make_product(sku="  rs-001  ")
    assert product.sku == "RS-001"


def test_duplicate_active_sku_is_rejected():
    make_product(sku="RS-001")
    with pytest.raises(IntegrityError):
        make_product(sku="rs-001", name="Another Shoe")


def test_sku_can_be_reused_after_soft_delete():
    original = make_product(sku="RS-001")
    original.deleted_at = timezone.now()
    original.save()

    replacement = make_product(sku="RS-001", name="Running Shoes v2")

    assert replacement.pk != original.pk
    assert Product.objects.filter(sku="RS-001").count() == 2


def test_negative_stock_is_rejected():
    with pytest.raises(IntegrityError):
        make_product(stock=-5)


def test_negative_price_is_rejected():
    with pytest.raises(IntegrityError):
        make_product(price=Decimal("-1.00"))


def test_price_round_trips_as_exact_decimal():
    make_product(price=Decimal("19.99"))
    stored = Product.objects.get(sku="RS-001").price
    assert stored == Decimal("19.99")
    assert isinstance(stored, Decimal)


def test_whitespace_only_name_is_rejected():
    with pytest.raises(IntegrityError):
        make_product(name="     ")


def test_empty_category_is_rejected():
    with pytest.raises(IntegrityError):
        make_product(category="")


def test_available_manager_excludes_soft_deleted():
    live = make_product(sku="RS-001")
    removed = make_product(sku="BS-021", name="Bluetooth Speaker")
    removed.deleted_at = timezone.now()
    removed.save()

    assert list(Product.available.all()) == [live]
    assert Product.objects.count() == 2


def test_weight_kg_is_optional():
    product = make_product(weight_kg=None)
    assert product.weight_kg is None


def test_is_available_requires_stock_and_not_deleted():
    in_stock = make_product(sku="RS-001", stock=5)
    out_of_stock = make_product(sku="VC-001", name="Vintage Clock", stock=0)

    assert in_stock.is_available is True
    assert out_of_stock.is_available is False
