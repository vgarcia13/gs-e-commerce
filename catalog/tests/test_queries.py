from decimal import Decimal

import pytest
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


@pytest.mark.parametrize(
    "term",
    ["Running", "running", "Lightweight", "RS-001", "rs-001", "Footwear"],
)
def test_search_matches_each_indexed_field_case_insensitively(term):
    make_product()

    assert Product.available.search(term).count() == 1


def test_search_excludes_non_matching_products():
    make_product()
    make_product(sku="BS-021", name="Bluetooth Speaker", description="Speaker", category="Electronics")

    assert [p.sku for p in Product.available.search("Bluetooth")] == ["BS-021"]


def test_empty_search_returns_everything():
    make_product()
    make_product(sku="BS-021", name="Bluetooth Speaker")

    assert Product.available.search("").count() == 2
    assert Product.available.search("   ").count() == 2


def test_like_wildcards_are_treated_as_literal_text():
    make_product(sku="PCT-001", name="100% Cotton Shirt")
    make_product(sku="RS-001", name="Running Shoes")

    assert [p.sku for p in Product.available.search("%")] == ["PCT-001"]


def test_underscore_is_treated_as_literal_text():
    make_product(sku="UN-001", name="Under_score Product")
    make_product(sku="RS-001", name="Running Shoes")

    assert [p.sku for p in Product.available.search("_")] == ["UN-001"]


def test_search_excludes_soft_deleted_products():
    removed = make_product()
    removed.deleted_at = timezone.now()
    removed.save()

    assert Product.available.search("Running").count() == 0


def test_in_stock_excludes_zero_stock():
    make_product(sku="VC-001", name="Vintage Clock", stock=0)
    make_product(sku="RS-001", stock=5)

    assert [p.sku for p in Product.available.in_stock()] == ["RS-001"]


def test_in_category_is_case_insensitive_and_exact():
    make_product(category="Footwear")
    make_product(sku="BS-021", name="Speaker", category="Electronics")

    assert [p.sku for p in Product.available.in_category("footwear")] == ["RS-001"]
    assert Product.available.in_category("").count() == 2


def test_filters_compose():
    make_product(sku="RS-001", category="Footwear", stock=10)
    make_product(sku="RS-002", name="Trail Shoes", category="Footwear", stock=0)
    make_product(sku="BS-021", name="Speaker", category="Electronics", stock=10)

    results = Product.available.search("Shoes").in_category("Footwear").in_stock()

    assert [p.sku for p in results] == ["RS-001"]
