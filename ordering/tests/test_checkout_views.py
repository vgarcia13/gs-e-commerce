import uuid
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from catalog.models import Product
from ordering import services
from ordering.models import Order
from ordering.payments import DECLINE_CARD, EXAMPLE_CARD

User = get_user_model()

pytestmark = pytest.mark.django_db

PASSWORD = "s3cret-pass-99"
CHECKOUT_URL = reverse("ordering:checkout")
ORDERS_URL = reverse("orders:order_list")
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


def pay(client, card=EXAMPLE_CARD, key=None, follow=True):
    return client.post(
        CHECKOUT_URL,
        {"card_number": card, "idempotency_key": str(key or uuid.uuid4())},
        follow=follow,
    )


@pytest.mark.parametrize("url", [CHECKOUT_URL, ORDERS_URL])
def test_checkout_and_orders_require_login(client, url):
    response = client.get(url)

    assert response.status_code == 302
    assert LOGIN_URL in response.url


def test_checkout_page_shows_the_cart_and_a_fresh_key(client, buyer):
    services.add_to_cart(buyer, make_product(), 2)

    response = client.get(CHECKOUT_URL)
    body = response.content.decode()

    assert "Running Shoes" in body
    assert "179.98" in body
    assert response.context["form"].initial["idempotency_key"] is not None


def test_successful_payment_redirects_to_the_order(client, buyer):
    services.add_to_cart(buyer, make_product(stock=10), 2)

    response = pay(client)
    body = response.content.decode()

    order = Order.objects.get()
    assert order.reference in body
    assert "placed" in body


def test_declined_payment_returns_to_the_cart_with_an_error(client, buyer):
    product = make_product(stock=10)
    services.add_to_cart(buyer, product, 2)

    response = pay(client, card=DECLINE_CARD)
    body = response.content.decode()

    assert "declined" in body
    assert Order.objects.count() == 0
    product.refresh_from_db()
    assert product.stock == 10
    assert services.get_cart(buyer).items.count() == 1


def test_double_submitting_the_same_key_places_one_order(client, buyer):
    product = make_product(stock=10)
    services.add_to_cart(buyer, product, 2)
    key = uuid.uuid4()

    pay(client, key=key)
    pay(client, key=key)

    assert Order.objects.count() == 1
    product.refresh_from_db()
    assert product.stock == 8


def test_short_card_number_is_a_form_error(client, buyer):
    services.add_to_cart(buyer, make_product(), 1)

    response = client.post(
        CHECKOUT_URL, {"card_number": "4242", "idempotency_key": str(uuid.uuid4())}
    )

    assert response.status_code == 200
    assert "13 to 19 digits" in response.content.decode()
    assert Order.objects.count() == 0


def test_order_history_lists_only_your_own_orders(client, buyer):
    other = User.objects.create_user(email="other@example.com", password=PASSWORD)
    product = make_product(stock=10)
    services.add_to_cart(other, product, 1)
    theirs = services.place_order(other, EXAMPLE_CARD, uuid.uuid4())
    services.add_to_cart(buyer, product, 1)
    mine = services.place_order(buyer, EXAMPLE_CARD, uuid.uuid4())

    body = client.get(ORDERS_URL).content.decode()

    assert Order.objects.count() == 2
    assert mine.reference in body
    assert theirs.reference not in body


def test_another_users_order_is_not_reachable(client, buyer):
    other = User.objects.create_user(email="other@example.com", password=PASSWORD)
    services.add_to_cart(other, make_product(stock=10), 1)
    theirs = services.place_order(other, EXAMPLE_CARD, uuid.uuid4())

    response = client.get(reverse("orders:order_detail", args=[theirs.reference]))

    assert response.status_code == 404


def test_order_detail_shows_snapshotted_values(client, buyer):
    product = make_product(stock=10, price=Decimal("89.99"))
    services.add_to_cart(buyer, product, 1)
    order = services.place_order(buyer, EXAMPLE_CARD, uuid.uuid4())
    product.name = "Renamed Shoes"
    product.price = Decimal("129.99")
    product.save()

    body = client.get(reverse("orders:order_detail", args=[order.reference])).content.decode()

    assert "Running Shoes" in body
    assert "89.99" in body
    assert "Renamed Shoes" not in body


def test_checkout_with_an_empty_cart_is_refused(client, buyer):
    response = pay(client)

    assert "empty" in response.content.decode()
    assert Order.objects.count() == 0
