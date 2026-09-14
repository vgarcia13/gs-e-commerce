import logging
import uuid
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from catalog.models import Product
from ordering import services as ordering_services
from ordering.payments import DECLINE_CARD, EXAMPLE_CARD

User = get_user_model()

pytestmark = pytest.mark.django_db

PASSWORD = "s3cret-pass-99"


def events(caplog) -> list[str]:
    return [record.event for record in caplog.records if hasattr(record, "event")]


def make_product(**overrides):
    defaults = {
        "name": "Running Shoes",
        "sku": "RS-001",
        "description": "Light shoes",
        "category": "Footwear",
        "price": Decimal("89.99"),
        "stock": 10,
        "weight_kg": Decimal("0.35"),
    }
    return Product.objects.create(**{**defaults, **overrides})


@pytest.fixture
def staff(client):
    user = User.objects.create_user(email="staff@example.com", password=PASSWORD, is_staff=True)
    client.login(email=user.email, password=PASSWORD)
    return user


@pytest.fixture
def buyer(client):
    user = User.objects.create_user(email="buyer@example.com", password=PASSWORD)
    client.login(email=user.email, password=PASSWORD)
    return user


def test_signup_and_login_are_logged(client, caplog):
    with caplog.at_level(logging.INFO):
        client.post(
            reverse("accounts:signup"),
            {"email": "new@example.com", "password1": PASSWORD, "password2": PASSWORD},
        )

    assert "auth.signup" in events(caplog)
    assert "auth.login_succeeded" in events(caplog)


def test_failed_login_is_logged_as_a_warning(client, caplog):
    User.objects.create_user(email="buyer@example.com", password=PASSWORD)

    with caplog.at_level(logging.INFO):
        client.post(
            reverse("accounts:login"),
            {"username": "buyer@example.com", "password": "wrong-password-99"},
        )

    failures = [r for r in caplog.records if getattr(r, "event", "") == "auth.login_failed"]
    assert len(failures) == 1
    assert failures[0].levelname == "WARNING"
    assert failures[0].attempted_username == "buyer@example.com"


def test_no_password_reaches_the_logs(client, caplog):
    User.objects.create_user(email="buyer@example.com", password=PASSWORD)

    with caplog.at_level(logging.DEBUG):
        client.post(
            reverse("accounts:login"),
            {"username": "buyer@example.com", "password": "hunter2-secret-value"},
        )

    assert "hunter2-secret-value" not in caplog.text


def test_denied_staff_access_is_logged(client, buyer, caplog):
    with caplog.at_level(logging.INFO):
        client.get(reverse("catalog_staff:product_list"))

    denials = [r for r in caplog.records if getattr(r, "event", "") == "auth.access_denied"]
    assert len(denials) == 1
    assert denials[0].actor_id == buyer.pk


def test_product_create_and_update_are_logged_with_the_actor(client, staff, caplog):
    payload = {
        "name": "Trail Shoes", "sku": "TS-100", "description": "d",
        "category": "Footwear", "price": "79.99", "stock": "25", "weight_kg": "0.4",
    }

    with caplog.at_level(logging.INFO):
        client.post(reverse("catalog_staff:product_create"), payload)
        product = Product.objects.get(sku="TS-100")
        client.post(reverse("catalog_staff:product_update", args=[product.pk]), payload)

    created = [r for r in caplog.records if getattr(r, "event", "") == "product.created"]
    updated = [r for r in caplog.records if getattr(r, "event", "") == "product.updated"]
    assert created[0].actor_id == staff.pk
    assert created[0].sku == "TS-100"
    assert updated[0].actor_id == staff.pk


def test_import_emits_start_and_completion_events(caplog):
    from importing.service import import_products

    data = (
        "name,sku,description,category,price,stock,weight_kg\n"
        "Running Shoes,RS-001,Light,Footwear,89.99,150,0.35\n"
        "Yoga Mat,YM-015,Mat,Sports,free,200,1.2\n"
    ).encode()

    with caplog.at_level(logging.INFO):
        import_products(data)

    assert "import.started" in events(caplog)
    assert "import.completed" in events(caplog)
    assert "import.rows_rejected" in events(caplog)


def test_rejected_file_is_logged(caplog):
    from importing.parser import CsvFormatError
    from importing.service import import_products

    with caplog.at_level(logging.INFO), pytest.raises(CsvFormatError):
        import_products(b"name,sku\nx,y\n")

    assert "import.file_rejected" in events(caplog)


def test_checkout_success_emits_the_full_trail(buyer, caplog):
    product = make_product()
    ordering_services.add_to_cart(buyer, product, 2)

    with caplog.at_level(logging.INFO):
        ordering_services.place_order(buyer, EXAMPLE_CARD, uuid.uuid4())

    emitted = events(caplog)
    assert "checkout.started" in emitted
    assert "order.placed" in emitted


def test_declined_payment_is_logged_with_the_amount(buyer, caplog):
    product = make_product()
    ordering_services.add_to_cart(buyer, product, 2)

    with caplog.at_level(logging.INFO):
        with pytest.raises(ordering_services.CheckoutError):
            ordering_services.place_order(buyer, DECLINE_CARD, uuid.uuid4())

    declined = [r for r in caplog.records if getattr(r, "event", "") == "payment.declined"]
    assert declined[0].amount == "179.98"
    assert declined[0].levelname == "WARNING"


def test_card_number_never_reaches_the_logs(buyer, caplog):
    product = make_product()
    ordering_services.add_to_cart(buyer, product, 1)

    with caplog.at_level(logging.DEBUG):
        ordering_services.place_order(buyer, EXAMPLE_CARD, uuid.uuid4())

    assert EXAMPLE_CARD not in caplog.text


def test_unavailable_stock_at_checkout_is_logged(buyer, caplog):
    product = make_product(stock=10)
    ordering_services.add_to_cart(buyer, product, 5)
    Product.objects.filter(pk=product.pk).update(stock=1)

    with caplog.at_level(logging.INFO):
        with pytest.raises(ordering_services.CheckoutError):
            ordering_services.place_order(buyer, EXAMPLE_CARD, uuid.uuid4())

    assert "checkout.stock_unavailable" in events(caplog)


def test_cart_operations_are_logged(buyer, caplog):
    product = make_product()

    with caplog.at_level(logging.INFO):
        ordering_services.add_to_cart(buyer, product, 2)
        ordering_services.set_quantity(buyer, product, 3)
        ordering_services.remove_item(buyer, product)

    emitted = events(caplog)
    assert "cart.item_added" in emitted
    assert "cart.item_updated" in emitted
    assert "cart.item_removed" in emitted
