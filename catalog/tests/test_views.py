from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from catalog.models import Product

pytestmark = pytest.mark.django_db

LIST_URL = reverse("catalog:product_list")


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


def make_many(count: int):
    return [make_product(sku=f"SK-{index:03d}", name=f"Product {index}") for index in range(count)]


def test_list_renders_products(client):
    make_product()

    response = client.get(LIST_URL)

    assert response.status_code == 200
    assert b"Running Shoes" in response.content


def test_list_narrows_by_search_term(client):
    make_product()
    make_product(sku="BS-021", name="Bluetooth Speaker", description="Speaker", category="Electronics")

    response = client.get(LIST_URL, {"q": "Bluetooth"})

    assert [p.sku for p in response.context["products"]] == ["BS-021"]


def test_list_filters_by_category_and_stock(client):
    make_product(sku="RS-001", category="Footwear", stock=10)
    make_product(sku="RS-002", name="Trail Shoes", category="Footwear", stock=0)

    response = client.get(LIST_URL, {"category": "Footwear", "in_stock": "on"})

    assert [p.sku for p in response.context["products"]] == ["RS-001"]


def test_list_hides_soft_deleted_products(client):
    removed = make_product()
    removed.deleted_at = timezone.now()
    removed.save()

    response = client.get(LIST_URL)

    assert list(response.context["products"]) == []


def test_list_shows_out_of_stock_products_as_unavailable(client):
    make_product(sku="VC-001", name="Vintage Clock", stock=0)

    response = client.get(LIST_URL)

    assert b"Vintage Clock" in response.content
    assert b"Out of stock" in response.content


def test_list_paginates_at_twenty(client):
    make_many(21)

    first = client.get(LIST_URL)
    second = client.get(LIST_URL, {"page": 2})

    assert len(first.context["products"]) == 20
    assert len(second.context["products"]) == 1


def test_overlong_search_term_does_not_break_the_page(client):
    make_product()

    response = client.get(LIST_URL, {"q": "x" * 500})

    assert response.status_code == 200


def test_detail_renders_product(client):
    product = make_product()

    response = client.get(reverse("catalog:product_detail", args=[product.pk]))

    assert response.status_code == 200
    assert b"Lightweight running shoes" in response.content


def test_detail_returns_404_for_soft_deleted_product(client):
    product = make_product()
    product.deleted_at = timezone.now()
    product.save()

    response = client.get(reverse("catalog:product_detail", args=[product.pk]))

    assert response.status_code == 404


def test_markup_in_product_name_is_escaped_in_the_list(client):
    make_product(sku="XS-001", name="<script>alert('xss')</script>")

    response = client.get(LIST_URL)
    body = response.content.decode()

    assert "<script>alert('xss')</script>" not in body
    assert "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;" in body


def test_markup_in_product_name_is_escaped_on_the_detail_page(client):
    product = make_product(sku="XS-001", name="<script>alert('xss')</script>")

    response = client.get(reverse("catalog:product_detail", args=[product.pk]))
    body = response.content.decode()

    assert "<script>alert('xss')</script>" not in body
    assert "&lt;script&gt;" in body


def test_search_term_is_escaped_when_reflected_into_the_page(client):
    response = client.get(LIST_URL, {"q": "<script>alert(1)</script>"})
    body = response.content.decode()

    assert "<script>alert(1)</script>" not in body
