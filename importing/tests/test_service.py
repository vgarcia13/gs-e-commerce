import logging
from decimal import Decimal

import pytest
from django.utils import timezone

from catalog.models import Product
from importing.service import import_products

pytestmark = pytest.mark.django_db

HEADER = "name,sku,description,category,price,stock,weight_kg\n"


def csv_bytes(*rows: str) -> bytes:
    return (HEADER + "".join(row + "\n" for row in rows)).encode("utf-8")


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


def test_new_sku_creates_a_product():
    report = import_products(csv_bytes("Running Shoes,RS-001,Light shoes,Footwear,89.99,150,0.35"))

    assert (report.created, report.updated) == (1, 0)
    assert Product.objects.get(sku="RS-001").price == Decimal("89.99")


def test_existing_sku_is_updated_in_place():
    make_product()

    report = import_products(csv_bytes("Running Shoes,RS-001,Better arch support,Footwear,94.99,120,0.35"))

    assert (report.created, report.updated) == (0, 1)
    assert Product.objects.count() == 1
    product = Product.objects.get(sku="RS-001")
    assert product.price == Decimal("94.99")
    assert product.description == "Better arch support"


def test_update_does_not_overwrite_stock():
    make_product(stock=120)

    import_products(csv_bytes("Running Shoes,RS-001,Light shoes,Footwear,94.99,150,0.35"))

    assert Product.objects.get(sku="RS-001").stock == 120


def test_create_takes_stock_from_the_file():
    import_products(csv_bytes("Running Shoes,RS-001,Light shoes,Footwear,89.99,150,0.35"))

    assert Product.objects.get(sku="RS-001").stock == 150


def test_blank_description_and_weight_leave_existing_values():
    make_product(description="Original copy", weight_kg=Decimal("0.35"))

    import_products(csv_bytes("Running Shoes,RS-001,,Footwear,94.99,150,"))

    product = Product.objects.get(sku="RS-001")
    assert product.description == "Original copy"
    assert product.weight_kg == Decimal("0.35")


def test_soft_deleted_product_is_resurrected_not_duplicated():
    removed = make_product()
    removed.deleted_at = timezone.now()
    removed.save()

    report = import_products(csv_bytes("Running Shoes,RS-001,Back in stock,Footwear,94.99,200,0.35"))

    assert (report.created, report.updated, report.resurrected) == (0, 0, 1)
    assert Product.objects.count() == 1
    product = Product.objects.get(sku="RS-001")
    assert product.pk == removed.pk
    assert product.deleted_at is None
    assert product.stock == 200


def test_resurrect_prefers_the_most_recently_deleted_row():
    older = make_product(name="Old", deleted_at=timezone.now() - timezone.timedelta(days=2))
    newer = make_product(name="New", deleted_at=timezone.now())

    import_products(csv_bytes("Running Shoes,RS-001,Back,Footwear,94.99,10,0.35"))

    newer.refresh_from_db()
    older.refresh_from_db()
    assert newer.deleted_at is None
    assert older.deleted_at is not None


def test_duplicate_sku_in_file_collapses_to_one_write_with_last_winning():
    report = import_products(
        csv_bytes(
            "Bluetooth Speaker,BS-021,First,Electronics,59.99,110,0.8",
            "Bluetooth Speaker,BS-021,Second,Electronics,49.99,200,0.75",
            "Bluetooth Speaker,BS-021,Third,Electronics,64.99,90,0.8",
        )
    )

    assert report.created == 1
    assert Product.objects.count() == 1
    product = Product.objects.get(sku="BS-021")
    assert product.price == Decimal("64.99")
    assert product.description == "Third"


def test_superseded_duplicates_are_reported_as_warnings():
    report = import_products(
        csv_bytes(
            "Bluetooth Speaker,BS-021,First,Electronics,59.99,110,0.8",
            "Bluetooth Speaker,BS-021,Second,Electronics,49.99,200,0.75",
        )
    )

    assert len(report.warnings) == 1
    assert "BS-021" in report.warnings[0].message
    assert "2" in report.warnings[0].message


def test_invalid_rows_do_not_prevent_valid_rows():
    report = import_products(
        csv_bytes(
            "Running Shoes,RS-001,Light shoes,Footwear,89.99,150,0.35",
            "Yoga Mat,YM-015,Mat,Sports,free,200,1.2",
            "Desk Lamp,DL-007,Lamp,Home & Office,24.99,40,1.0",
        )
    )

    assert report.created == 2
    assert report.rejected == 1
    assert set(Product.objects.values_list("sku", flat=True)) == {"RS-001", "DL-007"}


def test_reimporting_the_same_file_is_idempotent():
    data = csv_bytes(
        "Running Shoes,RS-001,Light shoes,Footwear,89.99,150,0.35",
        "Desk Lamp,DL-007,Lamp,Home & Office,24.99,40,1.0",
    )

    first = import_products(data)
    second = import_products(data)

    assert (first.created, first.updated) == (2, 0)
    assert (second.created, second.updated) == (0, 2)
    assert Product.objects.count() == 2


def test_blank_rows_are_counted_not_rejected():
    report = import_products(
        csv_bytes("Running Shoes,RS-001,Light shoes,Footwear,89.99,150,0.35", ",,,,,,")
    )

    assert report.blank_rows == 1
    assert report.rejected == 0
    assert report.created == 1


def test_markup_payload_is_stored_without_modification():
    import_products(csv_bytes("<script>alert('xss')</script>,XS-001,Normal,Electronics,19.99,100,0.1"))

    assert Product.objects.get(sku="XS-001").name == "<script>alert('xss')</script>"


def test_completion_is_logged_with_counts(caplog):
    with caplog.at_level(logging.INFO, logger="importing.service"):
        import_products(csv_bytes("Running Shoes,RS-001,Light shoes,Footwear,89.99,150,0.35"))

    assert "created=1" in caplog.text
    assert "rejected=0" in caplog.text


def test_rejected_rows_are_logged_once_as_a_warning(caplog):
    with caplog.at_level(logging.INFO, logger="importing.service"):
        import_products(
            csv_bytes(
                "Yoga Mat,YM-015,Mat,Sports,free,200,1.2",
                "Desk Lamp,DL-007,Lamp,Home,24.99,-5,1.0",
            )
        )

    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1
    assert "rejected 2 row(s)" in warnings[0].getMessage()


def test_clean_import_logs_no_warning(caplog):
    with caplog.at_level(logging.INFO, logger="importing.service"):
        import_products(csv_bytes("Running Shoes,RS-001,Light shoes,Footwear,89.99,150,0.35"))

    assert [r for r in caplog.records if r.levelname == "WARNING"] == []
