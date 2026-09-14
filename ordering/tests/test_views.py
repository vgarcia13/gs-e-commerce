from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from catalog.models import Product
from ordering import services
from ordering.models import CartItem

User = get_user_model()

pytestmark = pytest.mark.django_db

PASSWORD = "s3cret-pass-99"
CART_URL = reverse("ordering:cart")
LOGIN_URL = reverse("accounts:login")


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
def buyer(client):
    user = User.objects.create_user(email="buyer@example.com", password=PASSWORD)
    client.login(email=user.email, password=PASSWORD)
    return user


def test_cart_page_requires_login(client):
    response = client.get(CART_URL)

    assert response.status_code == 302
    assert LOGIN_URL in response.url


def test_anonymous_add_is_redirected_to_login(client):
    product = make_product()

    response = client.post(reverse("ordering:add", args=[product.pk]))

    assert response.status_code == 302
    assert LOGIN_URL in response.url
    assert CartItem.objects.count() == 0


def test_product_page_offers_login_instead_of_add_when_anonymous(client):
    product = make_product()

    body = client.get(reverse("catalog:product_detail", args=[product.pk])).content.decode()

    assert "Log in to buy" in body
    assert "Add to cart" not in body


def test_product_page_offers_add_to_cart_when_logged_in(client, buyer):
    product = make_product()

    body = client.get(reverse("catalog:product_detail", args=[product.pk])).content.decode()

    assert "Add to cart" in body


def test_out_of_stock_product_offers_no_purchase_control(client, buyer):
    product = make_product(sku="VC-001", name="Vintage Clock", stock=0)

    body = client.get(reverse("catalog:product_detail", args=[product.pk])).content.decode()

    assert "Add to cart" not in body


def test_adding_a_product_populates_the_cart(client, buyer):
    product = make_product()

    client.post(reverse("ordering:add", args=[product.pk]), {"quantity": "2"})

    assert CartItem.objects.get(cart__user=buyer).quantity == 2


def test_adding_beyond_stock_shows_an_error(client, buyer):
    product = make_product(stock=2)

    response = client.post(
        reverse("ordering:add", args=[product.pk]), {"quantity": "5"}, follow=True
    )

    assert "Only 2" in response.content.decode()
    assert CartItem.objects.count() == 0


def test_non_numeric_quantity_falls_back_to_one(client, buyer):
    product = make_product()

    client.post(reverse("ordering:add", args=[product.pk]), {"quantity": "abc"})

    assert CartItem.objects.get(cart__user=buyer).quantity == 1


def test_cart_page_lists_items_and_total(client, buyer):
    shoes = make_product()
    cable = make_product(sku="UC-003", name="USB-C Cable", price=Decimal("4.99"))
    services.add_to_cart(buyer, shoes, 2)
    services.add_to_cart(buyer, cable, 1)

    body = client.get(CART_URL).content.decode()

    assert "Running Shoes" in body
    assert "USB-C Cable" in body
    assert "184.97" in body


def test_updating_quantity_from_the_cart_page(client, buyer):
    product = make_product()
    services.add_to_cart(buyer, product, 4)

    client.post(reverse("ordering:update", args=[product.pk]), {"quantity": "2"})

    assert CartItem.objects.get(cart__user=buyer).quantity == 2


def test_removing_an_item_from_the_cart_page(client, buyer):
    product = make_product()
    services.add_to_cart(buyer, product, 4)

    client.post(reverse("ordering:remove", args=[product.pk]))

    assert CartItem.objects.count() == 0


def test_a_user_cannot_change_another_users_cart(client, buyer):
    other = User.objects.create_user(email="other@example.com", password=PASSWORD)
    product = make_product()
    services.add_to_cart(other, product, 3)

    client.post(reverse("ordering:remove", args=[product.pk]))

    assert CartItem.objects.get(cart__user=other).quantity == 3


def test_cart_badge_counts_items(client, buyer):
    product = make_product()
    services.add_to_cart(buyer, product, 3)

    body = client.get(reverse("catalog:product_list")).content.decode()

    assert "Cart (3)" in body


def test_cart_badge_is_absent_when_empty(client, buyer):
    body = client.get(reverse("catalog:product_list")).content.decode()

    assert "Cart (" not in body


def test_add_redirects_back_to_the_product_page(client, buyer):
    product = make_product()
    detail = reverse("catalog:product_detail", args=[product.pk])

    response = client.post(
        reverse("ordering:add", args=[product.pk]), {"quantity": "1", "next": detail}
    )

    assert response.url == detail


def test_markup_in_a_cart_product_name_is_escaped(client, buyer):
    product = make_product(sku="XS-001", name="<script>alert('xss')</script>")
    services.add_to_cart(buyer, product, 1)

    body = client.get(CART_URL).content.decode()

    assert "<script>alert('xss')</script>" not in body
