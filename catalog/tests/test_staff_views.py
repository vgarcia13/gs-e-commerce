from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from catalog.models import Product

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
        "stock": 150,
        "weight_kg": Decimal("0.35"),
    }
    return Product.objects.create(**{**defaults, **overrides})


@pytest.fixture
def staff(client):
    user = User.objects.create_user(email="staff@example.com", password=PASSWORD, is_staff=True)
    client.login(email=user.email, password=PASSWORD)
    return user


@pytest.fixture
def customer(client):
    user = User.objects.create_user(email="buyer@example.com", password=PASSWORD)
    client.login(email=user.email, password=PASSWORD)
    return user


def product_form_payload(**overrides):
    return {
        "name": "Trail Shoes",
        "sku": "TS-100",
        "description": "Grippy trail shoes",
        "category": "Footwear",
        "price": "79.99",
        "stock": "25",
        "weight_kg": "0.40",
        **overrides,
    }


def staff_urls(product):
    return [
        reverse("catalog_staff:product_list"),
        reverse("catalog_staff:product_create"),
        reverse("catalog_staff:product_update", args=[product.pk]),
        reverse("catalog_staff:product_delete", args=[product.pk]),
        reverse("catalog_staff:stock_adjust", args=[product.pk]),
    ]


def test_anonymous_users_are_redirected_to_login(client):
    product = make_product()

    for url in staff_urls(product):
        response = client.get(url)
        assert response.status_code == 302, url
        assert reverse("accounts:login") in response.url, url


def test_customers_are_sent_back_to_the_catalogue_with_a_warning(client, customer):
    product = make_product()

    for url in staff_urls(product):
        response = client.get(url, follow=True)
        assert response.redirect_chain[-1][0] == reverse("catalog:product_list"), url
        assert "staff only" in response.content.decode(), url


def test_staff_can_reach_every_page(client, staff):
    product = make_product()

    for url in staff_urls(product):
        assert client.get(url).status_code == 200, url


def test_staff_can_create_a_product(client, staff):
    response = client.post(reverse("catalog_staff:product_create"), product_form_payload())

    assert response.status_code == 302
    assert Product.objects.get(sku="TS-100").stock == 25


def test_created_sku_is_stored_uppercase(client, staff):
    client.post(reverse("catalog_staff:product_create"), product_form_payload(sku="ts-100"))

    assert Product.objects.filter(sku="TS-100").exists()


def test_duplicate_active_sku_is_a_form_error_not_a_server_error(client, staff):
    make_product(sku="TS-100", name="Existing")

    response = client.post(reverse("catalog_staff:product_create"), product_form_payload(sku="ts-100"))

    assert response.status_code == 200
    assert Product.objects.filter(sku="TS-100").count() == 1


def test_sku_may_be_reused_when_the_holder_is_soft_deleted(client, staff):
    existing = make_product(sku="TS-100", name="Existing")
    client.post(reverse("catalog_staff:product_delete", args=[existing.pk]))

    response = client.post(reverse("catalog_staff:product_create"), product_form_payload(sku="TS-100"))

    assert response.status_code == 302
    assert Product.objects.filter(sku="TS-100").count() == 2


def test_edit_form_does_not_expose_stock(client, staff):
    product = make_product(stock=150)

    body = client.get(reverse("catalog_staff:product_update", args=[product.pk])).content.decode()

    assert 'name="stock"' not in body


def test_editing_cannot_change_stock(client, staff):
    product = make_product(stock=150)

    client.post(
        reverse("catalog_staff:product_update", args=[product.pk]),
        product_form_payload(sku="RS-001", stock="9999"),
    )

    product.refresh_from_db()
    assert product.stock == 150


def test_delete_hides_the_product_from_the_public_catalogue(client, staff):
    product = make_product()

    client.post(reverse("catalog_staff:product_delete", args=[product.pk]))

    product.refresh_from_db()
    assert product.deleted_at is not None
    assert client.get(reverse("catalog:product_list")).context["products"].count() == 0


def test_restore_brings_a_product_back(client, staff):
    product = make_product()
    client.post(reverse("catalog_staff:product_delete", args=[product.pk]))

    client.post(reverse("catalog_staff:product_restore", args=[product.pk]))

    product.refresh_from_db()
    assert product.deleted_at is None


def test_restore_reports_a_sku_collision_instead_of_failing(client, staff):
    product = make_product()
    client.post(reverse("catalog_staff:product_delete", args=[product.pk]))
    client.post(reverse("catalog_staff:product_create"), product_form_payload(sku="RS-001"))

    response = client.post(reverse("catalog_staff:product_restore", args=[product.pk]), follow=True)

    product.refresh_from_db()
    assert product.deleted_at is not None
    assert "already uses that SKU" in response.content.decode()


def test_staff_list_includes_soft_deleted_products(client, staff):
    product = make_product()
    client.post(reverse("catalog_staff:product_delete", args=[product.pk]))

    body = client.get(reverse("catalog_staff:product_list")).content.decode()

    assert "RS-001" in body
    assert "Deleted" in body


def test_stock_adjustment_applies_a_relative_change(client, staff):
    product = make_product(stock=10)

    client.post(reverse("catalog_staff:stock_adjust", args=[product.pk]), {"delta": "-4"})

    product.refresh_from_db()
    assert product.stock == 6


def test_stock_adjustment_below_zero_is_rejected(client, staff):
    product = make_product(stock=3)

    response = client.post(reverse("catalog_staff:stock_adjust", args=[product.pk]), {"delta": "-4"})

    product.refresh_from_db()
    assert product.stock == 3
    assert "Stock cannot fall below zero" in response.content.decode()


def test_zero_stock_adjustment_is_rejected(client, staff):
    product = make_product(stock=3)

    response = client.post(reverse("catalog_staff:stock_adjust", args=[product.pk]), {"delta": "0"})

    assert response.status_code == 200
    product.refresh_from_db()
    assert product.stock == 3


def test_staff_nav_link_is_hidden_from_customers(client, customer):
    body = client.get(reverse("catalog:product_list")).content.decode()

    assert "Manage products" not in body


def test_staff_nav_link_is_shown_to_staff(client, staff):
    body = client.get(reverse("catalog:product_list")).content.decode()

    assert "Manage products" in body
